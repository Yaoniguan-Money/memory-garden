"""Product memory models for proposals, management, retrieval, and proof."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_garden.core.models import MemoryCard, MemoryType, SensitivityLevel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class MemoryProposalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    edited = "edited"
    superseded = "superseded"
    error = "error"
    partial = "partial"


class ProposalDecision(str, Enum):
    approve = "approve"
    reject = "reject"
    edit = "edit"
    auto_approve = "auto_approve"


class MemoryRelationType(str, Enum):
    duplicates = "duplicates"
    contradicts = "contradicts"
    supersedes = "supersedes"
    supports = "supports"
    derived_from = "derived_from"
    merged_into = "merged_into"


class ProposalWritePolicy(str, Enum):
    manual = "manual"
    trusted = "trusted"
    auto = "auto"


class VisibilityScope(str, Enum):
    internal = "internal"
    user = "user"
    model = "model"
    export = "export"
    provider = "provider"


class MemoryLayer(str, Enum):
    episodic = "episodic"
    semantic = "semantic"
    preference = "preference"
    procedural = "procedural"
    project_state = "project_state"
    identity = "identity"
    safety_boundary = "safety_boundary"


class MemoryScope(str, Enum):
    global_user = "global_user"
    project = "project"
    workspace = "workspace"
    session = "session"
    identity = "identity"


class MemoryMaturityStage(str, Enum):
    candidate = "candidate"
    observed = "observed"
    stable = "stable"
    canonical = "canonical"
    deprecated = "deprecated"


class ConflictResolutionStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    superseded = "superseded"
    needs_user_review = "needs_user_review"


class EvolutionAction(str, Enum):
    reinforce = "reinforce"
    decay = "decay"
    promote = "promote"
    demote = "demote"
    abstract = "abstract"
    archive = "archive"
    split_scope = "split_scope"


class MemoryProposal(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("prop"))
    title: str = Field(..., min_length=1)
    essence: str = Field(..., min_length=1)
    evidence: str = Field(default="")
    memory_type: MemoryType = MemoryType.unknown
    tags: list[str] = Field(default_factory=list)
    sensitivity: SensitivityLevel = SensitivityLevel.none
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    status: MemoryProposalStatus = MemoryProposalStatus.pending
    source: str = "local_rules"
    source_seed_ids: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    duplicate_memory_ids: list[str] = Field(default_factory=list)
    conflict_memory_ids: list[str] = Field(default_factory=list)
    suggested_layer: MemoryLayer | None = None
    suggested_scope: MemoryScope | None = None
    suggested_scope_id: str = ""
    created_memory_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "essence", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("value must be non-empty")
            return stripped
        return value


class MemoryPatch(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    title: str | None = None
    essence: str | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    fragrance: str | None = None
    thorns: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: SensitivityLevel | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def as_update(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump(exclude_none=True).items() if k != "metadata"}


class MemoryListFilter(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    memory_type: MemoryType | None = None
    sensitivity: SensitivityLevel | None = None
    tag: str | None = None
    layer: MemoryLayer | None = None
    scope: MemoryScope | None = None
    scope_id: str | None = None
    maturity: MemoryMaturityStage | None = None
    include_greenhouse: bool = False
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=500)


class MemoryView(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str
    title: str
    essence: str
    memory_type: str
    lifecycle: str
    tags: list[str] = Field(default_factory=list)
    sensitivity: str
    confidence: float
    importance: float
    source_seed_ids: list[str] = Field(default_factory=list)
    court_case_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None
    layer: str = ""
    scope: str = ""
    scope_id: str = ""
    maturity: str = ""
    strength: float | None = None
    evidence_count: int | None = None

    @classmethod
    def from_card(cls, card: MemoryCard) -> "MemoryView":
        return cls(
            id=card.id,
            title=card.title,
            essence=card.essence,
            memory_type=card.memory_type.value,
            lifecycle=card.lifecycle.value,
            tags=list(card.tags),
            sensitivity=card.sensitivity.value,
            confidence=card.confidence,
            importance=card.importance,
            source_seed_ids=list(card.source_seed_ids),
            court_case_ids=list(card.court_case_ids),
            created_at=card.created_at,
            updated_at=card.updated_at,
            last_used_at=card.last_used_at,
        )


class MemoryRelation(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("rel"))
    relation_type: MemoryRelationType
    source_memory_id: str
    target_memory_id: str
    reason: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryVersionRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("ver"))
    memory_id: str
    version: int
    reason: str
    snapshot: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


class MemoryInspection(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    memory: MemoryView
    versions: list[MemoryVersionRecord] = Field(default_factory=list)
    relations: list[MemoryRelation] = Field(default_factory=list)
    proposals: list[MemoryProposal] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    strategy: "MemoryStrategyProfile | None" = None
    applicability: list["ApplicabilityDecision"] = Field(default_factory=list)
    conflict_arbitrations: list["ConflictArbitrationRecord"] = Field(default_factory=list)
    evolution_plans: list["MemoryEvolutionPlan"] = Field(default_factory=list)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    memory: MemoryView
    score: float = 0.0
    why_used: list[str] = Field(default_factory=list)
    policy_status: str = "allowed"
    risk_flags: list[str] = Field(default_factory=list)
    source: str = "hybrid"
    applicability_score: float = 0.0
    applicability_reasons: list[str] = Field(default_factory=list)


class MemoryRetrievalResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    query: str
    hits: list[RetrievalHit] = Field(default_factory=list)
    provider_used: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ForgetPlanRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("forget_plan"))
    memory_id: str
    target: str = ""
    status: str = "planned"
    cascade: bool = True
    affected: dict[str, list[str]] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    executed_at: datetime | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    content_probe_fingerprint: str = ""
    content_probes_safe: dict[str, Any] = Field(default_factory=dict)


class ForgetProofRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("forget_proof"))
    plan_id: str
    memory_id: str
    proven: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_probe_fingerprint: str = ""
    proof_level: str = "id_only"


class MemoryStrategyProfile(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("strategy"))
    memory_id: str
    layer: MemoryLayer
    scope: MemoryScope = MemoryScope.global_user
    scope_id: str = ""
    maturity: MemoryMaturityStage = MemoryMaturityStage.observed
    strength: float = Field(default=0.55, ge=0.0, le=1.0)
    evidence_count: int = Field(default=1, ge=0)
    mention_count: int = Field(default=1, ge=0)
    use_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    correction_count: int = Field(default=0, ge=0)
    abstraction_of: list[str] = Field(default_factory=list)
    applies_to_tags: list[str] = Field(default_factory=list)
    blocked_contexts: list[str] = Field(default_factory=list)
    last_reinforced_at: datetime | None = None
    last_decayed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicabilityContext(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    query: str = ""
    project_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    session_id: str = ""
    task_type: str = ""
    tags: list[str] = Field(default_factory=list)
    allow_sensitive: bool = False
    include_scopes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicabilityDecision(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    memory_id: str
    allowed: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    scope_match: bool = True
    layer_match: bool = True
    maturity: MemoryMaturityStage | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ConflictArbitrationRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("conflict"))
    proposal_id: str = ""
    new_memory_id: str = ""
    existing_memory_id: str
    status: ConflictResolutionStatus = ConflictResolutionStatus.open
    winner_memory_id: str = ""
    loser_memory_id: str = ""
    resolution: str = ""
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEvolutionPlan(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("evolve"))
    memory_id: str
    action: EvolutionAction
    status: str = "planned"
    reason: str
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    related_memory_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    executed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryAbstraction(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str = Field(default_factory=lambda: new_id("abstract"))
    title: str
    essence: str
    layer: MemoryLayer
    scope: MemoryScope
    scope_id: str = ""
    source_memory_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    created_memory_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
