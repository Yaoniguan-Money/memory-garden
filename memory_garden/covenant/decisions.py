"""Policy decisions produced by Garden Covenant."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_decision_id() -> str:
    return f"pdec_{uuid.uuid4().hex[:16]}"


class PolicySeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class PolicyDecision(BaseModel):
    """Auditable result of one covenant policy check."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(default_factory=_new_decision_id)
    policy_name: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    allowed: bool
    reason: str = Field(..., min_length=1)
    matched_rules: list[str] = Field(default_factory=list)
    severity: PolicySeverity = PolicySeverity.info
    object_type: str | None = None
    object_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["PolicyDecision", "PolicySeverity"]
