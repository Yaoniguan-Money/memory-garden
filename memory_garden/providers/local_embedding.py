"""基于 sentence-transformers 的本地嵌入 Provider（可选依赖）。"""

from __future__ import annotations

from typing import Any

from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.schemas import EmbeddingResult
from memory_garden.runtime_config import LocalEmbeddingConfig, default_garden_runtime_config

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    SentenceTransformer = None  # type: ignore[misc, assignment]


def require_sentence_transformers() -> None:
    if not HAS_SENTENCE_TRANSFORMERS:
        raise ImportError(
            "本地嵌入需要可选依赖 sentence-transformers。"
            "请执行: pip install 'memory-garden[embeddings]'"
        )


class SentenceTransformersEmbeddingProvider:
    """本地 CPU/GPU 嵌入；模型名与 batch 等参数来自 ``LocalEmbeddingConfig``。"""

    is_remote = False

    def __init__(
        self,
        *,
        config: LocalEmbeddingConfig | None = None,
        name: str = "local-sentence-transformers",
    ) -> None:
        require_sentence_transformers()
        self._config = config or default_garden_runtime_config().embedding
        self.name = name
        self._model: Any = None

    def _model_instance(self) -> Any:
        if self._model is None:
            self._model = SentenceTransformer(self._config.model_name, device=self._config.device)
        return self._model

    def embed_texts(
        self,
        texts: list[str],
        *,
        truncate: bool = True,
        context: ProviderCallContext | None = None,
    ) -> EmbeddingResult | list[list[float]]:
        _ = truncate
        if not texts:
            result = EmbeddingResult(
                vectors=[],
                model=self._config.model_name,
                dimensions=0,
            )
            return result if context is not None else []

        model = self._model_instance()
        encoded = model.encode(
            texts,
            batch_size=self._config.batch_size,
            normalize_embeddings=self._config.normalize,
            show_progress_bar=False,
        )
        vectors = [list(map(float, row)) for row in encoded]
        dimensions = len(vectors[0]) if vectors else 0
        result = EmbeddingResult(
            vectors=vectors,
            model=self._config.model_name,
            dimensions=dimensions,
        )
        return result if context is not None else vectors


def create_local_embedding_provider(
    config: LocalEmbeddingConfig | None = None,
) -> SentenceTransformersEmbeddingProvider:
    """工厂：从运行时配置创建本地嵌入 Provider。"""
    return SentenceTransformersEmbeddingProvider(config=config)
