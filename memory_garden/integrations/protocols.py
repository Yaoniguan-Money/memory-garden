"""第五层 Stage 5A：宿主 chat agent 协议（仅类型契约，无默认实现）。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from memory_garden.integrations.models import AgentReplyResult


@runtime_checkable
class ChatAgentProtocol(Protocol):
    """同步宿主 agent：根据用户句与会话 id 生成助手回复。"""

    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str | AgentReplyResult:
        """返回纯文本或结构化回复；不得在此方法内隐式访问数据库或向量服务。"""
        ...


@runtime_checkable
class AsyncChatAgentProtocol(Protocol):
    """异步宿主 agent，语义与同步版一致。"""

    async def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str | AgentReplyResult:
        ...

