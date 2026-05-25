"""Memory Garden 核心领域模型（仅数据结构，无业务流程）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from memory_garden.core.court.verdict import CourtVerdict
from memory_garden.core.growth.lifecycle import MemoryLifecycle

# —— 枚举：一律使用字符串值 —— #


class SeedStatus(str, Enum):
    """种子在花园流程中的状态。"""

    pending = "pending"
    in_court = "in_court"
    held = "held"
    planted = "planted"
    composted = "composted"
    greenhoused = "greenhoused"
    merged = "merged"
    forgotten = "forgotten"


class SeedSignalType(str, Enum):
    """种子信号类型。"""

    preference = "preference"
    constraint = "constraint"
    decision = "decision"
    negative_self_talk = "negative_self_talk"
    sensitive_info = "sensitive_info"
    correction = "correction"
    ephemeral = "ephemeral"
    unknown = "unknown"


class MemoryType(str, Enum):
    """长期记忆卡片的语义类型。"""

    preference = "preference"
    boundary = "boundary"
    identity = "identity"
    project = "project"
    relationship = "relationship"
    procedural = "procedural"
    reflection = "reflection"
    avoidance = "avoidance"
    unknown = "unknown"


class SensitivityLevel(str, Enum):
    """敏感程度。"""

    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class GreenhouseAccessPolicy(str, Enum):
    """温室访问策略。"""

    excluded_by_default = "excluded_by_default"
    requires_explicit_include = "requires_explicit_include"


class GardenEventType(str, Enum):
    """花园日志事件类型。"""

    seed_created = "seed_created"
    court_opened = "court_opened"
    verdict_made = "verdict_made"
    memory_planted = "memory_planted"
    memory_merged = "memory_merged"
    dream_completed = "dream_completed"
    memory_pruned = "memory_pruned"
    memory_composted = "memory_composted"
    memory_greenhoused = "memory_greenhoused"
    memory_forgotten = "memory_forgotten"


class GardenObjectType(str, Enum):
    """花园中被记录的对象种类。"""

    seed = "seed"
    memory_card = "memory_card"
    court_case = "court_case"
    dream_record = "dream_record"
    compost_record = "compost_record"
    greenhouse_record = "greenhouse_record"
    pruning_record = "pruning_record"
    garden_event = "garden_event"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid_str() -> str:
    return str(uuid.uuid4())


def _strip_nonempty_string(name: str):
    """生成「非空字符串」校验器。"""

    def _validator(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError(f"{name} 不能为空")
            return s
        return v

    return _validator


class Seed(BaseModel):
    """对话中出现的候选记忆单元（未经法庭不得写入长期记忆）。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    content: str = Field(..., min_length=1)
    source_excerpt: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict, description="结构化附加上下文，默认可为空映射")
    tags: list[str] = Field(default_factory=list)
    signal_type: SeedSignalType = SeedSignalType.unknown
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    status: SeedStatus = SeedStatus.pending
    created_at: datetime = Field(default_factory=_utc_now)

    _v_content = field_validator("content", mode="before")(_strip_nonempty_string("content"))
    _v_source = field_validator("source_excerpt", mode="before")(_strip_nonempty_string("source_excerpt"))


class MemoryCard(BaseModel):
    """经法庭判决后扎根的长期记忆卡片。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    title: str = Field(..., min_length=1)
    essence: str = Field(..., min_length=1)
    memory_type: MemoryType = MemoryType.unknown
    lifecycle: MemoryLifecycle = MemoryLifecycle.sprout
    tags: list[str] = Field(default_factory=list)
    roots: list[str] = Field(default_factory=list)
    branches: list[str] = Field(default_factory=list)
    fragrance: str = Field(..., min_length=1)
    thorns: str = Field(..., min_length=1)
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    sensitivity: SensitivityLevel = SensitivityLevel.none
    source_seed_ids: list[str] = Field(default_factory=list)
    court_case_ids: list[str] = Field(default_factory=list)
    dream_record_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    last_used_at: Optional[datetime] = None

    _v_title = field_validator("title", "essence", "fragrance", "thorns", mode="before")(
        _strip_nonempty_string("文本字段")
    )


class CourtCase(BaseModel):
    """围绕一颗种子的法庭审议记录。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    seed_id: str = Field(..., min_length=1)
    prosecutor_argument: str = Field(..., min_length=1)
    defender_argument: str = Field(..., min_length=1)
    privacy_guard_argument: str = Field(..., min_length=1)
    judge_verdict: CourtVerdict
    matched_rules: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    _v_args = field_validator(
        "seed_id",
        "prosecutor_argument",
        "defender_argument",
        "privacy_guard_argument",
        mode="before",
    )(_strip_nonempty_string("法庭陈述"))


class DreamRecord(BaseModel):
    """梦境周期整理的结构化输出。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    input_seed_ids: list[str] = Field(default_factory=list)
    input_memory_ids: list[str] = Field(default_factory=list)
    observation: str = Field(..., min_length=1)
    reflection: str = Field(..., min_length=1)
    transformation: str = Field(..., min_length=1)
    morning_garden: str = Field(..., min_length=1)
    created_memory_ids: list[str] = Field(default_factory=list)
    merged_memory_ids: list[str] = Field(default_factory=list)
    composted_seed_ids: list[str] = Field(default_factory=list)
    pruned_memory_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    _v_dream_text = field_validator(
        "observation",
        "reflection",
        "transformation",
        "morning_garden",
        mode="before",
    )(_strip_nonempty_string("梦境文本"))


class CompostRecord(BaseModel):
    """堆肥：负面或短期内容的转化记录。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    source_seed_id: Optional[str] = None
    source_memory_id: Optional[str] = None
    discarded_surface: str = Field(..., min_length=1)
    retained_nutrient: str = Field(default="", description="允许为空表示无可保留养分")
    reason: str = Field(..., min_length=1)
    user_requested_hard_forget: bool = False
    created_at: datetime = Field(default_factory=_utc_now)

    _v_surface = field_validator("discarded_surface", "reason", mode="before")(
        _strip_nonempty_string("堆肥文本")
    )

    @model_validator(mode="after")
    def _at_least_one_nonempty_source_id(self) -> CompostRecord:
        def _nonempty(v: Optional[str]) -> bool:
            return v is not None and len(v.strip()) > 0

        if not _nonempty(self.source_seed_id) and not _nonempty(self.source_memory_id):
            raise ValueError(
                "source_seed_id 与 source_memory_id 至少其一必须为非空字符串"
            )
        return self


class GreenhouseRecord(BaseModel):
    """敏感记忆进入温室隔离的记录。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    memory_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    sensitivity_level: SensitivityLevel = SensitivityLevel.medium
    access_policy: GreenhouseAccessPolicy = GreenhouseAccessPolicy.excluded_by_default
    created_at: datetime = Field(default_factory=_utc_now)

    _v_ids = field_validator("memory_id", "reason", mode="before")(_strip_nonempty_string("温室字段"))


class PruningRecord(BaseModel):
    """修剪：生命周期迁移的可解释记录。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    memory_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    old_lifecycle: MemoryLifecycle
    new_lifecycle: MemoryLifecycle
    created_at: datetime = Field(default_factory=_utc_now)

    _v_prune = field_validator("memory_id", "reason", mode="before")(_strip_nonempty_string("修剪字段"))


class GardenEvent(BaseModel):
    """花园日志：关键行为的审计轨迹。"""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=_new_uuid_str)
    event_type: GardenEventType
    object_type: GardenObjectType
    object_id: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    _v_summary = field_validator("object_id", "summary", mode="before")(_strip_nonempty_string("日志字段"))
