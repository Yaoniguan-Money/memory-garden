from __future__ import annotations

from types import SimpleNamespace

from memory_garden.providers import (
    FakeEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleRerankerProvider,
    ProviderCallContext,
    ProviderPolicy,
    ProviderRegistry,
    RerankCandidate,
)
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden


class _ChatCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage={"total_tokens": 9},
        )


class _Embeddings:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[1.0, 0.0, 0.0]),
                SimpleNamespace(embedding=[0.0, 1.0, 0.0]),
            ],
            usage={"total_tokens": 2},
        )


class _Client:
    def __init__(self, content: str = '{"ok": true}') -> None:
        self._chat_completions = _ChatCompletions(content)
        self._embeddings = _Embeddings()
        self.chat = SimpleNamespace(completions=self._chat_completions)
        self.embeddings = self._embeddings


class _RemoteEmbedding(FakeEmbeddingProvider):
    name = "remote-test-embedding"
    is_remote = True


def test_openai_compatible_llm_returns_json_object() -> None:
    client = _Client('{"proposals": [{"title": "Dark mode", "essence": "Prefers dark mode"}]}')
    provider = OpenAICompatibleLLMProvider(model="test-chat", client=client)

    result = provider.complete_json(
        system="extract",
        user="remember: prefer dark mode",
        schema={"type": "object"},
        context=ProviderCallContext(purpose="memory_extraction", provider_kind="llm"),
    )

    assert result.data["proposals"][0]["title"] == "Dark mode"
    assert client._chat_completions.calls[0]["response_format"] == {"type": "json_object"}


def test_openai_compatible_embedding_provider_parses_vectors() -> None:
    client = _Client()
    provider = OpenAICompatibleEmbeddingProvider(model="test-embed", client=client)

    result = provider.embed_texts(
        ["query", "memory"],
        context=ProviderCallContext(purpose="memory_embedding_retrieval", provider_kind="embedding"),
    )

    assert result.vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert result.dimensions == 3
    assert client._embeddings.calls[0]["model"] == "test-embed"


def test_openai_compatible_reranker_filters_unknown_ids() -> None:
    client = _Client('{"ranked_ids": ["missing", "b", "a"], "scores": {"b": 0.9, "missing": 1.0}}')
    llm = OpenAICompatibleLLMProvider(model="test-chat", client=client)
    provider = OpenAICompatibleRerankerProvider(llm=llm)

    result = provider.rerank(
        query="dark mode",
        candidates=[
            RerankCandidate(id="a", text="light mode"),
            RerankCandidate(id="b", text="dark mode"),
        ],
        top_k=2,
        context=ProviderCallContext(purpose="memory_rerank", provider_kind="reranker"),
    )

    assert result.ranked_ids == ["b", "a"]
    assert result.scores == {"b": 0.9}


def test_remote_embedding_policy_is_independent_from_remote_llm_policy(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        product = ProductMemorySystem(
            garden_home=garden.home.root,
            repository=garden.core.repository,
            providers=ProviderRegistry(
                policy=ProviderPolicy(
                    allow_raw_user_text=True,
                    allow_remote_embeddings=True,
                    allow_remote_llm=False,
                ),
                embedding=_RemoteEmbedding(),
            ),
        )
        proposal = product.propose("remember: prefer dark mode dashboards")[0]
        card = product.approve(proposal.id)

        result = product.retrieve("dark mode dashboard")

        assert result.hits
        assert result.hits[0].memory.id == card.id
    finally:
        garden.close()
