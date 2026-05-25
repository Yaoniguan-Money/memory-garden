"""第四层：认知增强 (Cognition) — LLM 增强的语义检索、混合采摘、反思梦境与法庭旁听。

Stage 1: Semantic Harvest (v1.5.0)
Stage 2: Dream Reflective Clustering (v1.6.0)
Stage 3: Court Shadow Mode (v1.7.0)
"""

from memory_garden.cognition.court_shadow import run_court_shadow
from memory_garden.cognition.brief_llm import LLMBriefWriter
from memory_garden.cognition.dream_reflective import run_reflective_dream
from memory_garden.cognition.fallback import FallbackChecker, safe_call
from memory_garden.cognition.fake_providers import (
    FakeBriefWriterProvider,
    FakeCourtAdvisorProvider,
    FakeDreamWeaverProvider,
    FakeHarvestRerankerProvider,
)
from memory_garden.cognition.models import (
    CourtAdvice,
    CourtDisagreementType,
    CourtSeedInput,
    CourtShadowComparison,
    CourtShadowMode,
    DreamMemoryInput,
    DreamMode,
    DreamProposal,
    DreamProposalBatch,
    DreamRelationType,
    DreamSuggestedAction,
    DreamTrace,
    GardenBriefDraft,
    CognitiveHarvestMode,
    HarvestCandidate,
    HarvestMode,
    HarvestRerankResult,
    HarvestTrace,
)
from memory_garden.cognition.providers import (
    BriefWriterProvider,
    CourtAdvisorProvider,
    DreamWeaverProvider,
    EmbeddingProvider,
    HarvestRerankerProvider,
)
from memory_garden.cognition.validation import (
    flag_untraceable_content,
    generate_dream_trace,
    generate_trace,
    resolve_disagreement_type,
    validate_brief_traceability,
    validate_court_advice,
    validate_dream_batch,
    validate_dream_proposal,
    validate_rerank_candidates,
)

__all__ = [
    "BriefWriterProvider",
    "CourtAdvice",
    "CourtAdvisorProvider",
    "CourtDisagreementType",
    "CourtSeedInput",
    "CourtShadowComparison",
    "CourtShadowMode",
    "DreamMemoryInput",
    "DreamMode",
    "DreamProposal",
    "DreamProposalBatch",
    "DreamRelationType",
    "DreamSuggestedAction",
    "DreamTrace",
    "DreamWeaverProvider",
    "EmbeddingProvider",
    "FakeBriefWriterProvider",
    "FakeCourtAdvisorProvider",
    "FakeDreamWeaverProvider",
    "FakeHarvestRerankerProvider",
    "FallbackChecker",
    "GardenBriefDraft",
    "CognitiveHarvestMode",
    "HarvestCandidate",
    "HarvestRerankResult",
    "HarvestRerankerProvider",
    "HarvestTrace",
    "LLMBriefWriter",
    "flag_untraceable_content",
    "generate_dream_trace",
    "generate_trace",
    "resolve_disagreement_type",
    "run_court_shadow",
    "run_reflective_dream",
    "safe_call",
    "validate_brief_traceability",
    "validate_court_advice",
    "validate_dream_batch",
    "validate_dream_proposal",
    "validate_rerank_candidates",
]
