"""Benchmark 报告序列化：JSON（CI）与 Markdown（人类阅读）。"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmarks.retrieval.metrics import BaselineMetrics


def build_report_metadata(
    *,
    dataset: str,
    total_memories: int,
    total_queries: int,
    noise_ratio: float,
    version: str = "1.4.0",
) -> dict[str, Any]:
    return {
        "version": version,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "machine": f"{platform.processor() or platform.machine()} / {platform.system()}",
        "python": sys.version.split()[0],
        "dataset": dataset,
        "total_memories": total_memories,
        "total_queries": total_queries,
        "noise_ratio": round(noise_ratio, 4),
    }


def baseline_metrics_to_dict(item: BaselineMetrics) -> dict[str, Any]:
    return {
        "baseline": item.baseline,
        "k": item.k,
        "recall_at_k": round(item.recall_at_k, 4),
        "precision_at_k": round(item.precision_at_k, 4),
        "hit_at_k": round(item.hit_at_k, 4),
        "ndcg_at_k": round(item.ndcg_at_k, 4),
        "mrr": round(item.mrr, 4),
        "map_at_k": round(item.map_at_k, 4),
        "r_precision": round(item.r_precision, 4),
        "latency_ms_avg": round(item.latency_ms_avg, 2),
        "latency_p50_ms": round(item.latency_p50_ms, 2),
        "latency_p95_ms": round(item.latency_p95_ms, 2),
        "latency_p99_ms": round(item.latency_p99_ms, 2),
        "throughput_qps": round(item.throughput_qps, 2),
        "cold_start_ms": round(item.cold_start_ms, 2),
        "total_queries": item.total_queries,
        "quality_summary": item.quality_summary,
        "failure_summary": item.failure_summary,
        "meta": item.meta,
    }


def report_to_json(
    *,
    metadata: dict[str, Any],
    results: list[BaselineMetrics],
) -> dict[str, Any]:
    return {
        "metadata": metadata,
        "results": [baseline_metrics_to_dict(item) for item in results],
    }


def write_json_report(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_markdown_table(results: list[BaselineMetrics]) -> str:
    if not results:
        return "_无结果_\n"
    lines = [
        "| baseline | k | Recall@k | NDCG@k | MRR | Hit@k | P50(ms) | P95(ms) | QPS |",
        "|----------|---|----------|--------|-----|-------|---------|---------|-----|",
    ]
    for item in results:
        lines.append(
            f"| {item.baseline} | {item.k} | {item.recall_at_k:.2%} | {item.ndcg_at_k:.3f} | "
            f"{item.mrr:.3f} | {item.hit_at_k:.2%} | {item.latency_p50_ms:.0f} | "
            f"{item.latency_p95_ms:.0f} | {item.throughput_qps:.1f} |"
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(
    path: str | Path,
    *,
    metadata: dict[str, Any],
    results: list[BaselineMetrics],
    title: str = "Memory Garden 检索 Benchmark",
) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"# {title}",
        "",
        "## 实验设置",
        "",
        f"- 数据集：`{metadata.get('dataset', '')}`",
        f"- 记忆条数：{metadata.get('total_memories', 0)}",
        f"- 查询条数：{metadata.get('total_queries', 0)}",
        f"- 噪声比：{metadata.get('noise_ratio', 0)}",
        f"- 日期：{metadata.get('date', '')}",
        f"- 环境：{metadata.get('machine', '')} / Python {metadata.get('python', '')}",
        "",
        "## 核心结果",
        "",
        render_markdown_table(results),
    ]
    out.write_text("\n".join(body), encoding="utf-8")
