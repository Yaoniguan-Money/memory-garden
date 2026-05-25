"""从 benchmark_v2.json 生成 Ablations 瀑布图（Mermaid）与延迟分布 PNG。"""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_JSON = Path(__file__).resolve().parents[2] / "docs" / "reports" / "benchmark_v2.json"
_DEFAULT_PNG = Path(__file__).resolve().parents[2] / "docs" / "reports" / "latency_distribution.png"
_DEFAULT_MERMAID = Path(__file__).resolve().parents[2] / "docs" / "reports" / "ablations_waterfall.mmd"

ABLAATIONS_MERMAID = """```mermaid
graph TD
    A["FTS5 原始<br/>40% recall · 3ms · 0规则"] -->|"CJK ngram 修复<br/>中文从0%复活"| B["FTS5 CJK<br/>40% recall · 3ms · 312 QPS"]
    B -->|"+ 规则评分管线<br/>+3pp · 可解释"| C["Product 规则<br/>43% recall · 553ms"]
    C -->|"+ 特征向量<br/>回溯力增强"| D["+ 特征评分<br/>43% recall · 539ms"]
    D -->|"+ 候选截断+预分词+NumPy<br/>-48%延迟"| E["+ 组合优化<br/>43% recall · 260ms"]
    E -->|"+ 写入时索引<br/>token/embed预计算"| F["当前<br/>43% recall · 164ms<br/>累计-70%延迟"]
    style A fill:#f0f0f0
    style F fill:#4caf50,color:#fff
```"""

_BUCKET_ORDER = ("lt_50ms", "lt_200ms", "lt_500ms", "gte_500ms")
_BUCKET_LABELS = ("<50ms", "50-200ms", "200-500ms", ">500ms")


def load_benchmark_json(path: Path | None = None) -> dict:
    file_path = path or _DEFAULT_JSON
    return json.loads(file_path.read_text(encoding="utf-8"))


def ablations_mermaid_block() -> str:
    return ABLAATIONS_MERMAID


def _find_baseline(payload: dict, name: str) -> dict | None:
    for row in payload.get("results", []):
        if row.get("baseline") == name:
            return row
    return None


def _bucket_counts(quality_summary: dict | None) -> list[int]:
    buckets = dict((quality_summary or {}).get("latency_buckets") or {})
    return [int(buckets.get(key, 0)) for key in _BUCKET_ORDER]


def render_latency_distribution(
    payload: dict | None = None,
    *,
    output_path: Path | None = None,
) -> Path | None:
    data = payload if payload is not None else load_benchmark_json()
    product = _find_baseline(data, "product")
    embed = _find_baseline(data, "product_local_embed")
    if product is None or embed is None:
        return None

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    counts_product = _bucket_counts(product.get("quality_summary"))
    counts_embed = _bucket_counts(embed.get("quality_summary"))
    x = range(len(_BUCKET_LABELS))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar([i - width / 2 for i in x], counts_product, width, label="Product 规则")
    ax.bar([i + width / 2 for i in x], counts_embed, width, label="Product + 本地嵌入")
    ax.set_xticks(list(x))
    ax.set_xticklabels(list(_BUCKET_LABELS))
    ax.set_xlabel("延迟区间")
    ax.set_ylabel("查询数量")
    ax.set_title("检索延迟分布（medium 数据集，20 条查询）")
    ax.legend()
    fig.tight_layout()

    out = output_path or _DEFAULT_PNG
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def write_mermaid_file(path: Path | None = None) -> Path:
    target = path or _DEFAULT_MERMAID
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        ABLAATIONS_MERMAID.replace("```mermaid\n", "")
        .replace("```", "")
        .strip()
    )
    target.write_text(body + "\n", encoding="utf-8")
    return target


def main() -> None:
    payload = load_benchmark_json()
    mermaid_path = write_mermaid_file()
    print(f"已写入 Mermaid：{mermaid_path}")
    png_path = render_latency_distribution(payload)
    if png_path:
        print(f"已写入 PNG：{png_path}")
    else:
        print("跳过 PNG（matplotlib 不可用或缺少 baseline 数据）")


if __name__ == "__main__":
    main()
