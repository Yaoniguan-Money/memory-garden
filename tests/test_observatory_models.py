"""第四层 Stage 4A：Observatory 模型 JSON 与构造。"""

import json
from datetime import datetime, timezone

from memory_garden.observatory.models import (
    ObservationEvent,
    ObservationKind,
    ObservationLink,
    ObservationSourceRef,
    ObservationSpan,
    ObservationStatus,
    ObservationTrace,
    ObservationView,
    RedactionLevel,
)


def _roundtrip(model_cls, instance):
    raw = instance.model_dump(mode="json")
    dumped = json.dumps(raw)
    back = json.loads(dumped)
    return model_cls.model_validate(back)


def test_source_ref_json_roundtrip() -> None:
    ref = ObservationSourceRef(
        seed_id="s1",
        court_case_id=None,
        memory_id="m9",
        dream_record_id="d2",
        harvest_trace_id="htr_abc",
        event_id=None,
    )
    again = _roundtrip(ObservationSourceRef, ref)
    assert again.seed_id == "s1" and again.memory_id == "m9"


def test_span_parent_and_roundtrip() -> None:
    parent = ObservationSpan(name="root", span_id="p-fixed", parent_span_id=None)
    child = ObservationSpan(name="child", parent_span_id=parent.span_id, attributes={"k": 1})
    again = _roundtrip(ObservationSpan, child)
    assert again.parent_span_id == "p-fixed"
    assert again.attributes["k"] == 1


def test_event_attributes_roundtrip() -> None:
    ev = ObservationEvent(
        kind=ObservationKind.HARVEST,
        name="collected",
        attributes={"candidate_count": 3, "nested": {"a": True}},
    )
    again = _roundtrip(ObservationEvent, ev)
    assert again.attributes["candidate_count"] == 3
    assert again.kind == ObservationKind.HARVEST


def test_link_refs_and_relation() -> None:
    lk = ObservationLink(
        relation="derived_from",
        source_ref=ObservationSourceRef(seed_id="seed-x"),
        target_ref=ObservationSourceRef(memory_id="mem-y"),
    )
    again = _roundtrip(ObservationLink, lk)
    assert again.relation == "derived_from"
    assert again.source_ref and again.source_ref.seed_id == "seed-x"
    assert again.target_ref and again.target_ref.memory_id == "mem-y"


def test_trace_aggregates_roundtrip() -> None:
    t0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    sp = ObservationSpan(name="sp1", started_at=t0)
    ev = ObservationEvent(name="tick", occurred_at=t0)
    lk = ObservationLink(relation="refs", source_ref=ObservationSourceRef(event_id="e1"))
    ref = ObservationSourceRef(harvest_trace_id="ht_01")
    tr = ObservationTrace(
        title="一次编排",
        root_span_id=sp.span_id,
        spans=[sp],
        events=[ev],
        links=[lk],
        source_refs=[ref],
        metadata={"tier": "4a"},
    )
    again = _roundtrip(ObservationTrace, tr)
    assert len(again.spans) == 1 and len(again.events) == 1
    assert again.links[0].source_ref and again.links[0].source_ref.event_id == "e1"
    assert again.source_refs[0].harvest_trace_id == "ht_01"


def test_view_default_redaction_and_sections() -> None:
    vw = ObservationView(summary="简述", sections={"bullets": ["a"]}, source_trace_id="otr_z")
    assert vw.redaction_level == RedactionLevel.PUBLIC
    again = _roundtrip(ObservationView, vw)
    assert again.redaction_level == RedactionLevel.PUBLIC
    assert again.sections["bullets"] == ["a"]
    assert again.source_trace_id == "otr_z"


def test_redaction_safe_is_valid_roundtrip() -> None:
    vw = ObservationView(summary="对内", redaction_level=RedactionLevel.SAFE)
    again = _roundtrip(ObservationView, vw)
    assert again.redaction_level == RedactionLevel.SAFE


def test_source_refs_need_not_resolve_to_real_entities() -> None:
    ghost = ObservationSourceRef(seed_id="ghost-seed-not-resolved")
    tr = ObservationTrace(source_refs=[ghost])
    dumped = json.dumps(tr.model_dump(mode="json"))
    assert "ghost-seed-not-resolved" in dumped


def test_model_fields_exclude_external_sdk_objects() -> None:
    for cls in (
        ObservationTrace,
        ObservationSpan,
        ObservationEvent,
        ObservationLink,
        ObservationView,
        ObservationSourceRef,
    ):
        for fld in cls.model_fields.values():
            blob = repr(fld.annotation).lower()
            assert "langsmith" not in blob
            assert "opentelemetry" not in blob
            assert "otel" not in blob


def test_enums_roundtrip_inside_models() -> None:
    sp = ObservationSpan(status=ObservationStatus.PARTIAL, kind=ObservationKind.GROWTH)
    again = _roundtrip(ObservationSpan, sp)
    assert again.status == ObservationStatus.PARTIAL
    assert again.kind == ObservationKind.GROWTH
