"""第三层：外部能力协议占位（仅用 ``typing.Protocol``，不引入第三方 SDK）。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """将文本映射为向量；实现留桩，不包含具体推理后端。"""

    def embed_texts(
        self,
        texts: list[str],
        *,
        truncate: bool = True,
        context: Any | None = None,
    ) -> Any:
        """返回与 ``texts`` 等长的向量列表，或带 ``vectors`` 字段的结果对象。"""
        ...


@runtime_checkable
class RerankerProvider(Protocol):
    """重排序：对 query-document 对相关分数占位。"""

    def rerank(
        self,
        query_text: str,
        document_ids: list[str],
        snippets: list[str],
    ) -> list[tuple[str, float]]:
        """返回 (document_id, score) 列表，scores 由高到低或未定义顺序均可由实现约定。"""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """文本补全类模型网关占位。"""

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        ...

    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict[str, Any]:
        ...


__all__ = [
    "EmbeddingProvider",
    "LLMProvider",
    "RerankerProvider",
]
