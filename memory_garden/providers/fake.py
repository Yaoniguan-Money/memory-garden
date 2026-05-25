"""确定性的本地 fake providers，用于测试与离线产品流程。

这些实现不会访问真实模型或网络。Embedding provider 兼容 product 层带
``ProviderCallContext`` 的调用方式，也兼容 cognition 层直接返回向量列表的调用方式。
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from memory_garden.harvest.local_embedding import embed_local
from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.schemas import (
    EmbeddingResult,
    JsonCompletionResult,
    RerankCandidate,
    RerankResult,
    TextCompletionResult,
)


class FakeLLMProvider:
    """Local deterministic LLMProvider stand-in.

    It is useful for tests and product plumbing. It never calls a model.
    """

    name = "fake-llm"
    is_remote = False

    def complete_text(
        self,
        *,
        system: str,
        user: str,
        context: ProviderCallContext,
    ) -> TextCompletionResult:
        return TextCompletionResult(text=user[:500], model=self.name)

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        context: ProviderCallContext,
    ) -> JsonCompletionResult:
        data: dict[str, Any] = {"text": user[:500], "purpose": context.purpose}
        if context.purpose == "memory_extraction":
            data = {
                "proposals": [
                    {
                        "title": user[:80] or "Untitled memory",
                        "essence": user[:500] or "Empty proposal",
                        "memory_type": "preference",
                        "tags": ["provider_generated"],
                        "confidence": 0.7,
                        "sensitivity": "none",
                        "requires_confirmation": True,
                    }
                ]
            }
        return JsonCompletionResult(data=data, model=self.name)

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        limit = max_tokens if max_tokens is not None else 500
        return prompt[: max(0, limit)]

    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict[str, Any]:
        _ = system, kwargs
        data: dict[str, Any] = {}
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            for name, field in schema.model_fields.items():
                annotation = field.annotation
                if annotation is str:
                    data[name] = ""
                elif annotation is int:
                    data[name] = 0
                elif annotation is float:
                    data[name] = 0.0
                elif annotation is bool:
                    data[name] = False
                elif getattr(annotation, "__origin__", None) is list or annotation is list:
                    data[name] = []
            return data
        return {"text": prompt[:500]}


class FakeEmbeddingProvider:
    """使用 Memory Garden n-gram hashing 的确定性本地 embedding provider。"""

    name = "fake-local-embedding"
    is_remote = False

    def __init__(self, dimensions: int = 128) -> None:
        self._dimensions = dimensions

    def embed_texts(
        self,
        texts: list[str],
        *,
        truncate: bool = True,
        context: ProviderCallContext | None = None,
    ) -> EmbeddingResult | list[list[float]]:
        _ = truncate
        vectors = [embed_local(text, dimensions=self._dimensions) for text in texts]
        if context is None:
            return vectors
        dimensions = len(vectors[0]) if vectors else 0
        return EmbeddingResult(vectors=vectors, model=self.name, dimensions=dimensions)


class FakeRerankerProvider:
    """Local deterministic reranker based on token overlap."""

    name = "fake-reranker"
    is_remote = False

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int,
        context: ProviderCallContext,
    ) -> RerankResult:
        tokens = {t for t in query.casefold().replace("/", " ").split() if t}
        scored: list[tuple[float, str]] = []
        explanations: dict[str, list[str]] = {}
        for candidate in candidates:
            body = candidate.text.casefold()
            hits = sorted(t for t in tokens if t in body)
            score = float(len(hits))
            if query.casefold().strip() and query.casefold().strip() in body:
                score += 2.0
                hits.append("phrase_match")
            scored.append((score, candidate.id))
            explanations[candidate.id] = [f"token:{h}" for h in hits]
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        ranked = [cid for score, cid in scored if score > 0][: max(1, top_k)]
        return RerankResult(
            ranked_ids=ranked,
            scores={cid: score for score, cid in scored},
            explanations=explanations,
            model=self.name,
        )


class EnvSecretProvider:
    """Secret provider backed by environment variables."""

    name = "environment"

    def get_secret(self, name: str) -> str | None:
        return os.environ.get(name)
