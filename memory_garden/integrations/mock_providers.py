"""Mock provider implementations for testing and demonstration.

These satisfy the provider interface contracts without making real
API calls.  Use them to verify integration patterns before plugging
in a real provider backend (LLM service, embedding service, etc.).
"""

from __future__ import annotations

from typing import Any

from memory_garden.integrations.providers import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    RelevanceProvider,
)


class MockLLMProvider(LLMProvider):
    """Deterministic LLM stub that returns empty or template-filled responses.

    For structured_generate, it returns a dict with a single key
    ``response`` containing the echoed *prompt* (truncated).
    """

    def __init__(self, model: str = "mock-llm", echo: bool = True) -> None:
        self._config = ProviderConfig(provider="mock", model=model)
        self._echo = echo

    def structured_generate(
        self, prompt: str, schema: type, *, system: str = "", **kwargs: Any
    ) -> dict:
        result: dict[str, Any] = {}
        if self._echo:
            result["response"] = prompt[:200]
        if hasattr(schema, "model_fields"):
            for field_name, field_info in schema.model_fields.items():
                if field_name not in result:
                    if field_info.annotation is str:
                        result[field_name] = ""
                    elif field_info.annotation is int:
                        result[field_name] = 0
                    elif field_info.annotation is float:
                        result[field_name] = 0.0
                    elif field_info.annotation is bool:
                        result[field_name] = False
                    elif field_info.annotation is list:
                        result[field_name] = []
        return result

    @property
    def config(self) -> ProviderConfig:
        return self._config


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding stub based on string length + hash.

    NOT a neural model.  Returns a fixed-size embedding array where
    each component is derived from the character value at the
    corresponding position (wrapping).  Same input → same output.
    """

    def __init__(self, dimensions: int = 64, model: str = "mock-embed") -> None:
        self._config = ProviderConfig(provider="mock", model=model)
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dimensions
        for i, ch in enumerate(text):
            vec[i % self._dimensions] += float(ord(ch)) / 1000.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            return [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def dimensions(self) -> int:
        return self._dimensions


class MockRelevanceProvider(RelevanceProvider):
    """Deterministic relevance stub based on substring matching.

    Scores each candidate by the number of query terms found as
    substrings, normalized to [0, 1].
    """

    def __init__(self, model: str = "mock-relevance") -> None:
        self._config = ProviderConfig(provider="mock", model=model)

    def score(self, query: str, candidates: list[str]) -> list[float]:
        terms = [t.lower() for t in query.split() if len(t) >= 2]
        if not terms or not candidates:
            return [0.0] * len(candidates)
        scores: list[float] = []
        max_hits = 0.0
        for c in candidates:
            lower = c.lower()
            hits = sum(1.0 for t in terms if t in lower)
            scores.append(hits)
            if hits > max_hits:
                max_hits = hits
        if max_hits > 0:
            return [s / max_hits for s in scores]
        return scores

    @property
    def config(self) -> ProviderConfig:
        return self._config
