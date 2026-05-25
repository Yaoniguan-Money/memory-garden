"""第二层 Stage 2F：TriggerEngine 与 garden_tick。"""

import inspect
from unittest.mock import MagicMock

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.core.models import Seed, SeedStatus
from memory_garden.runtime import (
    GardenSessionManager,
    RuntimePolicy,
    TriggerEngine,
    TurnContext,
)
from memory_garden.runtime.policies import FeedbackMode
from memory_garden.runtime.session import GardenSession
from memory_garden.runtime.tick import garden_tick


@pytest.fixture
def core() -> MemoryGardenCore:
    return MemoryGardenCore()


@pytest.fixture
def manager() -> GardenSessionManager:
    return GardenSessionManager()


@pytest.fixture
def engine(core: MemoryGardenCore) -> TriggerEngine:
    return TriggerEngine(core)


def _session_open(manager: GardenSessionManager) -> GardenSession:
    manager.open_session()
    return manager.current_session()


def _turn_ctx(session_id: str, text: str, turn_index: int = 1) -> TurnContext:
    return TurnContext(
        session_id=session_id,
        turn_index=turn_index,
        user_message=text,
        assistant_reply=None,
        metadata={},
    )


def test_tick_closed_is_noop(manager: GardenSessionManager, core: MemoryGardenCore, engine: TriggerEngine) -> None:
    policy = RuntimePolicy(enable_auto_court=True, enable_auto_dream=True)
    sid = manager.current_session().session_id
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sid, "hi"),
        engine,
    )
    assert r.skipped_reasons
    assert "tick_noop_state_closed" in r.skipped_reasons[0]


def test_pending_below_threshold_no_court(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    core.repository.save_seed(
        Seed(content="a", source_excerpt="a", status=SeedStatus.pending)
    )
    policy = RuntimePolicy(
        enable_auto_court=True,
        court_pending_seed_threshold=3,
        feedback_mode=FeedbackMode.off,
    )
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "hello"),
        engine,
    )
    assert r.opened_court_case_ids == []


def test_pending_meets_threshold_opens_court(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    for i in range(3):
        core.repository.save_seed(
            Seed(content=f"x{i}", source_excerpt=f"x{i}", status=SeedStatus.pending)
        )
    policy = RuntimePolicy(
        enable_auto_court=True,
        court_pending_seed_threshold=3,
    )
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "开庭"),
        engine,
    )
    assert len(r.opened_court_case_ids) >= 1


def test_strong_signal_triggers_court(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    core.repository.save_seed(
        Seed(content="p", source_excerpt="p", status=SeedStatus.pending)
    )
    policy = RuntimePolicy(
        enable_auto_court=True,
        court_pending_seed_threshold=99,
        enable_strong_signal_trigger=True,
    )
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "务必今天处理完这件事"),
        engine,
    )
    assert len(r.opened_court_case_ids) >= 1


def test_turn_below_dream_threshold_no_dream(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    manager._session = manager.current_session().model_copy(update={"turn_count": 2})
    policy = RuntimePolicy(
        enable_auto_dream=True,
        dream_turn_threshold=5,
    )
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "hello"),
        engine,
    )
    assert r.dream_record_id is None


def test_turn_meets_dream_threshold_calls_dream(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    policy = RuntimePolicy(
        enable_auto_dream=True,
        dream_turn_threshold=2,
    )
    manager._session = manager.current_session().model_copy(update={"turn_count": 2})
    core.dream = MagicMock(return_value=None)
    garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "hello"),
        engine,
    )
    core.dream.assert_called_once()


def test_policy_disable_blocks_court(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    for i in range(3):
        core.repository.save_seed(
            Seed(content=f"y{i}", source_excerpt=f"y{i}", status=SeedStatus.pending)
        )
    policy = RuntimePolicy(
        enable_auto_court=False,
        court_pending_seed_threshold=3,
    )
    core.open_court = MagicMock(wraps=core.open_court)
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "hi"),
        engine,
    )
    core.open_court.assert_not_called()
    assert r.opened_court_case_ids == []


def test_topic_shift_records_reason_without_forcing_dream(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    policy = RuntimePolicy(
        enable_auto_dream=True,
        dream_turn_threshold=99,
        enable_topic_shift_trigger=True,
    )
    manager._session = manager.current_session().model_copy(update={"turn_count": 1})
    core.dream = MagicMock(return_value=None)
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "我们换个话题吧"),
        engine,
    )
    assert any("topic_shift" in x for x in r.skipped_reasons)
    core.dream.assert_not_called()


def test_tick_module_has_no_growth_actions() -> None:
    import memory_garden.runtime.tick as t

    src = inspect.getsource(t)
    for needle in (".plant(", "compost_seed", "greenhouse_memory", "prune_memory", "forget_memory", "merge_"):
        assert needle not in src


def test_tick_returns_traceable_ids_and_reasons(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    engine: TriggerEngine,
) -> None:
    sess = _session_open(manager)
    core.repository.save_seed(
        Seed(content="z", source_excerpt="z", status=SeedStatus.pending)
    )
    policy = RuntimePolicy(
        enable_auto_court=True,
        enable_strong_signal_trigger=True,
    )
    r = garden_tick(
        core,
        manager,
        policy,
        _turn_ctx(sess.session_id, "重要：请记录这条"),
        engine,
    )
    meta = manager.current_session().metadata
    assert "last_tick_court_case_ids" in meta
    assert isinstance(r.skipped_reasons, list)


def test_tick_no_user_visible_feedback_field():
    """GardenTickResult 不含面向用户的反馈文案字段。"""
    from memory_garden.runtime.session import GardenTickResult

    names = GardenTickResult.model_fields.keys()
    assert not any("feedback" in n for n in names)
