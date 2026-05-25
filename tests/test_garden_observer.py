"""第四层 Stage 4E：GardenObserver 门面。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from memory_garden.core.models import GardenEvent, GardenEventType, GardenObjectType
from memory_garden.harvest.models import (
    BouquetSlot,
    BriefMode,
    CandidateMatchType,
    GardenBouquet,
    HarvestGardenBrief,
    HarvestPolicyDecision,
    HarvestQuery,
    HarvestScore,
    HarvestTrace,
    MemoryCandidate,
)
from memory_garden.observatory.harvest import HarvestObservationAdapter
from memory_garden.observatory.models import ObservationTrace, ObservationView, RedactionLevel
from memory_garden.observatory.observer import GardenObserver
from memory_garden.runtime.hooks import RuntimeBeforeReplyResult
from memory_garden.runtime.session import GardenBrief, TurnContext


def _minimal_harvest_brief() -> HarvestGardenBrief:
    return HarvestGardenBrief(
        intent="观测门面测试用的简报意图字段",
        use="用途同上",
        avoid="规避同上",
        style="风格同上",
        safety="安全同上",
        nudge="提示同上",
        source_memory_ids=["m1"],
        token_estimate=10,
        mode=BriefMode.TEMPLATE,
    )


def _minimal_harvest_trace() -> HarvestTrace:
    q = HarvestQuery(raw_user_text="测", session_id="s-obs", turn_index=0)
    c = MemoryCandidate(
        candidate_id="c1",
        memory_id="m1",
        excerpt="短",
        match_type=CandidateMatchType.LEXICAL_STUB,
        metadata={},
    )
    pol = HarvestPolicyDecision(allow_candidate_ids=["c1"], reject_candidate_ids=[], capped_total=4, reasons=["ok"])
    bq = GardenBouquet(
        slots={BouquetSlot.PRIMARY: ["c1"], BouquetSlot.CORROBORATION: [], BouquetSlot.GUARDRAIL: []},
        metadata={"placements": []},
    )
    return HarvestTrace(
        query=q,
        candidates=[c],
        scores=[HarvestScore(candidate_id="c1", relevance=0.5, policy_boost=0.0)],
        policy_decisions=[pol],
        bouquet=bq,
        brief=_minimal_harvest_brief(),
        finalized_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
    )


class _RecordingHarvestAdapter(HarvestObservationAdapter):
    """记录 trace → view 调用顺序与脱敏参数，委托父类实现。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str | tuple[str, RedactionLevel]] = []

    def trace_from_harvest(self, harvest_trace: HarvestTrace) -> ObservationTrace:  # type: ignore[override]
        self.calls.append("trace_from_harvest")
        return super().trace_from_harvest(harvest_trace)

    def view_from_trace(  # type: ignore[override]
        self,
        trace: ObservationTrace,
        redaction_level: RedactionLevel = RedactionLevel.PUBLIC,
    ) -> ObservationView:
        self.calls.append(("view_from_trace", redaction_level))
        return super().view_from_trace(trace, redaction_level=redaction_level)


def test_observe_harvest_returns_observation_view() -> None:
    go = GardenObserver()
    v = go.observe_harvest(_minimal_harvest_trace())
    assert isinstance(v, ObservationView)
    json.dumps(v.model_dump(mode="json"))


def test_trace_harvest_returns_observation_trace() -> None:
    go = GardenObserver()
    t = go.trace_harvest(_minimal_harvest_trace())
    assert isinstance(t, ObservationTrace)
    json.dumps(t.model_dump(mode="json"))


def test_observe_journal_empty_list_ok() -> None:
    go = GardenObserver()
    v = go.observe_journal([])
    assert isinstance(v, ObservationView)
    json.dumps(v.model_dump(mode="json"))


def test_observe_runtime_turn_no_args_ok() -> None:
    go = GardenObserver()
    v = go.observe_runtime_turn()
    assert isinstance(v, ObservationView)
    json.dumps(v.model_dump(mode="json"))


def test_redaction_level_internal_passed_to_view() -> None:
    rec = _RecordingHarvestAdapter()
    go = GardenObserver(harvest_adapter=rec)
    go.observe_harvest(_minimal_harvest_trace(), redaction_level=RedactionLevel.INTERNAL)
    assert rec.calls == ["trace_from_harvest", ("view_from_trace", RedactionLevel.INTERNAL)]


def test_facade_call_order_trace_then_view() -> None:
    rec = _RecordingHarvestAdapter()
    go = GardenObserver(harvest_adapter=rec)
    go.observe_harvest(_minimal_harvest_trace())
    assert rec.calls[0] == "trace_from_harvest"
    assert rec.calls[1][0] == "view_from_trace"


def test_inputs_not_mutated() -> None:
    ht = _minimal_harvest_trace()
    snap_h = ht.model_dump()
    ev = GardenEvent(
        event_type=GardenEventType.seed_created,
        object_type=GardenObjectType.seed,
        object_id="seed-1",
        summary="观测输入不变更测试",
    )
    snap_e = ev.model_dump()
    tc = TurnContext(session_id="immut-obs", turn_index=0, user_message="hello")
    snap_tc = tc.model_dump()
    br = RuntimeBeforeReplyResult(
        brief=GardenBrief(
            intent="意",
            use="用",
            avoid="避",
            style="风",
            safety="安",
            nudge="提",
            source_memory_ids=[],
        ),
        skipped_reasons=[],
    )
    snap_br = br.model_dump()

    go = GardenObserver()
    go.observe_harvest(ht)
    go.observe_journal([ev])
    go.observe_runtime_turn(turn_context=tc, before_result=br)

    assert ht.model_dump() == snap_h
    assert ev.model_dump() == snap_e
    assert tc.model_dump() == snap_tc
    assert br.model_dump() == snap_br


def test_outputs_json_serializable() -> None:
    go = GardenObserver()
    for obj in (
        go.trace_harvest(_minimal_harvest_trace()),
        go.observe_harvest(_minimal_harvest_trace()),
        go.trace_journal([], trace_name="custom_j"),
        go.observe_journal([]),
        go.trace_runtime_turn(),
        go.observe_runtime_turn(),
    ):
        json.dumps(obj.model_dump(mode="json"))


def test_observer_module_has_no_sqlite_reference() -> None:
    src = Path(__file__).resolve().parent.parent / "memory_garden" / "observatory" / "observer.py"
    text = src.read_text(encoding="utf-8").lower()
    assert "sqlite" not in text


def test_package_exports_garden_observer() -> None:
    from memory_garden.observatory import GardenObserver as G

    assert G is GardenObserver
