"""Universal Garden Skill — framework-agnostic before/after LLM hooks.

A ``GardenSkill`` wraps a ``MemoryGarden`` instance into a drop-in
memory layer that works with any LLM framework.  The pattern is::

    skill = garden.as_skill()
    skill.open()

    # Before every LLM call
    context = skill.before(user_message)
    # context.brief_text is the Garden Brief as a string
    # context.messages is the modified message list (if using OpenAI format)

    # ... call your LLM with context ...

    # After every LLM call
    skill.after(user_message, assistant_reply)

    skill.close()  # optional, can also just stop calling

The shortcut ``skill.chat(user_message, llm_fn)`` does the full cycle
internally.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.models import GardenEvent, MemoryCard, SensitivityLevel
from memory_garden.product import (
    ApplicabilityContext,
    ApplicabilityDecision,
    ForgetPlanRecord,
    ForgetProofRecord,
    MemoryEvolutionPlan,
    MemoryInspection,
    MemoryListFilter,
    MemoryPatch,
    MemoryProposal,
    MemoryProposalStatus,
    MemoryRetrievalResult,
    MemoryStrategyProfile,
    MemoryView,
    ProductMemorySystem,
)
from memory_garden.providers import (
    DeepSeekLLMProvider,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeRerankerProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
    ProviderPolicy,
    ProviderRegistry,
    cognition_from_product_registry,
)
from memory_garden.runtime.session import GardenBrief
from memory_garden.soil.forget import execute_hard_forget

if TYPE_CHECKING:
    from memory_garden.sdk import MemoryGarden


class SkillProviderMode(str, Enum):
    """Provider policy for the Skill layer.

    ``custom`` is the default mode so developers can attach real providers
    without fighting disabled defaults. ``disabled`` remains available for
    tests and strictly local deployments. The Skill layer still only opens
    network connections after a caller explicitly configures a provider.
    """

    DISABLED = "disabled"
    FAKE = "fake"
    CUSTOM = "custom"


class SkillWriteMode(str, Enum):
    """How write requests are handled by the Skill layer."""

    COURT = "court"
    PREVIEW = "preview"


class SkillRedactionLevel(str, Enum):
    """Redaction policy label for outward-facing Skill responses."""

    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"


class SkillErrorCode(str, Enum):
    """Stable error codes returned by Skill APIs."""

    INVALID_INPUT = "invalid_input"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    RUNTIME_ERROR = "runtime_error"


class SkillError(BaseModel):
    """Structured Skill-layer error that avoids leaking backend exceptions."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    code: SkillErrorCode
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SkillConfig(BaseModel):
    """Product configuration for ``GardenSkill``.

    Defaults are local-first, rules-only, no-provider, and court-mediated
    writes. The config is serializable so it can be snapshotted in audits.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", arbitrary_types_allowed=True)

    garden_home: Path | None = None
    enable_harvest_brief: bool = True
    enable_dream: bool = False
    enable_court_shadow: bool = False
    enable_cognitive_harvest: bool = True
    provider_mode: SkillProviderMode = SkillProviderMode.CUSTOM
    redaction_level: SkillRedactionLevel = SkillRedactionLevel.BASIC
    default_write_mode: SkillWriteMode = SkillWriteMode.COURT
    allow_hard_forget: bool = True
    audit_events_limit: int = Field(default=50, ge=1, le=500)

    @field_validator("garden_home", mode="before")
    @classmethod
    def _coerce_home(cls, value: object) -> object:
        if value is None or isinstance(value, Path):
            return value
        if isinstance(value, str):
            return Path(value)
        return value


class SkillOperationResult(BaseModel):
    """Stable return envelope for write and command-like Skill operations."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    ok: bool
    operation: str
    mode: str = ""
    session_id: str = ""
    seed_ids: list[str] = Field(default_factory=list)
    court_case_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    verdicts: list[str] = Field(default_factory=list)
    preview: bool = False
    skipped_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: SkillError | None = None


class SkillHarvestResult(BaseModel):
    """Stable return envelope for rule-only Skill harvest."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    ok: bool
    query: str
    brief: GardenBrief | None = None
    source_memory_ids: list[str] = Field(default_factory=list)
    candidate_memory_ids: list[str] = Field(default_factory=list)
    mode: str = "rules_only"
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: SkillError | None = None


class SkillAuditView(BaseModel):
    """Small audit snapshot returned by ``GardenSkill.audit()``."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    event_count: int
    events: list[dict[str, Any]] = Field(default_factory=list)
    memory_count: int = 0
    seed_count: int = 0
    config: dict[str, Any] = Field(default_factory=dict)


@dataclass
class SkillContext:
    """The result of ``GardenSkill.before()`` — inject this into your LLM call."""

    session_id: str = ""
    brief_text: str = ""
    brief_dict: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_system_prefix(self) -> str:
        """Return the brief as a system prefix string, or empty string."""
        if not self.brief_text.strip():
            return ""
        return f"[Memory Garden Brief]\n{self.brief_text}\n"

    def to_openai_system_message(self) -> dict[str, str] | None:
        """Return an OpenAI-format system message, or None if brief is empty."""
        prefix = self.to_system_prefix()
        if not prefix:
            return None
        return {"role": "system", "content": prefix}

    def inject_into_messages(self, messages: list[dict]) -> list[dict]:
        """Return *messages* with the brief injected as a system message."""
        sys_msg = self.to_openai_system_message()
        if sys_msg is None:
            return list(messages)
        # Insert after any existing system message, or at the front
        out = list(messages)
        has_system = any(m.get("role") == "system" for m in out)
        if has_system:
            # Append to last system message
            for m in out:
                if m.get("role") == "system":
                    m["content"] = (m.get("content", "") or "") + "\n\n" + sys_msg["content"]
                    break
        else:
            out.insert(0, sys_msg)
        return out


class GardenSkill:
    """高层 Skill 接口，包装 Memory Garden 实例。

    基本用法::

        garden = MemoryGarden.local("./my_garden")
        skill = garden.as_skill()

        # 一键接入大模型（可选）
        # export DEEPSEEK_API_KEY="..."
        skill.with_deepseek()  # 或 with_openai()

        skill.open()
        ctx = skill.before("我喜欢深色模式。")
        # ... 调用你的 LLM，把 ctx 注入上下文 ...
        skill.after("我喜欢深色模式。", llm_response)
        skill.close()
    """

    def __init__(self, garden: MemoryGarden, config: SkillConfig | None = None) -> None:
        self._garden = garden
        cfg = config or SkillConfig()
        if cfg.garden_home is None:
            cfg = cfg.model_copy(update={"garden_home": garden.home.root})
        self._config = cfg
        self._session_id: str | None = None
        self._is_open: bool = False
        self._product_system: ProductMemorySystem | None = None
        self._product_providers: ProviderRegistry | None = garden._get_skill_product_providers()
        self._last_before_user_message: str | None = None
        self._last_after_result: dict[str, Any] | None = None

    # ── Lifecycle ──────────────────────────────────────────────────

    def open(self, *, metadata: dict[str, Any] | None = None) -> str:
        """打开一个 Garden 会话，并返回 ``session_id``。"""
        result = self._garden.chat("花花开", metadata=metadata)
        self._session_id = result.session_id
        self._is_open = True
        return self._session_id

    def open_session(self, *, metadata: dict[str, Any] | None = None) -> SkillOperationResult:
        """稳定 API：打开会话并返回结构化结果。"""
        try:
            sid = self.open(metadata=metadata)
            return SkillOperationResult(
                ok=True,
                operation="open_session",
                session_id=sid,
                metadata={"state": "open"},
            )
        except Exception as exc:
            return _skill_error_result("open_session", exc)

    def close(self) -> Any:
        """关闭当前 Garden 会话，并返回运行时反馈。"""
        if not self._is_open or self._session_id is None:
            return None
        result = self._garden.chat("花花关", session_id=self._session_id)
        self._is_open = False
        return result.feedback

    def close_session(self) -> SkillOperationResult:
        """稳定 API：关闭会话并返回结构化的反馈元数据。"""
        try:
            fb = self.close()
            return SkillOperationResult(
                ok=True,
                operation="close_session",
                session_id=self._session_id or "",
                metadata={
                    "feedback_id": getattr(fb, "feedback_id", None),
                    "summary": getattr(fb, "summary", None),
                },
            )
        except Exception as exc:
            return _skill_error_result("close_session", exc, session_id=self._session_id or "")

    # ── Before / After hooks ───────────────────────────────────────

    def before(
        self,
        user_message: str,
        *,
        messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SkillContext:
        """在调用 LLM 前准备可注入的 Garden 上下文。

        请在把 ``user_message`` 发送给真实模型前调用本方法。返回值包含可追踪的
        Garden Brief，以及可选的 OpenAI messages 注入结果。
        """
        if not self._is_open:
            self.open()

        result = self._garden.chat(user_message, session_id=self._session_id, metadata=metadata)
        self._last_before_user_message = user_message

        brief_text = ""
        brief_dict: dict[str, Any] = {}
        if result.garden_brief is not None:
            try:
                brief_dict = result.garden_brief.model_dump(mode="json")
                parts = []
                for slot in ("use", "avoid", "style", "safety", "nudge"):
                    val = brief_dict.get(slot, "")
                    if val and str(val).strip():
                        parts.append(f"[{slot}] {val}")
                brief_text = "\n".join(parts)
            except Exception:
                brief_text = str(result.garden_brief)

        ctx = SkillContext(
            session_id=self._session_id or result.session_id or "",
            brief_text=brief_text,
            brief_dict=brief_dict,
            metadata=result.metadata if hasattr(result, "metadata") else {},
        )

        if messages is not None:
            ctx.messages = ctx.inject_into_messages(messages)

        return ctx

    def after(self, user_message: str, assistant_reply: str) -> None:
        """在 LLM 返回后记录本轮交互信号。

        当前阶段只保留安全钩子形状，不会把不可追踪的模型输出直接写入长期记忆。
        """
        if not self._is_open:
            return
        metadata = {
            "skill_phase": "after",
            "session_id": self._session_id or "",
            "assistant_reply_excerpt": (assistant_reply or "")[:480],
            "assistant_reply_length": len(assistant_reply or ""),
            "source_role": "user",
        }
        self._last_after_result = dict(metadata)
        if user_message and user_message != self._last_before_user_message:
            seeds = self._garden.core.observe(user_message, metadata)
            self._last_after_result["seed_ids"] = [s.id for s in seeds]

    # ── Stable product APIs ───────────────────────────────────────

    def remember(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
        mode: SkillWriteMode | str | None = None,
    ) -> SkillOperationResult:
        """观察一段文本，运行规则法庭，并应用安全的裁定结果。

        ``preview`` 模式只开庭但不执行生长动作；
        ``court`` 模式下的写入仍由 RuleCourt 中介。
        """
        requested = _coerce_write_mode(mode, self._config.default_write_mode)
        if not text or not text.strip():
            return _skill_error_result(
                "remember",
                ValueError("text must be non-empty"),
                code=SkillErrorCode.INVALID_INPUT,
                session_id=self._session_id or "",
            )

        try:
            ctx = {"skill_operation": "remember", **dict(metadata or {})}
            seeds = self._garden.core.observe(text, ctx)
            cases = self._garden.core.open_court([s.id for s in seeds])
            result = SkillOperationResult(
                ok=True,
                operation="remember",
                mode=requested.value,
                session_id=self._session_id or "",
                seed_ids=[s.id for s in seeds],
                court_case_ids=[c.id for c in cases],
                verdicts=[c.judge_verdict.verdict.value for c in cases],
                preview=requested == SkillWriteMode.PREVIEW,
            )

            if requested == SkillWriteMode.PREVIEW:
                result.skipped_reasons.append("write_mode_preview")
                return result

            for case in cases:
                if case.judge_verdict.verdict == CourtVerdictType.forget:
                    result.skipped_reasons.append(
                        f"forget_verdict_requires_explicit_skill_forget:{case.seed_id}"
                    )
                    continue
                before_events = self._event_ids()
                action = self._garden.core.apply_verdict(case)
                if isinstance(action, MemoryCard):
                    result.memory_ids.append(action.id)
                after_events = self._event_ids()
                result.event_ids.extend([eid for eid in after_events if eid not in before_events])
            result.memory_ids = list(dict.fromkeys(result.memory_ids))
            result.event_ids = list(dict.fromkeys(result.event_ids))
            return result
        except Exception as exc:
            return _skill_error_result("remember", exc, session_id=self._session_id or "")

    def forget(
        self,
        target: str,
        *,
        memory_id: str | None = None,
        reason: str = "skill forget request",
        dry_run: bool = False,
        cascade: bool = True,
    ) -> SkillOperationResult:
        """按 memory_id 或本地子串匹配硬删除一条记忆。

        本方法绝不调用外部 provider，直接委托给 Soil 层执行硬删除，
        确保 FTS 索引清理与审计元数据一并生成。
        """
        if not self._config.allow_hard_forget:
            return _skill_error_result(
                "forget",
                PermissionError("hard forget is disabled by SkillConfig"),
                code=SkillErrorCode.PERMISSION_DENIED,
                session_id=self._session_id or "",
            )
        resolved = (memory_id or "").strip() or self._resolve_memory_id(target)
        if not resolved:
            return _skill_error_result(
                "forget",
                LookupError("no matching memory found"),
                code=SkillErrorCode.NOT_FOUND,
                session_id=self._session_id or "",
                details={"target": target},
            )

        try:
            res = execute_hard_forget(
                self._garden.home.root,
                resolved,
                reason=reason,
                dry_run=dry_run,
                cascade=cascade,
            )
            return SkillOperationResult(
                ok=res.status == "ok",
                operation="forget",
                mode="hard",
                session_id=self._session_id or "",
                memory_ids=[resolved],
                preview=dry_run,
                metadata=res.model_dump(mode="json"),
                skipped_reasons=[] if res.status == "ok" else [i.message for i in res.issues],
            )
        except Exception as exc:
            return _skill_error_result("forget", exc, session_id=self._session_id or "")

    def harvest(self, query: str, *, limit: int = 5) -> SkillHarvestResult:
        """纯规则本地采摘：不依赖外部 provider，始终保留 source_memory_ids。"""
        try:
            if not query or not query.strip():
                raise ValueError("query 不能为空")
            memories = self._garden.core.list_memories(include_greenhouse=False)
            ranked = _rank_memories(query, memories)
            selected = ranked[: max(1, min(limit, 32))]
            source_ids = [m.id for m in selected]
            if source_ids:
                use = "参考记忆：" + "、".join(source_ids)
            else:
                use = "当前没有匹配的本地记忆。"
            brief = GardenBrief(
                intent=f"规则采摘：{query.strip()[:120]}",
                use=use,
                avoid="不要把未命中的记忆编造成事实。",
                style="保持中性，按当前上下文回答。",
                safety="只使用本地已保存且可追溯的记忆线索。",
                nudge="如记忆与当前问题无关，请忽略。",
                source_memory_ids=source_ids,
            )
            return SkillHarvestResult(
                ok=True,
                query=query,
                brief=brief,
                source_memory_ids=source_ids,
                candidate_memory_ids=[m.id for m in ranked],
                metadata={"mode": "rules_only", "limit": limit},
            )
        except Exception as exc:
            return SkillHarvestResult(
                ok=False,
                query=query,
                error=_skill_error(exc),
            )

    def audit(self, *, limit: int | None = None) -> SkillAuditView:
        """返回当前本地花园的审计快照（事件数、记忆数、种子数）。"""
        lim = limit or self._config.audit_events_limit
        events = self._garden.core.recent_events(limit=lim)
        memories = self._garden.core.list_memories(include_greenhouse=True)
        seeds = self._garden.core.repository.list_seeds(limit=lim)
        return SkillAuditView(
            event_count=len(events),
            events=[_event_to_dict(e) for e in events],
            memory_count=len(memories),
            seed_count=len(seeds),
            config=self._config.model_dump(mode="json"),
        )

    # ── Product memory APIs ───────────────────────────────────────────────

    @property
    def product(self) -> ProductMemorySystem:
        """返回绑定到此花园的产品级记忆系统。"""
        if self._product_system is None:
            if self._product_providers is None:
                self._product_providers = self._garden._get_skill_product_providers()
            cognition_providers = (
                cognition_from_product_registry(self._product_providers, garden_home=str(self._garden.home.root))
                if self._product_providers is not None
                else {}
            )
            self._product_system = ProductMemorySystem(
                garden_home=self._garden.home.root,
                repository=self._garden.core.repository,
                providers=self._product_providers,
                cognition_providers=cognition_providers,
            )
        return self._product_system

    def configure_providers(self, providers: ProviderRegistry) -> None:
        """注入调用方自有的 LLM、Embedding、Reranker 或 Secret provider。"""
        self._garden._set_skill_product_providers(providers)
        self._product_providers = providers
        self._product_system = None

    def with_deepseek(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        base_url: str | None = None,
    ) -> "GardenSkill":
        """一键接入 DeepSeek 的 OpenAI 兼容大模型 provider。

        未显式传入 ``api_key`` 时会读取 ``DEEPSEEK_API_KEY``。本方法只配置 provider，
        不会在配置阶段发起真实模型调用。
        """
        key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise ValueError("缺少 DeepSeek API Key：请传入 api_key 或设置 DEEPSEEK_API_KEY")
        self.configure_providers(
            ProviderRegistry(
                policy=_remote_provider_policy(),
                llm=DeepSeekLLMProvider(
                    api_key=key,
                    model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                    base_url=base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                ),
            )
        )
        self._config = self._config.model_copy(
            update={"provider_mode": SkillProviderMode.CUSTOM, "enable_cognitive_harvest": True}
        )
        return self

    def with_openai(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        base_url: str | None = None,
        embedding_model: str | None = None,
    ) -> "GardenSkill":
        """一键接入 OpenAI 的 LLM 与 Embedding providers。

        未显式传入 ``api_key`` 时会读取 ``OPENAI_API_KEY``。默认模型可通过
        ``model`` / ``OPENAI_MODEL`` 覆盖；配置阶段不会发起真实模型调用。
        """
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("缺少 OpenAI API Key：请传入 api_key 或设置 OPENAI_API_KEY")
        base = base_url or os.environ.get("OPENAI_BASE_URL")
        llm = OpenAICompatibleLLMProvider(
            api_key=key,
            model=model or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            base_url=base,
            name="openai-llm",
        )
        embedding = OpenAICompatibleEmbeddingProvider(
            api_key=key,
            model=embedding_model or os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            base_url=base,
            name="openai-embedding",
        )
        self.configure_providers(
            ProviderRegistry(
                policy=_remote_provider_policy(),
                llm=llm,
                embedding=embedding,
            )
        )
        self._config = self._config.model_copy(
            update={"provider_mode": SkillProviderMode.CUSTOM, "enable_cognitive_harvest": True}
        )
        return self

    def with_fake_providers(self) -> "GardenSkill":
        """为测试或离线演示接入确定性的 fake providers。"""
        self.configure_providers(
            ProviderRegistry(
                policy=_local_fake_provider_policy(),
                llm=FakeLLMProvider(),
                embedding=FakeEmbeddingProvider(),
                reranker=FakeRerankerProvider(),
            )
        )
        self._config = self._config.model_copy(
            update={"provider_mode": SkillProviderMode.FAKE, "enable_cognitive_harvest": True}
        )
        return self

    def propose_memory(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[MemoryProposal]:
        """从文本中提取记忆提案，不写入长期记忆。"""
        return self.product.propose(text, metadata=metadata)

    def memory_inbox(
        self,
        *,
        status: MemoryProposalStatus | str | None = MemoryProposalStatus.pending,
        limit: int = 100,
    ) -> list[MemoryProposal]:
        """列出待处理或历史记忆提案。"""
        return self.product.inbox(status=status, limit=limit)

    def approve_memory_proposal(self, proposal_id: str, *, auto: bool = False) -> MemoryCard:
        """批准一条提案，创建带版本的 MemoryCard。"""
        return self.product.approve(proposal_id, auto=auto)

    def reject_memory_proposal(self, proposal_id: str, *, reason: str = "") -> MemoryProposal:
        """拒绝一条提案，保留审计记录。"""
        return self.product.reject(proposal_id, reason=reason)

    def edit_memory_proposal(self, proposal_id: str, patch: MemoryPatch) -> MemoryProposal:
        """在批准前编辑一条提案。"""
        return self.product.edit_proposal(proposal_id, patch)

    def remember_memory(
        self,
        text: str,
        *,
        mode: str = "trusted",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """运行产品级提案管线，可选自动批准安全记忆。"""
        return self.product.remember(text, mode=mode, metadata=metadata)

    def list_memories(self, filters: MemoryListFilter | None = None) -> list[MemoryView]:
        """列出产品级记忆视图，支持类型、标签、敏感度和生命周期过滤。"""
        return self.product.list_memories(filters)

    def inspect_memory(self, memory_id: str, *, applicability_queries: list[str] | None = None) -> MemoryInspection:
        """查看一条记忆的版本、关联、提案、事件和世系。"""
        return self.product.inspect_memory(memory_id, applicability_queries=applicability_queries)

    def update_memory(self, memory_id: str, patch: MemoryPatch, *, reason: str = "skill_update") -> MemoryCard:
        """修补一条记忆，并在变更前记录版本快照。"""
        return self.product.edit_memory(memory_id, patch, reason=reason)

    def retag_memory(self, memory_id: str, tags: list[str]) -> MemoryCard:
        """替换记忆的标签，保持顺序和唯一性。"""
        return self.product.retag_memory(memory_id, tags)

    def set_memory_sensitivity(self, memory_id: str, level: SensitivityLevel | str) -> MemoryCard:
        """设置记忆的敏感度标签。"""
        return self.product.set_sensitivity(memory_id, level)

    def archive_memory(self, memory_id: str, *, reason: str = "skill_archive") -> MemoryCard:
        """将记忆移出活跃检索范围，不执行硬删除。"""
        return self.product.archive_memory(memory_id, reason=reason)

    def restore_memory(self, memory_id: str, *, reason: str = "skill_restore") -> MemoryCard:
        """将已归档记忆恢复到活跃生命周期。"""
        return self.product.restore_memory(memory_id, reason=reason)

    def merge_memories(self, source_ids: list[str], target_id: str | None = None) -> MemoryCard:
        """将多条记忆合并到一条目标记忆，并将源记忆归档。"""
        return self.product.merge_memories(source_ids, target_id=target_id)

    def retrieve_memories(
        self,
        query: str,
        *,
        limit: int = 5,
        explain: bool = True,
        context: ApplicabilityContext | dict[str, Any] | None = None,
    ) -> MemoryRetrievalResult:
        """检索相关记忆，附带可解释的本地/provider 评分。"""
        return self.product.retrieve(query, limit=limit, explain=explain, context=context)

    def build_memory_brief(
        self,
        query: str,
        *,
        limit: int = 5,
        context: ApplicabilityContext | dict[str, Any] | None = None,
    ) -> GardenBrief:
        """构建保留 source-id 的简报，适合注入 LLM 上下文。"""
        return self.product.build_brief(query, limit=limit, context=context)

    def get_memory_strategy(self, memory_id: str) -> MemoryStrategyProfile:
        """返回记忆的层级、范围、成熟度、强度和使用/证据计数。"""
        return self.product.get_strategy_profile(memory_id)

    def assess_memory_applicability(
        self,
        memory_id: str,
        query: str,
        *,
        context: ApplicabilityContext | dict[str, Any] | None = None,
    ) -> ApplicabilityDecision:
        """评估一条记忆是否适用于某个任务或查询。"""
        return self.product.assess_applicability(memory_id, query, context=context)

    def reinforce_memory_strategy(
        self,
        memory_id: str,
        *,
        reason: str = "skill_reinforce",
        amount: float = 0.08,
    ) -> MemoryStrategyProfile:
        """增强一条记忆，允许成熟度晋升。"""
        return self.product.reinforce_memory(memory_id, reason=reason, amount=amount)

    def decay_memory_strategies(self, *, limit: int = 500) -> list[MemoryEvolutionPlan]:
        """执行确定性的陈旧度衰减，按需生成归档计划。"""
        return self.product.decay_memories(limit=limit)

    def plan_memory_abstractions(self, *, limit: int = 500) -> list[MemoryEvolutionPlan]:
        """从稳定的关联记忆中规划更高层的抽象候选。"""
        return self.product.plan_abstractions(limit=limit)

    def plan_memory_forget(self, target: str = "", *, memory_id: str | None = None, cascade: bool = True) -> ForgetPlanRecord:
        """创建一条可审计的硬删除计划（不执行）。"""
        return self.product.plan_forget(target, memory_id=memory_id, cascade=cascade)

    def execute_memory_forget(self, plan_id: str) -> tuple[ForgetPlanRecord, ForgetProofRecord]:
        """执行删除计划，重建索引并保存证明检查结果。"""
        return self.product.execute_forget(plan_id)

    def prove_memory_forget(self, memory_id: str, *, plan_id: str = "") -> ForgetProofRecord:
        """对指定记忆执行并持久化硬删除证明检查。"""
        return self.product.prove_forget(memory_id, plan_id=plan_id)

    # ── Convenience ────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        llm_fn: Callable[[SkillContext, str], str],
        *,
        messages: list[dict[str, Any]] | None = None,
    ) -> tuple[str, SkillContext]:
        """执行完整一轮：``before`` -> 调用 LLM -> ``after``。

        ``llm_fn`` 会收到 ``(context, user_message)``，并返回 assistant 回复字符串。
        """
        ctx = self.before(user_message, messages=messages)
        reply = llm_fn(ctx, user_message)
        self.after(user_message, reply)
        return reply, ctx

    # ── Properties ─────────────────────────────────────────────────

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def garden(self) -> MemoryGarden:
        return self._garden

    @property
    def config(self) -> SkillConfig:
        return self._config

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def health(self) -> Any:
        return self._garden.health()

    @property
    def summary(self) -> Any:
        return self._garden.summary()

    def _resolve_memory_id(self, target: str) -> str | None:
        needle = (target or "").strip().casefold()
        if not needle:
            return None
        memories = self._garden.core.list_memories(include_greenhouse=True)
        for memory in memories:
            if memory.id == target:
                return memory.id
        for memory in memories:
            haystack = "\n".join(
                [memory.title, memory.essence, memory.fragrance, memory.thorns, " ".join(memory.tags)]
            ).casefold()
            if needle in haystack:
                return memory.id
        return None

    def _event_ids(self) -> list[str]:
        return [e.id for e in self._garden.core.recent_events(limit=200)]


def _coerce_write_mode(value: SkillWriteMode | str | None, default: SkillWriteMode) -> SkillWriteMode:
    if value is None:
        return default
    if isinstance(value, SkillWriteMode):
        return value
    return SkillWriteMode(value)


def _remote_provider_policy() -> ProviderPolicy:
    return ProviderPolicy(
        allow_remote_llm=True,
        allow_remote_embeddings=True,
        allow_remote_rerank=True,
        allow_raw_user_text=True,
    )


def _local_fake_provider_policy() -> ProviderPolicy:
    return ProviderPolicy(allow_raw_user_text=True)


def _skill_error(
    exc: Exception,
    *,
    code: SkillErrorCode | None = None,
    details: dict[str, Any] | None = None,
) -> SkillError:
    if code is None:
        if isinstance(exc, (ValueError, TypeError)):
            code = SkillErrorCode.INVALID_INPUT
        elif isinstance(exc, LookupError):
            code = SkillErrorCode.NOT_FOUND
        elif isinstance(exc, PermissionError):
            code = SkillErrorCode.PERMISSION_DENIED
        else:
            code = SkillErrorCode.RUNTIME_ERROR
    return SkillError(code=code, message=str(exc) or type(exc).__name__, details=dict(details or {}))


def _skill_error_result(
    operation: str,
    exc: Exception,
    *,
    code: SkillErrorCode | None = None,
    session_id: str = "",
    details: dict[str, Any] | None = None,
) -> SkillOperationResult:
    return SkillOperationResult(
        ok=False,
        operation=operation,
        session_id=session_id,
        error=_skill_error(exc, code=code, details=details),
    )


def _rank_memories(query: str, memories: list[MemoryCard]) -> list[MemoryCard]:
    tokens = [t for t in query.casefold().replace("/", " ").split() if t]

    def score(memory: MemoryCard) -> tuple[int, float, str]:
        text = "\n".join([memory.title, memory.essence, " ".join(memory.tags)]).casefold()
        hits = sum(1 for token in tokens if token in text)
        phrase = 2 if query.casefold().strip() and query.casefold().strip() in text else 0
        return (hits + phrase, float(memory.importance), memory.id)

    ranked = sorted(memories, key=score, reverse=True)
    return [m for m in ranked if score(m)[0] > 0]


def _event_to_dict(event: GardenEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type.value,
        "object_type": event.object_type.value,
        "object_id": event.object_id,
        "summary": event.summary,
        "created_at": event.created_at.isoformat(),
        "metadata": dict(event.metadata),
    }


__all__ = [
    "GardenSkill",
    "SkillAuditView",
    "SkillConfig",
    "SkillContext",
    "SkillError",
    "SkillErrorCode",
    "SkillHarvestResult",
    "SkillOperationResult",
    "SkillProviderMode",
    "SkillRedactionLevel",
    "SkillWriteMode",
]
