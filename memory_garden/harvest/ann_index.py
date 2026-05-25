"""Harvest 语义检索可选 ANN 向量索引（hnswlib 为 optional 依赖）。"""

from __future__ import annotations

import logging
from typing import Any

from memory_garden.runtime_config import AnnIndexConfig, default_garden_runtime_config

logger = logging.getLogger(__name__)

try:
    import hnswlib

    HAS_HNSWLIB = True
except ImportError:
    HAS_HNSWLIB = False


class AnnVectorIndex:
    """内存 HNSW 向量索引；不可用时回退 O(n) cosine。"""

    def __init__(
        self,
        dimensions: int | None = None,
        max_elements: int | None = None,
        *,
        config: AnnIndexConfig | None = None,
    ) -> None:
        cfg = config or default_garden_runtime_config().harvest.ann
        self._config = cfg
        self._dimensions = dimensions if dimensions is not None else cfg.default_dimensions
        self._max_elements = max_elements if max_elements is not None else cfg.max_elements
        self._index: Any = None
        self._id_to_vector: dict[str, list[float]] = {}
        self._id_list: list[str] = []
        self._built = False

    def add(self, memory_id: str, vector: list[float]) -> None:
        self._id_to_vector[memory_id] = vector
        self._built = False

    def add_batch(self, items: dict[str, list[float]]) -> None:
        self._id_to_vector.update(items)
        self._built = False

    def _ensure_built(self) -> None:
        if self._built:
            return
        cfg = self._config
        if not HAS_HNSWLIB or len(self._id_to_vector) < cfg.min_vectors_for_hnsw:
            self._built = True
            return
        ids = list(self._id_to_vector.keys())
        vectors = [self._id_to_vector[mid] for mid in ids]
        n = len(ids)
        dim = len(vectors[0]) if vectors else self._dimensions
        if dim != self._dimensions:
            logger.warning("ANN dimension %d != expected %d, falling back", dim, self._dimensions)
            self._built = True
            return
        try:
            self._index = hnswlib.Index(space=cfg.space, dim=dim)
            self._index.init_index(
                max_elements=max(n, 16),
                ef_construction=cfg.ef_construction,
                M=cfg.m,
            )
            self._index.add_items(vectors, list(range(n)))
            self._index.set_ef(cfg.ef)
            self._id_list = ids
            self._built = True
        except Exception as exc:
            logger.warning("ANN build failed (%s), falling back to O(n)", exc)
            self._built = True

    def search(self, query_vector: list[float], k: int = 10) -> list[tuple[str, float]]:
        """返回 (memory_id, similarity) 列表，按相似度降序。"""
        self._ensure_built()
        if self._index is not None and self._built and HAS_HNSWLIB and self._id_list:
            try:
                labels, distances = self._index.knn_query([query_vector], k=min(k, len(self._id_list)))
                scores = [1.0 - float(d) for d in distances[0]]
                return [(self._id_list[int(label)], score) for label, score in zip(labels[0], scores)]
            except Exception as exc:
                logger.warning("ANN search failed (%s), falling back", exc)

        from memory_garden.harvest.local_embedding import cosine_similarity

        scored: list[tuple[str, float]] = []
        for mid, vec in self._id_to_vector.items():
            sim = cosine_similarity(query_vector, vec)
            scored.append((mid, sim))
        scored.sort(key=lambda item: -item[1])
        return scored[:k]

    def clear(self) -> None:
        self._id_to_vector.clear()
        self._index = None
        self._id_list = []
        self._built = False

    @property
    def size(self) -> int:
        return len(self._id_to_vector)

    @property
    def is_hnsw(self) -> bool:
        return self._index is not None and HAS_HNSWLIB
