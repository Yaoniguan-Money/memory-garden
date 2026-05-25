"""CLI：python -m benchmarks.retrieval.run --dataset small --output docs/reports/benchmark_v2.json"""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.retrieval.report import write_json_report, write_markdown_report
from benchmarks.retrieval.runners import default_baseline_names, run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory Garden 检索 benchmark")
    parser.add_argument("--dataset", default="small", help="tiny|small|medium|large|xlarge")
    parser.add_argument("--garden-home", default=".benchmark_garden", help="临时 garden 目录")
    parser.add_argument("--k", type=int, default=5, help="Recall@k 的 k")
    parser.add_argument(
        "--baselines",
        default="default",
        help="逗号分隔 baseline 名，或 default / all",
    )
    parser.add_argument("--output", default="", help="JSON 报告输出路径")
    parser.add_argument("--markdown", default="", help="Markdown 报告输出路径")
    args = parser.parse_args()

    if args.baselines == "default":
        baseline_names = default_baseline_names()
    elif args.baselines == "all":
        baseline_names = ["fts5", "product", "product_local_embed"]
    else:
        baseline_names = [part.strip() for part in args.baselines.split(",") if part.strip()]

    report, garden = run_benchmark(
        Path(args.garden_home),
        k_values=[args.k],
        dataset_name=args.dataset,
        baseline_names=baseline_names,
    )
    try:
        payload = report.to_v2_json()
        if args.output:
            write_json_report(args.output, payload)
            print(f"已写入 JSON：{args.output}")
        if args.markdown:
            write_markdown_report(
                args.markdown,
                metadata=payload["metadata"],
                results=report.baselines,
            )
            print(f"已写入 Markdown：{args.markdown}")
        if not args.output and not args.markdown:
            for row in payload["results"]:
                print(
                    f"{row['baseline']}@{row['k']}: "
                    f"recall={row['recall_at_k']:.2%} ndcg={row['ndcg_at_k']:.3f} "
                    f"p95={row['latency_p95_ms']:.0f}ms"
                )
    finally:
        garden.close()


if __name__ == "__main__":
    main()
