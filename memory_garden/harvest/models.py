"""第三层：采摘（Harvest）数据模型——仅结构与追溯，不含检索/简报实现。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_garden.runtime.session import GardenBrief as RuntimeGardenBrief

_MAX_FIELD = 512


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _strip_nonempty(name: str):
    def _v(cls: type, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError(f"{name} 不能为空")
            return s
        return v

    return _v


class HarvestMode(str, Enum):
    """采摘流水线模式占位（ Stage 3A 仅占位枚举）。"""

    OFF = "off"
    LEXICAL_STUB = "lexical_stub"
    FULL_PIPELINE_STUB = "full_pipeline_stub"


class BriefMode(str, Enum):
    """简报生成形态（实现留待后续 Stage）。"""

    TEMPLATE = "template"
    CURATED = "curated"
    HYBRID = "hybrid"


class CandidateMatchType(str, Enum):
    """候选与查询的匹配类型标记（不含真实打分实现）。"""

    UNKNOWN = "unknown"
    LEXICAL_STUB = "lexical_stub"
    PINNED = "pinned"
    EXACT_ID = "exact_id"
    SEMANTIC_STUB = "semantic_stub"


class BouquetSlot(str, Enum):
    """花束槽位：多段记忆在编组时的角色占位。"""

    PRIMARY = "primary"
    CORROBORATION = "corroboration"
    CONTRAST = "contrast"
    GUARDRAIL = "guardrail"
    RESERVED = "reserved"


class MemoryLens(BaseModel):
    """观察记忆的「透镜」维度：仅存元数据与权重占位。"""

    model_config = ConfigDict(validate_assignment=True)

    lens_id: str = Field(default_factory=lambda: _new_id("lens"))
    name: str = Field(..., min_length=1, max_length=128, description="人类可读透镜名")
    facet_keys: list[str] = Field(
        default_factory=list,
        description="可选事实面标签，如 preference / episodic",
    )
    priority: float = Field(default=0.5, ge=0.0, le=1.0)


class HarvestQuery(BaseModel):
    """一次采摘请求的查询快照。"""

    model_config = ConfigDict(validate_assignment=True)

    query_id: str = Field(default_factory=lambda: _new_id("hq"))
    session_id: str | None = Field(default=None, description="可选运行时会话 id")
    turn_index: int | None = Field(default=None, ge=0)
    raw_user_text: str = Field(default="", max_length=8192, description="用户句原文占位")
    harvest_mode: HarvestMode = Field(default=HarvestMode.LEXICAL_STUB)
    lenses: list[MemoryLens] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class MemoryCandidate(BaseModel):
    """单层记忆候选条目（可追溯至第一层 MemoryCard.id）。"""

    model_config = ConfigDict(validate_assignment=True)

    candidate_id: str = Field(default_factory=lambda: _new_id("cand"))
    memory_id: str = Field(..., min_length=1, description="MemoryCard.id")
    excerpt: str = Field(default="", max_length=2048)
    match_type: CandidateMatchType = Field(default=CandidateMatchType.UNKNOWN)
    lens_id: str | None = Field(default=None, description="归因透镜")
    metadata: dict[str, Any] = Field(default_factory=dict)


class HarvestScore(BaseModel):
    """对单个候选的分项分值占位。"""

    model_config = ConfigDict(validate_assignment=True)

    score_id: str = Field(default_factory=lambda: _new_id("sc"))
    candidate_id: str = Field(..., min_length=1)
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    policy_boost: float = Field(default=0.0, description="策略层加减分项占位")
    notes: list[str] = Field(default_factory=list)


class HarvestPolicyDecision(BaseModel):
    """采摘策略门禁结果（是否准入、配额、拒绝原因）。"""

    model_config = ConfigDict(validate_assignment=True)

    decision_id: str = Field(default_factory=lambda: _new_id("hpd"))
    allow_candidate_ids: list[str] = Field(default_factory=list)
    reject_candidate_ids: list[str] = Field(default_factory=list)
    capped_total: int | None = Field(default=None, ge=0)
    reasons: list[str] = Field(default_factory=list)


class GardenBouquet(BaseModel):
    """按槽位编组的记忆候选 id 列表。"""

    model_config = ConfigDict(validate_assignment=True)

    bouquet_id: str = Field(default_factory=lambda: _new_id("bouq"))
    slots: dict[BouquetSlot, list[str]] = Field(
        default_factory=dict,
        description="槽位 → candidate_id 列表",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class HarvestModelCallStub(BaseModel):
    """追溯中的模型调用占位（无真实推理负载）。"""

    model_config = ConfigDict(validate_assignment=True)

    call_id: str = Field(default_factory=lambda: _new_id("mc"))
    provider_kind: str = Field(..., min_length=1, description="如 llm / embedding / rerank")
    stub_payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_utc_now)


class HarvestGardenBrief(BaseModel):
    """第三层简报：兼容第二层 ``GardenBrief`` 字段并扩展估计与模式。"""

    model_config = ConfigDict(validate_assignment=True)

    intent: str = Field(..., max_length=_MAX_FIELD)
    use: str = Field(..., max_length=_MAX_FIELD)
    avoid: str = Field(..., max_length=_MAX_FIELD)
    style: str = Field(..., max_length=_MAX_FIELD)
    safety: str = Field(..., max_length=_MAX_FIELD)
    nudge: str = Field(..., max_length=_MAX_FIELD)
    source_memory_ids: list[str] = Field(default_factory=list)
    token_estimate: int | None = Field(default=None, ge=0, description="简报相关 token 粗估占位")
    mode: BriefMode = Field(default=BriefMode.TEMPLATE)

    _v_nonempty = field_validator(
        "intent",
        "use",
        "avoid",
        "style",
        "safety",
        "nudge",
        mode="before",
    )(_strip_nonempty("简报字段"))

    def to_runtime_brief(self) -> RuntimeGardenBrief:
        """裁剪为第二层 ``GardenBrief``（忽略 token_estimate / mode）。"""
        return RuntimeGardenBrief(
            intent=self.intent,
            use=self.use,
            avoid=self.avoid,
            style=self.style,
            safety=self.safety,
            nudge=self.nudge,
            source_memory_ids=list(self.source_memory_ids),
        )

    @classmethod
    def from_runtime_brief(cls, brief: RuntimeGardenBrief, *, mode: BriefMode = BriefMode.TEMPLATE) -> HarvestGardenBrief:
        """由运行时简报扩展为第三层模型。"""
        return cls(
            intent=brief.intent,
            use=brief.use,
            avoid=brief.avoid,
            style=brief.style,
            safety=brief.safety,
            nudge=brief.nudge,
            source_memory_ids=list(brief.source_memory_ids),
            token_estimate=None,
            mode=mode,
        )


class HarvestTrace(BaseModel):
    """一次采摘请求的端到端可追溯快照（占位串联各阶段产出）。"""

    model_config = ConfigDict(validate_assignment=True, protected_namespaces=())

    trace_id: str = Field(default_factory=lambda: _new_id("htr"))
    query: HarvestQuery
    lenses: list[MemoryLens] = Field(default_factory=list)
    candidates: list[MemoryCandidate] = Field(default_factory=list)
    scores: list[HarvestScore] = Field(default_factory=list)
    policy_decisions: list[HarvestPolicyDecision] = Field(default_factory=list)
    bouquet: GardenBouquet | None = None
    brief: HarvestGardenBrief | None = None
    model_calls: list[HarvestModelCallStub] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    finalized_at: datetime | None = None
