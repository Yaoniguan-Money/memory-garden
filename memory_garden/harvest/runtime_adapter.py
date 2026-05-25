"""第三层 Stage 3H：Runtime 侧的 HarvesterProtocol 适配器（不接仓库、不接外部模型）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.models import HarvestQuery, HarvestTrace
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.runtime.session import GardenBrief, TurnContext

MemoryProvider: TypeAlias = Callable[[TurnContext], list[MemoryCard]]
TraceSink: TypeAlias = Callable[[HarvestTrace], None]


def turn_context_to_harvest_query(turn: TurnContext) -> HarvestQuery:
    """将第二层回合上下文裁剪为采摘查询快照（不设透镜，由流水线内部处理）。"""
    meta = dict(turn.metadata or {})
    meta.setdefault("namespace", turn.session_id)
    return HarvestQuery(
        session_id=turn.session_id,
        turn_index=turn.turn_index,
        raw_user_text=turn.user_message,
        metadata=meta,
    )


class RuntimeGardenHarvesterAdapter:
    """将 ``GardenHarvester`` 包装为 ``HarvesterProtocol``；不暴露检索/排序实现细节。"""

    last_trace: HarvestTrace | None
    last_cognitive_trace: Any | None

    def __init__(
        self,
        harvester: GardenHarvester,
        memory_provider: MemoryProvider | None = None,
        trace_sink: TraceSink | None = None,
        *,
        policy: HarvestBudgetPolicy | None = None,
        cognitive_mode: Any | None = None,
    ) -> None:
        self._harvester = harvester
        self._memory_provider: MemoryProvider = memory_provider or (lambda _tc: [])
        self._trace_sink = trace_sink
        self._policy = policy
        self._cognitive_mode = cognitive_mode
        self.last_trace = None
        self.last_cognitive_trace = None

    def harvest(self, turn_context: TurnContext) -> GardenBrief:
        memories = self._memory_provider(turn_context)
        query = turn_context_to_harvest_query(turn_context)
        memories_in = list(memories)
        if self._cognitive_mode is not None:
            brief, cog_trace = self._harvester.harvest_cognitive(
                query,
                memories_in,
                self._policy,
                mode=self._cognitive_mode,
            )
            self.last_trace = None
            self.last_cognitive_trace = cog_trace
            return brief.to_runtime_brief()
        trace = self._harvester.harvest(query, memories_in, self._policy)
        self.last_trace = trace
        self.last_cognitive_trace = None
        if self._trace_sink is not None:
            self._trace_sink(trace)
        hb = getattr(trace, "brief", None)
        if hb is None:
            return GardenBrief(
                intent="本轮无第三层简报对象，使用保守占位。",
                use="暂无可用药引式记忆标识。",
                avoid="避免臆测用户长期事实。",
                style="中性简短。",
                safety="默认保守、无外部检索。",
                nudge="若需记忆辅助请检查采摘流水线。",
                source_memory_ids=[],
            )
        return hb.to_runtime_brief()
