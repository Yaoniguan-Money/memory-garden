"""旧版 Provider 接口（v0.10）—— 可选 LLM、Embedding 与 Relevance 后端。

.. deprecated::
    新代码请使用 ``memory_garden.providers``，它携带 ``ProviderCallContext``
    审计元数据并支持策略门禁。本模块中的 ABC 和 ProviderRegistry 仍可正常工作，但
    建议迁移到新版接口。

本模块不绑定任何真实实现，具体 provider 由应用层注入。

设计来源（规划文档 Layer 3, 4, 7, 8）:
- LLMProvider: 带 schema 约束的结构化生成
- EmbeddingProvider: 文本 → 嵌入向量
- RelevanceProvider: 查询 + 候选列表 → 相关性分数
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderConfig:
    """Minimal provider identity that every concrete provider should carry."""

    provider: str = ""
    model: str = ""
    api_base_url: str = ""


class LLMProvider(ABC):
    """Structured generation interface.

    Concrete implementations must accept a system/user prompt and a
    Pydantic model *schema* type, and return a dict that passes
    ``schema.model_validate(result)``.

    This is the contract expected by optional LLM Lens, Brief Writer,
    and Judge components.  No concrete provider is bundled.
    """

    @abstractmethod
    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict:
        ...

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        result = self.structured_generate(prompt, dict)
        if isinstance(result, dict):
            value = result.get("response") or result.get("text") or ""
            return str(value)
        return str(result)

    @property
    @abstractmethod
    def config(self) -> ProviderConfig:
        ...


class EmbeddingProvider(ABC):
    """Text → embedding interface.

    Concrete implementations return a list of floats per input text.
    This is the contract expected by optional embedding-based Harvest
    candidate retrieval and memory similarity scoring.
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def config(self) -> ProviderConfig:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...


class RelevanceProvider(ABC):
    """Query + candidates → relevance scores interface.

    Concrete implementations take a query string and a list of candidate
    texts, and return a relevance score for each candidate.
    """

    @abstractmethod
    def score(self, query: str, candidates: list[str]) -> list[float]:
        ...

    @property
    @abstractmethod
    def config(self) -> ProviderConfig:
        ...


# ── Provider registry (deprecated — use memory_garden.providers.ProviderRegistry) ──


@dataclass
class ProviderRegistry:
    """旧版 Provider 注册表 —— 已废弃，新代码请用 ``memory_garden.providers.ProviderRegistry``。

    旧版仍保留 ``llm`` / ``embedding`` / ``relevance`` 三个字段和对应的
    ``has_*`` 属性，向后兼容已有测试和示例。
    """

    llm: LLMProvider | None = None
    embedding: EmbeddingProvider | None = None
    relevance: RelevanceProvider | None = None

    def __post_init__(self) -> None:
        warnings.warn(
            "integrations.providers.ProviderRegistry 已废弃，请改用 "
            "memory_garden.providers.ProviderRegistry（支持策略门禁与 ProviderCallContext）",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def has_llm(self) -> bool:
        return self.llm is not None

    @property
    def has_embedding(self) -> bool:
        return self.embedding is not None

    @property
    def has_relevance(self) -> bool:
        return self.relevance is not None
