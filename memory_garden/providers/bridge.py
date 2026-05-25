"""Provider bridge adapters between product providers and cognition protocols."""

from __future__ import annotations

from typing import Any

from memory_garden.cognition.models import HarvestCandidate, HarvestRerankResult
from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.errors import ProviderPolicyError
from memory_garden.providers.registry import ProviderRegistry
from memory_garden.providers.schemas import RerankCandidate


class ProductEmbeddingToCognition:
    """Expose a product embedding provider through the cognition embed_texts shape."""

    def __init__(self, provider: Any, *, garden_home: str = "", policy: Any | None = None) -> None:
        self.provider = provider
        self.garden_home = garden_home
        self.policy = policy

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        context = ProviderCallContext(
            purpose="cognition_embedding",
            provider_kind="embedding",
            garden_home=self.garden_home,
            allow_remote=bool(getattr(self.provider, "is_remote", False)),
        )
        _assert_bridge_call_allowed(self.policy, context, "\n".join(texts), "embedding")
        result = self.provider.embed_texts(texts, context=context)
        return list(getattr(result, "vectors", result))


class ProductRerankerToCognition:
    """Expose a product reranker provider through the cognition reranker shape."""

    def __init__(self, provider: Any, *, garden_home: str = "", policy: Any | None = None) -> None:
        self.provider = provider
        self.garden_home = garden_home
        self.policy = policy

    def rerank(
        self,
        query: str,
        candidates: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> HarvestRerankResult:
        top_k = int(getattr(policy, "max_candidates", len(candidates)) or len(candidates) or 1)
        context = ProviderCallContext(
            purpose="cognition_rerank",
            provider_kind="reranker",
            garden_home=self.garden_home,
            allow_remote=bool(getattr(self.provider, "is_remote", False)),
        )
        _assert_bridge_call_allowed(
            self.policy,
            context,
            "\n".join([query, *[c.text for c in candidates]]),
            "reranker",
        )
        result = self.provider.rerank(
            query=query,
            candidates=[
                RerankCandidate(id=c.memory_id, text=c.text, metadata={"source_ids": list(c.source_ids)})
                for c in candidates
            ],
            top_k=top_k,
            context=context,
        )
        by_id = {c.memory_id: c for c in candidates}
        ranked: list[HarvestCandidate] = []
        seen: set[str] = set()
        for mid in getattr(result, "ranked_ids", []):
            if mid in by_id and mid not in seen:
                score = getattr(result, "scores", {}).get(mid)
                ranked.append(by_id[mid].model_copy(update={"rerank_score": score}))
                seen.add(mid)
        for c in candidates:
            if c.memory_id not in seen:
                ranked.append(c)
        return HarvestRerankResult(
            candidates=ranked,
            provider_name=getattr(self.provider, "name", "product_reranker"),
            metadata={"bridge": "ProductRerankerToCognition"},
        )


def cognition_from_product_registry(registry: ProviderRegistry, *, garden_home: str = "") -> dict[str, Any]:
    """Build cognition provider kwargs from the canonical product ProviderRegistry."""
    out: dict[str, Any] = {}
    embedding = registry.optional_embedding()
    if embedding is not None:
        out["emb_provider"] = ProductEmbeddingToCognition(
            embedding,
            garden_home=garden_home,
            policy=registry.policy,
        )
    reranker = registry.optional_reranker()
    if reranker is not None:
        out["rank_provider"] = ProductRerankerToCognition(
            reranker,
            garden_home=garden_home,
            policy=registry.policy,
        )
    return out


def _assert_bridge_call_allowed(policy: Any | None, context: ProviderCallContext, text: str, kind: str) -> None:
    if policy is not None:
        from memory_garden.product.policy import MemoryPolicy

        MemoryPolicy(provider_policy=policy).assert_provider_call_allowed(context, text)
    elif context.allow_remote:
        raise ProviderPolicyError(f"Remote cognition {kind} bridge requires an explicit ProviderPolicy opt-in")


__all__ = [
    "ProductEmbeddingToCognition",
    "ProductRerankerToCognition",
    "cognition_from_product_registry",
]
