"""Calibrate Product retrieval fusion weights on labeled feature rows.

This stays local and deterministic. It can consume a JSON file shaped as:

{
  "queries": [
    {
      "query_id": "q1",
      "candidates": [
        {"memory_id": "m1", "relevance": 3, "features": {"fts_score": 1.0, ...}}
      ]
    }
  ]
}

When no file is provided, a tiny built-in fixture validates the calibration
path. The output can be copied into ``GardenRuntimeConfig.retrieval_fusion``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FusionWeights:
    fts: float
    lexical: float
    applicability: float
    recency_policy: float
    embedding: float
    vector_recall_bonus: float


DEFAULT_DATASET = {
    "queries": [
        {
            "query_id": "literal",
            "candidates": [
                {
                    "memory_id": "gold-fts",
                    "relevance": 3,
                    "features": {
                        "fts_score": 1.0,
                        "lexical_score": 0.9,
                        "applicability_score": 0.55,
                        "recency_policy_score": 0.6,
                        "embedding_score": 0.2,
                        "vector_recall": False,
                    },
                },
                {
                    "memory_id": "noise-policy",
                    "relevance": 0,
                    "features": {
                        "fts_score": 0.1,
                        "lexical_score": 0.1,
                        "applicability_score": 0.9,
                        "recency_policy_score": 0.8,
                        "embedding_score": 0.1,
                        "vector_recall": False,
                    },
                },
            ],
        },
        {
            "query_id": "semantic",
            "candidates": [
                {
                    "memory_id": "gold-vector",
                    "relevance": 3,
                    "features": {
                        "fts_score": 0.0,
                        "lexical_score": 0.2,
                        "applicability_score": 0.65,
                        "recency_policy_score": 0.55,
                        "embedding_score": 0.92,
                        "vector_recall": True,
                    },
                },
                {
                    "memory_id": "noise-lexical",
                    "relevance": 0,
                    "features": {
                        "fts_score": 0.5,
                        "lexical_score": 0.5,
                        "applicability_score": 0.25,
                        "recency_policy_score": 0.5,
                        "embedding_score": 0.1,
                        "vector_recall": False,
                    },
                },
            ],
        },
    ]
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Labeled feature JSON file")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8")) if args.input else DEFAULT_DATASET
    best_weights, best_score = calibrate(payload, k=args.k)
    print(json.dumps({"ndcg_at_k": round(best_score, 4), "weights": asdict(best_weights)}, indent=2))
    return 0


def calibrate(payload: dict[str, Any], *, k: int) -> tuple[FusionWeights, float]:
    best_weights = None
    best_score = -1.0
    for weights in weight_grid():
        score = mean_ndcg(payload, weights, k=k)
        if score > best_score:
            best_score = score
            best_weights = weights
    assert best_weights is not None
    return best_weights, best_score


def weight_grid():
    for fts, lexical, applicability, embedding in itertools.product(
        [0.45, 0.55, 0.65],
        [0.10, 0.20, 0.30],
        [0.10, 0.20, 0.30],
        [0.15, 0.25, 0.35],
    ):
        yield FusionWeights(
            fts=fts,
            lexical=lexical,
            applicability=applicability,
            recency_policy=0.05,
            embedding=embedding,
            vector_recall_bonus=0.15,
        )


def mean_ndcg(payload: dict[str, Any], weights: FusionWeights, *, k: int) -> float:
    values = []
    for query in payload.get("queries", []):
        candidates = list(query.get("candidates", []))
        ranked = sorted(candidates, key=lambda item: score_candidate(item, weights), reverse=True)
        gains = [float(item.get("relevance", 0.0)) for item in ranked[:k]]
        ideal = sorted((float(item.get("relevance", 0.0)) for item in candidates), reverse=True)[:k]
        values.append(dcg(gains) / dcg(ideal) if dcg(ideal) > 0.0 else 0.0)
    return sum(values) / len(values) if values else 0.0


def score_candidate(item: dict[str, Any], weights: FusionWeights) -> float:
    features = dict(item.get("features") or {})
    score = (
        float(features.get("fts_score", 0.0)) * weights.fts
        + float(features.get("lexical_score", 0.0)) * weights.lexical
        + float(features.get("applicability_score", 0.0)) * weights.applicability
        + float(features.get("recency_policy_score", 0.0)) * weights.recency_policy
        + float(features.get("embedding_score", 0.0)) * weights.embedding
    )
    if features.get("vector_recall"):
        score += weights.vector_recall_bonus
    return score


def dcg(gains: list[float]) -> float:
    return sum((2.0**gain - 1.0) / math.log2(index + 2.0) for index, gain in enumerate(gains))


if __name__ == "__main__":
    raise SystemExit(main())
