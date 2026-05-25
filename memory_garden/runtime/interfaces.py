"""第二层：编排与服务契约占位（仅方法签名，无实现）。"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from memory_garden.runtime.policies import RuntimePolicy
from memory_garden.runtime.session import (
    GardenBrief,
    GardenSession,
    GardenTickResult,
    RuntimeFeedback,
    TurnContext,
)


@runtime_checkable
class SessionLifecycleProtocol(Protocol):
    """会话生命周期：打开时可带元数据；关闭时可挂载 ``RuntimeFeedback``（具体写入逻辑后续实现）。"""

    def open_session(self, metadata: dict[str, Any] | None = None) -> GardenSession:
        """创建或登记一条 OPEN 会话；metadata 供编排层扩展，非必需。"""
        ...

    def close_session(self, feedback: RuntimeFeedback | None = None) -> GardenSession:
        """结束会话；可选附带反馈占位，便于 close 阶段有可序列化载体。"""
        ...


@runtime_checkable
class TurnHooksProtocol(Protocol):
    """单轮钩子占位：对应 ``RuntimeHooks.before_reply`` / ``after_reply``。"""

    def before_reply(
        self,
        session_id: str,
        user_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """用户消息已进入上下文、助手尚未回复之前。"""
        ...

    def after_reply(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """助手回复已写入上下文之后。"""
        ...


@runtime_checkable
class TickOrchestratorProtocol(Protocol):
    """一轮 garden tick 编排占位：签名对齐 ``runtime.tick.garden_tick``。"""

    def __call__(
        self,
        core: Any,
        session_manager: Any,
        policy: RuntimePolicy,
        turn_context: TurnContext,
        trigger_engine: Any,
        *,
        created_seed_ids: list[str] | None = None,
    ) -> GardenTickResult:
        """根据会话、策略和触发器返回本轮编排结果（可为空操作）。"""
        ...


@runtime_checkable
class HarvesterProtocol(Protocol):
    """before_reply 采摘占位：输入回合上下文，产出结构化 ``GardenBrief``（实现可替换）。"""

    def harvest(self, turn_context: TurnContext) -> GardenBrief:
        """由编排层在助手回复前调用；不得在本接口层假设向量检索或 LLM。"""
        ...


@runtime_checkable
class BriefWriterProtocol(Protocol):
    """将已选记忆标识转为 ``GardenBrief`` 的占位写入器（实现可替换）。"""

    def write(self, selected_memories: list[Any], turn_context: TurnContext) -> GardenBrief:
        """selected_memories 可为内存 id 字符串或其它占位对象；禁止拼接长正文记忆块。"""
        ...
