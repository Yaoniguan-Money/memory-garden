"""Memory Garden 第五层：集成契约（模型、配置、协议、错误、provider 接口）。"""

from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.errors import (
    AdapterRuntimeError,
    AgentProtocolError,
    BriefInjectionError,
    IntegrationAgentError,
    IntegrationError,
    IntegrationRuntimeError,
)
from memory_garden.integrations.models import AgentReplyResult, IntegrationDebugInfo, IntegrationResult
from memory_garden.integrations.async_adapter import AsyncGardenChatAdapter
from memory_garden.integrations.protocols import AsyncChatAgentProtocol, ChatAgentProtocol
from memory_garden.integrations.providers import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    RelevanceProvider,
)
from memory_garden.integrations.sync import SyncGardenChatAdapter

__all__ = [
    "AdapterRuntimeError",
    "AsyncGardenChatAdapter",
    "AgentProtocolError",
    "AgentReplyResult",
    "AsyncChatAgentProtocol",
    "BriefInjectionError",
    "BriefInjectionMode",
    "ChatAgentProtocol",
    "EmbeddingProvider",
    "GardenAdapterConfig",
    "IntegrationAgentError",
    "IntegrationDebugInfo",
    "IntegrationError",
    "IntegrationResult",
    "IntegrationRuntimeError",
    "LLMProvider",
    "ProviderConfig",
    "RelevanceProvider",
    "SyncGardenChatAdapter",
]
