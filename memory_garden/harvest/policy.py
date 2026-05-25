"""第三层：采摘侧策略参数（数据类，不执行门禁逻辑）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.harvest.models import BriefMode, HarvestMode, MemoryLens


class HarvestBudgetPolicy(BaseModel):
    """配额与模式开关：具体执行在后续 Stage。"""

    model_config = ConfigDict(validate_assignment=True)

    default_harvest_mode: HarvestMode = Field(default=HarvestMode.FULL_PIPELINE_STUB)
    default_brief_mode: BriefMode = Field(default=BriefMode.TEMPLATE)
    max_candidates: int = Field(default=16, ge=0, le=256)
    token_budget_soft: int | None = Field(default=None, ge=0, description="软预算占位")
    default_lenses: list[MemoryLens] = Field(default_factory=list)
