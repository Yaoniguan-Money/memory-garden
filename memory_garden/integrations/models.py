"""第五层 Stage 5A：集成层结果与 agent 回复载体（契约数据，无执行逻辑）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.runtime.session import GardenBrief, RuntimeFeedback


class AgentReplyResult(BaseModel):
    """宿主 agent 可选返回结构：正文 + 可序列化元数据。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    content: str = Field(..., min_length=1, description="助手回复正文")
    metadata: dict[str, Any] = Field(default_factory=dict, description="宿主自定义键值，须可 JSON 化")


class IntegrationDebugInfo(BaseModel):
    """debug 开启时的诊断片段：不得默认包含用户长正文或密钥。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    adapter_name: str | None = Field(default=None, description="适配器标识")
    phases_completed: list[str] = Field(default_factory=list, description="已完成的编排阶段名")
    notes: list[str] = Field(default_factory=list, description="短说明行")
    timings_ms: dict[str, float] = Field(default_factory=dict, description="阶段耗时毫秒")
    observation_trace_id: str | None = Field(default=None, description="可选观测 trace id")


class IntegrationResult(BaseModel):
    """单轮集成对外结果：至少须可构造出合法 reply。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    reply: str = Field(..., min_length=1, description="对外助手回复")
    garden_brief: GardenBrief | None = Field(default=None, description="本轮注入用简报快照，可为空")
    feedback: RuntimeFeedback | None = Field(default=None, description="关停或收尾反馈")
    trace_id: str | None = Field(default=None, description="业务或观测侧追溯 id")
    session_id: str = Field(default="", description="Runtime 会话 id，未知时可为空串")
    debug: IntegrationDebugInfo | None = Field(
        default=None,
        description="config.debug 为真时由 adapter 填充，否则保持 None",
    )
    events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="轻量集成事件日志，须可 JSON 序列化",
    )
