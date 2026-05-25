"""第二层：TriggerEngine — 仅决策是否触发 open_court / dream，不执行 Growth。"""

from __future__ import annotations

from memory_garden.core.garden import MemoryGardenCore
from memory_garden.core.models import SeedStatus
from memory_garden.runtime.policies import RuntimePolicy
from memory_garden.runtime.session import GardenSession, TriggerDecision, TurnContext

_STRONG_MARKERS: tuple[str, ...] = (
    "务必",
    "紧急",
    "重要",
    "千万不要",
)

_TOPIC_SHIFT_MARKERS: tuple[str, ...] = (
    "换个话题",
    "不说这个了",
    "换题目",
)


def _count_pending_seeds(core: MemoryGardenCore) -> int:
    return len(
        [s for s in core.repository.list_seeds() if s.status == SeedStatus.pending]
    )


def _strong_hit(text: str, meta: dict[str, object]) -> bool:
    if meta.get("strong_signal") is True:
        return True
    return any(m in text for m in _STRONG_MARKERS)


def _topic_shift_hit(text: str, meta: dict[str, object]) -> bool:
    if meta.get("topic_shift") is True:
        return True
    return any(m in text for m in _TOPIC_SHIFT_MARKERS)


class TriggerEngine:
    """根据会话、策略与回合上下文判定是否建议开庭 / 梦境（最终仍由 tick 与策略开关执行）。"""

    __slots__ = ("_core",)

    def __init__(self, core: MemoryGardenCore) -> None:
        self._core = core

    def evaluate(
        self,
        session: GardenSession,
        policy: RuntimePolicy,
        turn_context: TurnContext,
        created_seed_ids: list[str] | None = None,
    ) -> TriggerDecision:
        reasons: list[str] = []
        text = turn_context.user_message.strip()
        meta = dict(turn_context.metadata)

        strong = False
        topic_shift = False
        if policy.enable_strong_signal_trigger:
            strong = _strong_hit(text, meta)
        if policy.enable_topic_shift_trigger:
            topic_shift = _topic_shift_hit(text, meta)

        pending = _count_pending_seeds(self._core)
        if created_seed_ids:
            reasons.append(f"created_seed_ids_hint:{len(created_seed_ids)}")

        should_open = False
        should_dream = False

        if policy.court_pending_seed_threshold is not None and pending >= policy.court_pending_seed_threshold:
            should_open = True
            reasons.append("pending_seed_count_threshold")
        if policy.court_turn_threshold is not None and session.turn_count >= policy.court_turn_threshold:
            should_open = True
            reasons.append("court_turn_threshold")
        if policy.enable_strong_signal_trigger and strong:
            should_open = True
            reasons.append("strong_signal")

        if policy.dream_turn_threshold is not None and session.turn_count >= policy.dream_turn_threshold:
            should_dream = True
            reasons.append("dream_turn_threshold")

        if topic_shift:
            reasons.append("topic_shift_noted_no_auto_dream")

        return TriggerDecision(
            should_open_court=should_open,
            should_dream=should_dream,
            should_prune_check=False,
            strong_signal=strong,
            topic_shift=topic_shift,
            reasons=reasons,
        )
