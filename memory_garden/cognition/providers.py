"""认知层外部能力协议（仅 typing.Protocol，不引入第三方 SDK）。

**Stage 1-3 专用 (v1.5-v1.7).** 这些 Protocol 服务于 Harvest/Dream/Court
三阶段的 LLM 增强管线。与 ``memory_garden.providers.base`` 的接口签名
不同——此类注重语义任务的领域语义（advise/propose/rerank），彼类注重
通用 provider 审计（ProviderCallContext + policy gating）。

二者可以桥接：Product 层的 LLMProvider 可通过适配器实现此处的
HarvestRerankerProvider / DreamWeaverProvider / CourtAdvisorProvider。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from memory_garden.cognition.models import (
    CourtAdvice,
    CourtSeedInput,
    DreamMemoryInput,
    DreamProposalBatch,
    GardenBriefDraft,
    HarvestCandidate,
    HarvestRerankResult,
)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """将文本列表映射为等长向量列表。"""

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
class HarvestRerankerProvider(Protocol):
    """在候选池内重排序，不得引入新的 memory_id。"""

    def rerank(
        self,
        query: str,
        candidates: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> HarvestRerankResult:
        """返回重排序后的候选列表。"""
        ...


@runtime_checkable
class BriefWriterProvider(Protocol):
    """从入选记忆生成 GardenBrief 草稿。"""

    def write_brief(
        self,
        query: str,
        selected_memories: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> GardenBriefDraft:
        """返回简报草稿，每条结论须可追溯至 source_memory_ids。"""
        ...


@runtime_checkable
class DreamWeaverProvider(Protocol):
    """对记忆集合生成反思聚类提案——仅返回 proposal，不修改原始 memory。"""

    def propose_clusters(
        self,
        memories: list[DreamMemoryInput],
        policy: Any | None = None,
    ) -> DreamProposalBatch:
        """返回一批 DreamProposal，全部 source_memory_ids 须可追溯至入参。"""
        ...


@runtime_checkable
class CourtAdvisorProvider(Protocol):
    """法庭旁听顾问——仅生成建议，不替代规则判决。"""

    def advise(
        self,
        seed: CourtSeedInput,
        context: dict[str, Any] | None = None,
        policy: Any | None = None,
    ) -> CourtAdvice:
        """返回旁听建议，advised_verdict 不替代规则判决。"""
        ...


__all__ = [
    "BriefWriterProvider",
    "CourtAdvisorProvider",
    "DreamWeaverProvider",
    "EmbeddingProvider",
    "HarvestRerankerProvider",
]
