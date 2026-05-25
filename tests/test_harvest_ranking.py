"""第三层 Stage 3D：RuleBasedHarvestRanker。"""

import inspect
import json

from memory_garden.harvest.models import HarvestQuery, HarvestScore, MemoryCandidate
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.ranking import HarvestRankOutcome, RuleBasedHarvestRanker


def _c(cid: str) -> MemoryCandidate:
    return MemoryCandidate(candidate_id=cid, memory_id=f"m-{cid}", metadata={})


def _s(cid: str, rel: float, policy_boost: float = 0.0, **kw) -> HarvestScore:
    return HarvestScore(
        candidate_id=cid,
        relevance=rel,
        recency=kw.get("recency", 0.5),
        policy_boost=policy_boost,
        notes=[],
    )


def test_higher_relevance_first() -> None:
    q = HarvestQuery(raw_user_text="x")
    c1, c2 = _c("a"), _c("b")
    out = RuleBasedHarvestRanker().rank(
        q,
        [c1, c2],
        [_s("a", 0.2), _s("b", 0.92)],
        policy=None,
    )
    ids = [c.candidate_id for c in out.ranked_candidates]
    assert ids == ["b", "a"]


def test_stable_when_relevance_equal() -> None:
    q = HarvestQuery(raw_user_text="x")
    c1, c2, c3 = _c("x1"), _c("x2"), _c("x3")
    s = 0.55
    out = RuleBasedHarvestRanker().rank(
        q,
        [c1, c2, c3],
        [
            _s("x1", s, policy_boost=-0.1),
            _s("x2", s, policy_boost=-0.1),
            _s("x3", s, policy_boost=-0.1),
        ],
        policy=None,
    )
    assert [c.candidate_id for c in out.ranked_candidates] == ["x1", "x2", "x3"]


def test_policy_boost_tiebreak_not_overriding_relevance() -> None:
    q = HarvestQuery(raw_user_text="")
    c1, c2 = _c("p1"), _c("p2")
    out = RuleBasedHarvestRanker().rank(
        q,
        [c1, c2],
        [_s("p1", 0.6, policy_boost=0.0), _s("p2", 0.61, policy_boost=-0.99)],
        policy=None,
    )
    assert out.ranked_candidates[0].candidate_id == "p2"


def test_missing_score_goes_last() -> None:
    q = HarvestQuery(raw_user_text="")
    ca, cb, cc = _c("ok"), _c("lost"), _c("ok2")
    out = RuleBasedHarvestRanker().rank(
        q,
        [ca, cb, cc],
        [_s("ok", 0.1), _s("ok2", 0.5)],
        policy=None,
    )
    assert out.ranked_candidates[-1].candidate_id == "lost"
    blob = ";".join(out.policy_decision.reasons)
    assert "missing_score:candidate_id=lost" in blob


def test_max_candidates_truncates_trailing_low_scores_not_promoted() -> None:
    """低分不会因 ranker「补偿」前移；裁剪仅保留前缀。"""
    q = HarvestQuery(raw_user_text="")
    cand = [_c(str(i)) for i in range(5)]
    scores = [_s(str(i), 0.1 * (i + 1)) for i in range(5)]
    pol = HarvestBudgetPolicy(max_candidates=2)
    out = RuleBasedHarvestRanker().rank(q, cand, scores, policy=pol)
    assert len(out.ranked_candidates) == 2
    ids = [c.candidate_id for c in out.ranked_candidates]
    assert ids == ["4", "3"]
    assert "ranking_cap_applied:max_candidates=2" in " ".join(out.policy_decision.reasons)


def test_recency_breaks_tie_when_relevance_equal() -> None:
    q = HarvestQuery(raw_user_text="x")
    c1, c2 = _c("r1"), _c("r2")
    out = RuleBasedHarvestRanker().rank(
        q,
        [c1, c2],
        [_s("r1", 0.72, recency=0.4), _s("r2", 0.72, recency=0.9)],
        policy=None,
    )
    assert [c.candidate_id for c in out.ranked_candidates] == ["r2", "r1"]


def test_neutral_recency_same_relevance_stable_order() -> None:
    q = HarvestQuery(raw_user_text="x")
    c1, c2 = _c("r1"), _c("r2")
    out = RuleBasedHarvestRanker().rank(
        q,
        [c1, c2],
        [_s("r1", 0.72, recency=0.5), _s("r2", 0.72, recency=0.5)],
        policy=None,
    )
    assert [c.candidate_id for c in out.ranked_candidates] == ["r1", "r2"]


def test_low_relevance_greenhouse_like_stays_rear() -> None:
    """低 relevance 不因 ranker特例提前（模拟已降权的温室/休眠卡）。"""
    q = HarvestQuery(raw_user_text="")
    good, gh = _c("good"), _c("gh")
    out = RuleBasedHarvestRanker().rank(
        q,
        [gh, good],
        [_s("gh", 0.05), _s("good", 0.88)],
        policy=None,
    )
    assert out.ranked_candidates[0].candidate_id == "good"


def test_ranker_preserves_candidate_object_identity() -> None:
    q = HarvestQuery(raw_user_text="z")
    c = _c("idkeep")
    before = id(c)
    scores = [_s("idkeep", 0.77)]
    out = RuleBasedHarvestRanker().rank(q, [c], scores)
    assert out.ranked_candidates[0] is c
    assert id(out.ranked_candidates[0]) == before


def test_ranker_preserves_score_object_identity() -> None:
    q = HarvestQuery(raw_user_text="")
    c = _c("skeep")
    s_obj = _s("skeep", 0.41)
    sid = id(s_obj)
    RuleBasedHarvestRanker().rank(q, [c], [s_obj])
    assert id(s_obj) == sid


def test_rank_outcome_json_roundtrip() -> None:
    q = HarvestQuery(raw_user_text="j")
    c = _c("j1")
    outcome = RuleBasedHarvestRanker().rank(q, [c], [_s("j1", 0.33)], None)
    raw = outcome.model_dump(mode="json")
    json.dumps(raw)
    o2 = HarvestRankOutcome.model_validate(raw)
    assert o2.ranked_candidates[0].candidate_id == "j1"
    assert o2.policy_decision.allow_candidate_ids == ["j1"]


def test_ranking_module_has_no_ml_stack_strings() -> None:
    import memory_garden.harvest.ranking as rk

    text = inspect.getsource(rk).lower()
    for bad in ("openai", "anthropic", "embed", "vector", "faiss", "chroma", "rerank", "llm"):
        assert bad not in text


def test_reject_lists_non_ranked_under_cap() -> None:
    q = HarvestQuery(raw_user_text="")
    cand = [_c("u0"), _c("u1"), _c("u2")]
    scores = [_s("u0", 1.0), _s("u1", 0.9), _s("u2", 0.8)]
    out = RuleBasedHarvestRanker().rank(q, cand, scores, HarvestBudgetPolicy(max_candidates=1))
    assert out.policy_decision.allow_candidate_ids == ["u0"]
    assert set(out.policy_decision.reject_candidate_ids) == {"u1", "u2"}
