"""运行时可调参数树（默认值集中于此，经依赖注入向下传递）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
try:
    from typing import Self
except ImportError:  # pragma: no cover - Python < 3.11 compatibility for local tooling
    from typing_extensions import Self

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetrievalStrategy(str, Enum):
    fts_only = "fts_only"
    fts_with_vector_rescore = "fts_with_vector_rescore"
    full_hybrid = "full_hybrid"

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DEFAULT_PAIRS_PATH = _DATA_DIR / "contradiction_pairs.json"


class CoarseScoreWeights(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    token_overlap_unit: float = Field(default=1.0, ge=0.0)
    tag_match_bonus: float = Field(default=1.5, ge=0.0)
    substring_match_bonus: float = Field(default=2.0, ge=0.0)
    local_embedding_threshold: float = Field(default=0.1, ge=0.0, le=1.0)
    local_embedding_weight: float = Field(default=1.0, ge=0.0)


class HarvestScoreWeights(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    lexical: float = Field(default=0.34, ge=0.0, le=1.0)
    tag: float = Field(default=0.26, ge=0.0, le=1.0)
    lens: float = Field(default=0.06, ge=0.0, le=1.0)
    importance: float = Field(default=0.18, ge=0.0, le=1.0)
    confidence: float = Field(default=0.12, ge=0.0, le=1.0)
    base_weak: float = Field(default=0.14, ge=0.0, le=1.0)
    recency_neutral: float = Field(default=0.5, ge=0.0, le=1.0)
    max_lens_hits: int = Field(default=4, ge=0, le=32)


class HarvestPenaltyTier(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    min_chars: int = Field(ge=0)
    multiplier: float = Field(ge=0.0, le=1.0)
    label: str = Field(min_length=1)


class HarvestPenaltyConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    lifecycle_multipliers: dict[str, float] = Field(
        default_factory=lambda: {
            "pruned": 0.32,
            "composted": 0.32,
            "greenhouse": 0.18,
            "fading": 0.88,
            "sprout": 1.0,
            "bloom": 1.0,
            "rooted": 1.0,
        }
    )
    unknown_lifecycle_multiplier: float = Field(default=0.95, ge=0.0, le=1.0)
    thorns_tiers: list[HarvestPenaltyTier] = Field(
        default_factory=lambda: [
            HarvestPenaltyTier(min_chars=800, multiplier=0.86, label="long"),
            HarvestPenaltyTier(min_chars=400, multiplier=0.92, label="medium"),
            HarvestPenaltyTier(min_chars=200, multiplier=0.96, label="light"),
        ]
    )

    @field_validator("lifecycle_multipliers", mode="before")
    @classmethod
    def _coerce_lifecycle_multipliers(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        return {str(k).strip().lower(): float(v) for k, v in value.items() if str(k).strip()}


class RecencyDecayConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    canonical_half_life_days: float = Field(default=3650.0, gt=0.0)
    project_half_life_days: float = Field(default=60.0, gt=0.0)
    default_half_life_days: float = Field(default=180.0, gt=0.0)
    canonical_recency_floor: float = Field(default=0.9, ge=0.0, le=1.0)


class AnnIndexConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    space: str = "cosine"
    ef_construction: int = Field(default=200, ge=1)
    m: int = Field(default=16, ge=2)
    ef: int = Field(default=50, ge=1)
    min_vectors_for_hnsw: int = Field(default=2, ge=1)
    default_dimensions: int = Field(default=128, ge=1)
    max_elements: int = Field(default=10000, ge=16)


class HarvestCollectorConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    max_snippet_chars: int = Field(default=160, ge=16, le=4096)
    max_matched_terms: int = Field(default=32, ge=1, le=512)
    min_full_query_chars: int = Field(default=2, ge=1, le=64)
    min_ascii_token_chars: int = Field(default=2, ge=1, le=64)


class BouquetPlacementConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    core_pool_min_relevance: float = Field(default=0.25, ge=0.0, le=1.0)
    caution_max_relevance: float = Field(default=0.12, ge=0.0, le=1.0)
    thorns_caution_min_chars: int = Field(default=400, ge=0, le=100_000)
    core_quota: int = Field(default=3, ge=0, le=256)
    min_token_estimate: int = Field(default=8, ge=0, le=10_000)
    token_estimate_chars_per_token: int = Field(default=4, ge=1, le=256)
    token_estimate_overhead: int = Field(default=4, ge=0, le=10_000)
    caution_lifecycles: list[str] = Field(
        default_factory=lambda: ["greenhouse", "pruned", "composted"]
    )


class ConflictDetectionConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    pair_score: float = Field(default=0.3, ge=0.0)
    conflict_threshold: float = Field(default=0.5, ge=0.0)
    embedding_similarity_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    embedding_boost: float = Field(default=0.25, ge=0.0)
    duplicate_token_overlap: int = Field(default=4, ge=1)
    pairs_file: Path | None = Field(default=None, description="JSON 词对文件路径；None 使用内置默认")
    extra_pairs: list[tuple[str, str]] = Field(default_factory=list)

    @field_validator("extra_pairs", mode="before")
    @classmethod
    def _coerce_pairs(cls, value: object) -> list[tuple[str, str]]:
        if not value:
            return []
        out: list[tuple[str, str]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((str(item[0]), str(item[1])))
        return out


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    scan_limit: int = Field(default=500, ge=1, le=100_000)
    coarse_top_m: int = Field(default=200, ge=1, le=1000)
    strategy: RetrievalStrategy = Field(default=RetrievalStrategy.fts_with_vector_rescore)
    vector_top_n: int = Field(default=120, ge=1, le=10_000, description="Max vectors to load/compare per query")
    score_top_n: int = Field(default=60, ge=5, le=1000, description="Max FTS candidates to run full scoring on")


class RetrievalFusionWeights(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    fts: float = Field(default=0.55, ge=0.0)
    lexical: float = Field(default=0.20, ge=0.0)
    applicability: float = Field(default=0.20, ge=0.0)
    recency_policy: float = Field(default=0.05, ge=0.0)
    embedding: float = Field(default=0.25, ge=0.0)
    vector_recall_bonus: float = Field(default=0.15, ge=0.0)


class ReindexConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    fts_batch_size: int = Field(default=500, ge=1, le=10_000)


class CjkScriptConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    codepoint_ranges: list[tuple[int, int]] = Field(
        default_factory=lambda: [
            (0x3400, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
            (0x3040, 0x309F),
            (0x30A0, 0x30FF),
            (0xAC00, 0xD7AF),
        ]
    )

    @field_validator("codepoint_ranges", mode="before")
    @classmethod
    def _coerce_ranges(cls, value: object) -> list[tuple[int, int]]:
        if not value:
            return []
        out: list[tuple[int, int]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((int(item[0]), int(item[1])))
        return out


class LocalEmbeddingConfig(BaseModel):
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        protected_namespaces=(),
    )

    model_name: str = Field(default="BAAI/bge-small-zh-v1.5")
    device: str = Field(default="cpu", description="cpu 或 cuda")
    normalize: bool = Field(default=True)
    batch_size: int = Field(default=32, ge=1, le=512)


class HarvestSubsystemConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    scoring: HarvestScoreWeights = Field(default_factory=HarvestScoreWeights)
    recency: RecencyDecayConfig = Field(default_factory=RecencyDecayConfig)
    ann: AnnIndexConfig = Field(default_factory=AnnIndexConfig)
    coarse: CoarseScoreWeights = Field(default_factory=CoarseScoreWeights)
    collector: HarvestCollectorConfig = Field(default_factory=HarvestCollectorConfig)
    bouquet: BouquetPlacementConfig = Field(default_factory=BouquetPlacementConfig)
    penalties: HarvestPenaltyConfig = Field(default_factory=HarvestPenaltyConfig)


class GardenRuntimeConfig(BaseModel):
    """统一运行时配置入口。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    harvest: HarvestSubsystemConfig = Field(default_factory=HarvestSubsystemConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    retrieval_fusion: RetrievalFusionWeights = Field(default_factory=RetrievalFusionWeights)
    conflict: ConflictDetectionConfig = Field(default_factory=ConflictDetectionConfig)
    reindex: ReindexConfig = Field(default_factory=ReindexConfig)
    cjk: CjkScriptConfig = Field(default_factory=CjkScriptConfig)
    embedding: LocalEmbeddingConfig = Field(default_factory=LocalEmbeddingConfig)

    @classmethod
    def default(cls) -> Self:
        return cls()


def default_garden_runtime_config() -> GardenRuntimeConfig:
    return GardenRuntimeConfig.default()


@lru_cache(maxsize=4)
def load_contradiction_pairs(path: str | None = None) -> tuple[tuple[str, str], ...]:
    """从 JSON 文件加载对立词对；路径为空时使用包内默认文件。"""
    file_path = Path(path) if path else _DEFAULT_PAIRS_PATH
    if not file_path.is_file():
        return ()
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    pairs = raw.get("pairs", raw) if isinstance(raw, dict) else raw
    if not isinstance(pairs, list):
        return ()
    out: list[tuple[str, str]] = []
    for item in pairs:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            out.append((str(item[0]), str(item[1])))
    return tuple(out)


def resolved_contradiction_pairs(config: ConflictDetectionConfig) -> tuple[tuple[str, str], ...]:
    """合并文件词对与配置注入的 extra_pairs。"""
    base = load_contradiction_pairs(
        str(config.pairs_file) if config.pairs_file is not None else None
    )
    if not config.extra_pairs:
        return base
    seen: set[tuple[str, str]] = set(base)
    merged = list(base)
    for pair in config.extra_pairs:
        if pair not in seen:
            seen.add(pair)
            merged.append(pair)
    return tuple(merged)
