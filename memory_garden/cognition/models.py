"""认知层数据模型：混合采摘模式、候选、追溯与简报草稿。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CognitiveHarvestMode(str, Enum):
    """认知采摘模式：纯规则 / 纯语义 / 混合。"""

    RULES_ONLY = "rules_only"
    SEMANTIC_ONLY = "semantic_only"
    HYBRID = "hybrid"


HarvestMode = CognitiveHarvestMode


class HarvestCandidate(BaseModel):
    """混合采摘候选：携带规则分、语义分、重排序分及来源追溯。"""

    memory_id: str
    source_ids: list[str]
    text: str
    tags: list[str] = Field(default_factory=list)
    rule_score: float | None = None
    semantic_score: float | None = None
    rerank_score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class HarvestRerankResult(BaseModel):
    """重排序结果：排序后候选列表及提供方元信息。"""

    candidates: list[HarvestCandidate]
    provider_name: str
    prompt_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GardenBriefDraft(BaseModel):
    """简报草稿：由 BriefWriterProvider 产出，可桥接至 HarvestGardenBrief。"""

    intent: str
    use: str
    avoid: str
    style: str
    safety: str
    nudge: str
    source_memory_ids: list[str]
    token_estimate: int | None = None


class HarvestTrace(BaseModel):
    """认知流水线审计追溯：记录候选池、选择、拒绝、评分分解与降级信息。"""

    query: str
    mode: CognitiveHarvestMode
    candidate_memory_ids: list[str]
    selected_memory_ids: list[str]
    rejected_memory_ids: list[str]
    score_breakdown: dict[str, Any]
    provider_name: str | None = None
    prompt_version: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ── Stage 2: Dream Reflective Clustering ────────────────────────────


class DreamMode(str, Enum):
    """梦境模式：纯规则 / 反思聚类。"""

    RULES_ONLY = "rules_only"
    REFLECTIVE = "reflective"


class DreamRelationType(str, Enum):
    """梦境发现的两个记忆间的关系类型。"""

    DUPLICATE = "duplicate"
    COMPLEMENTARY = "complementary"
    CONFLICTING = "conflicting"
    EVOLVING = "evolving"
    SAME_THEME = "same_theme"
    OTHER = "other"


class DreamSuggestedAction(str, Enum):
    """梦境建议动作——仅建议，不自动执行 Forget/Merge/Prune。"""

    RECORD_REFLECTION = "record_reflection"
    SUGGEST_MERGE = "suggest_merge"
    SUGGEST_PROTECT = "suggest_protect"
    SUGGEST_PRUNE = "suggest_prune"
    NO_ACTION = "no_action"


class DreamMemoryInput(BaseModel):
    """梦境反思输入：将领域记忆包装为 provider 可消费的轻量结构。"""

    memory_id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    source_seed_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DreamProposal(BaseModel):
    """梦境反思提案——派生记录，不覆盖原始 memory。"""

    proposal_id: str
    title: str
    summary: str
    source_memory_ids: list[str]
    relation_type: DreamRelationType
    suggested_action: DreamSuggestedAction
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    risk_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider_name: str | None = None
    prompt_version: str | None = None


class DreamProposalBatch(BaseModel):
    """一批梦境反思提案。"""

    proposals: list[DreamProposal]
    provider_name: str | None = None
    prompt_version: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DreamTrace(BaseModel):
    """梦境反思审计追溯。"""

    dream_run_id: str
    mode: DreamMode
    input_memory_ids: list[str]
    proposal_ids: list[str]
    provider_name: str | None = None
    prompt_version: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ── Stage 3: Court Shadow Mode ──────────────────────────────────────


class CourtShadowMode(str, Enum):
    """法庭旁听模式：关闭 / 影子顾问。"""

    DISABLED = "disabled"
    SHADOW = "shadow"


class CourtSeedInput(BaseModel):
    """法庭旁听输入：将种子包装为 provider 可消费的轻量结构。"""

    seed_id: str
    text: str
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    signal_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CourtAdvice(BaseModel):
    """法庭旁听建议——派生建议，不替代规则判决。"""

    seed_id: str
    advised_verdict: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    source_seed_ids: list[str]
    related_memory_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider_name: str | None = None
    prompt_version: str | None = None


class CourtDisagreementType(str, Enum):
    """规则判决与 LLM 建议之间的分歧类型。"""

    RULE_PLANT_LLM_HOLD = "rule_plant_llm_hold"
    RULE_HOLD_LLM_PLANT = "rule_hold_llm_plant"
    RULE_FORGET_LLM_PLANT = "rule_forget_llm_plant"
    RULE_COMPOST_LLM_MERGE = "rule_compost_llm_merge"
    RULE_PROTECT_LLM_OTHER = "rule_protect_llm_other"
    SAME_VERDICT = "same_verdict"
    OTHER = "other"


class CourtShadowComparison(BaseModel):
    """法庭影子对比记录——审计分歧，不改变最终判决。"""

    seed_id: str
    rule_verdict: str
    llm_advised_verdict: str | None = None
    final_verdict: str
    agreement: bool
    disagreement_type: str | None = None
    rule_reason: str | None = None
    llm_reason: str | None = None
    confidence: float | None = None
    risk_flags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    final_decision_source: str = "rule_court"
    provider_name: str | None = None
    prompt_version: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None


__all__ = [
    "CognitiveHarvestMode",
    "HarvestCandidate",
    "HarvestRerankResult",
    "GardenBriefDraft",
    "HarvestTrace",
    "DreamMode",
    "DreamRelationType",
    "DreamSuggestedAction",
    "DreamMemoryInput",
    "DreamProposal",
    "DreamProposalBatch",
    "DreamTrace",
    "CourtShadowMode",
    "CourtSeedInput",
    "CourtAdvice",
    "CourtDisagreementType",
    "CourtShadowComparison",
]
