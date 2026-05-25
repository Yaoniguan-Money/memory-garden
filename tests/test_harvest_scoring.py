"""第三层 Stage 3C：RuleBasedHarvestScorer。"""

import inspect
import json
from datetime import datetime, timezone

import pytest

from memory_garden.harvest.models import HarvestQuery, MemoryCandidate
from memory_garden.harvest.scoring import RuleBasedHarvestScorer
from memory_garden.runtime_config import HarvestPenaltyConfig, HarvestPenaltyTier


def _mem(
    *,
    lifecycle="sprout",
    importance=0.5,
    confidence=0.7,
    thorns="短刺",
) -> dict:
    return {
        "lifecycle": lifecycle,
        "importance": importance,
        "confidence": confidence,
        "thorns": thorns,
    }


def _cand(cid: str, mid: str, **meta) -> MemoryCandidate:
    return MemoryCandidate(candidate_id=cid, memory_id=mid, metadata=meta)


def test_one_score_per_candidate_in_order() -> None:
    q = HarvestQuery(raw_user_text="x")
    cands = [
        _cand("c1", "m1", hit_channels=["lexical_text"], source_memory=_mem()),
        _cand("c2", "m2", hit_channels=["tag_metadata"], source_memory=_mem()),
    ]
    scores = RuleBasedHarvestScorer().score(q, cands)
    assert len(scores) == 2
    assert scores[0].candidate_id == "c1"
    assert scores[1].candidate_id == "c2"


def test_lexical_candidate_scores_above_weak_candidate() -> None:
    q = HarvestQuery(raw_user_text="q")
    base = _mem()
    strong = _cand("c1", "m1", hit_channels=["lexical_text"], source_memory=base)
    weak = _cand("c2", "m2", hit_channels=[], source_memory=base)
    s_strong, s_weak = RuleBasedHarvestScorer().score(q, [strong, weak])
    assert s_strong.relevance > s_weak.relevance


def test_tag_metadata_candidate_scores_above_no_channel_candidate() -> None:
    q = HarvestQuery(raw_user_text="q")
    base = _mem()
    tagged = _cand("a", "m1", hit_channels=["tag_metadata"], source_memory=base)
    plain = _cand("b", "m2", hit_channels=[], source_memory=base)
    st, sp = RuleBasedHarvestScorer().score(q, [tagged, plain])
    assert st.relevance > sp.relevance


def test_more_matched_lenses_boosts_notes_and_score() -> None:
    q = HarvestQuery(raw_user_text="")
    src = _mem()
    low = _cand("x", "m1", hit_channels=["lexical_text"], matched_lenses=[], source_memory=src)
    high = _cand(
        "y",
        "m2",
        hit_channels=["lexical_text"],
        matched_lenses=["l1", "l2", "l3"],
        source_memory=src,
    )
    sl, sh = RuleBasedHarvestScorer().score(q, [low, high])
    assert sh.relevance >= sl.relevance
    nh = "\n".join(sh.notes)
    nl = "\n".join(sl.notes)
    assert "(n=3)" in nh
    assert "(n=0)" in nl or "n=0" in nh.split("matched_lenses=")[-1][:40]


def test_greenhouse_downweighted_and_risk_flag() -> None:
    q = HarvestQuery(raw_user_text="")
    normal = _cand(
        "n",
        "m1",
        hit_channels=["lexical_text"],
        source_memory=_mem(lifecycle="bloom"),
    )
    gh = _cand(
        "g",
        "m2",
        hit_channels=["lexical_text"],
        source_memory=_mem(lifecycle="greenhouse"),
    )
    sn, sg = RuleBasedHarvestScorer().score(q, [normal, gh])
    assert sn.relevance > sg.relevance
    assert any("risk:greenhouse" in n for n in sg.notes)


def test_pruned_composted_downweighted() -> None:
    q = HarvestQuery(raw_user_text="")
    ok = _cand(
        "o",
        "m1",
        hit_channels=["tag_metadata"],
        source_memory=_mem(lifecycle="bloom"),
    )
    pr = _cand(
        "p",
        "m2",
        hit_channels=["tag_metadata"],
        source_memory=_mem(lifecycle="pruned"),
    )
    cp = _cand(
        "c",
        "m3",
        hit_channels=["tag_metadata"],
        source_memory=_mem(lifecycle="composted"),
    )
    s_ok, s_pr, s_cp = RuleBasedHarvestScorer().score(q, [ok, pr, cp])
    assert s_ok.relevance > s_pr.relevance
    assert s_ok.relevance > s_cp.relevance
    assert any("pruned" in n.lower() or "lifecycle_penalty:pruned" in n for n in s_pr.notes)


def test_long_thorns_slight_penalty() -> None:
    q = HarvestQuery(raw_user_text="")
    short_t = _cand(
        "s",
        "m1",
        hit_channels=["lexical_text"],
        source_memory=_mem(thorns="短"),
    )
    long_t = _cand(
        "L",
        "m2",
        hit_channels=["lexical_text"],
        source_memory=_mem(thorns="痛" * 500),
    )
    ss, sl = RuleBasedHarvestScorer().score(q, [short_t, long_t])
    assert ss.relevance >= sl.relevance


def test_scorer_uses_injected_thorns_penalty_tiers() -> None:
    q = HarvestQuery(raw_user_text="")
    short_t = _cand(
        "s",
        "m1",
        hit_channels=["lexical_text"],
        source_memory=_mem(thorns="x"),
    )
    medium_t = _cand(
        "m",
        "m2",
        hit_channels=["lexical_text"],
        source_memory=_mem(thorns="x" * 10),
    )
    penalties = HarvestPenaltyConfig(
        thorns_tiers=[HarvestPenaltyTier(min_chars=10, multiplier=0.5, label="custom")]
    )

    ss, sm = RuleBasedHarvestScorer(penalties=penalties).score(q, [short_t, medium_t])

    assert ss.relevance > sm.relevance
    assert "thorns_len_penalty:custom" in "\n".join(sm.notes)


def test_harvest_score_json_roundtrip() -> None:
    q = HarvestQuery(raw_user_text="hi")
    c = _cand("c", "m", hit_channels=["lexical_text"], source_memory=_mem())
    hs = RuleBasedHarvestScorer().score(q, [c])[0]
    raw = hs.model_dump(mode="json")
    json.dumps(raw)
    assert raw["candidate_id"] == "c"


def test_scorer_source_has_no_ml_stack() -> None:
    import memory_garden.harvest.scoring as sc

    text = inspect.getsource(sc).lower()
    for bad in ("openai", "anthropic", "embed", "vector", "faiss", "chroma", "rerank", "llm"):
        assert bad not in text


def test_scorer_does_not_mutate_candidates() -> None:
    q = HarvestQuery(raw_user_text="z")
    c = _cand("cid", "mid", hit_channels=["lexical_text"], matched_lenses=["l1"])
    snap = c.model_dump()
    RuleBasedHarvestScorer().score(q, [c])
    assert c.model_dump() == snap


def test_missing_source_memory_conservative_but_valid() -> None:
    q = HarvestQuery(raw_user_text="!")
    c = MemoryCandidate(candidate_id="c0", memory_id="m0", metadata={})
    hs = RuleBasedHarvestScorer().score(q, [c])[0]
    assert hs.relevance == hs.relevance
    assert 0.0 <= hs.relevance <= 1.0


def test_recency_computed_from_timestamp_and_differs_from_confidence() -> None:
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    q = HarvestQuery(raw_user_text="r", metadata={"score_now": fixed_now.isoformat()})
    src = _mem(confidence=0.99)
    src["updated_at"] = "2025-12-01T00:00:00+00:00"
    src["memory_type"] = "preference"
    c = _cand(
        "c",
        "m",
        hit_channels=["lexical_text"],
        source_memory=src,
    )
    hs = RuleBasedHarvestScorer().score(q, [c])[0]
    assert hs.recency != 0.5
    assert abs(hs.recency - 0.99) > 0.01
    blob = "\n".join(hs.notes)
    assert "recency:computed" in blob
    assert "confidence:source_memory_value=0.9900" in blob


def test_recent_memory_ranks_above_stale_when_relevance_equal() -> None:
    fixed_now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    q = HarvestQuery(raw_user_text="x", metadata={"score_now": fixed_now.isoformat()})
    recent_src = _mem()
    recent_src["updated_at"] = "2026-05-01T00:00:00+00:00"
    stale_src = _mem()
    stale_src["updated_at"] = "2025-01-01T00:00:00+00:00"
    recent = _cand("recent", "m1", hit_channels=["lexical_text"], source_memory=recent_src)
    stale = _cand("stale", "m2", hit_channels=["lexical_text"], source_memory=stale_src)
    sr, ss = RuleBasedHarvestScorer().score(q, [stale, recent])
    assert sr.relevance == pytest.approx(ss.relevance)
    assert ss.recency > sr.recency


def test_canonical_old_memory_keeps_high_recency() -> None:
    fixed_now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    q = HarvestQuery(raw_user_text="x", metadata={"score_now": fixed_now.isoformat()})
    src = _mem()
    src["updated_at"] = "2020-01-01T00:00:00+00:00"
    src["tags"] = ["canonical"]
    src["maturity"] = "stable"
    hs = RuleBasedHarvestScorer().score(q, [_cand("c", "m", hit_channels=["lexical_text"], source_memory=src)])[0]
    assert hs.recency >= 0.9
    assert "recency:computed" in "\n".join(hs.notes)


def test_confidence_still_affects_relevance() -> None:
    q = HarvestQuery(raw_user_text="c")
    low = _cand("a", "m1", hit_channels=["lexical_text"], source_memory=_mem(confidence=0.15))
    high = _cand("b", "m2", hit_channels=["lexical_text"], source_memory=_mem(confidence=0.95))
    s_lo, s_hi = RuleBasedHarvestScorer().score(q, [low, high])
    assert s_hi.relevance > s_lo.relevance
    assert "confidence:source_memory_value=0.9500" in "\n".join(s_hi.notes)
