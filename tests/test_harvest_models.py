"""第三层 Stage 3A：Harvest 模型 JSON round-trip 与追溯链占位。"""

import inspect
import json

import pytest
from pydantic import ValidationError

from memory_garden.harvest.models import (
    BouquetSlot,
    BriefMode,
    CandidateMatchType,
    GardenBouquet,
    HarvestGardenBrief,
    HarvestMode,
    HarvestModelCallStub,
    HarvestPolicyDecision,
    HarvestQuery,
    HarvestScore,
    HarvestTrace,
    MemoryCandidate,
    MemoryLens,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.runtime.session import GardenBrief as RuntimeGardenBrief


def _json_roundtrip(model):
    raw = model.model_dump(mode="json")
    dumped = json.dumps(raw, ensure_ascii=False)
    loaded = json.loads(dumped)
    return model.__class__.model_validate(loaded)


def test_memory_lens_roundtrip() -> None:
    m = MemoryLens(name="偏好", facet_keys=["preference"], priority=0.8)
    rt = _json_roundtrip(m)
    assert rt.name == "偏好"
    assert rt.priority == 0.8


def test_harvest_query_roundtrip() -> None:
    lens = MemoryLens(name="事实")
    q = HarvestQuery(
        session_id="s1",
        turn_index=1,
        raw_user_text="  hello  ",
        harvest_mode=HarvestMode.LEXICAL_STUB,
        lenses=[lens],
        metadata={"k": 1},
    )
    rt = _json_roundtrip(q)
    assert rt.harvest_mode == HarvestMode.LEXICAL_STUB
    assert len(rt.lenses) == 1


def test_memory_candidate_and_score_roundtrip() -> None:
    c = MemoryCandidate(memory_id="m-1", excerpt="片段", match_type=CandidateMatchType.PINNED)
    rt_c = _json_roundtrip(c)
    assert rt_c.memory_id == "m-1"
    s = HarvestScore(candidate_id=c.candidate_id, relevance=0.9, notes=["ok"])
    rt_s = _json_roundtrip(s)
    assert rt_s.relevance == 0.9


def test_harvest_policy_decision_roundtrip() -> None:
    d = HarvestPolicyDecision(
        allow_candidate_ids=["a"],
        reject_candidate_ids=["b"],
        capped_total=5,
        reasons=["额度"],
    )
    rt = _json_roundtrip(d)
    assert rt.capped_total == 5


def test_garden_bouquet_roundtrip() -> None:
    b = GardenBouquet(
        slots={
            BouquetSlot.PRIMARY: ["id1"],
            BouquetSlot.CORROBORATION: ["id2"],
        },
    )
    rt = _json_roundtrip(b)
    assert BouquetSlot.PRIMARY in rt.slots


def test_harvest_garden_brief_fields_and_runtime_bridge() -> None:
    hb = HarvestGardenBrief(
        intent="协助",
        use="简洁",
        avoid="编造",
        style="中性",
        safety="保守",
        nudge="需确认",
        source_memory_ids=["m1", "m2"],
        token_estimate=120,
        mode=BriefMode.CURATED,
    )
    rt = _json_roundtrip(hb)
    assert rt.token_estimate == 120
    assert rt.mode == BriefMode.CURATED

    rb = hb.to_runtime_brief()
    assert isinstance(rb, RuntimeGardenBrief)
    assert rb.source_memory_ids == ["m1", "m2"]

    back = HarvestGardenBrief.from_runtime_brief(rb)
    assert back.token_estimate is None
    assert back.mode == BriefMode.TEMPLATE


def test_harvest_garden_brief_empty_field_rejected() -> None:
    with pytest.raises(ValidationError):
        HarvestGardenBrief(
            intent=" ",
            use="u",
            avoid="a",
            style="s",
            safety="sf",
            nudge="n",
        )


def test_harvest_trace_chains_components() -> None:
    lens = MemoryLens(name="默认")
    q = HarvestQuery(session_id="sid", lenses=[lens])
    cand = MemoryCandidate(memory_id="mem-x", excerpt="...")
    scr = HarvestScore(candidate_id=cand.candidate_id, relevance=0.5)
    pol = HarvestPolicyDecision(allow_candidate_ids=[cand.candidate_id])
    bq = GardenBouquet(slots={BouquetSlot.PRIMARY: [cand.candidate_id]})
    br = HarvestGardenBrief(
        intent="i",
        use="u",
        avoid="a",
        style="s",
        safety="sf",
        nudge="n",
        source_memory_ids=["mem-x"],
        token_estimate=90,
        mode=BriefMode.HYBRID,
    )
    call = HarvestModelCallStub(provider_kind="llm", stub_payload={"stub": True})
    tr = HarvestTrace(
        query=q,
        lenses=[lens],
        candidates=[cand],
        scores=[scr],
        policy_decisions=[pol],
        bouquet=bq,
        brief=br,
        model_calls=[call],
        finalized_at=q.created_at,
    )
    rt = _json_roundtrip(tr)
    assert rt.query.query_id == q.query_id
    assert rt.brief is not None
    assert len(rt.model_calls) == 1


def test_harvest_budget_policy_roundtrip() -> None:
    p = HarvestBudgetPolicy(max_candidates=8, token_budget_soft=1000)
    rt = _json_roundtrip(p)
    assert rt.max_candidates == 8
    duplicate = HarvestBudgetPolicy.model_validate(rt.model_dump(mode="json"))
    assert duplicate.max_candidates == 8


def test_provider_modules_have_no_vendor_imports() -> None:
    import memory_garden.harvest.interfaces as iface

    src = inspect.getsource(iface)
    lowered = src.lower()
    assert "openai" not in lowered
    assert "anthropic" not in lowered
    assert "tiktoken" not in lowered
