"""第四层 Stage 4D：RuntimeObservationAdapter — Runtime 单次交互 → ObservationTrace / View。"""

from __future__ import annotations

import json

import pytest

from memory_garden.core.models import Seed
from memory_garden.observatory.models import RedactionLevel
from memory_garden.observatory.runtime import RuntimeObservationAdapter
from memory_garden.runtime.hooks import RuntimeAfterReplyResult, RuntimeBeforeReplyResult
from memory_garden.runtime.runtime import RuntimeCommandResult
from memory_garden.runtime.session import GardenBrief, GardenSession, GardenTickResult, RuntimeFeedback, TurnContext
from memory_garden.runtime.state import RuntimeState


def _brief(*, memory_ids: list[str]) -> GardenBrief:
    return GardenBrief(
        intent="意图：测试简报字段均需非空以通过校验",
        use="用途：同上",
        avoid="规避：测试中性的占位短语",
        style="语气：简短中性",
        safety="安全：不断言个人隐私",
        nudge="提示：仅供观测链路测试",
        source_memory_ids=memory_ids,
    )


def test_before_after_tick_produce_observation_trace() -> None:
    sess = GardenSession(session_id="s-runtime-1", state=RuntimeState.OPEN)
    brief = _brief(memory_ids=["mem-a"])
    before = RuntimeBeforeReplyResult(brief=brief, skipped_reasons=[], tick_skipped=True)
    after = RuntimeAfterReplyResult(
        turn_count=1,
        seeds=[Seed(content="c", source_excerpt="e")],
        tick_result=GardenTickResult(
            opened_court_case_ids=["cc-1"],
            dream_record_id="dr-9",
            applied_action_ids=[],
            event_ids=["ev-1"],
        ),
    )
    tick_direct = GardenTickResult(opened_court_case_ids=["cc-99"])
    ot = RuntimeObservationAdapter().trace_from_turn(
        session=sess,
        before_result=before,
        after_result=after,
        tick_result=tick_direct,
    )
    assert ot.root_span_id
    assert ot.trace_id
    dumped = ot.model_dump(mode="json")
    json.dumps(dumped)


def test_trace_has_root_runtime_turn_and_expected_child_spans() -> None:
    ot = RuntimeObservationAdapter().trace_from_turn(
        session=GardenSession(session_id="x", state=RuntimeState.CLOSED),
    )
    by_name = {s.name: s for s in ot.spans}
    assert by_name["runtime_turn"].parent_span_id is None
    expected_children = (
        "command_check",
        "before_reply",
        "harvest_brief",
        "after_reply",
        "garden_tick",
        "closing_feedback",
    )
    for nm in expected_children:
        assert nm in by_name
        assert by_name[nm].parent_span_id == by_name["runtime_turn"].span_id


def test_brief_source_memory_ids_yield_memory_refs_or_links() -> None:
    brief = _brief(memory_ids=["m-used-1", "m-used-2"])
    ot = RuntimeObservationAdapter().trace_from_turn(
        before_result=RuntimeBeforeReplyResult(brief=brief, skipped_reasons=[]),
    )
    mem_refs = [r.memory_id for r in ot.source_refs if r.memory_id]
    assert "m-used-1" in mem_refs
    rels = {lk.relation for lk in ot.links}
    assert "brief_used_memory" in rels


def test_tick_court_and_dream_yield_refs_or_links() -> None:
    tick = GardenTickResult(opened_court_case_ids=["case-a"], dream_record_id="dream-zz")
    ot = RuntimeObservationAdapter().trace_from_turn(tick_result=tick)
    court_refs = [r.court_case_id for r in ot.source_refs if r.court_case_id]
    dream_refs = [r.dream_record_id for r in ot.source_refs if r.dream_record_id]
    assert "case-a" in court_refs
    assert "dream-zz" in dream_refs
    rels = {lk.relation for lk in ot.links}
    assert "tick_opened_court_case" in rels
    assert "tick_completed_dream" in rels


def test_command_handled_true_surfaces_in_command_section() -> None:
    cmd = RuntimeCommandResult(
        command="open",
        session_id="sid",
        state=RuntimeState.OPEN,
        handled=True,
        message="会话已就绪",
    )
    ad = RuntimeObservationAdapter()
    tr = ad.trace_from_turn(command_result=cmd)
    vw = ad.view_from_trace(tr, RedactionLevel.PUBLIC)
    assert vw.sections["command"]["handled"] is True
    assert vw.sections["command"]["command"] == "open"
    evt_names = [e.name for e in tr.events]
    assert "command_handled" in evt_names


def test_closed_skipped_before_shows_skip_not_successful_harvest_pipeline() -> None:
    sess = GardenSession(session_id="closed-s", state=RuntimeState.CLOSED)
    skipped = RuntimeBeforeReplyResult(brief=None, skipped_reasons=["harvest_skipped_state_closed"], tick_skipped=True)
    tr = RuntimeObservationAdapter().trace_from_turn(session=sess, before_result=skipped)
    names_in_order = [e.name for e in tr.events]
    assert names_in_order.index("before_reply_skipped") < names_in_order.index("harvest_brief_empty")
    assert "harvest_brief_available" not in names_in_order


def test_feedback_in_section_feedback_id_not_fake_memory_ref() -> None:
    fb = RuntimeFeedback(session_id="s-fb", summary="收尾摘要占位")
    ad = RuntimeObservationAdapter()
    tr = ad.trace_from_turn(feedback=fb)
    vw = ad.view_from_trace(tr, RedactionLevel.PUBLIC)
    assert vw.sections["feedback"]["has_feedback"] is True
    assert vw.sections["feedback"]["feedback_id"] == fb.feedback_id
    for r in tr.source_refs:
        assert r.memory_id != fb.feedback_id
        assert r.event_id != fb.feedback_id


def test_public_view_hides_full_user_and_assistant_messages() -> None:
    long_u = "用户长文" + "X" * 3000
    long_a = "助手长文" + "Y" * 3000
    tc = TurnContext(session_id="sid", turn_index=0, user_message=long_u, assistant_reply=long_a)
    tr = RuntimeObservationAdapter().trace_from_turn(turn_context=tc)
    pub = RuntimeObservationAdapter().view_from_trace(tr, RedactionLevel.PUBLIC)
    blob = json.dumps(pub.model_dump(mode="json"))
    assert long_u not in blob
    assert long_a not in blob
    assert "turn_excerpts_internal" not in pub.sections


def test_internal_view_serializable_and_only_truncated_excerpts() -> None:
    long_u = "内测用户" + "Z" * 500
    long_a = "内测助手" + "W" * 500
    tc = TurnContext(session_id="sid2", turn_index=1, user_message=long_u, assistant_reply=long_a)
    tr = RuntimeObservationAdapter().trace_from_turn(turn_context=tc)
    internal = RuntimeObservationAdapter().view_from_trace(tr, RedactionLevel.INTERNAL)
    ex = internal.sections.get("turn_excerpts_internal") or {}
    ue = str(ex.get("user_message_excerpt_truncated") or "")
    ae = str(ex.get("assistant_reply_excerpt_truncated") or "")
    assert len(ue) <= 125
    assert len(ae) <= 125
    assert long_u not in json.dumps(internal.model_dump(mode="json"))
    json.dumps(internal.model_dump(mode="json"))


def test_all_none_still_produces_trace_and_view() -> None:
    ad = RuntimeObservationAdapter()
    tr = ad.trace_from_turn()
    assert tr.root_span_id
    vw = ad.view_from_trace(tr)
    assert vw.source_trace_id == tr.trace_id
    json.dumps(tr.model_dump(mode="json"))
    json.dumps(vw.model_dump(mode="json"))


def test_adapter_does_not_mutate_runtime_result_objects() -> None:
    brief = _brief(memory_ids=["m1"])
    before = RuntimeBeforeReplyResult(brief=brief, skipped_reasons=["r1"], tick_skipped=True)
    after = RuntimeAfterReplyResult(turn_count=2, seeds=[], tick_result=None)
    tick = GardenTickResult(opened_court_case_ids=[], skipped_reasons=["noop"])
    tc = TurnContext(session_id="immut", turn_index=0, user_message="hi")
    cmd = RuntimeCommandResult(command=None, session_id="immut", state=RuntimeState.CLOSED, handled=False)
    fb = RuntimeFeedback(session_id="immut", summary="s")
    snap_b = before.model_dump()
    snap_a = after.model_dump()
    snap_t = tick.model_dump()
    snap_tc = tc.model_dump()
    snap_c = cmd.model_dump()
    snap_f = fb.model_dump()
    RuntimeObservationAdapter().trace_from_turn(
        before_result=before,
        after_result=after,
        tick_result=tick,
        turn_context=tc,
        command_result=cmd,
        feedback=fb,
    )
    assert before.model_dump() == snap_b
    assert after.model_dump() == snap_a
    assert tick.model_dump() == snap_t
    assert tc.model_dump() == snap_tc
    assert cmd.model_dump() == snap_c
    assert fb.model_dump() == snap_f


def test_exports_runtime_adapter_from_observatory_package() -> None:
    from memory_garden.observatory import RuntimeObservationAdapter as R

    assert R is RuntimeObservationAdapter


@pytest.mark.parametrize("level", [RedactionLevel.PUBLIC, RedactionLevel.SAFE, RedactionLevel.INTERNAL])
def test_trace_and_views_json_dump_always(level: RedactionLevel) -> None:
    tr = RuntimeObservationAdapter().trace_from_turn(
        session=GardenSession(state=RuntimeState.OPEN),
        turn_context=TurnContext(session_id="j", turn_index=0, user_message="."),
    )
    vw = RuntimeObservationAdapter().view_from_trace(tr, level)
    json.dumps(tr.model_dump(mode="json"))
    json.dumps(vw.model_dump(mode="json"))


def test_command_result_accepts_plain_dict_via_validate() -> None:
    payload = {"command": "close", "session_id": "p", "state": "closing", "handled": True, "message": "关"}
    tr = RuntimeObservationAdapter().trace_from_turn(command_result=payload)
    assert any(e.name == "command_handled" for e in tr.events)


def test_after_reply_skipped_when_closed_semantic() -> None:
    # 使用 CLOSED + 零种子 → 语义跳过 after_reply（非采摘成功路径）
    sess = GardenSession(session_id="acd", state=RuntimeState.CLOSED)
    after = RuntimeAfterReplyResult(turn_count=3, seeds=[])
    tr = RuntimeObservationAdapter().trace_from_turn(session=sess, after_result=after)
    assert any(e.name == "after_reply_skipped" and e.attributes.get("after_reply_semantic_skip") for e in tr.events)
