"""Benchmark 查询用例与分层数据集定义。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class BenchmarkCase:
    """单条 benchmark 查询；支持分级相关性分数。"""

    query_id: str
    query: str
    relevant_ids: list[str]
    relevance_scores: dict[str, int] | None = None
    language: str = "zh"
    subset: str = "general"

    def graded_relevance(self) -> dict[str, int]:
        if self.relevance_scores:
            return dict(self.relevance_scores)
        return {memory_id: 3 for memory_id in self.relevant_ids}

    def relevant_set(self) -> set[str]:
        return set(self.relevant_ids)


@dataclass(frozen=True)
class DatasetSpec:
    """分层数据集规模定义。"""

    name: str
    gold_count: int
    noise_count: int
    case_ids: tuple[str, ...] | None = None
    description: str = ""


DATASET_SPECS: dict[str, DatasetSpec] = {
    "tiny": DatasetSpec(
        name="tiny",
        gold_count=15,
        noise_count=35,
        case_ids=tuple(f"q{i:02d}" for i in range(1, 6)),
        description="15 gold + 35 noise = 50；5 条查询，CI 快速验证",
    ),
    "small": DatasetSpec(
        name="small",
        gold_count=15,
        noise_count=85,
        description="15 gold + 85 noise = 100；全量 20 查询",
    ),
    "medium": DatasetSpec(
        name="medium",
        gold_count=50,
        noise_count=450,
        description="50 gold + 450 noise = 500",
    ),
    "large": DatasetSpec(
        name="large",
        gold_count=100,
        noise_count=900,
        description="100 gold + 900 noise = 1000",
    ),
    "xlarge": DatasetSpec(
        name="xlarge",
        gold_count=200,
        noise_count=1800,
        description="200 gold + 1800 noise = 2000（压力测试）",
    ),
}

CJK_ONLY_QUERY_IDS: tuple[str, ...] = tuple(f"cjk-{i:02d}" for i in range(1, 11))


def _data_path(name: str) -> Path:
    return _DATA_DIR / name


def load_cases_jsonl(path: Path | None = None) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    file_path = path or _data_path("cases.jsonl")
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        scores = row.get("relevance_scores")
        if isinstance(scores, dict):
            relevance_scores = {str(k): int(v) for k, v in scores.items()}
        else:
            relevance_scores = None
        cases.append(
            BenchmarkCase(
                query_id=row["query_id"],
                query=row["query"],
                relevant_ids=list(row["relevant_ids"]),
                relevance_scores=relevance_scores,
                language=str(row.get("language", "zh")),
                subset=str(row.get("subset", "general")),
            )
        )
    return cases


def load_cjk_only_cases() -> list[BenchmarkCase]:
    path = _data_path("cases_cjk.jsonl")
    if path.is_file():
        return [c for c in load_cases_jsonl(path) if c.subset == "cjk_only"]
    return [
        BenchmarkCase(
            query_id=f"cjk-{i:02d}",
            query=query,
            relevant_ids=[f"bench-gold-cjk-{i:02d}"],
            relevance_scores={f"bench-gold-cjk-{i:02d}": 3},
            language="zh",
            subset="cjk_only",
        )
        for i, query in enumerate(
            [
                "编程语言偏好",
                "深色界面",
                "快速发布",
                "本地部署",
                "同步接口",
                "前端迭代",
                "简洁写作",
                "手动审批",
                "安全边界",
                "调试流程",
            ],
            start=1,
        )
    ]


def filter_cases_for_dataset(cases: list[BenchmarkCase], spec: DatasetSpec) -> list[BenchmarkCase]:
    if spec.case_ids is None:
        return list(cases)
    allowed = set(spec.case_ids)
    return [case for case in cases if case.query_id in allowed]


def expand_gold_specs(base_specs: list[dict[str, Any]], target_count: int) -> list[dict[str, Any]]:
    """将基础 gold 规格扩展到 target_count（用于 medium/large/xlarge）。"""
    if target_count <= len(base_specs):
        return list(base_specs[:target_count])
    expanded = list(base_specs)
    index = 0
    while len(expanded) < target_count:
        template = base_specs[index % len(base_specs)]
        variant = index // len(base_specs) + 1
        expanded.append(
            {
                **template,
                "id": f"{template['id']}-v{variant:02d}",
                "title": f"{template['title']} (变体 {variant})",
                "essence": f"{template['essence']} 扩展记录 {variant}",
                "tags": list(template.get("tags", [])) + [f"variant-{variant}"],
            }
        )
        index += 1
    return expanded
