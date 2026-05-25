"""第四层 Stage 4C：JournalObservationAdapter。"""

import inspect
import json
from datetime import datetime, timezone

from memory_garden.core.models import (
    GardenEvent,
    GardenEventType,
    GardenObjectType,
)
from memory_garden.observatory.journal import JournalObservationAdapter
from memory_garden.observatory.models import RedactionLevel


def _ev(
    et: GardenEventType,
    ot: GardenObjectType,
    oid: str,
    *,
    summary: str = "短摘要",
    eid: str | None = None,
    md: dict | None = None,
) -> GardenEvent:
    return GardenEvent(
        id=eid or f"gev_{oid}_{et.value}",
        event_type=et,
        object_type=ot,
        object_id=oid,
        summary=summary,
        metadata=dict(md or {}),
        created_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_events_convert_to_observation_trace() -> None:
    adapter = JournalObservationAdapter()
    evs = [
        _ev(GardenEventType.seed_created, GardenObjectType.seed, "s-root", eid="e1"),
    ]
    otr = adapter.trace_from_events(evs, trace_name="unit")
    assert otr.root_span_id
    assert any(s.name == "garden_journal" for s in otr.spans)


def test_phase_child_spans_present() -> None:
    adapter = JournalObservationAdapter()
    otr = adapter.trace_from_events([])
    names = {s.name for s in otr.spans}
    for n in (
        "garden_journal",
        "seed_events",
        "court_events",
        "growth_events",
        "dream_events",
        "runtime_or_other_events",
    ):
        assert n in names


def test_each_garden_event_yields_observation_event() -> None:
    adapter = JournalObservationAdapter()
    evs = [
        _ev(GardenEventType.seed_created, GardenObjectType.seed, "a", eid="g1"),
        _ev(GardenEventType.verdict_made, GardenObjectType.court_case, "c1", eid="g2"),
    ]
    otr = adapter.trace_from_events(evs)
    assert len(otr.events) == 2


def test_type_stats_in_sections_buckets() -> None:
    adapter = JournalObservationAdapter()
    evs = [
        _ev(GardenEventType.seed_created, GardenObjectType.seed, "s1", eid="a"),
        _ev(GardenEventType.verdict_made, GardenObjectType.court_case, "cc1", eid="b"),
        _ev(GardenEventType.memory_planted, GardenObjectType.memory_card, "m1", eid="c"),
        _ev(GardenEventType.dream_completed, GardenObjectType.dream_record, "d1", eid="d"),
    ]
    otr = adapter.trace_from_events(evs)
    vw = adapter.view_from_trace(otr)
    assert vw.sections["seeds"]["count"] == 1
    assert vw.sections["court"]["count"] == 1
    assert vw.sections["growth"]["count"] == 1
    assert vw.sections["dream"]["count"] == 1


def test_metadata_ids_produce_links() -> None:
    adapter = JournalObservationAdapter()
    ev = _ev(
        GardenEventType.memory_planted,
        GardenObjectType.memory_card,
        "m-root",
        eid="link_ev",
        md={
            "seed_id": "s_extra",
            "court_case_id": "cc_extra",
            "dream_record_id": "dr_extra",
            "memory_card_id": "m_extra",
        },
    )
    otr = adapter.trace_from_events([ev])
    rels = {lk.relation for lk in otr.links}
    assert "event_to_seed" in rels
    assert "event_to_case" in rels
    assert "event_to_dream" in rels
    assert "event_to_memory" in rels


def test_public_view_excludes_massive_blob() -> None:
    adapter = JournalObservationAdapter()
    huge = "HUGE_META_XXX_" + ("Z" * 6000)
    ev = _ev(
        GardenEventType.seed_created,
        GardenObjectType.seed,
        "sx",
        eid="bulk",
        summary="正常摘要",
        md={"note": huge},
    )
    otr = adapter.trace_from_events([ev])
    pub = adapter.view_from_trace(otr, RedactionLevel.PUBLIC)
    dumped = json.dumps(pub.model_dump(mode="json"))
    assert "HUGE_META_XXX_" not in dumped


def test_public_view_timeline_has_no_full_summary_field() -> None:
    adapter = JournalObservationAdapter()
    ev = _ev(
        GardenEventType.verdict_made,
        GardenObjectType.court_case,
        "c99",
        eid="tline",
        summary="判决摘要短语",
    )
    otr = adapter.trace_from_events([ev])
    pub = adapter.view_from_trace(otr, RedactionLevel.PUBLIC)
    for row in pub.sections["timeline"]:
        assert "summary_preview" not in row


def test_internal_view_serializable_has_truncated_preview() -> None:
    adapter = JournalObservationAdapter()
    long_sum = "L" + "o" * 500 + "tail"
    ev = _ev(
        GardenEventType.memory_greenhoused,
        GardenObjectType.memory_card,
        "mg1",
        eid="intl",
        summary=long_sum,
    )
    otr = adapter.trace_from_events([ev])
    internal = adapter.view_from_trace(otr, RedactionLevel.INTERNAL)
    sp_row = internal.sections["timeline"][0]["summary_preview"]
    assert isinstance(sp_row, str) and len(sp_row) <= 230


def test_empty_events_stable() -> None:
    adapter = JournalObservationAdapter()
    otr = adapter.trace_from_events([], trace_name="empty")
    vw = adapter.view_from_trace(otr)
    assert vw.sections["timeline"] == []
    assert vw.summary


def test_garden_events_not_mutated() -> None:
    ev = _ev(GardenEventType.dream_completed, GardenObjectType.dream_record, "dr", eid="im")
    snap = ev.model_dump()
    hid = id(ev)
    JournalObservationAdapter().trace_from_events([ev])
    assert id(ev) == hid and ev.model_dump() == snap


def test_outputs_json_roundtrip() -> None:
    adapter = JournalObservationAdapter()
    otr = adapter.trace_from_events([_ev(GardenEventType.seed_created, GardenObjectType.seed, "sx", eid="rt")])
    json.dumps(otr.model_dump(mode="json"))
    vw = adapter.view_from_trace(otr)
    json.dumps(vw.model_dump(mode="json"))


def test_record_object_ids_not_mapped_to_memory_id_source_ref() -> None:
    """堆肥/温室/修剪等记录 id 不得伪装为 MemoryCard.memory_id。"""
    adapter = JournalObservationAdapter()
    rec_id = "compost-record-stable-id-001"
    gh_id = "greenhouse-rec-002"
    pr_id = "pruning-rec-003"
    events = [
        _ev(GardenEventType.memory_composted, GardenObjectType.compost_record, rec_id, eid="e_comp"),
        _ev(GardenEventType.memory_greenhoused, GardenObjectType.greenhouse_record, gh_id, eid="e_gh"),
        _ev(GardenEventType.memory_pruned, GardenObjectType.pruning_record, pr_id, eid="e_pr"),
    ]
    otr = adapter.trace_from_events(events)
    for r in otr.source_refs:
        assert r.memory_id not in (rec_id, gh_id, pr_id)


def test_unmapped_object_refs_traceable_via_event_id_and_attributes() -> None:
    adapter = JournalObservationAdapter()
    oid = "cr-orphan-9"
    ev = _ev(GardenEventType.memory_composted, GardenObjectType.compost_record, oid, eid="trace_unmapped")
    otr = adapter.trace_from_events([ev])
    jm = otr.metadata.get("journal", {})
    um = jm.get("unmapped_object_refs", [])
    assert any(
        x.get("garden_event_id") == "trace_unmapped"
        and x.get("object_type") == GardenObjectType.compost_record.value
        and x.get("object_id") == oid
        for x in um
    )
    assert any(r.event_id == "trace_unmapped" for r in otr.source_refs)
    assert otr.events[0].attributes["object_id"] == oid


def test_internal_view_serializable_with_unmapped_record() -> None:
    adapter = JournalObservationAdapter()
    ev = _ev(
        GardenEventType.memory_greenhoused,
        GardenObjectType.greenhouse_record,
        "rec-only",
        eid="int_u",
        summary="概要",
    )
    otr = adapter.trace_from_events([ev])
    internal = adapter.view_from_trace(otr, RedactionLevel.INTERNAL)
    json.dumps(internal.model_dump(mode="json"))


def test_metadata_memory_id_still_links_for_record_object() -> None:
    adapter = JournalObservationAdapter()
    real_mem = "card-m-true-88"
    oid = "greenhouse-record-surface-only"
    noise = "W" * 8000
    ev = _ev(
        GardenEventType.memory_greenhoused,
        GardenObjectType.greenhouse_record,
        oid,
        eid="lnk_meta",
        md={"memory_card_id": real_mem, "noise_note": noise},
    )
    otr = adapter.trace_from_events([ev])
    assert any(lk.relation == "event_to_memory" and lk.target_ref and lk.target_ref.memory_id == real_mem for lk in otr.links)
    pub = adapter.view_from_trace(otr, RedactionLevel.PUBLIC)
    dumped = json.dumps(pub.model_dump(mode="json"))
    assert noise not in dumped


def test_journal_adapter_source_has_no_ml_or_db() -> None:
    import memory_garden.observatory.journal as jmod

    src = inspect.getsource(jmod).lower()
    for bad in (
        "openai",
        "anthropic",
        "embedding",
        "rerank",
        "vector",
        "faiss",
        "langsmith",
        "opentelemetry",
        "sqlite",
        "recent_events",
    ):
        assert bad not in src
    assert "memory_garden_core" not in src  # Core 门面未引用
