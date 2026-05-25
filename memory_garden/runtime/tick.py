"""第二层：garden_tick — 仅按需调用 Core.open_court / Core.dream，不执行 Growth 动作。"""

from __future__ import annotations

from memory_garden.core.garden import MemoryGardenCore
from memory_garden.runtime.interfaces import TickOrchestratorProtocol
from memory_garden.runtime.policies import RuntimePolicy
from memory_garden.runtime.session import GardenTickResult, TurnContext
from memory_garden.runtime.session_manager import GardenSessionManager
from memory_garden.runtime.state import RuntimeState
from memory_garden.runtime.triggers import TriggerEngine


def garden_tick(
    core: MemoryGardenCore,
    session_manager: GardenSessionManager,
    policy: RuntimePolicy,
    turn_context: TurnContext,
    trigger_engine: TriggerEngine,
    *,
    created_seed_ids: list[str] | None = None,
) -> GardenTickResult:
    """每轮可调用；仅在 ``OPEN`` 且决策与策略允许时触发开庭或梦境（重活）。"""
    sess = session_manager.current_session()
    if sess.state not in (RuntimeState.OPEN,):
        return GardenTickResult(
            skipped_reasons=[f"tick_noop_state_{sess.state.value}"],
        )

    decision = trigger_engine.evaluate(sess, policy, turn_context, created_seed_ids)

    opened_ids: list[str] = []
    dream_rid: str | None = None
    skipped: list[str] = []

    if decision.should_open_court and policy.enable_auto_court:
        cases = core.open_court()
        opened_ids = [c.id for c in cases]
    elif decision.should_open_court and not policy.enable_auto_court:
        skipped.append("decision_open_court_but_policy_disabled_auto_court")
    elif not decision.should_open_court:
        skipped.append("open_court_not_selected")

    if decision.should_dream and policy.enable_auto_dream:
        dr = core.dream()
        dream_rid = dr.id if dr else None
    elif decision.should_dream and not policy.enable_auto_dream:
        skipped.append("decision_dream_but_policy_disabled_auto_dream")
    elif not decision.should_dream:
        skipped.append("dream_not_selected")

    merged_skip = list(dict.fromkeys(skipped + decision.reasons))

    session_manager.record_tick_summary(
        court_case_ids=opened_ids,
        dream_record_ids=[dream_rid] if dream_rid else [],
        skipped_reasons=merged_skip,
        decision_reasons=list(decision.reasons),
    )

    return GardenTickResult(
        opened_court_case_ids=opened_ids,
        applied_action_ids=[],
        dream_record_id=dream_rid,
        event_ids=[],
        skipped_reasons=merged_skip,
    )


GARDEN_TICK_ORCHESTRATOR: TickOrchestratorProtocol = garden_tick
