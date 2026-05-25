"""Tests for local, deterministic embedding."""

from memory_garden.harvest.local_embedding import (
    cosine_similarity,
    embed_local,
    _ngrams,
)


def test_ngrams_are_deterministic():
    assert _ngrams("hello") == _ngrams("hello")


def test_embedding_is_deterministic():
    v1 = embed_local("test text")
    v2 = embed_local("test text")
    assert v1 == v2


def test_embedding_has_requested_dimensions():
    v = embed_local("test", dimensions=64)
    assert len(v) == 64


def test_similar_texts_have_higher_similarity():
    v1 = embed_local("I prefer dark mode")
    v2 = embed_local("I like dark themes")
    v3 = embed_local("banana smoothie recipe")
    sim_12 = cosine_similarity(v1, v2)
    sim_13 = cosine_similarity(v1, v3)
    assert sim_12 > sim_13, f"similar={sim_12:.3f}, dissimilar={sim_13:.3f}"


def test_identical_texts_have_max_similarity():
    v1 = embed_local("hello world")
    v2 = embed_local("hello world")
    assert cosine_similarity(v1, v2) > 0.99


def test_embedding_is_normalized():
    v = embed_local("some random text for testing purposes")
    norm = sum(x * x for x in v) ** 0.5
    assert 0.99 < norm < 1.01, f"norm={norm:.6f}"


def test_empty_text_returns_zero_vector():
    v = embed_local("")
    assert len(v) == 128
    assert all(x == 0.0 for x in v)


def test_short_text_works():
    v = embed_local("hi")
    assert len(v) == 128
    assert any(x != 0.0 for x in v)


def test_cosine_similarity_different_lengths():
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_cosine_similarity_zero_vectors():
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
