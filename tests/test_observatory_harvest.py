"""第四层 Stage 4B：HarvestObservationAdapter。"""

import inspect
import json
from datetime import datetime, timezone

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
from memory_garden.observatory.models import RedactionLevel


def _minimal_brief() -> HarvestGardenBrief:
    return HarvestGardenBrief(
        intent="围绕用户表达的摘录式简报（非断言）。上下文摘录：测试",
        use="如与当前话题相关，可参考以下记忆标识：m1。**不得**将此视为对用户状态的必然结论。",
        avoid="无单独 GUARDRAIL 条目；仍请避免对用户意图作过度断言。",
        style="语气中性简短。",
        safety="安全：不断言用户偏好或事实确定性。",
        nudge="复核提示：请将简报仅作编排线索。",
        source_memory_ids=["m1"],
        token_estimate=42,
        mode=BriefMode.TEMPLATE,
    )


def _rich_harvest_trace() -> HarvestTrace:
    q = HarvestQuery(raw_user_text="深色模式护眼", session_id="sess-1", turn_index=0)
    c = MemoryCandidate(
        candidate_id="cand_a",
        memory_id="m1",
        excerpt="title:短摘录",
        match_type=CandidateMatchType.LEXICAL_STUB,
        metadata={
            "source_memory": {
                "ZZZ_HUGE_OBSERVATORY_LEAK_999": "X" * 8000,
                "lifecycle": "sprout",
                "thorns": "短",
            }
        },
    )
    sc = HarvestScore(candidate_id="cand_a", relevance=0.8, policy_boost=0.0)
    pol = HarvestPolicyDecision(
        allow_candidate_ids=["cand_a"],
        reject_candidate_ids=[],
        capped_total=8,
        reasons=["ok"],
    )
    bq = GardenBouquet(
        slots={
            BouquetSlot.PRIMARY: ["cand_a"],
            BouquetSlot.CORROBORATION: [],
            BouquetSlot.GUARDRAIL: [],
        },
        metadata={
            "placements": [
                {"candidate_id": "cand_a", "memory_id": "m1", "slot": "primary", "reason": "test"},
            ],
        },
    )
    br = _minimal_brief()
    return HarvestTrace(
        query=q,
        candidates=[c],
        scores=[sc],
        policy_decisions=[pol],
        bouquet=bq,
        brief=br,
        finalized_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
    )


def test_harvest_trace_converts_to_observation_trace() -> None:
    ht = _rich_harvest_trace()
    otr = HarvestObservationAdapter().trace_from_harvest(ht)
    assert otr.root_span_id
    assert any(s.name == "harvest_pipeline" and s.parent_span_id is None for s in otr.spans)


def test_trace_has_root_and_child_spans() -> None:
    otr = HarvestObservationAdapter().trace_from_harvest(_rich_harvest_trace())
    names = {s.name for s in otr.spans}
    assert "harvest_pipeline" in names
    for step in (
        "collect_candidates",
        "score_candidates",
        "rank_candidates",
        "build_bouquet",
        "write_brief",
    ):
        assert step in names


def test_trace_events_include_key_milestones() -> None:
    otr = HarvestObservationAdapter().trace_from_harvest(_rich_harvest_trace())
    enames = {e.name for e in otr.events}
    assert enames >= {
        "harvest_started",
        "candidates_collected",
        "scores_created",
        "bouquet_built",
        "brief_written",
        "harvest_completed",
    }


def test_source_refs_and_links_for_memory_ids() -> None:
    ht = _rich_harvest_trace()
    otr = HarvestObservationAdapter().trace_from_harvest(ht)
    assert any(r.harvest_trace_id == ht.trace_id for r in otr.source_refs)
    assert any(r.memory_id == "m1" for r in otr.source_refs)
    rels = {lk.relation for lk in otr.links}
    assert "candidate_to_memory" in rels
    assert "brief_to_memory" in rels
    assert "bouquet_to_candidate" in rels


def test_view_from_trace_builds_sections() -> None:
    otr = HarvestObservationAdapter().trace_from_harvest(_rich_harvest_trace())
    vw = HarvestObservationAdapter().view_from_trace(otr, RedactionLevel.PUBLIC)
    assert vw.source_trace_id == otr.trace_id
    assert set(vw.sections.keys()) >= {"pipeline", "candidates", "bouquet", "brief", "safety"}
    assert vw.sections["brief"].get("source_memory_ids") == ["m1"]


def test_public_view_excludes_huge_source_memory_blob() -> None:
    ht = _rich_harvest_trace()
    otr = HarvestObservationAdapter().trace_from_harvest(ht)
    pub = HarvestObservationAdapter().view_from_trace(otr, RedactionLevel.PUBLIC)
    blob = json.dumps(pub.model_dump(mode="json"))
    assert "ZZZ_HUGE_OBSERVATORY_LEAK_999" not in blob


def test_internal_view_serializable() -> None:
    otr = HarvestObservationAdapter().trace_from_harvest(_rich_harvest_trace())
    internal = HarvestObservationAdapter().view_from_trace(otr, RedactionLevel.INTERNAL)
    json.dumps(internal.model_dump(mode="json"))


def test_empty_candidates_and_brief_ids_safe() -> None:
    q = HarvestQuery(raw_user_text="空")
    ht = HarvestTrace(query=q, candidates=[], scores=[], policy_decisions=[], bouquet=None, brief=None)
    otr = HarvestObservationAdapter().trace_from_harvest(ht)
    vw = HarvestObservationAdapter().view_from_trace(otr, RedactionLevel.SAFE)
    assert vw.sections["candidates"]["count"] == 0
    assert vw.sections["brief"].get("source_memory_ids") == []


def test_adapter_does_not_mutate_harvest_trace() -> None:
    ht = _rich_harvest_trace()
    snap = ht.model_dump()
    hid = id(ht)
    HarvestObservationAdapter().trace_from_harvest(ht)
    assert id(ht) == hid
    assert ht.model_dump() == snap


def test_outputs_json_roundtrip() -> None:
    otr = HarvestObservationAdapter().trace_from_harvest(_rich_harvest_trace())
    json.dumps(otr.model_dump(mode="json"))
    vw = HarvestObservationAdapter().view_from_trace(otr)
    json.dumps(vw.model_dump(mode="json"))


def test_adapter_module_has_no_ml_or_storage() -> None:
    import memory_garden.observatory.harvest as m

    src = inspect.getsource(m).lower()
    for bad in ("openai", "anthropic", "embedding", "rerank", "vector", "faiss", "langsmith", "opentelemetry", "sqlite", "repository"):
        assert bad not in src


def test_harvest_observation_includes_retrieval_diagnostics_section() -> None:
    q = HarvestQuery(raw_user_text="深色模式")
    ht = HarvestTrace(
        query=q,
        metadata={
            "retrieval_diagnostics": {
                "total_available": 501,
                "scanned_count": 500,
                "candidate_count": 12,
                "truncated": True,
                "source": "runtime_memory_provider",
                "fallback_reason": "scan_limit_reached",
                "candidate_source": "in_memory",
            }
        },
    )
    otr = HarvestObservationAdapter().trace_from_harvest(ht)
    vw = HarvestObservationAdapter().view_from_trace(otr, RedactionLevel.PUBLIC)
    quality = vw.sections.get("retrieval_quality")
    assert quality is not None
    assert quality["truncated"] is True
    assert quality["scanned_count"] == 500
