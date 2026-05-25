"""检索 benchmark baseline 适配层与编排。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from memory_garden.harvest.retrieval_diagnostics import RETRIEVAL_DIAGNOSTICS_KEY
from memory_garden.observatory.retrieval_quality import DiagnosticRow, summarize_retrieval_diagnostics
from memory_garden.product import ProductMemorySystem
from memory_garden.providers.config import ProviderPolicy
from memory_garden.providers.registry import ProviderRegistry
from memory_garden.soil.search import search_garden

from benchmarks.retrieval.cases import load_cases_jsonl
from benchmarks.retrieval.dataset import BenchmarkGarden, build_benchmark_garden, load_cases
from benchmarks.retrieval.metrics import (
    BaselineMetrics,
    QueryMetrics,
    aggregate_baseline_metrics,
    hit_at_k,
    map_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    r_precision,
    recall_at_k,
)
from benchmarks.retrieval.report import build_report_metadata, report_to_json


@dataclass(frozen=True)
class BaselineMeta:
    name: str
    provider: str
    mode: str
    network_calls: bool
    cost_per_1k_queries: float = 0.0


BASELINE_REGISTRY: dict[str, BaselineMeta] = {
    "fts5": BaselineMeta(name="fts5", provider="none", mode="no_llm", network_calls=False),
    "product": BaselineMeta(
        name="product",
        provider="none",
        mode="no_llm",
        network_calls=False,
    ),
    "product_local_embed": BaselineMeta(
        name="product_local_embed",
        provider="local_bge_small",
        mode="local",
        network_calls=False,
    ),
}


@dataclass(frozen=True)
class BenchmarkReport:
    """完整 benchmark 报告（v1 兼容 + v2 扩展字段）。"""

    noise_ratio: float
    total_memories: int
    total_queries: int
    k_values: list[int]
    baselines: list[BaselineMetrics]
    dataset_name: str = "small"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "noise_ratio": self.noise_ratio,
            "total_memories": self.total_memories,
            "total_queries": self.total_queries,
            "k_values": self.k_values,
            "baselines": [asdict(item) for item in self.baselines],
            "dataset_name": self.dataset_name,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    def to_v2_json(self) -> dict[str, Any]:
        meta = self.metadata or build_report_metadata(
            dataset=self.dataset_name,
            total_memories=self.total_memories,
            total_queries=self.total_queries,
            noise_ratio=self.noise_ratio,
        )
        return report_to_json(metadata=meta, results=self.baselines)


def run_fts5(query: str, *, garden_home: Path, limit: int) -> list[str]:
    hits = search_garden(garden_home, query, limit=limit, target_types=["memory_card"])
    return [hit.target_id for hit in hits]


def run_product(
    query: str,
    *,
    garden_home: Path,
    repository,
    limit: int,
    providers: ProviderRegistry | None = None,
    _product_cache: ProductMemorySystem | None = None,
) -> tuple[list[str], dict]:
    product = _product_cache or ProductMemorySystem(
        garden_home=garden_home,
        repository=repository,
        providers=providers or ProviderRegistry(),
    )
    result = product.retrieve(query, limit=limit, explain=False, mutate=False)
    diagnostics = dict(result.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY) or {})
    return [hit.memory.id for hit in result.hits], diagnostics


def warm_retrieval_index(
    *,
    garden_home: Path,
    repository,
    providers: ProviderRegistry,
) -> tuple[float, dict[str, int]]:
    started = time.perf_counter()
    product = ProductMemorySystem(
        garden_home=garden_home,
        repository=repository,
        providers=providers,
    )
    result = product.reindex_retrieval_scores()
    return (time.perf_counter() - started) * 1000.0, result


def warm_product_embedding_cache(
    *,
    garden_home: Path,
    repository,
    providers: ProviderRegistry,
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    product = ProductMemorySystem(
        garden_home=garden_home,
        repository=repository,
        providers=providers,
    )
    summary = product.warm_embedding_cache()
    return (time.perf_counter() - started) * 1000.0, summary


def _local_embedding_registry() -> ProviderRegistry | None:
    try:
        from memory_garden.providers.local_embedding import create_local_embedding_provider

        return ProviderRegistry(
            embedding=create_local_embedding_provider(),
            policy=ProviderPolicy(
                allow_remote_embeddings=False,
                allow_remote_rerank=False,
                allow_raw_user_text=True,
                allow_sensitive_text=True,
            ),
        )
    except ImportError:
        return None


def _evaluate_baseline(
    *,
    baseline: str,
    search_fn: Callable[[str], list[str] | tuple[list[str], dict]],
    cases: list,
    k: int,
) -> list[QueryMetrics]:
    per_query: list[QueryMetrics] = []
    for case in cases:
        start = time.perf_counter()
        raw = search_fn(case.query)
        latency_ms = (time.perf_counter() - start) * 1000.0
        diagnostics: dict | None = None
        if isinstance(raw, tuple):
            ranked, diagnostics = raw
        else:
            ranked = raw
        relevant = case.relevant_set()
        grades = case.graded_relevance()
        top_k = ranked[:k]
        missed = sorted(relevant - set(top_k))
        per_query.append(
            QueryMetrics(
                query_id=case.query_id,
                recall_at_k=recall_at_k(ranked, relevant_ids=relevant, k=k),
                precision_at_k=precision_at_k(ranked, relevant_ids=relevant, k=k),
                hit_at_k=hit_at_k(ranked, relevant_ids=relevant, k=k),
                ndcg_at_k=ndcg_at_k(ranked, relevance_scores=grades, k=k),
                mrr=mrr(ranked, relevant_ids=relevant),
                map_at_k=map_at_k(ranked, relevant_ids=relevant, k=k),
                r_precision=r_precision(ranked, relevant_ids=relevant),
                latency_ms=latency_ms,
                retrieval_diagnostics=diagnostics,
                failure_analysis={
                    "query": case.query,
                    "ranked_top_k": top_k,
                    "missed_relevant_ids": missed,
                    "hit_count": len(relevant & set(top_k)),
                    "relevant_count": len(relevant),
                },
            )
        )
    return per_query


def _summarize_failures(per_query: list[QueryMetrics]) -> dict[str, Any]:
    failures = []
    total_missed = 0
    for item in per_query:
        failure = dict(item.failure_analysis or {})
        missed = list(failure.get("missed_relevant_ids") or [])
        if not missed:
            continue
        total_missed += len(missed)
        failures.append(
            {
                "query_id": item.query_id,
                "missed_relevant_ids": missed,
                "ranked_top_k": list(failure.get("ranked_top_k") or []),
            }
        )
    return {
        "failed_query_count": len(failures),
        "total_missed_relevant": total_missed,
        "examples": failures[:10],
    }


def _run_single_baseline(
    garden: BenchmarkGarden,
    *,
    baseline_key: str,
    k: int,
) -> BaselineMetrics | None:
    meta = BASELINE_REGISTRY.get(baseline_key)
    if meta is None:
        return None

    if baseline_key == "fts5":
        per_query = _evaluate_baseline(
            baseline=baseline_key,
            search_fn=lambda q: run_fts5(q, garden_home=garden.garden_home, limit=k),
            cases=garden.cases,
            k=k,
        )
        return aggregate_baseline_metrics(
            baseline=baseline_key,
            k=k,
            per_query=per_query,
            failure_summary=_summarize_failures(per_query),
            meta=asdict(meta),
        )

    if baseline_key == "product":
        warm_retrieval_index(
            garden_home=garden.garden_home,
            repository=garden.repository,
            providers=ProviderRegistry(),
        )
        per_query = _evaluate_baseline(
            baseline=baseline_key,
            search_fn=lambda q: run_product(
                q,
                garden_home=garden.garden_home,
                repository=garden.repository,
                limit=k,
            ),
            cases=garden.cases,
            k=k,
        )
        quality = summarize_retrieval_diagnostics(
            [
                DiagnosticRow(
                    diagnostics=dict(item.retrieval_diagnostics or {}),
                    latency_ms=item.latency_ms,
                )
                for item in per_query
            ]
        )
        return aggregate_baseline_metrics(
            baseline=baseline_key,
            k=k,
            per_query=per_query,
            quality_summary=quality,
            failure_summary=_summarize_failures(per_query),
            meta=asdict(meta),
        )

    if baseline_key == "product_local_embed":
        registry = _local_embedding_registry()
        if registry is None:
            return None
        warm_retrieval_index(
            garden_home=garden.garden_home,
            repository=garden.repository,
            providers=registry,
        )
        cold_start_ms, warm_summary = warm_product_embedding_cache(
            garden_home=garden.garden_home,
            repository=garden.repository,
            providers=registry,
        )
        per_query = _evaluate_baseline(
            baseline=baseline_key,
            search_fn=lambda q: run_product(
                q,
                garden_home=garden.garden_home,
                repository=garden.repository,
                limit=k,
                providers=registry,
            ),
            cases=garden.cases,
            k=k,
        )
        quality = summarize_retrieval_diagnostics(
            [
                DiagnosticRow(
                    diagnostics=dict(item.retrieval_diagnostics or {}),
                    latency_ms=item.latency_ms,
                )
                for item in per_query
            ]
        )
        return aggregate_baseline_metrics(
            baseline=baseline_key,
            k=k,
            per_query=per_query,
            quality_summary=quality,
            failure_summary=_summarize_failures(per_query),
            cold_start_ms=cold_start_ms,
            meta={**asdict(meta), "warm_cache": warm_summary},
        )

    return None


def run_benchmark_on_garden(
    garden: BenchmarkGarden,
    *,
    k_values: list[int] | None = None,
    baseline_names: list[str] | None = None,
) -> BenchmarkReport:
    k_values = k_values if k_values is not None else [5]
    names = baseline_names if baseline_names is not None else ["fts5", "product"]
    baselines: list[BaselineMetrics] = []

    for k in k_values:
        for name in names:
            item = _run_single_baseline(garden, baseline_key=name, k=k)
            if item is not None:
                baselines.append(item)

    metadata = build_report_metadata(
        dataset=garden.dataset_name,
        total_memories=garden.total_memories,
        total_queries=len(garden.cases),
        noise_ratio=garden.noise_ratio,
    )
    return BenchmarkReport(
        noise_ratio=garden.noise_ratio,
        total_memories=garden.total_memories,
        total_queries=len(garden.cases),
        k_values=k_values,
        baselines=baselines,
        dataset_name=garden.dataset_name,
        metadata=metadata,
    )


def run_benchmark(
    garden_home: str | Path,
    *,
    noise_ratio: float = 0.85,
    k_values: list[int] | None = None,
    dataset_name: str = "small",
    baseline_names: list[str] | None = None,
) -> tuple[BenchmarkReport, BenchmarkGarden]:
    garden = build_benchmark_garden(
        garden_home,
        noise_ratio=noise_ratio,
        dataset_name=dataset_name,
    )
    report = run_benchmark_on_garden(
        garden,
        k_values=k_values,
        baseline_names=baseline_names,
    )
    return report, garden


def default_baseline_names(include_local_embed: bool = True) -> list[str]:
    names = ["fts5", "product"]
    if include_local_embed and _local_embedding_registry() is not None:
        names.append("product_local_embed")
    return names


def _real_queries_path() -> Path:
    return Path(__file__).resolve().parent / "real_queries.jsonl"


@dataclass(frozen=True)
class RealDatasetComparison:
    """真实（改写）查询集 vs 合成查询集的 recall 对比。"""

    synthetic: BenchmarkReport
    real: BenchmarkReport
    comparison_rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "synthetic": self.synthetic.to_dict(),
            "real": self.real.to_dict(),
            "comparison_rows": self.comparison_rows,
        }


def run_on_real_dataset(
    garden_home: str | Path,
    *,
    k: int = 5,
    dataset_name: str = "medium",
    baseline_names: list[str] | None = None,
) -> tuple[RealDatasetComparison, BenchmarkGarden, BenchmarkGarden]:
    """在同一记忆库规模下对比真实改写查询与合成查询。"""
    names = baseline_names if baseline_names is not None else default_baseline_names()
    real_cases = load_cases_jsonl(_real_queries_path())
    synthetic_cases = load_cases()

    base_home = Path(garden_home)
    garden_real = build_benchmark_garden(
        base_home / "real",
        cases=real_cases,
        dataset_name=dataset_name,
    )
    garden_syn = build_benchmark_garden(
        base_home / "synthetic",
        cases=synthetic_cases,
        dataset_name=dataset_name,
    )
    report_real = run_benchmark_on_garden(
        garden_real,
        k_values=[k],
        baseline_names=names,
    )
    report_syn = run_benchmark_on_garden(
        garden_syn,
        k_values=[k],
        baseline_names=names,
    )
    syn_by_name = {row.baseline: row for row in report_syn.baselines}
    comparison_rows: list[dict[str, Any]] = []
    for real_row in report_real.baselines:
        syn_row = syn_by_name.get(real_row.baseline)
        delta = (
            real_row.recall_at_k - syn_row.recall_at_k
            if syn_row is not None
            else None
        )
        comparison_rows.append(
            {
                "baseline": real_row.baseline,
                "recall_synthetic": syn_row.recall_at_k if syn_row else None,
                "recall_real": real_row.recall_at_k,
                "recall_delta_real_minus_syn": delta,
                "ndcg_synthetic": syn_row.ndcg_at_k if syn_row else None,
                "ndcg_real": real_row.ndcg_at_k,
            }
        )
    return (
        RealDatasetComparison(
            synthetic=report_syn,
            real=report_real,
            comparison_rows=comparison_rows,
        ),
        garden_real,
        garden_syn,
    )
