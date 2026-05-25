"""Feature-based product retrieval scoring.

The Product layer keeps policy decisions auditable while preserving strong
coarse-recall signals such as FTS rank and optional vector similarity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from memory_garden.core.models import MemoryCard
from memory_garden.product.models import ApplicabilityDecision, MemoryStrategyProfile
from memory_garden.runtime_config import RetrievalFusionWeights, default_garden_runtime_config


@dataclass(frozen=True)
class RetrievalFeatureVector:
    memory_id: str
    fts_score: float
    lexical_score: float
    applicability_score: float
    recency_policy_score: float
    embedding_score: float = 0.0
    vector_recall: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "fts_score": round(self.fts_score, 6),
            "lexical_score": round(self.lexical_score, 6),
            "applicability_score": round(self.applicability_score, 6),
            "recency_policy_score": round(self.recency_policy_score, 6),
            "embedding_score": round(self.embedding_score, 6),
            "vector_recall": self.vector_recall,
        }


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_lexical(score: float) -> float:
    return clamp01(score / 6.0)


def recency_policy_score(
    card: MemoryCard,
    profile: MemoryStrategyProfile,
    *,
    now: datetime | None = None,
) -> float:
    score = 0.5
    if card.importance is not None:
        score += (clamp01(float(card.importance)) - 0.5) * 0.25
    score += (profile.strength - 0.5) * 0.25
    updated = card.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    _now = now if now is not None else datetime.now(timezone.utc)
    age_days = max(0.0, (_now - updated).total_seconds() / 86400.0)
    score += max(0.0, 1.0 - age_days / 365.0) * 0.25
    return clamp01(score)


def fts_score_from_metadata(meta: dict[str, object]) -> float:
    value = meta.get("fts_position_score")
    if isinstance(value, (int, float)):
        return clamp01(float(value))
    position = meta.get("fts_position")
    if isinstance(position, int):
        return clamp01(1.0 / float(position + 1))
    return 0.0


def is_hard_block(decision: ApplicabilityDecision) -> bool:
    risks = set(decision.risk_flags)
    if "memory_is_archived" in decision.reasons:
        return True
    if "sensitive_memory_blocked_for_context" in risks:
        return True
    if any(risk.startswith("scope_") for risk in risks):
        return True
    return False


def build_feature_vector(
    *,
    card: MemoryCard,
    profile: MemoryStrategyProfile,
    decision: ApplicabilityDecision,
    lexical_score: float,
    source_metadata: dict[str, object],
    embedding_score: float = 0.0,
    now: datetime | None = None,
) -> RetrievalFeatureVector:
    return RetrievalFeatureVector(
        memory_id=card.id,
        fts_score=fts_score_from_metadata(source_metadata),
        lexical_score=normalize_lexical(lexical_score),
        applicability_score=clamp01(float(decision.score)),
        recency_policy_score=recency_policy_score(card, profile, now=now),
        embedding_score=clamp01(embedding_score),
        vector_recall=source_metadata.get("candidate_source") == "vector"
        or bool(source_metadata.get("vector_recall")),
    )


def score_feature_vector(
    features: RetrievalFeatureVector,
    *,
    weights: RetrievalFusionWeights | None = None,
) -> tuple[float, list[str]]:
    w = weights or default_garden_runtime_config().retrieval_fusion
    total = (
        features.fts_score * w.fts
        + features.lexical_score * w.lexical
        + features.applicability_score * w.applicability
        + features.recency_policy_score * w.recency_policy
        + features.embedding_score * w.embedding
    )
    if features.vector_recall:
        total += w.vector_recall_bonus
    notes = [
        f"feature:fts={features.fts_score:.4f}",
        f"feature:lexical={features.lexical_score:.4f}",
        f"feature:applicability={features.applicability_score:.4f}",
        f"feature:recency_policy={features.recency_policy_score:.4f}",
    ]
    if features.embedding_score > 0.0:
        notes.append(f"feature:embedding={features.embedding_score:.4f}")
    if features.vector_recall:
        notes.append("feature:vector_recall_bonus")
    return total, notes
