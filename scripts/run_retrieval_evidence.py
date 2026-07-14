"""Run the fixed, seeded Memory Garden retrieval evidence experiment."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.retrieval.cases import BenchmarkCase, load_cases_jsonl
from benchmarks.retrieval.dataset import build_benchmark_garden
from benchmarks.retrieval.metrics import (
    hit_at_k,
    map_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    r_precision,
    recall_at_k,
)
from benchmarks.retrieval.runners import (
    _local_embedding_registry,
    run_fts5,
    warm_product_embedding_cache,
    warm_retrieval_index,
)
from memory_garden.product import ProductMemorySystem
from memory_garden.providers.registry import ProviderRegistry


CONFIG_PATH = ROOT / "evidence" / "config" / "retrieval_experiment.json"


def _load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_evidence_cases(config: dict[str, Any]) -> list[BenchmarkCase]:
    return load_cases_jsonl(ROOT / config["query_dataset"])


def _metric_row(case: BenchmarkCase, ranked: list[str], latency_ms: float, k: int) -> dict[str, Any]:
    relevant = case.relevant_set()
    top = ranked[:k]
    is_negative = not relevant
    return {
        "query_id": case.query_id,
        "query": case.query,
        "relevant_ids": sorted(relevant),
        "ranked_top_k": top,
        "missed_relevant_ids": sorted(relevant - set(top)),
        "is_negative": is_negative,
        "false_positive": is_negative and bool(top),
        "recall_at_k": recall_at_k(ranked, relevant_ids=relevant, k=k),
        "precision_at_k": precision_at_k(ranked, relevant_ids=relevant, k=k),
        "hit_at_k": hit_at_k(ranked, relevant_ids=relevant, k=k),
        "ndcg_at_k": ndcg_at_k(ranked, relevance_scores=case.graded_relevance(), k=k),
        "mrr": mrr(ranked, relevant_ids=relevant),
        "map_at_k": map_at_k(ranked, relevant_ids=relevant, k=k),
        "r_precision": r_precision(ranked, relevant_ids=relevant),
        "latency_ms": latency_ms,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = sorted(row["latency_ms"] for row in rows)
    positives = [row for row in rows if not row["is_negative"]]
    negatives = [row for row in rows if row["is_negative"]]
    percentile = lambda p: latencies[max(0, min(len(latencies) - 1, int((p / 100) * len(latencies) + 0.9999) - 1))]
    return {
        "total_queries": len(rows),
        "positive_queries": len(positives),
        "negative_queries": len(negatives),
        "recall_at_5": statistics.fmean(row["recall_at_k"] for row in positives),
        "ndcg_at_5": statistics.fmean(row["ndcg_at_k"] for row in positives),
        "mrr": statistics.fmean(row["mrr"] for row in positives),
        "negative_false_positive_rate": statistics.fmean(row["false_positive"] for row in negatives),
        "failed_query_count": sum(bool(row["missed_relevant_ids"]) for row in rows),
        "latency_p50_ms": percentile(50),
        "latency_p95_ms": percentile(95),
    }


def _run_baseline(garden, cases: list[BenchmarkCase], baseline: str, k: int, embed_registry):
    if baseline == "fts5":
        search = lambda query: run_fts5(query, garden_home=garden.garden_home, limit=k)
        setup: dict[str, Any] = {}
    else:
        providers = embed_registry if baseline == "product_local_embed" else ProviderRegistry()
        warm_ms, warm_result = warm_retrieval_index(
            garden_home=garden.garden_home,
            repository=garden.repository,
            providers=providers,
        )
        setup = {"retrieval_index_warm_ms": warm_ms, "retrieval_index": warm_result}
        if baseline == "product_local_embed":
            embed_ms, embed_result = warm_product_embedding_cache(
                garden_home=garden.garden_home,
                repository=garden.repository,
                providers=providers,
            )
            setup.update({"embedding_cache_warm_ms": embed_ms, "embedding_cache": embed_result})
        product = ProductMemorySystem(
            garden_home=garden.garden_home,
            repository=garden.repository,
            providers=providers,
        )
        search = lambda query: [
            hit.memory.id for hit in product.retrieve(query, limit=k, explain=False, mutate=False).hits
        ]

    rows = []
    for case in cases:
        started = time.perf_counter()
        ranked = search(case.query)
        rows.append(_metric_row(case, ranked, (time.perf_counter() - started) * 1000.0, k))
    return {"setup": setup, "summary": _summarize(rows), "queries": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "evidence" / "raw" / "retrieval_runs.json"))
    parser.add_argument("--failures", default=str(ROOT / "evidence" / "failures" / "retrieval_failures.jsonl"))
    parser.add_argument("--skip-local-embed", action="store_true")
    args = parser.parse_args()

    config = _load_config()
    cases = _load_evidence_cases(config)
    baselines = [name for name in config["baselines"] if name != "product_local_embed"]
    embedding_status: dict[str, Any] = {"requested": not args.skip_local_embed}
    embed_registry = None
    if not args.skip_local_embed:
        try:
            embed_registry = _local_embedding_registry()
            if embed_registry is None:
                embedding_status.update({"available": False, "reason": "optional dependency unavailable"})
            else:
                baselines.append("product_local_embed")
                embedding_status.update({"available": True, "model": "BAAI/bge-small-zh-v1.5"})
        except Exception as exc:
            embedding_status.update({"available": False, "reason": f"{type(exc).__name__}: {exc}"})

    runs = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="memory-garden-evidence-") as temp_root:
        for dataset in config["datasets"]:
            for seed in config["seeds"]:
                garden = build_benchmark_garden(
                    Path(temp_root) / f"{dataset}-{seed}",
                    dataset_name=dataset,
                    cases=cases,
                    seed=seed,
                )
                try:
                    for baseline in baselines:
                        try:
                            result = _run_baseline(garden, cases, baseline, config["k"], embed_registry)
                            run = {
                                "dataset": dataset,
                                "seed": seed,
                                "baseline": baseline,
                                "total_memories": garden.total_memories,
                                "noise_ratio": garden.noise_ratio,
                                **result,
                            }
                            runs.append(run)
                            failures.extend(
                                {"dataset": dataset, "seed": seed, "baseline": baseline, **row}
                                for row in result["queries"]
                                if row["missed_relevant_ids"] or row["false_positive"]
                            )
                        except Exception as exc:
                            error = {
                                "dataset": dataset,
                                "seed": seed,
                                "baseline": baseline,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                            failures.append(error)
                            if baseline == "product_local_embed":
                                embedding_status.update({"available": False, "reason": error["error"]})
                            else:
                                raise
                finally:
                    garden.close()

    aggregates = []
    for dataset in config["datasets"]:
        for baseline in sorted({run["baseline"] for run in runs}):
            selected = [run["summary"] for run in runs if run["dataset"] == dataset and run["baseline"] == baseline]
            if not selected:
                continue
            aggregates.append(
                {
                    "dataset": dataset,
                    "baseline": baseline,
                    "seed_count": len(selected),
                    "query_runs": sum(row["total_queries"] for row in selected),
                    "recall_at_5_mean": statistics.fmean(row["recall_at_5"] for row in selected),
                    "recall_at_5_sample_sd": statistics.stdev(row["recall_at_5"] for row in selected) if len(selected) > 1 else 0.0,
                    "ndcg_at_5_mean": statistics.fmean(row["ndcg_at_5"] for row in selected),
                    "ndcg_at_5_sample_sd": statistics.stdev(row["ndcg_at_5"] for row in selected) if len(selected) > 1 else 0.0,
                    "negative_false_positive_rate_mean": statistics.fmean(row["negative_false_positive_rate"] for row in selected),
                    "negative_false_positive_rate_sample_sd": statistics.stdev(row["negative_false_positive_rate"] for row in selected) if len(selected) > 1 else 0.0,
                    "latency_p50_ms_mean": statistics.fmean(row["latency_p50_ms"] for row in selected),
                    "latency_p95_ms_mean": statistics.fmean(row["latency_p95_ms"] for row in selected),
                    "failed_query_count": sum(row["failed_query_count"] for row in selected),
                }
            )

    payload = {
        "schema_version": 1,
        "config": config,
        "independent_query_count": len(cases),
        "embedding_status": embedding_status,
        "aggregates": aggregates,
        "runs": runs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failure_path = Path(args.failures)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in failures),
        encoding="utf-8",
    )
    print(json.dumps({"aggregates": aggregates, "embedding_status": embedding_status}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
