"""Retrieval benchmark v1 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.retrieval.dataset import (
    build_mini_benchmark_garden,
    compute_noise_count,
    load_cases,
    load_gold_memories,
)
from benchmarks.retrieval.metrics import (
    aggregate_baseline_metrics,
    hit_at_k,
    precision_at_k,
    recall_at_k,
)
from benchmarks.retrieval.runners import run_benchmark, run_benchmark_on_garden


# ---------------------------------------------------------------------------
# A. 指标单测
# ---------------------------------------------------------------------------


def test_recall_at_k_partial_hits():
    ranked = ["a", "b", "c", "d"]
    relevant = {"a", "c", "x"}
    assert recall_at_k(ranked, relevant_ids=relevant, k=2) == pytest.approx(1 / 3)


def test_precision_at_k_partial_hits():
    ranked = ["a", "b", "c", "d"]
    relevant = {"a", "c", "x"}
    assert precision_at_k(ranked, relevant_ids=relevant, k=2) == pytest.approx(0.5)


def test_hit_at_k_true_and_false():
    ranked = ["noise", "gold", "other"]
    assert hit_at_k(ranked, relevant_ids={"gold"}, k=2) == 1.0
    assert hit_at_k(ranked, relevant_ids={"gold"}, k=1) == 0.0


def test_recall_at_k_empty_relevant():
    assert recall_at_k(["a"], relevant_ids=set(), k=1) == 0.0


def test_hit_at_k_empty_relevant():
    assert hit_at_k(["a"], relevant_ids=set(), k=1) == 0.0


def test_precision_at_k_k_larger_than_ranked():
    ranked = ["a", "b"]
    relevant = {"a"}
    assert precision_at_k(ranked, relevant_ids=relevant, k=5) == pytest.approx(0.2)


def test_aggregate_baseline_metrics_macro_average():
    from benchmarks.retrieval.metrics import QueryMetrics

    per_query = [
        QueryMetrics("q1", recall_at_k=1.0, precision_at_k=0.5, hit_at_k=1.0, latency_ms=10.0),
        QueryMetrics("q2", recall_at_k=0.0, precision_at_k=0.0, hit_at_k=0.0, latency_ms=20.0),
    ]
    agg = aggregate_baseline_metrics(baseline="product", k=2, per_query=per_query)
    assert agg.recall_at_k == pytest.approx(0.5)
    assert agg.precision_at_k == pytest.approx(0.25)
    assert agg.hit_at_k == pytest.approx(0.5)
    assert agg.latency_ms_avg == pytest.approx(15.0)


def test_compute_noise_count_default_ratio():
    assert compute_noise_count(15, 0.85) == 85


# ---------------------------------------------------------------------------
# B. 微型端到端
# ---------------------------------------------------------------------------


def _metrics_without_latency(report):
    return [
        {
            "baseline": item.baseline,
            "k": item.k,
            "recall_at_k": item.recall_at_k,
            "precision_at_k": item.precision_at_k,
            "hit_at_k": item.hit_at_k,
        }
        for item in report.baselines
    ]


def test_mini_benchmark_product_hit_and_deterministic(tmp_path):
    garden = build_mini_benchmark_garden(tmp_path / "mini")
    try:
        report_first = run_benchmark_on_garden(garden, k_values=[5])
        report_second = run_benchmark_on_garden(garden, k_values=[5])
        assert _metrics_without_latency(report_first) == _metrics_without_latency(report_second)

        product_k5 = next(
            item for item in report_first.baselines if item.baseline == "product" and item.k == 5
        )
        assert product_k5.hit_at_k == 1.0
        assert product_k5.recall_at_k == 1.0
        assert product_k5.quality_summary is not None
        assert "candidate_sources" in product_k5.quality_summary
        assert "latency_buckets" in product_k5.quality_summary

        fts5_k5 = next(
            item for item in report_first.baselines if item.baseline == "fts5" and item.k == 5
        )
        assert fts5_k5.total_queries == 2
        assert fts5_k5.latency_ms_avg >= 0.0
    finally:
        garden.close()


# ---------------------------------------------------------------------------
# C. 全量 smoke
# ---------------------------------------------------------------------------


def test_full_benchmark_smoke(tmp_path):
    report, garden = run_benchmark(
        tmp_path / "full",
        k_values=[5],
        dataset_name="small",
    )
    try:
        payload = report.to_dict()
        assert payload["total_queries"] == len(load_cases())
        assert payload["total_memories"] == 100
        assert payload["noise_ratio"] == pytest.approx(0.85, abs=0.02)

        required = {"baseline", "k", "recall_at_k", "precision_at_k", "hit_at_k", "latency_ms_avg"}
        for item in payload["baselines"]:
            assert required.issubset(item.keys())

        product_k5 = next(
            item for item in report.baselines if item.baseline == "product" and item.k == 5
        )
        assert product_k5.recall_at_k > 0.0
    finally:
        garden.close()
