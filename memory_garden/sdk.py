"""Memory Garden SDK 门面：最高层公共入口。

本模块提供 ``MemoryGarden`` 类，把 Core、Runtime、Harvest 与 Observatory
包装成统一 API。默认在本地运行；当调用方显式配置 provider 时，可以接入真实大模型。

SDK 入口负责组装本地仓库、运行时钩子、检索管线和健康检查。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from memory_garden.core.garden import MemoryGardenCore
from memory_garden.cognition.models import CognitiveHarvestMode
from memory_garden.integrations.config import GardenAdapterConfig
from memory_garden.integrations.models import IntegrationResult
from memory_garden.integrations.protocols import ChatAgentProtocol
from memory_garden.integrations.sync import SyncGardenChatAdapter
from memory_garden.observatory.observer import GardenObserver
from memory_garden.covenant.enforcer import CovenantEnforcer
from memory_garden.harvest.bounded_scan import create_bounded_runtime_memory_provider
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.runtime_adapter import RuntimeGardenHarvesterAdapter
from memory_garden.runtime.harvest import TemplateBriefWriter
from memory_garden.runtime.hooks import RuntimeHooks
from memory_garden.runtime.runtime import GardenRuntime
from memory_garden.runtime.session_manager import GardenSessionManager
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.health import check_garden_health
from memory_garden.soil.models import GardenHome, GardenHealthReport
from memory_garden.storage.base import GardenRepository
from memory_garden.storage.sqlite import SQLiteGardenRepository

if TYPE_CHECKING:
    from memory_garden.observatory.views import GardenSummaryView
    from memory_garden.product.system import ProductMemorySystem
    from memory_garden.providers import ProviderRegistry
    from memory_garden.product.models import MemoryRetrievalResult
    from memory_garden.runtime.session import GardenBrief
    from memory_garden.skill import GardenSkill


class _DefaultRuleBasedAgent:
    """Package-internal fallback agent used when callers do not attach one."""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str:
        self.calls.append((user_message, session_id))
        has_context = bool(extra_context and extra_context.strip())
        context_label = "with memory context" if has_context else "without memory context"
        return f"[demo agent reply {context_label}: {user_message[:50]}]"


class MemoryGarden:
    """Unified SDK entry point for the complete Memory Garden stack.

    Usage::

        garden = MemoryGarden.local("./my_garden")
        result = garden.chat("花花开")
        result = garden.chat("I prefer dark mode.", session_id=result.session_id)
        result = garden.chat("花花关", session_id=result.session_id)
        garden.close()
    """

    def __init__(
        self,
        *,
        core: MemoryGardenCore,
        runtime: GardenRuntime,
        observer: GardenObserver,
        garden_home: GardenHome,
        adapter_config: GardenAdapterConfig | None = None,
        covenant: "Any | None" = None,
        strategy_context: dict[str, Any] | None = None,
    ) -> None:
        self._core = core
        self._runtime = runtime
        self._observer = observer
        self._garden_home = garden_home
        self._adapter_config = adapter_config or GardenAdapterConfig()
        self._adapter: SyncGardenChatAdapter | None = None
        self._host_agent: ChatAgentProtocol | None = None
        self._enforcer: CovenantEnforcer | None = None
        if covenant is not None:
            self._enforcer = CovenantEnforcer(covenant)
        self._cognition_providers: dict[str, Any] = {}
        self._strategy_context: dict[str, Any] = dict(strategy_context or {})
        self._default_skill: GardenSkill | None = None
        self._skill_product_providers: ProviderRegistry | None = None
        self._product_system: ProductMemorySystem | None = None

    # ── Factory ────────────────────────────────────────────────────

    @classmethod
    def local(
        cls,
        path: str | Path = "./.memory_garden",
        *,
        repository: GardenRepository | None = None,
        adapter_config: GardenAdapterConfig | None = None,
        covenant: "Any | None" = None,
        cognition: dict[str, Any] | None = None,
        strategy_context: dict[str, Any] | None = None,
    ) -> "MemoryGarden":
        """创建一个本地 Memory Garden 实例。

        该方法会初始化 garden home、打开 SQLite 数据库，并串起 Core、Runtime、
        Harvest 与 Observatory。默认 harvester 会从本地长期记忆中检索可追踪的
        ``MemoryCard.id``，不再使用空采摘器。

        如果传入 ``covenant``，会附加 ``CovenantEnforcer``。如果传入
        ``cognition``（可包含 ``emb_provider``、``rank_provider``、``cog_writer``），
        这些 provider 可通过 ``garden.harvest_cognitive()`` 使用。
        """
        home = initialize_garden_home(path, create=True)
        db_path = str(home.root / "garden.db")
        repo = repository or SQLiteGardenRepository(db_path)
        core = MemoryGardenCore(repository=repo)
        manager = GardenSessionManager()
        cognition_config = dict(cognition or {})
        if cognition_config:
            garden_harvester = GardenHarvester(
                emb_provider=cognition_config.get("emb_provider"),
                rank_provider=cognition_config.get("rank_provider"),
                cog_writer=cognition_config.get("cog_writer"),
            )
        else:
            garden_harvester = GardenHarvester()
        harvester = RuntimeGardenHarvesterAdapter(
            garden_harvester,
            memory_provider=create_bounded_runtime_memory_provider(core.repository),
            cognitive_mode=CognitiveHarvestMode.HYBRID if cognition_config else None,
        )
        hooks = RuntimeHooks(manager, harvester, TemplateBriefWriter(), core)
        runtime = GardenRuntime(core, manager, hooks)
        observer = GardenObserver()
        instance = cls(
            core=core,
            runtime=runtime,
            observer=observer,
            garden_home=home,
            adapter_config=adapter_config or GardenAdapterConfig(),
            covenant=covenant,
            strategy_context=strategy_context,
        )
        instance._cognition_providers = cognition_config
        return instance

    # ── Chat ───────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        """处理一条用户消息，并执行完整的 Garden 会话流程。

        方法会委托给 ``SyncGardenChatAdapter.reply()``。首次调用通常使用“花花开”
        打开会话，结束时使用“花花关”关闭会话。
        """
        adapter = self._get_adapter()
        return adapter.reply(user_message, session_id=session_id, metadata=metadata)

    def set_host_agent(self, agent: ChatAgentProtocol) -> None:
        """Replace the default rule-based agent with a custom host agent.

        Must be called before the first ``chat()`` invocation.
        """
        self._host_agent = agent
        self._adapter = None  # force rebuild on next chat

    def retrieve(self, query: str, limit: int = 5) -> "MemoryRetrievalResult":
        """Retrieve memories through the product strategy layer.

        This is an optional high-level API.  ``chat()`` continues to use the
        existing ``SyncGardenChatAdapter`` path.
        """
        return self._get_product_system().retrieve(
            query,
            limit=limit,
            context=self._product_strategy_context(query),
        )

    def build_brief(self, query: str, limit: int = 5) -> "GardenBrief":
        """Build a source-id-preserving brief through the strategy layer."""
        return self._get_product_system().build_brief(
            query,
            limit=limit,
            context=self._product_strategy_context(query),
        )

    # ── Async ──────────────────────────────────────────────────────

    @classmethod
    def local_async(
        cls,
        path: str | Path = "./.memory_garden",
        *,
        adapter_config: GardenAdapterConfig | None = None,
    ) -> "MemoryGarden":
        """Create a local-first Memory Garden instance (identical to ``local()``).

        Use ``async_chat()`` instead of ``chat()`` for async adapter support.
        """
        return cls.local(path, adapter_config=adapter_config)

    async def async_chat(
        self,
        user_message: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationResult:
        """Process one user message through the async garden cycle."""
        from memory_garden.integrations.async_adapter import AsyncGardenChatAdapter
        from memory_garden.integrations.protocols import AsyncChatAgentProtocol

        class _AsyncDemo(AsyncChatAgentProtocol):
            async def generate_assistant_reply(self, *, user_message, session_id, extra_context=None):
                return f"[demo agent reply to: {user_message[:50]}]"

        adapter = AsyncGardenChatAdapter(
            agent=_AsyncDemo(),
            runtime=self._runtime,
            config=self._adapter_config,
        )
        return await adapter.reply(user_message, session_id=session_id, metadata=metadata)

    # ── Health ─────────────────────────────────────────────────────

    def health(self) -> GardenHealthReport:
        """检查当前 Garden 健康状态，包括 manifest、FTS 索引和陈旧条目。"""
        return check_garden_health(self._garden_home.root)

    # ── Observatory ─────────────────────────────────────────────────

    def summary(self, *, limit: int = 50) -> "GardenSummaryView":
        """Query the garden database and return a populated observatory summary."""
        from memory_garden.observatory.views import GardenSummaryView
        return GardenSummaryView.from_garden_home(self._garden_home.root, limit=limit)

    # ── Properties ─────────────────────────────────────────────────

    @property
    def home(self) -> GardenHome:
        return self._garden_home

    # ── Skill ─────────────────────────────────────────────────────

    def as_skill(self, config: "Any | None" = None) -> "GardenSkill":
        """返回绑定当前 Garden 的 ``GardenSkill``。

        Skill 提供框架无关的 ``before()`` / ``after()`` 钩子，可接入任意 LLM 或
        Agent 框架；也可继续调用 ``with_deepseek()`` / ``with_openai()`` 一键配置 provider。
        """
        from memory_garden.skill import GardenSkill
        if config is None:
            if self._default_skill is None:
                self._default_skill = GardenSkill(self)
            return self._default_skill
        return GardenSkill(self, config=config)

    def _get_skill_product_providers(self) -> "ProviderRegistry | None":
        return self._skill_product_providers

    def _set_skill_product_providers(self, providers: "ProviderRegistry | None") -> None:
        self._skill_product_providers = providers
        if self._default_skill is not None:
            self._default_skill._product_providers = providers
            self._default_skill._product_system = None

    # ── Cognition ──────────────────────────────────────────────────

    @property
    def cognition_providers(self) -> dict[str, Any]:
        """Return the cognition providers dict set at construction time."""
        return dict(self._cognition_providers)

    def harvest_cognitive(
        self,
        query: Any,
        memories: list[Any],
        *,
        policy: Any = None,
        mode: Any = None,
    ) -> tuple[Any, Any]:
        """Run cognitive harvest (Hybrid mode) with configured providers.

        Requires cognition providers to be set via ``local(cognition={...})``.
        Falls back to rules_only on provider failure.
        """
        from memory_garden.harvest.harvester import GardenHarvester

        harvester = GardenHarvester(
            emb_provider=self._cognition_providers.get("emb_provider"),
            rank_provider=self._cognition_providers.get("rank_provider"),
            cog_writer=self._cognition_providers.get("cog_writer"),
        )
        return harvester.harvest_cognitive(query, memories, policy=policy, mode=mode)

    @property
    def core(self) -> MemoryGardenCore:
        return self._core

    @property
    def runtime(self) -> GardenRuntime:
        return self._runtime

    @property
    def observer(self) -> GardenObserver:
        return self._observer

    @property
    def enforcer(self) -> CovenantEnforcer | None:
        """Return the attached CovenantEnforcer, or None."""
        return self._enforcer

    # ── Close ──────────────────────────────────────────────────────

    def close(self) -> None:
        """关闭数据库连接并释放本地资源。"""
        self._product_system = None
        repo = self._core._repository
        if hasattr(repo, "close"):
            repo.close()

    # ── Context managers ────────────────────────────────────────────

    def __enter__(self) -> "MemoryGarden":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> "MemoryGarden":
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.close()

    # ── Internal ───────────────────────────────────────────────────

    def _get_adapter(self) -> SyncGardenChatAdapter:
        if self._adapter is None:
            agent = self._host_agent or _DefaultRuleBasedAgent()
            self._adapter = SyncGardenChatAdapter(
                agent=agent,
                runtime=self._runtime,
                config=self._adapter_config,
            )
        return self._adapter

    def _get_product_system(self) -> "ProductMemorySystem":
        if self._product_system is None:
            from memory_garden.product import ProductMemorySystem

            self._product_system = ProductMemorySystem(
                garden_home=self._garden_home.root,
                repository=self._core.repository,
            )
        return self._product_system

    def _product_strategy_context(self, query: str) -> dict[str, Any]:
        context = dict(self._strategy_context)
        requested_scope = str(context.pop("scope", "") or "").strip()
        include_scopes = list(context.get("include_scopes") or [])
        if requested_scope and requested_scope not in include_scopes:
            include_scopes.append(requested_scope)
        if include_scopes:
            context["include_scopes"] = include_scopes
        return context
