"""第二层 Stage 2A：Runtime 模型 round-trip 与默认值。"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from memory_garden.runtime.policies import FeedbackMode, RuntimePolicy
from memory_garden.runtime.session import (
    GardenBrief,
    GardenSession,
    GardenTickResult,
    RuntimeFeedback,
    TriggerDecision,
    TurnContext,
)
from memory_garden.runtime.state import RuntimeState


def _json_roundtrip(model):
    raw = model.model_dump(mode="json")
    dumped = json.dumps(raw, ensure_ascii=False)
    loaded = json.loads(dumped)
    return model.__class__.model_validate(loaded)


def test_runtime_state_values() -> None:
    assert RuntimeState.CLOSED.value == "closed"
    assert RuntimeState.OPEN.value == "open"
    assert RuntimeState.CLOSING.value == "closing"


def test_garden_session_defaults_closed() -> None:
    s = GardenSession()
    assert s.state == RuntimeState.CLOSED
    assert s.turn_count == 0
    assert s.closed_at is None
    rt = _json_roundtrip(s)
    assert rt.state == RuntimeState.CLOSED


def test_garden_session_round_trip() -> None:
    fixed = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    s = GardenSession(
        session_id="sid-1",
        state=RuntimeState.OPEN,
        opened_at=fixed,
        closed_at=None,
        turn_count=3,
        last_user_message_at=fixed,
        metadata={"client": "pytest"},
    )
    rt = _json_roundtrip(s)
    assert rt.session_id == "sid-1"
    assert rt.state == RuntimeState.OPEN
    assert rt.turn_count == 3


def test_turn_context_round_trip() -> None:
    t = TurnContext(
        session_id="sid",
        turn_index=0,
        user_message="  hello  ",
        assistant_reply=None,
        metadata={},
    )
    assert t.user_message == "hello"
    rt = _json_roundtrip(t)
    assert rt.turn_index == 0
    assert rt.user_message == "hello"


def test_turn_context_user_message_empty_raises() -> None:
    with pytest.raises(ValidationError):
        TurnContext(session_id="s", turn_index=0, user_message="   ")


def test_garden_brief_short_fields_and_sources_round_trip() -> None:
    b = GardenBrief(
        intent="协助写作",
        use="简洁中文",
        avoid="编造隐私",
        style="中性",
        safety="敏感话题降级",
        nudge="需要时再展开",
        source_memory_ids=["m1", "m2"],
    )
    rt = _json_roundtrip(b)
    assert rt.source_memory_ids == ["m1", "m2"]
    assert "m1" in rt.source_memory_ids


def test_garden_brief_no_llm_or_search_field_names() -> None:
    dumped = GardenBrief(
        intent="i",
        use="u",
        avoid="a",
        style="s",
        safety="sf",
        nudge="n",
        source_memory_ids=[],
    ).model_dump()
    forbidden_substrings = ("llm", "embedding", "vector", "search", "rerank")
    blob = json.dumps(dumped).lower()
    for bad in forbidden_substrings:
        assert bad not in blob


def test_runtime_policy_round_trip_and_thresholds() -> None:
    p = RuntimePolicy(
        feedback_mode=FeedbackMode.normal,
        court_turn_threshold=5,
        court_pending_seed_threshold=3,
        dream_turn_threshold=10,
        prune_check_turn_threshold=20,
        enable_auto_court=True,
        enable_auto_dream=False,
        enable_strong_signal_trigger=True,
        enable_topic_shift_trigger=True,
        auto_close_on_session_end=True,
        enable_harvest_brief=True,
    )
    rt = _json_roundtrip(p)
    assert rt.court_turn_threshold == 5
    assert rt.court_pending_seed_threshold == 3
    assert rt.enable_auto_court is True
    assert rt.enable_strong_signal_trigger is True
    assert rt.auto_close_on_session_end is True


def test_runtime_policy_trigger_field_mapping_documented() -> None:
    """策略字段与 TriggerDecision 配对关系见 policies 模块文档字符串。"""
    import memory_garden.runtime.policies as pol

    doc = pol.__doc__ or ""
    assert "court_pending_seed_threshold" in doc or "seed" in doc
    assert "strong_signal" in doc or "强信号" in doc


def test_runtime_policy_threshold_validation() -> None:
    with pytest.raises(ValidationError):
        RuntimePolicy(court_turn_threshold=0)


def test_trigger_decision_round_trip() -> None:
    d = TriggerDecision(
        should_open_court=True,
        should_dream=False,
        should_prune_check=True,
        strong_signal=True,
        topic_shift=False,
        reasons=["达到回合阈值", "策略允许"],
    )
    rt = _json_roundtrip(d)
    assert rt.should_open_court is True
    assert rt.strong_signal is True
    assert rt.topic_shift is False
    assert len(rt.reasons) == 2


def test_runtime_feedback_round_trip_for_close_session_stage() -> None:
    """close_session 阶段可挂载 RuntimeFeedback；文案生成后续 Feedback Stage。"""
    f = RuntimeFeedback(
        session_id="sess-1",
        summary="本会话已关闭，花园未执行额外动作",
        bullets=["开庭：跳过", "梦境：未触发"],
        metadata={"stage": "acceptance"},
    )
    rt = _json_roundtrip(f)
    assert rt.session_id == "sess-1"
    assert len(rt.bullets) == 2


def test_garden_tick_result_round_trip() -> None:
    r = GardenTickResult(
        opened_court_case_ids=["c1"],
        applied_action_ids=["a1"],
        dream_record_id="d1",
        event_ids=["e1", "e2"],
        skipped_reasons=["auto_dream 关闭"],
    )
    rt = _json_roundtrip(r)
    assert rt.dream_record_id == "d1"
    assert "e2" in rt.event_ids
