"""标准 IR 指标单元测试。"""

from __future__ import annotations

import pytest

from benchmarks.retrieval.metrics import (
    latency_percentiles,
    map_at_k,
    mrr,
    ndcg_at_k,
    r_precision,
    recall_at_k,
)


def test_ndcg_perfect_ranking() -> None:
    scores = {"a": 3, "b": 2, "c": 1}
    ranked = ["a", "b", "c", "x"]
    value = ndcg_at_k(ranked, relevance_scores=scores, k=3)
    assert value == pytest.approx(1.0, abs=0.01)


def test_mrr_first_hit() -> None:
    assert mrr(["x", "gold", "y"], relevant_ids={"gold"}) == pytest.approx(0.5)


def test_map_and_r_precision() -> None:
    ranked = ["a", "noise", "b", "c"]
    relevant = {"a", "b", "c"}
    assert map_at_k(ranked, relevant_ids=relevant, k=4) > 0.0
    assert r_precision(ranked, relevant_ids=relevant) == pytest.approx(2 / 3, abs=0.01)


def test_latency_percentiles() -> None:
    out = latency_percentiles([10.0, 20.0, 30.0, 40.0, 100.0], [50, 95])
    assert out[50] <= out[95]

