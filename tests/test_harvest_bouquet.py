"""第三层 Stage 3E：GardenBouquetBuilder。"""

import inspect
import json

from memory_garden.harvest.bouquet import GardenBouquetBuilder
from memory_garden.harvest.models import (
    BouquetSlot,
    HarvestPolicyDecision,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.ranking import HarvestRankOutcome
from memory_garden.runtime_config import BouquetPlacementConfig


def _sm(
    lifecycle: str = "sprout",
    thorns: str = "刺",
) -> dict:
    return {"lifecycle": lifecycle, "thorns": thorns, "importance": 0.5, "confidence": 0.5}


def _c(cid: str, mid: str, excerpt: str = "", lifecycle: str = "sprout", thorns: str = "刺") -> MemoryCandidate:
    return MemoryCandidate(
        candidate_id=cid,
        memory_id=mid,
        excerpt=excerpt,
        metadata={"source_memory": _sm(lifecycle=lifecycle, thorns=thorns)},
    )


def _s(cid: str, rel: float, notes: list | None = None) -> HarvestScore:
    return HarvestScore(candidate_id=cid, relevance=rel, notes=list(notes or []))


def _outcome(rank: list[MemoryCandidate], *, reject: list[str] | None = None) -> HarvestRankOutcome:
    return HarvestRankOutcome(
        ranked_candidates=rank,
        policy_decision=HarvestPolicyDecision(
            allow_candidate_ids=[c.candidate_id for c in rank],
            reject_candidate_ids=list(reject or []),
            reasons=[],
        ),
    )


def test_high_scores_go_primary() -> None:
    q = HarvestQuery(raw_user_text="hi")
    a, b = _c("ca", "ma"), _c("cb", "mb")
    out = _outcome([a, b])
    scores = [_s("ca", 0.92), _s("cb", 0.88)]
    bouq = GardenBouquetBuilder().build(q, out, scores)
    prim = bouq.slots[BouquetSlot.PRIMARY]
    assert prim == ["ca", "cb"]


def test_moderate_goes_support_not_primary() -> None:
    q = HarvestQuery(raw_user_text="hi")
    a, low = _c("top", "m1"), _c("mid", "m2")
    rk = _outcome([a, low])
    scores = [_s("top", 0.95), _s("mid", 0.22)]
    bouq = GardenBouquetBuilder().build(q, rk, scores)
    assert "top" in bouq.slots[BouquetSlot.PRIMARY]
    assert bouq.slots[BouquetSlot.CORROBORATION] == ["mid"]


def test_greenhouse_not_primary() -> None:
    q = HarvestQuery(raw_user_text="hi")
    g = _c("gh", "mg", lifecycle="greenhouse")
    rk = _outcome([g])
    scores = [_s("gh", 0.99)]
    bouq = GardenBouquetBuilder().build(q, rk, scores)
    assert bouq.slots[BouquetSlot.PRIMARY] == []
    assert "gh" in bouq.slots[BouquetSlot.GUARDRAIL]


def test_pruned_prefers_guardrail_not_primary() -> None:
    q = HarvestQuery(raw_user_text="x")
    p = _c("pr", "mp", lifecycle="pruned")
    rk = _outcome([p])
    scores = [_s("pr", 0.9)]
    bouq = GardenBouquetBuilder().build(q, rk, scores)
    assert p.candidate_id in bouq.slots[BouquetSlot.GUARDRAIL]


def test_composted_goes_guardrail() -> None:
    q = HarvestQuery(raw_user_text="cp")
    c = _c("cp", "mcp", lifecycle="composted")
    rk = _outcome([c])
    bouq = GardenBouquetBuilder().build(q, rk, scores=[_s("cp", 0.88)])
    assert "cp" in bouq.slots[BouquetSlot.GUARDRAIL]


def test_rejected_not_in_bouquet() -> None:
    q = HarvestQuery(raw_user_text=".")
    ok, bad = _c("ok", "mk"), _c("bad", "mb")
    rk = _outcome([bad, ok], reject=["bad"])
    scores = [_s("bad", 0.99), _s("ok", 0.5)]
    bouq = GardenBouquetBuilder().build(q, rk, scores)
    all_ids = [cid for lst in bouq.slots.values() for cid in lst]
    assert "bad" not in all_ids
    assert "ok" in all_ids


def test_max_candidates_limits_placements() -> None:
    q = HarvestQuery(raw_user_text="-")
    cands = [_c(str(i), f"m{i}") for i in range(4)]
    rk = _outcome(cands)
    scores = [_s(str(i), 0.4 + i * 0.01) for i in range(4)]
    bouq = GardenBouquetBuilder().build(
        q,
        rk,
        scores,
        HarvestBudgetPolicy(max_candidates=1),
    )
    placed = sum(len(v) for v in bouq.slots.values())
    assert placed == 1
    assert len(bouq.metadata.get("excluded", [])) == 3


def test_missing_score_not_primary_slot() -> None:
    q = HarvestQuery(raw_user_text="!")
    lone = _c("no_sc", "mns")
    rk = _outcome([lone])
    bouq = GardenBouquetBuilder().build(q, rk, scores=[])
    assert bouq.slots[BouquetSlot.PRIMARY] == []
    assert "no_sc" in bouq.slots[BouquetSlot.GUARDRAIL]


def test_missing_score_with_normal_lifecycle_is_guardrail_not_crash() -> None:
    q = HarvestQuery(raw_user_text="!")
    lone = _c("normal_no_score", "mns", lifecycle="bloom")
    rk = _outcome([lone])

    bouq = GardenBouquetBuilder().build(q, rk, scores=[])

    assert "normal_no_score" in bouq.slots[BouquetSlot.GUARDRAIL]


def test_metadata_traces_ids() -> None:
    q = HarvestQuery(raw_user_text="!")
    cand = _c("c7", "m7")
    bouq = GardenBouquetBuilder().build(
        q,
        _outcome([cand]),
        [_s("c7", 0.9)],
        None,
    )
    placements = bouq.metadata.get("placements", [])
    assert placements and placements[0]["candidate_id"] == "c7"
    assert placements[0]["memory_id"] == "m7"


def test_no_long_concatenated_body_in_bouquet_dump() -> None:
    q = HarvestQuery(raw_user_text="!")
    cand = _c("long", "mL", excerpt="x" * 500)
    bouq = GardenBouquetBuilder().build(q, _outcome([cand]), [_s("long", 0.4)])
    dumped = bouq.model_dump(mode="json")
    blob = json.dumps(dumped)
    assert "xxx" not in blob or blob.count("x") < 200


def test_builder_preserves_upstream_objects() -> None:
    q = HarvestQuery(raw_user_text="z")
    c = _c("k", "mk")
    s = [_s("k", 0.66)]
    out = _outcome([c])
    b = GardenBouquetBuilder()
    cb, sb, ob = id(c), id(s[0]), id(out)
    b.build(q, out, s, None)
    assert id(c) == cb and id(s[0]) == sb and id(out) == ob


def test_bouquet_json_roundtrip() -> None:
    q = HarvestQuery(raw_user_text="-")
    c = _c("j", "mj")
    bouq = GardenBouquetBuilder().build(q, _outcome([c]), [_s("j", 0.85)])
    raw = bouq.model_dump(mode="json")
    json.dumps(raw)


def test_bouquet_module_no_ml_patterns() -> None:
    import memory_garden.harvest.bouquet as b

    txt = inspect.getsource(b).lower()
    for bad in ("openai", "anthropic", "embed", "vector", "faiss", "llm"):
        assert bad not in txt


def test_token_soft_budget_excludes_overflow() -> None:
    q = HarvestQuery(raw_user_text="tok")
    a = _c("a", "ma", excerpt="eeee")
    long_ex = _c("b", "mb", excerpt="word " * 200)
    rk = _outcome([a, long_ex])
    scores = [_s("a", 0.92), _s("b", 0.91)]
    pol = HarvestBudgetPolicy(max_candidates=16, token_budget_soft=60)
    bouq = GardenBouquetBuilder().build(q, rk, scores, pol)
    ex = bouq.metadata.get("excluded", [])
    reasons = str(ex)
    assert "excluded_by_budget_token_soft" in reasons


def test_bouquet_uses_injected_primary_threshold_and_core_quota() -> None:
    q = HarvestQuery(raw_user_text="cfg")
    a, b = _c("a", "ma"), _c("b", "mb")
    rk = _outcome([a, b])
    scores = [_s("a", 0.8), _s("b", 0.7)]
    builder = GardenBouquetBuilder(
        BouquetPlacementConfig(core_pool_min_relevance=0.75, core_quota=1)
    )

    bouq = builder.build(q, rk, scores)

    assert bouq.slots[BouquetSlot.PRIMARY] == ["a"]
    assert bouq.slots[BouquetSlot.CORROBORATION] == ["b"]

