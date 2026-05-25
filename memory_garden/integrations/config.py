"""第五层 Stage 5A：集成配置与简报注入模式（无密钥，允许显式接入远程模型）。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BriefInjectionMode(str, Enum):
    """Garden 简报进入宿主对话构造的方式（由后续 BriefInjector 消费）。"""

    none = "none"
    context_argument = "context_argument"
    system_prefix = "system_prefix"
    developer_message = "developer_message"
    metadata = "metadata"


class GardenAdapterConfig(BaseModel):
    """Adapter 行为契约：默认不携带云厂商 API 密钥，但允许上层显式注入远程 provider。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    brief_injection_mode: BriefInjectionMode = Field(
        default=BriefInjectionMode.context_argument,
        description="简报附着方式，由上层 injector 解释",
    )
    debug: bool = Field(
        default=False,
        description="是否填充 IntegrationResult.debug（默认关闭）",
    )
    prefer_local_runtime: bool = Field(
        default=False,
        description="优先使用进程内 Runtime/Core，而非远程托管执行",
    )
    enable_remote_model_provider: bool = Field(
        default=True,
        description="是否允许走外部模型托管（默认开启；本层不自行创建 provider）",
    )
    attach_observation_trace_to_debug: bool = Field(
        default=False,
        description="debug 开启时是否允许附带观测 trace 引用（仅 id/元信息，非默认）",
    )
