"""运行 Memory Garden 本地检索 benchmark（非生产实验基线）。

用法::

    python scripts/run_retrieval_benchmark.py
    python scripts/run_retrieval_benchmark.py --noise-ratio 0.85 --k 5
    python scripts/run_retrieval_benchmark.py --output json --json-out /tmp/report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.retrieval.runners import run_benchmark


def _parse_k_values(raw: str) -> list[int]:
    values = [int(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("至少需要一个 k 值")
    for k in values:
        if k <= 0:
            raise argparse.ArgumentTypeError("k 必须为正整数")
    return values


def _format_text(report) -> str:
    lines = [
        "=== Retrieval Benchmark v1 (local, not production) ===",
        (
            f"noise_ratio={report.noise_ratio:.2f}  "
            f"total_memories={report.total_memories}  "
            f"total_queries={report.total_queries}"
        ),
        "",
    ]
    for item in report.baselines:
        lines.append(f"[{item.baseline}] k={item.k}")
        lines.append(
            f"  recall@{item.k}={item.recall_at_k:.4f}  "
            f"precision@{item.k}={item.precision_at_k:.4f}  "
            f"hit@{item.k}={item.hit_at_k:.4f}  "
            f"latency_ms_avg={item.latency_ms_avg:.2f}"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memory Garden retrieval benchmark v1")
    parser.add_argument("--noise-ratio", type=float, default=0.85, help="噪声记忆占比，默认 0.85")
    parser.add_argument("--k", type=str, default="5", help="逗号分隔的 k 值，默认 5")
    parser.add_argument(
        "--garden-path",
        type=Path,
        default=None,
        help="可选持久化 garden 目录；默认使用临时目录",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="控制台输出格式",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="可选 JSON 报告输出路径（不提交 git）",
    )
    args = parser.parse_args(argv)

    if not 0.0 <= args.noise_ratio < 1.0:
        parser.error("noise_ratio 必须在 [0, 1) 范围内")

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    garden_path = args.garden_path
    if garden_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="mg_retrieval_bench_")
        garden_path = Path(temp_dir.name) / "bench_garden"

    report, garden = run_benchmark(
        garden_path,
        noise_ratio=args.noise_ratio,
        k_values=_parse_k_values(args.k),
    )
    try:
        payload = report.to_dict()
        if args.output == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(_format_text(report), end="")

        if args.json_out is not None:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if args.output == "text":
                print(f"JSON report written to {args.json_out}")
    finally:
        garden.close()
        if temp_dir is not None:
            temp_dir.cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
