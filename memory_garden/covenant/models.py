"""Garden Covenant data models.

The covenant is the policy source for Memory Garden. These models are pure
configuration structures; they do not execute garden workflows.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConsentDefaultState(str, Enum):
    closed = "closed"
    open = "open"


class SessionScope(str, Enum):
    current_session = "current_session"
    persistent = "persistent"


class NegativeEmotionAction(str, Enum):
    compost_or_hold = "compost_or_hold"
    hold = "hold"
    compost = "compost"


class FeedbackMode(str, Enum):
    closing_only = "closing_only"
    debug_only = "debug_only"
    every_turn = "every_turn"


class ModelCallPurpose(str, Enum):
    memory_lens = "memory_lens"
    brief_writer = "brief_writer"
    llm_judge = "llm_judge"
    rerank = "rerank"
    seed_extraction = "seed_extraction"
    dream_reflection = "dream_reflection"
    court_argument = "court_argument"


class ConsentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    default_state: ConsentDefaultState = ConsentDefaultState.closed
    open_commands: list[str] = Field(default_factory=lambda: ["花花开", "/garden on"])
    close_commands: list[str] = Field(default_factory=lambda: ["花花关", "/garden off"])
    memorize_commands: bool = False
    session_scope: SessionScope = SessionScope.current_session
    require_explicit_open: bool = True
    stop_observing_on_close: bool = True
    stop_harvesting_on_close: bool = True


class MemoryAdmissionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    allow_long_term_preferences: bool = True
    allow_user_decisions: bool = True
    allow_stable_collaboration_style: bool = True
    allow_ai_self_memory: bool = False
    require_user_adoption_signal: bool = True
    ignore_smalltalk_by_default: bool = True
    control_commands_never_memorized: bool = True
    adoption_signals: list[str] = Field(
        default_factory=lambda: ["我认可", "按这个来", "就这样", "采纳", "accepted", "use this"]
    )
    rejection_signals: list[str] = Field(
        default_factory=lambda: ["这个不要", "你理解错了", "不要这样", "reject", "not this"]
    )


class EmotionalSafetyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prevent_negative_identity_lock: bool = True
    negative_emotion_default_action: NegativeEmotionAction = NegativeEmotionAction.compost_or_hold
    hard_forget_overrides_compost: bool = True
    forbidden_identity_phrases: list[str] = Field(
        default_factory=lambda: [
            "一无是处",
            "我很失败",
            "我没用",
            "I am useless",
            "I am a failure",
            "I'm a failure",
        ]
    )
    compost_allowed_for_negative_emotion: bool = True
    require_soft_language_for_emotional_memory: bool = True


class SensitiveMemoryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    greenhouse_default_for_sensitive: bool = True
    greenhouse_excluded_from_harvest: bool = True
    greenhouse_hidden_in_reports: bool = True
    greenhouse_hidden_in_exports: bool = True
    greenhouse_hidden_from_llm_judge: bool = True
    allow_greenhouse_abstract_hint: bool = True
    allow_greenhouse_raw_text_in_debug: bool = False


class ModelCallPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    allow_external_llm: bool = True
    allow_external_embedding: bool = False
    allow_external_reranker: bool = False
    allow_full_garden_context: bool = False
    allow_greenhouse_raw_text: bool = False
    allow_hard_forgotten_text: bool = False
    require_selected_context_only: bool = True
    record_model_calls: bool = True
    require_prompt_hash: bool = True
    max_memories_per_model_call: int = Field(default=8, ge=0)
    allowed_model_call_purposes: list[ModelCallPurpose] = Field(
        default_factory=lambda: [
            ModelCallPurpose.memory_lens,
            ModelCallPurpose.brief_writer,
            ModelCallPurpose.llm_judge,
            ModelCallPurpose.rerank,
            ModelCallPurpose.seed_extraction,
            ModelCallPurpose.dream_reflection,
            ModelCallPurpose.court_argument,
        ]
    )


class HarvestPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    brief_token_budget: int = Field(default=600, ge=1)
    max_selected_memories: int = Field(default=8, ge=0)
    require_source_memory_ids: bool = True
    allow_unsupported_user_preference_instruction: bool = False
    pruned_memory_allowed_slots: list[str] = Field(default_factory=lambda: ["avoid"])
    compost_allowed_slots: list[str] = Field(default_factory=lambda: ["safety", "nudge"])
    greenhouse_allowed_slots: list[str] = Field(default_factory=list)
    require_avoid_slot_for_rejected_direction: bool = True
    enable_twig_boost: bool = True
    enable_avoid_retrieval: bool = True


class VisibilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    feedback_mode: FeedbackMode = FeedbackMode.closing_only
    debug_can_show_trace: bool = True
    debug_can_show_policy_decisions: bool = True
    debug_can_show_redacted_text: bool = False
    report_hide_greenhouse_raw_text: bool = True
    report_hide_redacted_text: bool = True
    report_hide_hard_forgotten_text: bool = True
    snapshot_allow_abstract_summary: bool = True


class PortabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    export_api_keys: bool = False
    export_greenhouse_raw_text: bool = False
    export_redacted_text: bool = False
    export_hard_forgotten_text: bool = False
    export_model_call_details: bool = False
    import_requires_checksum: bool = True
    hard_forget_deletes_embeddings: bool = True
    hard_forget_deletes_fts: bool = True
    hard_forget_redacts_traces: bool = True
    keep_minimal_forget_audit: bool = True


class HardBaselines(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    hard_forgotten_never_visible: bool = True
    commands_never_memorized: bool = True
    unsupported_user_preference_never_in_brief: bool = True
    hard_forget_overrides_compost: bool = True
    ai_self_memory_requires_user_adoption: bool = True
    external_model_never_receives_full_garden_by_default: bool = True
    api_keys_never_exported: bool = True


class AuditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_policy_decisions: bool = True
    record_blocked_operations: bool = True
    include_covenant_hash: bool = True
    max_recent_decisions: int = Field(default=50, ge=1)


class GardenCovenant(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, protected_namespaces=())

    version: int = 1
    consent: ConsentPolicy = Field(default_factory=ConsentPolicy)
    memory_admission: MemoryAdmissionPolicy = Field(default_factory=MemoryAdmissionPolicy)
    emotional_safety: EmotionalSafetyPolicy = Field(default_factory=EmotionalSafetyPolicy)
    sensitive_memory: SensitiveMemoryPolicy = Field(default_factory=SensitiveMemoryPolicy)
    model_calls: ModelCallPolicy = Field(default_factory=ModelCallPolicy)
    harvest: HarvestPolicy = Field(default_factory=HarvestPolicy)
    visibility: VisibilityPolicy = Field(default_factory=VisibilityPolicy)
    portability: PortabilityPolicy = Field(default_factory=PortabilityPolicy)
    hard_baselines: HardBaselines = Field(default_factory=HardBaselines)
    audit: AuditPolicy = Field(default_factory=AuditPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AuditPolicy",
    "ConsentDefaultState",
    "ConsentPolicy",
    "EmotionalSafetyPolicy",
    "FeedbackMode",
    "GardenCovenant",
    "HardBaselines",
    "HarvestPolicy",
    "MemoryAdmissionPolicy",
    "ModelCallPolicy",
    "ModelCallPurpose",
    "NegativeEmotionAction",
    "PortabilityPolicy",
    "SensitiveMemoryPolicy",
    "SessionScope",
    "VisibilityPolicy",
]
