"""第五层 Stage 5A：集成层异常基类与分类（无业务实现）。"""

from __future__ import annotations


class IntegrationError(Exception):
    """集成层根异常：SDK / Adapter 与宿主 agent 协作时的可捕获基类。"""


class AgentProtocolError(IntegrationError):
    """宿主提供的 chat agent 未满足协议或返回形态非法。"""


class BriefInjectionError(IntegrationError):
    """Garden 简报注入到对话上下文时失败（格式、模式或约束）。"""


class AdapterRuntimeError(IntegrationError):
    """Adapter 编排 Runtime / Harvest 等子系统时出现的运行时错误。"""


class IntegrationAgentError(AgentProtocolError):
    """宿主 agent 在集成编排中抛出异常时的包装类型。"""


class IntegrationRuntimeError(AdapterRuntimeError):
    """GardenRuntime / Hooks 调用失败时的包装类型。"""
