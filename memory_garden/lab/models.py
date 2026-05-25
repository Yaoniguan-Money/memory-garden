"""第六层 Stage 6A：Garden Lab 评估与回归结构模型（无执行器、无外部服务）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class LabAssertionType(str, Enum):
    """支持的断言运算符（第一版）。"""

    equals = "equals"
    not_equals = "not_equals"
    contains = "contains"
    not_contains = "not_contains"
    is_true = "is_true"
    is_false = "is_false"
    count_equals = "count_equals"
    count_at_most = "count_at_most"
    field_present = "field_present"
    field_absent = "field_absent"


class LabTarget(str, Enum):
    """断言所指的子域（占位枚举，与实际执行层解耦）。"""

    seed = "seed"
    court = "court"
    growth = "growth"
    dream = "dream"
    harvest = "harvest"
    runtime = "runtime"
    observatory = "observatory"


class LabSeverity(str, Enum):
    """失败或告警严重程度。"""

    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class LabStatus(str, Enum):
    """用例或运行状态。"""

    pending = "pending"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    errored = "errored"


class LabAssertion(BaseModel):
    """单条断言：由后续 LabRunner 消费；此处仅数据结构。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    assertion_id: str | None = Field(default=None, description="可选的稳定 id")
    assertion_type: LabAssertionType
    target: LabTarget
    field_path: str = Field(
        default="",
        description="点分路径，如 items 或 nested.value；空字符串表示靶对象根",
    )
    expected: Any | None = Field(
        default=None,
        description="equals/count/contains 等所需的期望值；is_true/is_false 可省略",
    )


class LabFailure(BaseModel):
    """断言未满足时的可读失败记录。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1)
    target: LabTarget
    field_path: str = Field(default="", description="与断言一致的字段路径")
    expected: Any | None = None
    actual: Any | None = None
    message: str = Field(..., min_length=1)
    assertion_type: LabAssertionType | None = None
    severity: LabSeverity = Field(default=LabSeverity.error)


class LabMetricResult(BaseModel):
    """浅层指标快照（不参与 Core 计算）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    value: float | int | str
    unit: str | None = None


class LabCase(BaseModel):
    """单个实验用例定义。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(default_factory=lambda: _new_id("lcase"))
    name: str = Field(default="", max_length=512)
    description: str = Field(default="", max_length=4096)
    assertions: list[LabAssertion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LabSuite(BaseModel):
    """用例套件。"""

    model_config = ConfigDict(extra="forbid")

    suite_id: str = Field(default_factory=lambda: _new_id("lsuite"))
    name: str = Field(default="", max_length=512)
    cases: list[LabCase] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LabCaseResult(BaseModel):
    """单用例在某次运行下的结果。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1)
    status: LabStatus = Field(default=LabStatus.pending)
    failures: list[LabFailure] = Field(default_factory=list)
    metrics: list[LabMetricResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class LabRun(BaseModel):
    """一次套件运行记录（结构体；本阶段不写入存储）。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: _new_id("lrun"))
    suite_id: str = Field(default="", description="可为空占位")
    status: LabStatus = Field(default=LabStatus.pending)
    case_results: list[LabCaseResult] = Field(default_factory=list)
    started_at: datetime | None = Field(default_factory=_utc_now)
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "LabAssertion",
    "LabAssertionType",
    "LabCase",
    "LabCaseResult",
    "LabFailure",
    "LabMetricResult",
    "LabRun",
    "LabSeverity",
    "LabStatus",
    "LabSuite",
    "LabTarget",
]
