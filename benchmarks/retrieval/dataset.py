"""检索 benchmark 数据集加载与 garden 构建。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard, MemoryType, SensitivityLevel
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import reindex_garden
from memory_garden.storage.sqlite import SQLiteGardenRepository

from benchmarks.retrieval.cases import (
    BenchmarkCase,
    DATASET_SPECS,
    DatasetSpec,
    expand_gold_specs,
    filter_cases_for_dataset,
    load_cases_jsonl,
)

_DATA_DIR = Path(__file__).resolve().parent
_FIXED_TS = datetime(2025, 1, 15, 12, 0, 0)


@dataclass
class BenchmarkGarden:
    """已构建的 benchmark 记忆库。"""

    garden_home: Path
    repository: SQLiteGardenRepository
    gold_count: int
    noise_count: int
    total_memories: int
    noise_ratio: float
    cases: list[BenchmarkCase]
    dataset_name: str = "small"

    def close(self) -> None:
        self.repository.close()


def _data_path(name: str) -> Path:
    return _DATA_DIR / name


def load_gold_memories() -> list[dict[str, Any]]:
    return json.loads(_data_path("gold_memories.json").read_text(encoding="utf-8"))


def load_noise_templates() -> list[dict[str, Any]]:
    return json.loads(_data_path("noise_templates.json").read_text(encoding="utf-8"))


def load_cases() -> list[BenchmarkCase]:
    return load_cases_jsonl()


def compute_noise_count(gold_count: int, noise_ratio: float) -> int:
    if not 0.0 <= noise_ratio < 1.0:
        raise ValueError("noise_ratio must be in [0, 1)")
    if gold_count <= 0:
        return 0
    return round(gold_count * noise_ratio / (1.0 - noise_ratio))


def _memory_card_from_spec(spec: dict[str, Any], *, memory_id: str) -> MemoryCard:
    memory_type = MemoryType(spec.get("memory_type", "unknown"))
    title = spec["title"]
    essence = spec["essence"]
    return MemoryCard(
        id=memory_id,
        title=title,
        essence=essence,
        memory_type=memory_type,
        lifecycle=MemoryLifecycle.bloom,
        tags=list(spec.get("tags", [])),
        fragrance=f"benchmark fragrance for {title}",
        thorns="none",
        confidence=0.8,
        importance=0.6,
        sensitivity=SensitivityLevel.none,
        created_at=_FIXED_TS,
        updated_at=_FIXED_TS,
        last_used_at=_FIXED_TS,
    )


def build_benchmark_garden(
    garden_home: str | Path,
    *,
    noise_ratio: float = 0.85,
    gold_specs: list[dict[str, Any]] | None = None,
    noise_templates: list[dict[str, Any]] | None = None,
    cases: list[BenchmarkCase] | None = None,
    reindex: bool = True,
    dataset_name: str = "small",
) -> BenchmarkGarden:
    """写入 gold + noise 记忆并可选重建 FTS5 索引。"""
    spec = DATASET_SPECS.get(dataset_name)
    if spec is not None:
        noise_count = spec.noise_count
        target_gold = spec.gold_count
    else:
        target_gold = None
        noise_count = None

    home = initialize_garden_home(garden_home)
    db_path = home.root / "garden.db"
    repo = SQLiteGardenRepository(str(db_path))

    base_gold = gold_specs if gold_specs is not None else load_gold_memories()
    if target_gold is not None:
        gold_specs = expand_gold_specs(base_gold, target_gold)
    else:
        gold_specs = list(base_gold)

    noise_templates = noise_templates if noise_templates is not None else load_noise_templates()
    all_cases = cases if cases is not None else load_cases()
    if spec is not None:
        cases = filter_cases_for_dataset(all_cases, spec)
        if noise_count is None:
            noise_count = compute_noise_count(len(gold_specs), noise_ratio)
    else:
        cases = all_cases
        if noise_count is None:
            noise_count = compute_noise_count(len(gold_specs), noise_ratio)

    for item in gold_specs:
        repo.save_memory_card(_memory_card_from_spec(item, memory_id=item["id"]))

    for idx in range(noise_count):
        template = noise_templates[idx % len(noise_templates)]
        noise_id = f"bench-noise-{idx + 1:04d}"
        repo.save_memory_card(_memory_card_from_spec(template, memory_id=noise_id))

    if reindex:
        reindex_garden(home.root, dry_run=False)

    total = len(gold_specs) + noise_count
    ratio = noise_count / total if total else 0.0
    return BenchmarkGarden(
        garden_home=home.root,
        repository=repo,
        gold_count=len(gold_specs),
        noise_count=noise_count,
        total_memories=total,
        noise_ratio=ratio,
        cases=cases,
        dataset_name=dataset_name,
    )


def build_mini_benchmark_garden(garden_home: str | Path) -> BenchmarkGarden:
    """微型确定性 fixture：2 gold + 8 noise + 2 queries。"""
    gold_specs = [
        {
            "id": "bench-gold-mini-01",
            "title": "独特偏好 ALPHA",
            "essence": "用户唯一标识 ALPHA 偏好 Python 深色界面",
            "tags": ["alpha", "python"],
            "memory_type": "preference",
        },
        {
            "id": "bench-gold-mini-02",
            "title": "独特偏好 BETA",
            "essence": "用户唯一标识 BETA 偏好 TypeScript 紧凑布局",
            "tags": ["beta", "typescript"],
            "memory_type": "preference",
        },
    ]
    noise_templates = [
        {
            "title": f"噪声主题 {i}",
            "essence": f"Atlas Zephyr 发布流程 通用噪声 {i}，不涉及特定用户偏好标识",
            "tags": ["noise"],
            "memory_type": "reflection",
        }
        for i in range(1, 9)
    ]
    cases = [
        BenchmarkCase(
            query_id="mini-q1",
            query="独特标识 ALPHA Python",
            relevant_ids=["bench-gold-mini-01"],
        ),
        BenchmarkCase(
            query_id="mini-q2",
            query="独特标识 BETA TypeScript",
            relevant_ids=["bench-gold-mini-02"],
        ),
    ]
    return build_benchmark_garden(
        garden_home,
        noise_ratio=0.8,
        gold_specs=gold_specs,
        noise_templates=noise_templates,
        cases=cases,
        dataset_name="mini",
    )
