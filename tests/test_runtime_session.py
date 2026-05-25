"""第二层 Stage 2C：GardenSessionManager 生命周期。"""

import inspect
import json

from memory_garden.runtime.session import RuntimeFeedback
from memory_garden.runtime.session_manager import GardenSessionManager
from memory_garden.runtime.state import RuntimeState


def test_manager_starts_closed() -> None:
    m = GardenSessionManager()
    assert m.current_session().state == RuntimeState.CLOSED


def test_open_then_open_state_and_timestamps() -> None:
    m = GardenSessionManager()
    placeholder_id = m.current_session().session_id
    s = m.open_session()
    assert s.session_id != placeholder_id
    assert s.state == RuntimeState.OPEN
    assert s.closed_at is None
    assert s.turn_count == 0
    assert s.opened_at is not None


def test_close_then_open_new_session_id() -> None:
    m = GardenSessionManager()
    m.open_session()
    sid_open = m.current_session().session_id
    m.close_session()
    assert m.current_session().session_id == sid_open
    m.open_session()
    assert m.current_session().session_id != sid_open
    assert m.current_session().state == RuntimeState.OPEN


def test_close_sets_closed_and_closed_at() -> None:
    m = GardenSessionManager()
    m.open_session()
    s = m.close_session()
    assert s.state == RuntimeState.CLOSED
    assert s.closed_at is not None


def test_repeat_open_does_not_corrupt_open_session() -> None:
    m = GardenSessionManager()
    m.open_session(metadata={"a": 1})
    first_id = m.current_session().session_id
    opened_first = m.current_session().opened_at
    turn_before = m.current_session().turn_count
    m.open_session(metadata={"b": 2})
    cur = m.current_session()
    assert cur.state == RuntimeState.OPEN
    assert cur.session_id == first_id
    assert cur.opened_at == opened_first
    assert cur.turn_count == turn_before
    assert cur.metadata.get("a") == 1
    assert cur.metadata.get("b") == 2


def test_repeat_close_idempotent() -> None:
    m = GardenSessionManager()
    m.open_session()
    m.close_session()
    m.close_session()
    assert m.current_session().state == RuntimeState.CLOSED


def test_close_accepts_runtime_feedback_without_generating_copy() -> None:
    m = GardenSessionManager()
    m.open_session()
    fb = RuntimeFeedback(
        session_id=m.current_session().session_id,
        summary="用户传入占位摘要",
        bullets=[],
    )
    m.close_session(feedback=fb)
    hist = m.current_session().metadata.get("feedback_history", [])
    assert len(hist) == 1
    assert hist[0]["summary"] == "用户传入占位摘要"
    assert "feedback_history" in m.current_session().metadata


def test_session_json_dump_roundtrip() -> None:
    m = GardenSessionManager()
    m.open_session()
    raw = m.current_session().model_dump(mode="json")
    json.dumps(raw)
    assert raw["session_id"]


def test_session_manager_has_no_core_imports() -> None:
    import memory_garden.runtime.session_manager as sm

    src = inspect.getsource(sm)
    assert "memory_garden.core" not in src
    for needle in ("MemoryGardenCore", "SeedObserver", "SQLiteGardenRepository"):
        assert needle not in src


def test_no_before_after_tick_implemented() -> None:
    import memory_garden.runtime.session_manager as sm

    src = inspect.getsource(sm)
    for needle in ("before_reply", "after_reply", "garden_tick", "before_turn", "after_turn"):
        assert needle not in src
