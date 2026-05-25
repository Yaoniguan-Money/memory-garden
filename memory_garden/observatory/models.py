"""第四层 Stage 4A：Observatory 结构化观测模型（仅存数据形态，无导出器与外部 SDK）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_obs_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class ObservationKind(str, Enum):
    """观测条目语义类别（占位枚举，可扩展，不绑定具体子系统实现）。"""

    TRACE_ROOT = "trace_root"
    SPAN = "span"
    SEED = "seed"
    COURT = "court"
    MEMORY = "memory"
    DREAM = "dream"
    HARVEST = "harvest"
    RUNTIME = "runtime"
    GROWTH = "growth"
    CUSTOM = "custom"


class ObservationStatus(str, Enum):
    """跨度或节点状态：用于解释链，而非 HTTP 状态码。"""

    UNKNOWN = "unknown"
    OK = "ok"
    ERROR = "error"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class RedactionLevel(str, Enum):
    """视图脱敏分级：默认采用 public + safe 收敛档。"""

    PUBLIC = "public"
    SAFE = "safe"
    INTERNAL = "internal"


class ObservationSourceRef(BaseModel):
    """对第一层/第三层等业务 id 的弱引用；**不要求**目标对象在存储中存在。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    seed_id: str | None = Field(default=None, description="种子 id")
    court_case_id: str | None = Field(default=None, description="法庭案例 id")
    memory_id: str | None = Field(default=None, description="记忆卡 id")
    dream_record_id: str | None = Field(default=None, description="梦境记录 id")
    harvest_trace_id: str | None = Field(default=None, description="采摘追溯 id")
    event_id: str | None = Field(default=None, description="花园事件 id")


class ObservationSpan(BaseModel):
    """时间或有向结构上的观测跨度。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    span_id: str = Field(default_factory=lambda: _new_obs_id("osp"))
    parent_span_id: str | None = Field(default=None, description="父跨度 id，根节点为 None")
    name: str = Field(default="", max_length=256, description="跨度人类可读名")
    kind: ObservationKind = Field(default=ObservationKind.SPAN)
    status: ObservationStatus = Field(default=ObservationStatus.UNKNOWN)
    started_at: datetime | None = Field(default=None)
    ended_at: datetime | None = Field(default=None)
    attributes: dict[str, Any] = Field(default_factory=dict, description="结构化附属键值")


class ObservationEvent(BaseModel):
    """瞬时观测点。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    event_id: str = Field(default_factory=lambda: _new_obs_id("oev"))
    kind: ObservationKind = Field(default=ObservationKind.CUSTOM)
    name: str = Field(default="", max_length=256)
    occurred_at: datetime = Field(default_factory=_utc_now)
    status: ObservationStatus = Field(default=ObservationStatus.OK)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ObservationLink(BaseModel):
    """溯源图边：源/目标引用 + 关系谓词。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    link_id: str = Field(default_factory=lambda: _new_obs_id("olk"))
    relation: str = Field(default="related", max_length=128)
    source_ref: ObservationSourceRef | None = None
    target_ref: ObservationSourceRef | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ObservationTrace(BaseModel):
    """单次观测会话根：聚合跨度、事件、链接与弱引用表。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    trace_id: str = Field(default_factory=lambda: _new_obs_id("otr"))
    root_span_id: str | None = Field(default=None, description="可选根跨度 id")
    spans: list[ObservationSpan] = Field(default_factory=list)
    events: list[ObservationEvent] = Field(default_factory=list)
    links: list[ObservationLink] = Field(default_factory=list)
    source_refs: list[ObservationSourceRef] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    title: str = Field(default="", max_length=512)
    started_at: datetime | None = Field(default=None)
    ended_at: datetime | None = Field(default=None)


class ObservationView(BaseModel):
    """面向解释/导出的视图快照（非 UI、非外部平台载荷）。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    view_id: str = Field(default_factory=lambda: _new_obs_id("ovw"))
    redaction_level: RedactionLevel = Field(
        default=RedactionLevel.PUBLIC,
        description="默认对外 public；与 safe 同属保守展示档，具体策略由后续层执行",
    )
    summary: str = Field(default="", max_length=4096)
    sections: dict[str, Any] = Field(
        default_factory=dict,
        description='分节内容，如 {"highlights": [...], "facts": {...}}',
    )
    source_trace_id: str | None = Field(default=None, description="回溯至 ObservationTrace.trace_id")
    metadata: dict[str, Any] = Field(default_factory=dict)
