"""Real embedding provider implementations (optional, lazy-loaded).

These providers implement the ``EmbeddingProvider`` ABC from
``memory_garden.integrations.providers``.  They are NOT loaded at import
time — only when the user explicitly constructs one.

Available providers:

- ``SentenceTransformersProvider`` — uses ``sentence-transformers``
  (must be installed separately: ``pip install sentence-transformers``)
- ``LocalEmbeddingProvider`` — wraps the built-in local n-gram hash
  embedding as a proper ``EmbeddingProvider``
"""

from __future__ import annotations

from typing import Any

from memory_garden.integrations.providers import EmbeddingProvider, ProviderConfig


class LocalEmbeddingProvider(EmbeddingProvider):
    """Wraps the built-in local n-gram hash embedding as a proper provider.

    Zero additional dependencies.  Always available.  Not a neural model.
    Suitable for basic approximate matching.
    """

    def __init__(self, dimensions: int = 128) -> None:
        self._config = ProviderConfig(provider="memory-garden-local", model="ngram-hash")
        self._dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        from memory_garden.harvest.local_embedding import embed_local
        return embed_local(text, dimensions=self._dimensions)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        from memory_garden.harvest.local_embedding import embed_local
        return [embed_local(t, dimensions=self._dimensions) for t in texts]

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def dimensions(self) -> int:
        return self._dimensions


class SentenceTransformersProvider(EmbeddingProvider):
    """Real ML embedding via ``sentence-transformers``.

    Requires: ``pip install sentence-transformers``

    Uses the ``all-MiniLM-L6-v2`` model by default (80 MB download on
    first use, cached locally thereafter).  Suitable for semantic search.

    Usage::

        from memory_garden.integrations.embedding_providers import (
            SentenceTransformersProvider,
        )
        provider = SentenceTransformersProvider()
        vec = provider.embed("I prefer dark mode.")
        # vec is a 384-dimensional ML embedding
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
    ) -> None:
        self._config = ProviderConfig(provider="sentence-transformers", model=model_name)
        self._model_name = model_name
        self._device = device
        self._model: Any = None
        self._dimensions_val: int = 384

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for SentenceTransformersProvider. "
                "Install it with: pip install sentence-transformers"
            )
        self._model = SentenceTransformer(self._model_name, device=self._device)
        # Probe dimensions from a tiny input
        probe = self._model.encode(["test"], show_progress_bar=False)
        self._dimensions_val = probe.shape[1] if len(probe.shape) > 1 else len(probe[0])

    def embed(self, text: str) -> list[float]:
        self._ensure_model()
        result = self._model.encode([text], show_progress_bar=False)  # type: ignore[union-attr]
        return result[0].tolist() if len(result.shape) > 1 else result.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        result = self._model.encode(texts, show_progress_bar=False)  # type: ignore[union-attr]
        return result.tolist()

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def dimensions(self) -> int:
        if self._model is None:
            return self._dimensions_val
        return self._dimensions_val
