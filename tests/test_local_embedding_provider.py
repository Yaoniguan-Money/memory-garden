"""本地 sentence-transformers 嵌入 Provider 测试。"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("sentence_transformers")

from memory_garden.harvest.local_embedding import cosine_similarity
from memory_garden.providers.local_embedding import SentenceTransformersEmbeddingProvider
from memory_garden.runtime_config import LocalEmbeddingConfig

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMORY_GARDEN_RUN_REAL_EMBEDDINGS") != "1",
    reason="real sentence-transformers model tests are opt-in and may download models",
)


@pytest.fixture(scope="module")
def provider() -> SentenceTransformersEmbeddingProvider:
    cfg = LocalEmbeddingConfig(model_name="BAAI/bge-small-zh-v1.5", device="cpu", batch_size=8)
    return SentenceTransformersEmbeddingProvider(config=cfg)


def test_semantic_similarity_cat_preference(provider: SentenceTransformersEmbeddingProvider) -> None:
    vectors = provider.embed_texts(["我喜欢猫", "我对猫有好感"])
    sim = cosine_similarity(vectors[0], vectors[1])
    assert sim > 0.7


def test_semantic_dissimilarity(provider: SentenceTransformersEmbeddingProvider) -> None:
    vectors = provider.embed_texts(["我喜欢猫", "今天天气不错"])
    sim = cosine_similarity(vectors[0], vectors[1])
    assert sim < 0.5


def test_batch_embedding_dimensions(provider: SentenceTransformersEmbeddingProvider) -> None:
    texts = [f"测试句子 {i}" for i in range(50)]
    vectors = provider.embed_texts(texts)
    assert len(vectors) == 50
    assert all(len(vec) == 512 for vec in vectors)


def test_import_error_message_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "memory_garden.providers.local_embedding.HAS_SENTENCE_TRANSFORMERS",
        False,
        raising=False,
    )
    with pytest.raises(ImportError, match="sentence-transformers"):
        SentenceTransformersEmbeddingProvider()
