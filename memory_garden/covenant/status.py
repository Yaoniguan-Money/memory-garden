"""Garden Covenant status payloads for future SDK/CLI use."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.covenant.audit import covenant_hash
from memory_garden.covenant.models import GardenCovenant


class CovenantStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    covenant_version: int
    covenant_hash: str = Field(..., min_length=1)
    feedback_mode: str
    external_llm_allowed: bool
    full_garden_context_allowed: bool
    greenhouse_raw_export_allowed: bool
    hard_baselines_status: str


def build_covenant_status(covenant: GardenCovenant) -> CovenantStatus:
    baselines = covenant.hard_baselines.model_dump()
    all_ok = all(v is True for v in baselines.values())
    return CovenantStatus(
        covenant_version=covenant.version,
        covenant_hash=covenant_hash(covenant),
        feedback_mode=covenant.visibility.feedback_mode.value,
        external_llm_allowed=covenant.model_calls.allow_external_llm,
        full_garden_context_allowed=covenant.model_calls.allow_full_garden_context,
        greenhouse_raw_export_allowed=covenant.portability.export_greenhouse_raw_text,
        hard_baselines_status="ok" if all_ok else "unsafe",
    )


__all__ = ["CovenantStatus", "build_covenant_status"]
