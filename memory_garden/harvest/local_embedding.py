"""Local, deterministic text embedding — zero dependencies, no API keys.

This is NOT a neural embedding.  It is a character n-gram hash based
vector that produces *semantically looser* but *deterministic and local*
representations.  It makes ``search_garden()`` work with approximate
matching when keyword FTS5 misses.

When a real ``EmbeddingProvider`` is configured, that takes precedence.
This module provides the fallback.
"""

from __future__ import annotations

import hashlib


def _ngrams(text: str, n: int = 3) -> list[str]:
    """Yield character n-grams, padded with spaces at edges."""
    padded = "  " + text.lower().strip() + "  "
    return [padded[i : i + n] for i in range(len(padded) - n + 1)]


def embed_local(text: str, *, dimensions: int = 128) -> list[float]:
    """Produce a fixed-size deterministic vector for *text*.

    Uses character n-gram hashing into *dimensions* buckets, then
    L2-normalizes the result.  The same text always produces the same
    vector on any machine.

    This is a baseline, not a semantic model.  For production-quality
    embeddings, plug in a real ``EmbeddingProvider``.
    """
    if not text or not text.strip():
        return [0.0] * dimensions

    ngrams_3 = _ngrams(text, 3)
    ngrams_4 = _ngrams(text, 4)

    # Accumulate into buckets via hash
    buckets = [0.0] * dimensions
    for ng in ngrams_3:
        h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
        buckets[h % dimensions] += 0.6  # 3-grams weight
    for ng in ngrams_4:
        h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
        buckets[h % dimensions] += 0.4  # 4-grams weight

    # L2 normalize
    norm = sum(v * v for v in buckets) ** 0.5
    if norm > 0:
        return [v / norm for v in buckets]
    return buckets


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
