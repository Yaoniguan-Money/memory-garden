"""法庭判决类型与结构化判决模型。"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CourtVerdictType(str, Enum):
    """法官可作出的判决种类。"""

    plant = "plant"
    hold = "hold"
    forget = "forget"
    compost = "compost"
    greenhouse = "greenhouse"
    prune = "prune"
    merge = "merge"


class CourtVerdict(BaseModel):
    """结构化判决：不得用普通字符串替代。"""

    verdict: CourtVerdictType
    reason: str = Field(..., min_length=1, description="判决理由，必填且非空")
    target_memory_id: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("reason", mode="before")
    @classmethod
    def _reason_strip_nonempty(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            raise ValueError("reason 不能为空")
        return v
