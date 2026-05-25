"""Memory Garden 外部 Provider 的 canonical 协议接口（v1.4.0）。

这是 ``memory_garden.product`` 使用的主要 provider 接口。每次调用都会携带
``ProviderCallContext``，用于审计、来源追踪与策略校验。

Historical note: Two earlier provider interface sets exist:
- ``memory_garden.integrations.providers`` — early ABC definitions (v0.10)
- ``memory_garden.cognition.providers`` — Stage 1-3 Protocol interfaces (v1.5-v1.7)

新的 provider 集成应优先使用本模块。旧接口仅为各自历史层保持兼容。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.providers.schemas import (
    EmbeddingResult,
    JsonCompletionResult,
    RerankCandidate,
    RerankResult,
    TextCompletionResult,
)


class ProviderKind(str, Enum):
    llm = "llm"
    embedding = "embedding"
    reranker = "reranker"
    secret = "secret"


class ProviderCallContext(BaseModel):
    """传给 providers 与策略门禁的审计上下文。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    purpose: str
    provider_kind: str = ""
    garden_home: str = ""
    user_id: str = ""
    workspace_id: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    allow_remote: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    is_remote: bool

    def complete_text(
        self,
        *,
        system: str,
        user: str,
        context: ProviderCallContext,
    ) -> TextCompletionResult:
        ...

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        context: ProviderCallContext,
    ) -> JsonCompletionResult:
        ...

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        ...

    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict[str, Any]:
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    is_remote: bool

    def embed_texts(
        self,
        texts: list[str],
        *,
        truncate: bool = True,
        context: ProviderCallContext | None = None,
    ) -> EmbeddingResult | list[list[float]]:
        ...


@runtime_checkable
class RerankerProvider(Protocol):
    name: str
    is_remote: bool

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int,
        context: ProviderCallContext,
    ) -> RerankResult:
        ...


@runtime_checkable
class SecretProvider(Protocol):
    name: str

    def get_secret(self, name: str) -> str | None:
        ...
