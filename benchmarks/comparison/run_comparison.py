"""行业对比 benchmark：Memory Garden vs ChromaDB vs FAISS。

用法：
    python -m benchmarks.comparison.run_comparison \\
        --dataset medium --output docs/reports/comparison_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from benchmarks.retrieval.cases import BenchmarkCase, load_cases_jsonl
from benchmarks.retrieval.dataset import (
    BenchmarkGarden,
    build_benchmark_garden,
    load_gold_memories,
)
from benchmarks.retrieval.metrics import (
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
from benchmarks.retrieval.runners import run_fts5, run_product, warm_retrieval_index

_DEFAULT_K = 5
_LATENCY_RUNS = 5
_CHROMA_MODEL = "all-MiniLM-L6-v2"
_FAISS_MODEL = "BAAI/bge-small-zh-v1.5"
_REPORTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "reports"


@dataclass(frozen=True)
class SystemResult:
    name: str
    recall_at_5: float | None
    ndcg_at_5: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    memory_mb: float | None
    dependencies: int | None
    network_calls: int | None
    co2_g: float | None
    embedding_model: str = ""
    status: str = "ok"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _memory_rss_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


def _pip_package_count() -> int:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if proc.returncode != 0:
            return 0
        return len([line for line in proc.stdout.splitlines() if line.strip()])
    except (OSError, subprocess.TimeoutExpired):
        return 0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round(p / 100.0 * len(ordered))) - 1))
    return ordered[rank]


def _evaluate_search(
    *,
    cases: list[BenchmarkCase],
    search_fn: Callable[[str], list[str]],
    k: int,
) -> tuple[list[QueryMetrics], list[float]]:
    per_query: list[QueryMetrics] = []
    query_latencies: list[float] = []
    for case in cases:
        run_latencies: list[float] = []
        ranked: list[str] = []
        for _ in range(_LATENCY_RUNS):
            start = time.perf_counter()
            ranked = search_fn(case.query)
            run_latencies.append((time.perf_counter() - start) * 1000.0)
        latency_ms = _median(run_latencies)
        query_latencies.append(latency_ms)
        relevant = case.relevant_set()
        grades = case.graded_relevance()
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
            )
        )
    return per_query, query_latencies


def _metrics_from_queries(
    *,
    name: str,
    per_query: list[QueryMetrics],
    query_latencies: list[float],
    k: int,
    memory_mb: float,
    dependencies: int,
    network_calls: int,
    embedding_model: str = "",
    co2_g: float = 0.0,
) -> SystemResult:
    agg = aggregate_baseline_metrics(baseline=name, k=k, per_query=per_query)
    return SystemResult(
        name=name,
        recall_at_5=agg.recall_at_k,
        ndcg_at_5=agg.ndcg_at_k,
        latency_p50_ms=_percentile(query_latencies, 50),
        latency_p95_ms=_percentile(query_latencies, 95),
        memory_mb=round(memory_mb, 1),
        dependencies=dependencies,
        network_calls=network_calls,
        co2_g=co2_g,
        embedding_model=embedding_model,
    )


def _memory_documents(garden: BenchmarkGarden) -> tuple[list[str], list[str], list[str]]:
    """从 benchmark 库读取全部记忆文本。"""
    ids: list[str] = []
    texts: list[str] = []
    titles: list[str] = []
    cards = sorted(garden.repository.list_memory_cards(), key=lambda card: card.id)
    for card in cards:
        ids.append(card.id)
        titles.append(card.title)
        texts.append(f"{card.title}\n{card.essence}".strip())
    return ids, texts, titles


def run_memory_garden_fts5(garden: BenchmarkGarden, *, k: int) -> SystemResult:
    mem_before = _memory_rss_mb()
    per_query, latencies = _evaluate_search(
        cases=garden.cases,
        search_fn=lambda q: run_fts5(q, garden_home=garden.garden_home, limit=k),
        k=k,
    )
    return _metrics_from_queries(
        name="Memory Garden FTS5",
        per_query=per_query,
        query_latencies=latencies,
        k=k,
        memory_mb=_memory_rss_mb() - mem_before + _memory_rss_mb(),
        dependencies=2,
        network_calls=0,
        embedding_model="none (FTS5 CJK ngram)",
    )


def run_memory_garden_product(garden: BenchmarkGarden, *, k: int) -> SystemResult:
    from memory_garden.providers.registry import ProviderRegistry

    mem_before = _memory_rss_mb()
    warm_retrieval_index(
        garden_home=garden.garden_home,
        repository=garden.repository,
        providers=ProviderRegistry(),
    )
    per_query, latencies = _evaluate_search(
        cases=garden.cases,
        search_fn=lambda q: run_product(
            q,
            garden_home=garden.garden_home,
            repository=garden.repository,
            limit=k,
        )[0],
        k=k,
    )
    return _metrics_from_queries(
        name="Memory Garden Product",
        per_query=per_query,
        query_latencies=latencies,
        k=k,
        memory_mb=max(_memory_rss_mb(), mem_before),
        dependencies=2,
        network_calls=0,
        embedding_model="rules-only",
    )


def run_chromadb(garden: BenchmarkGarden, *, k: int) -> SystemResult:
    try:
        import chromadb
    except ImportError:
        return SystemResult(
            name="ChromaDB",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            embedding_model=_CHROMA_MODEL,
            status="na",
            note="未安装 chromadb",
        )

    ids, texts, _ = _memory_documents(garden)
    if not ids:
        return SystemResult(
            name="ChromaDB",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            status="na",
            note="记忆库为空",
        )

    tmp_dir = tempfile.mkdtemp(prefix="mg_chroma_")
    mem_before = _memory_rss_mb()
    try:
        client = chromadb.PersistentClient(path=tmp_dir)
        collection = client.get_or_create_collection(
            name="benchmark",
            metadata={"hnsw:space": "cosine"},
        )
        batch = 100
        for start in range(0, len(ids), batch):
            end = start + batch
            collection.add(
                ids=ids[start:end],
                documents=texts[start:end],
            )

        def search_fn(query: str) -> list[str]:
            result = collection.query(query_texts=[query], n_results=k)
            ranked = list(result.get("ids") or [[]])[0]
            return [str(mid) for mid in ranked]

        per_query, latencies = _evaluate_search(
            cases=garden.cases,
            search_fn=search_fn,
            k=k,
        )
        deps = _pip_package_count()
        return _metrics_from_queries(
            name="ChromaDB",
            per_query=per_query,
            query_latencies=latencies,
            k=k,
            memory_mb=max(_memory_rss_mb() - mem_before, 0.0) + mem_before,
            dependencies=deps,
            network_calls=0,
            embedding_model=_CHROMA_MODEL,
            co2_g=0.0,
        )
    except Exception as exc:  # noqa: BLE001 — 对比脚本需优雅降级
        return SystemResult(
            name="ChromaDB",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            embedding_model=_CHROMA_MODEL,
            status="error",
            note=str(exc),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_faiss(garden: BenchmarkGarden, *, k: int) -> SystemResult:
    try:
        import faiss
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return SystemResult(
            name="FAISS Flat",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            embedding_model=_FAISS_MODEL,
            status="na",
            note="未安装 faiss-cpu 或 sentence-transformers",
        )

    ids, texts, _ = _memory_documents(garden)
    if not ids:
        return SystemResult(
            name="FAISS Flat",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            status="na",
            note="记忆库为空",
        )

    tmp_dir = tempfile.mkdtemp(prefix="mg_faiss_")
    mem_before = _memory_rss_mb()
    try:
        model = SentenceTransformer(_FAISS_MODEL)
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        matrix = np.asarray(vectors, dtype=np.float32)
        dim = matrix.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(matrix)
        id_list = ids

        def search_fn(query: str) -> list[str]:
            qvec = model.encode([query], normalize_embeddings=True, show_progress_bar=False)
            qmat = np.asarray(qvec, dtype=np.float32)
            _, indices = index.search(qmat, k)
            return [id_list[int(i)] for i in indices[0] if int(i) >= 0]

        per_query, latencies = _evaluate_search(
            cases=garden.cases,
            search_fn=search_fn,
            k=k,
        )
        _ = tmp_dir
        return _metrics_from_queries(
            name="FAISS Flat",
            per_query=per_query,
            query_latencies=latencies,
            k=k,
            memory_mb=max(_memory_rss_mb() - mem_before, 0.0) + mem_before,
            dependencies=_pip_package_count(),
            network_calls=0,
            embedding_model=_FAISS_MODEL,
            co2_g=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        return SystemResult(
            name="FAISS Flat",
            recall_at_5=None,
            ndcg_at_5=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            memory_mb=None,
            dependencies=None,
            network_calls=None,
            co2_g=None,
            embedding_model=_FAISS_MODEL,
            status="error",
            note=str(exc),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_comparison(
    garden_home: str | Path,
    *,
    dataset_name: str = "medium",
    k: int = _DEFAULT_K,
) -> dict[str, Any]:
    garden = build_benchmark_garden(garden_home, dataset_name=dataset_name)
    try:
        systems = [
            run_memory_garden_fts5(garden, k=k),
            run_memory_garden_product(garden, k=k),
            run_chromadb(garden, k=k),
            run_faiss(garden, k=k),
        ]
        return {
            "dataset": dataset_name,
            "total_memories": garden.total_memories,
            "total_queries": len(garden.cases),
            "noise_ratio": round(garden.noise_ratio, 4),
            "k": k,
            "gold_template_count": len(load_gold_memories()),
            "systems": [item.to_dict() for item in systems],
        }
    finally:
        garden.close()


def format_markdown_table(report: dict[str, Any]) -> str:
    lines = [
        "| 系统 | Recall@5 | NDCG@5 | P50 | P95 | 内存(MB) | 依赖数 | 网络调用 | CO₂(g) | 嵌入模型 |",
        "|------|----------|--------|-----|-----|----------|--------|---------|--------|----------|",
    ]
    for row in report.get("systems", []):
        if row.get("status") != "ok":
            lines.append(
                f"| {row['name']} | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | {row.get('note', 'N/A')} |"
            )
            continue
        recall = f"{row['recall_at_5'] * 100:.1f}%" if row.get("recall_at_5") is not None else "N/A"
        ndcg = f"{row['ndcg_at_5']:.3f}" if row.get("ndcg_at_5") is not None else "N/A"
        p50 = f"{row['latency_p50_ms']:.1f}ms" if row.get("latency_p50_ms") is not None else "N/A"
        p95 = f"{row['latency_p95_ms']:.1f}ms" if row.get("latency_p95_ms") is not None else "N/A"
        mem = f"{row['memory_mb']:.0f}" if row.get("memory_mb") is not None else "N/A"
        deps = str(row.get("dependencies", "N/A"))
        net = str(row.get("network_calls", "N/A"))
        co2 = f"{row['co2_g']:.2f}" if row.get("co2_g") is not None else "N/A"
        model = row.get("embedding_model") or "-"
        lines.append(
            f"| {row['name']} | {recall} | {ndcg} | {p50} | {p95} | {mem} | {deps} | {net} | {co2} | {model} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Garden 行业对比 benchmark")
    parser.add_argument("--dataset", default="medium")
    parser.add_argument("--garden-home", default=".benchmark_comparison")
    parser.add_argument("--k", type=int, default=_DEFAULT_K)
    parser.add_argument(
        "--output",
        default=str(_REPORTS_DIR / "comparison_benchmark.json"),
        help="JSON 报告路径",
    )
    parser.add_argument("--markdown", default="", help="Markdown 表格输出路径")
    args = parser.parse_args()

    report = run_comparison(Path(args.garden_home), dataset_name=args.dataset, k=args.k)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 JSON：{out_path}")
    table = format_markdown_table(report)
    try:
        print(table)
    except UnicodeEncodeError:
        print(table.replace("\u2082", "2"))
    if args.markdown:
        md_path = Path(args.markdown)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(table + "\n", encoding="utf-8")
        print(f"已写入 Markdown：{md_path}")


if __name__ == "__main__":
    main()
