"""Tests for provider interfaces (LLM, Embedding, Reranker ABCs)."""

import pytest

from memory_garden.integrations.providers import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    ProviderRegistry,
    RelevanceProvider,
)


class _FakeLLM(LLMProvider):
    def __init__(self, model="fake"):
        self._config = ProviderConfig(provider="fake", model=model)

    def structured_generate(self, prompt, schema, *, system="", **kwargs):
        return {"response": "fake"}

    @property
    def config(self):
        return self._config


class _FakeEmbedding(EmbeddingProvider):
    def embed(self, text):
        return [0.1] * 8

    def embed_batch(self, texts):
        return [[0.1] * 8 for _ in texts]

    @property
    def config(self):
        return ProviderConfig(provider="fake", model="fake-embed")

    @property
    def dimensions(self):
        return 8


class _FakeRelevance(RelevanceProvider):
    def score(self, query, candidates):
        return [0.5] * len(candidates)

    @property
    def config(self):
        return ProviderConfig(provider="fake", model="fake-relevance")


def test_llm_provider_is_abstract():
    import inspect
    assert inspect.isabstract(LLMProvider)


def test_embedding_provider_is_abstract():
    import inspect
    assert inspect.isabstract(EmbeddingProvider)


def test_relevance_provider_is_abstract():
    import inspect
    assert inspect.isabstract(RelevanceProvider)


def test_fake_llm_satisfies_protocol():
    provider = _FakeLLM()
    result = provider.structured_generate("hello", dict, system="be helpful")
    assert isinstance(result, dict)
    assert provider.config.provider == "fake"


def test_fake_embedding_satisfies_protocol():
    provider = _FakeEmbedding()
    vec = provider.embed("test")
    assert len(vec) == 8
    assert provider.dimensions == 8
    batch = provider.embed_batch(["a", "b"])
    assert len(batch) == 2


def test_fake_relevance_satisfies_protocol():
    provider = _FakeRelevance()
    scores = provider.score("query", ["a", "b", "c"])
    assert len(scores) == 3
    assert provider.config.model == "fake-relevance"


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def test_provider_registry_empty():
    reg = ProviderRegistry()
    assert reg.llm is None
    assert reg.has_llm is False
    assert reg.has_embedding is False
    assert reg.has_relevance is False


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def test_provider_registry_with_llm():
    llm = _FakeLLM()
    reg = ProviderRegistry(llm=llm)
    assert reg.has_llm is True
    assert reg.has_embedding is False


@pytest.mark.filterwarnings('ignore::DeprecationWarning')
def test_provider_registry_full():
    reg = ProviderRegistry(llm=_FakeLLM(), embedding=_FakeEmbedding(), relevance=_FakeRelevance())
    assert reg.has_llm and reg.has_embedding and reg.has_relevance


def test_provider_config():
    cfg = ProviderConfig(provider="openai", model="gpt-4", api_base_url="https://api.openai.com")
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4"
