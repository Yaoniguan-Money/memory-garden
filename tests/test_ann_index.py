"""ANN 向量索引单元测试。"""

from __future__ import annotations

import pytest

from memory_garden.harvest.ann_index import HAS_HNSWLIB, AnnVectorIndex
from memory_garden.harvest.local_embedding import embed_local


def test_empty_index_brute_force_fallback():
    index = AnnVectorIndex(dimensions=128)
    query = embed_local("alpha query")
    assert index.search(query, k=5) == []


def test_batch_add_and_search_returns_best_match():
    index = AnnVectorIndex(dimensions=128)
    target_vec = embed_local("unique target memory about gardening")
    noise_vec = embed_local("unrelated finance quarterly report")
    index.add_batch(
        {
            "mem-target": target_vec,
            "mem-noise": noise_vec,
        }
    )
    query = embed_local("gardening target memory")
    hits = index.search(query, k=2)
    assert hits
    assert hits[0][0] == "mem-target"
    assert hits[0][1] >= hits[1][1]


def test_clear_resets_index():
    index = AnnVectorIndex(dimensions=128)
    index.add("a", embed_local("hello world"))
    assert index.size == 1
    index.clear()
    assert index.size == 0
    assert index.search(embed_local("hello"), k=3) == []


def test_dimension_mismatch_falls_back_to_brute_force():
    index = AnnVectorIndex(dimensions=64)
    index.add("a", [1.0] * 128)
    hits = index.search([1.0] * 128, k=1)
    assert hits
    assert hits[0][0] == "a"
    assert not index.is_hnsw


@pytest.mark.skipif(not HAS_HNSWLIB, reason="hnswlib optional")
def test_hnsw_path_when_installed():
    index = AnnVectorIndex(dimensions=128)
    index.add_batch(
        {
            "x": embed_local("dog park walk"),
            "y": embed_local("database migration sql"),
        }
    )
    index._ensure_built()
    assert index.is_hnsw
    hits = index.search(embed_local("walking in the park"), k=1)
    assert hits[0][0] == "x"
