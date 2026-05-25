"""Provider 注册表与策略校验。

新代码应使用本模块作为统一入口。它只保存调用方注入的 provider，不会自行读取
API key 或创建网络客户端。
"""

from __future__ import annotations

from dataclasses import dataclass

from memory_garden.providers.base import EmbeddingProvider, LLMProvider, ProviderKind, RerankerProvider, SecretProvider
from memory_garden.providers.config import ProviderPolicy
from memory_garden.providers.errors import ProviderPolicyError


@dataclass
class ProviderRegistry:
    """保存可选外部 providers，并在使用前执行策略校验。"""

    policy: ProviderPolicy | None = None
    llm: LLMProvider | None = None
    embedding: EmbeddingProvider | None = None
    reranker: RerankerProvider | None = None
    secrets: SecretProvider | None = None

    def __post_init__(self) -> None:
        if self.policy is None:
            self.policy = ProviderPolicy()

    @staticmethod
    def _safe_is_remote(provider: object) -> bool:
        return bool(getattr(provider, "is_remote", False))

    def require_llm(self) -> LLMProvider:
        if self.llm is None:
            raise ProviderPolicyError("未注册 LLMProvider")
        self._check_remote(ProviderKind.llm.value, self._safe_is_remote(self.llm))
        return self.llm

    def optional_llm(self) -> LLMProvider | None:
        if self.llm is None:
            return None
        self._check_remote(ProviderKind.llm.value, self._safe_is_remote(self.llm))
        return self.llm

    def optional_embedding(self) -> EmbeddingProvider | None:
        if self.embedding is None:
            return None
        self._check_remote(ProviderKind.embedding.value, self._safe_is_remote(self.embedding))
        return self.embedding

    def optional_reranker(self) -> RerankerProvider | None:
        if self.reranker is None:
            return None
        self._check_remote(ProviderKind.reranker.value, self._safe_is_remote(self.reranker))
        return self.reranker

    def _check_remote(self, provider_kind: str, is_remote: bool) -> None:
        if is_remote and self.policy is not None and not self.policy.allows_remote(provider_kind):
            raise ProviderPolicyError(f"ProviderPolicy 禁止远程 {provider_kind} provider 调用")
