"""第二层：会话、回合与编排结果模型（不含命令解析与业务编排）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from memory_garden.runtime.state import RuntimeState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid_str() -> str:
    return str(uuid.uuid4())


def _strip_nonempty(name: str):
    def _v(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if not s:
                raise ValueError(f"{name} 不能为空")
            return s
        return v

    return _v


_MAX_BRIEF_FIELD_LEN = 512


class GardenSession(BaseModel):
    """一条 Agent 侧会话与 Garden 编排的绑定上下文。"""

    model_config = ConfigDict(validate_assignment=True)

    session_id: str = Field(default_factory=_new_uuid_str)
    state: RuntimeState = Field(default=RuntimeState.CLOSED)
    opened_at: datetime = Field(default_factory=_utc_now)
    closed_at: datetime | None = None
    turn_count: int = Field(default=0, ge=0)
    last_user_message_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeFeedback(BaseModel):
    """用户可见的运行时反馈占位：供 close_session / 回合收尾挂载。

    具体生成逻辑（是否展示、文案模板）放在后续 Feedback Stage；本模型仅占位数据结构，
    避免会话关闭阶段缺少可序列化载体。
    """

    model_config = ConfigDict(validate_assignment=True)

    feedback_id: str = Field(default_factory=_new_uuid_str)
    session_id: str = Field(..., min_length=1)
    summary: str = Field(..., max_length=768, description="短摘要，一行为主")
    bullets: list[str] = Field(
        default_factory=list,
        description="可选要点列表；编排层可限制每项长度",
    )
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _v_summary = field_validator("summary", mode="before")(_strip_nonempty("summary"))


class TurnContext(BaseModel):
    """单轮用户输入与助手回复的编排快照（可选持久化）。"""

    model_config = ConfigDict(validate_assignment=True)

    session_id: str = Field(..., min_length=1)
    turn_index: int = Field(..., ge=0)
    user_message: str = Field(..., min_length=1)
    assistant_reply: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    _v_user = field_validator("user_message", mode="before")(_strip_nonempty("user_message"))


class GardenBrief(BaseModel):
    """面向编排层的短简报：须可追溯至第一层记忆卡 id，不做检索语义。"""

    model_config = ConfigDict(validate_assignment=True)

    intent: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    use: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    avoid: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    style: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    safety: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    nudge: str = Field(..., max_length=_MAX_BRIEF_FIELD_LEN)
    source_memory_ids: list[str] = Field(
        default_factory=list,
        description="第一层 MemoryCard.id 列表，用于溯源",
    )

    _v_nonempty = field_validator(
        "intent",
        "use",
        "avoid",
        "style",
        "safety",
        "nudge",
        mode="before",
    )(_strip_nonempty("简报字段"))


class TriggerDecision(BaseModel):
    """规则或编排层对本轮是否触发各类动作的决策快照。

    ``strong_signal`` / ``topic_shift`` 与 ``RuntimePolicy.enable_*_trigger`` 配对，
    仅记录编排结论，此处不包含信号检测实现。
    """

    model_config = ConfigDict(validate_assignment=True)

    should_open_court: bool = False
    should_dream: bool = False
    should_prune_check: bool = False
    strong_signal: bool = Field(default=False, description="本轮是否检出强信号维度")
    topic_shift: bool = Field(default=False, description="本轮是否检出话题切换维度")
    reasons: list[str] = Field(default_factory=list, description="人类可读触发/跳过理由")


class GardenTickResult(BaseModel):
    """一次 tick 编排后的结果摘要（仅占位 id 列表，无具体动作实现）。"""

    model_config = ConfigDict(validate_assignment=True)

    opened_court_case_ids: list[str] = Field(default_factory=list)
    applied_action_ids: list[str] = Field(default_factory=list)
    dream_record_id: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    skipped_reasons: list[str] = Field(default_factory=list)
