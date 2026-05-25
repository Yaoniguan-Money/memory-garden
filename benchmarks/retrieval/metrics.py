"""检索 benchmark 指标：recall / precision / hit / NDCG / MRR / MAP / 延迟分位数。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryMetrics:
    """单条查询在某 k 下的指标。"""

    query_id: str
    recall_at_k: float
    precision_at_k: float
    hit_at_k: float
    ndcg_at_k: float = 0.0
    mrr: float = 0.0
    map_at_k: float = 0.0
    r_precision: float = 0.0
    latency_ms: float = 0.0
    retrieval_diagnostics: dict | None = None
    failure_analysis: dict | None = None


@dataclass(frozen=True)
class BaselineMetrics:
    """某 baseline 在指定 k 上的宏平均指标。"""

    baseline: str
    k: int
    recall_at_k: float
    precision_at_k: float
    hit_at_k: float
    ndcg_at_k: float = 0.0
    mrr: float = 0.0
    map_at_k: float = 0.0
    r_precision: float = 0.0
    latency_ms_avg: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    throughput_qps: float = 0.0
    total_queries: int = 0
    quality_summary: dict | None = None
    failure_summary: dict | None = None
    cold_start_ms: float = 0.0
    meta: dict = field(default_factory=dict)


def recall_at_k(ranked_ids: list[str], *, relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    return len(relevant_ids & top_k) / len(relevant_ids)


def precision_at_k(ranked_ids: list[str], *, relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for mid in top_k if mid in relevant_ids)
    return hits / k


def hit_at_k(ranked_ids: list[str], *, relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    return 1.0 if relevant_ids & top_k else 0.0


def _dcg(relevances: list[float]) -> float:
    total = 0.0
    for index, rel in enumerate(relevances):
        if rel <= 0.0:
            continue
        total += (2.0**rel - 1.0) / math.log2(index + 2.0)
    return total


def ndcg_at_k(
    ranked_ids: list[str],
    *,
    relevance_scores: dict[str, int],
    k: int,
) -> float:
    """分级相关性 NDCG@k；``relevance_scores`` 为 memory_id -> 等级 (0 表示不相关)。"""
    if not relevance_scores:
        return 0.0
    gains = [float(relevance_scores.get(mid, 0)) for mid in ranked_ids[:k]]
    ideal = sorted(relevance_scores.values(), reverse=True)[:k]
    ideal_gains = [float(v) for v in ideal]
    denom = _dcg(ideal_gains)
    if denom <= 0.0:
        return 0.0
    return _dcg(gains) / denom


def mrr(ranked_ids: list[str], *, relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 0.0
    for index, mid in enumerate(ranked_ids, start=1):
        if mid in relevant_ids:
            return 1.0 / index
    return 0.0


def map_at_k(ranked_ids: list[str], *, relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for index, mid in enumerate(ranked_ids[:k], start=1):
        if mid in relevant_ids:
            hits += 1
            precision_sum += hits / index
    if hits == 0:
        return 0.0
    return precision_sum / len(relevant_ids)


def r_precision(ranked_ids: list[str], *, relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 0.0
    r = len(relevant_ids)
    top_r = ranked_ids[:r]
    if not top_r:
        return 0.0
    hits = sum(1 for mid in top_r if mid in relevant_ids)
    return hits / r


def latency_percentiles(latencies_ms: list[float], percentiles: list[int]) -> dict[int, float]:
    if not latencies_ms:
        return {p: 0.0 for p in percentiles}
    ordered = sorted(latencies_ms)
    out: dict[int, float] = {}
    n = len(ordered)
    for p in percentiles:
        if p <= 0:
            out[p] = ordered[0]
            continue
        if p >= 100:
            out[p] = ordered[-1]
            continue
        rank = max(0, min(n - 1, math.ceil(p / 100.0 * n) - 1))
        out[p] = ordered[rank]
    return out


def aggregate_baseline_metrics(
    *,
    baseline: str,
    k: int,
    per_query: list[QueryMetrics],
    quality_summary: dict | None = None,
    failure_summary: dict | None = None,
    cold_start_ms: float = 0.0,
    meta: dict | None = None,
) -> BaselineMetrics:
    if not per_query:
        return BaselineMetrics(
            baseline=baseline,
            k=k,
            recall_at_k=0.0,
            precision_at_k=0.0,
            hit_at_k=0.0,
            total_queries=0,
            quality_summary=quality_summary,
            failure_summary=failure_summary,
            cold_start_ms=cold_start_ms,
            meta=dict(meta or {}),
        )
    count = len(per_query)
    latencies = [item.latency_ms for item in per_query]
    percentiles = latency_percentiles(latencies, [50, 95, 99])
    total_latency_s = sum(latencies) / 1000.0
    throughput = count / total_latency_s if total_latency_s > 0 else 0.0
    return BaselineMetrics(
        baseline=baseline,
        k=k,
        recall_at_k=sum(item.recall_at_k for item in per_query) / count,
        precision_at_k=sum(item.precision_at_k for item in per_query) / count,
        hit_at_k=sum(item.hit_at_k for item in per_query) / count,
        ndcg_at_k=sum(item.ndcg_at_k for item in per_query) / count,
        mrr=sum(item.mrr for item in per_query) / count,
        map_at_k=sum(item.map_at_k for item in per_query) / count,
        r_precision=sum(item.r_precision for item in per_query) / count,
        latency_ms_avg=sum(latencies) / count,
        latency_p50_ms=percentiles[50],
        latency_p95_ms=percentiles[95],
        latency_p99_ms=percentiles[99],
        throughput_qps=throughput,
        total_queries=count,
        quality_summary=quality_summary,
        failure_summary=failure_summary,
        cold_start_ms=cold_start_ms,
        meta=dict(meta or {}),
    )
