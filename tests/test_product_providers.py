import pytest

from memory_garden.providers import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeRerankerProvider,
    ProviderCallContext,
    ProviderPolicy,
    ProviderPolicyError,
    ProviderRegistry,
    RerankCandidate,
    cognition_from_product_registry,
)
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden
from memory_garden.cognition.providers import EmbeddingProvider as CognitionEmbeddingProvider
from memory_garden.harvest.interfaces import EmbeddingProvider as HarvestEmbeddingProvider
from memory_garden.harvest.interfaces import LLMProvider as HarvestLLMProvider
from memory_garden.providers.base import EmbeddingProvider as ProductEmbeddingProvider
from memory_garden.providers.base import LLMProvider as ProductLLMProvider


class _RemoteLLM(FakeLLMProvider):
    name = "remote-llm"
    is_remote = True


class _RemoteEmbedding(FakeEmbeddingProvider):
    name = "remote-embedding"
    is_remote = True


class _RemoteReranker(FakeRerankerProvider):
    name = "remote-reranker"
    is_remote = True


def test_provider_registry_blocks_remote_by_default():
    registry = ProviderRegistry(llm=_RemoteLLM())

    with pytest.raises(ProviderPolicyError):
        registry.optional_llm()


def test_provider_registry_allows_explicit_remote_opt_in():
    registry = ProviderRegistry(policy=ProviderPolicy(allow_remote_llm=True), llm=_RemoteLLM())

    assert registry.optional_llm().name == "remote-llm"


def test_fake_providers_are_deterministic_and_schema_compatible():
    ctx = ProviderCallContext(purpose="memory_extraction", garden_home="/tmp/garden")
    llm = FakeLLMProvider()
    data = llm.complete_json(system="extract", user="remember: prefer dark mode", schema={}, context=ctx).data
    assert data["proposals"][0]["tags"] == ["provider_generated"]

    embedding = FakeEmbeddingProvider()
    vectors = embedding.embed_texts(["dark mode", "light mode"], context=ctx)
    assert vectors.dimensions > 0
    assert len(vectors.vectors) == 2

    reranker = FakeRerankerProvider()
    ranked = reranker.rerank(
        query="dark dashboard",
        candidates=[
            RerankCandidate(id="a", text="dark dashboard preference"),
            RerankCandidate(id="b", text="unrelated note"),
        ],
        top_k=1,
        context=ProviderCallContext(purpose="memory_rerank"),
    )
    assert ranked.ranked_ids == ["a"]


def test_canonical_fake_providers_satisfy_legacy_protocol_shapes():
    llm = FakeLLMProvider()
    embedding = FakeEmbeddingProvider()

    assert isinstance(llm, ProductLLMProvider)
    assert isinstance(llm, HarvestLLMProvider)
    assert isinstance(embedding, ProductEmbeddingProvider)
    assert isinstance(embedding, HarvestEmbeddingProvider)
    assert isinstance(embedding, CognitionEmbeddingProvider)
    assert embedding.embed_texts(["x"])[0]


def test_product_provider_calls_require_raw_text_policy(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        product = ProductMemorySystem(
            garden_home=garden.home.root,
            repository=garden.core.repository,
            providers=ProviderRegistry(llm=FakeLLMProvider()),
        )

        with pytest.raises(ProviderPolicyError):
            product.propose("remember: prefer dark mode")

        allowed = ProductMemorySystem(
            garden_home=garden.home.root,
            repository=garden.core.repository,
            providers=ProviderRegistry(policy=ProviderPolicy(allow_raw_user_text=True), llm=FakeLLMProvider()),
        )
        assert allowed.propose("remember: prefer dark mode")[0].source == "fake-llm"
    finally:
        garden.close()


def test_cognition_embedding_bridge_requires_raw_text_policy() -> None:
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=False, allow_remote_embeddings=True),
        embedding=_RemoteEmbedding(),
    )

    bridge = cognition_from_product_registry(providers, garden_home="/tmp/garden")["emb_provider"]

    with pytest.raises(ProviderPolicyError):
        bridge.embed_texts(["dark mode", "release checklist"])


def test_cognition_reranker_bridge_requires_raw_text_policy() -> None:
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=False, allow_remote_rerank=True),
        reranker=_RemoteReranker(),
    )

    bridge = cognition_from_product_registry(providers, garden_home="/tmp/garden")["rank_provider"]

    with pytest.raises(ProviderPolicyError):
        bridge.rerank(
            "dark mode",
            [
                type(
                    "HC",
                    (),
                    {
                        "memory_id": "mem-1",
                        "text": "User prefers dark dashboards.",
                        "source_ids": ["mem-1"],
                    },
                )(),
            ],
        )
