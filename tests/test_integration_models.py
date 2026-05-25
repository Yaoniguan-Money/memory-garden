"""第五层 Stage 5A：integrations 契约模型与协议测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.errors import (
    AdapterRuntimeError,
    AgentProtocolError,
    BriefInjectionError,
    IntegrationError,
)
from memory_garden.integrations.models import AgentReplyResult, IntegrationDebugInfo, IntegrationResult
from memory_garden.integrations.protocols import AsyncChatAgentProtocol, ChatAgentProtocol
from memory_garden.runtime.session import GardenBrief, RuntimeFeedback


def _minimal_brief() -> GardenBrief:
    return GardenBrief(
        intent="集成测试简报意图字段非空",
        use="同上",
        avoid="同上",
        style="同上",
        safety="同上",
        nudge="同上",
        source_memory_ids=["mem-x"],
    )


def test_brief_injection_mode_enum_complete() -> None:
    names = {m.value for m in BriefInjectionMode}
    assert names == {"none", "context_argument", "system_prefix", "developer_message", "metadata"}


def test_garden_adapter_config_defaults_local_first() -> None:
    c = GardenAdapterConfig(prefer_local_runtime=True, enable_remote_model_provider=False)
    assert c.prefer_local_runtime is True
    assert c.enable_remote_model_provider is False
    assert c.debug is False
    assert c.attach_observation_trace_to_debug is False
    dumped = c.model_dump(mode="json")
    json.dumps(dumped)
    clone = GardenAdapterConfig.model_validate(dumped)
    assert clone == c


def test_integration_result_minimal_reply_only_round_trip() -> None:
    r = IntegrationResult(reply="好的。")
    assert r.garden_brief is None
    assert r.feedback is None
    assert r.trace_id is None
    assert r.session_id == ""
    assert r.debug is None
    assert r.events == []
    blob = json.dumps(r.model_dump(mode="json"))
    r2 = IntegrationResult.model_validate_json(blob)
    assert r2.reply == r.reply


def test_integration_result_full_round_trip() -> None:
    fb = RuntimeFeedback(session_id="s1", summary="收尾摘要占位说明")
    dbg = IntegrationDebugInfo(
        adapter_name="stub",
        phases_completed=["before", "after"],
        notes=["ok"],
        timings_ms={"total": 1.5},
        observation_trace_id="otr_1",
    )
    inner = IntegrationResult(
        reply="完整一轮",
        garden_brief=_minimal_brief(),
        feedback=fb,
        trace_id="t-99",
        session_id="s1",
        debug=dbg,
        events=[{"name": "turn_done", "ok": True}],
    )
    blob = json.dumps(inner.model_dump(mode="json"))
    outer = IntegrationResult.model_validate_json(blob)
    assert outer.reply == inner.reply
    assert outer.feedback is not None
    assert outer.debug is not None
    assert outer.debug.adapter_name == "stub"


def test_agent_reply_result_round_trip() -> None:
    ar = AgentReplyResult(content="正文", metadata={"k": 1})
    blob = json.dumps(ar.model_dump(mode="json"))
    assert AgentReplyResult.model_validate_json(blob).content == "正文"


def test_integration_debug_info_optional_serializable() -> None:
    d = IntegrationDebugInfo()
    assert d.adapter_name is None
    json.dumps(d.model_dump(mode="json"))


class _FakeSyncAgent:
    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str:
        return f"sync:{session_id}:{user_message}"


class _FakeAsyncAgent:
    async def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> AgentReplyResult:
        return AgentReplyResult(content=f"async-{user_message}", metadata={})


def test_chat_agent_protocol_sync_fake() -> None:
    agent: ChatAgentProtocol = _FakeSyncAgent()
    assert isinstance(agent, ChatAgentProtocol)
    out = agent.generate_assistant_reply(user_message="hi", session_id="sid")
    assert out == "sync:sid:hi"


def test_async_chat_agent_protocol_fake() -> None:
    agent: AsyncChatAgentProtocol = _FakeAsyncAgent()
    assert isinstance(agent, AsyncChatAgentProtocol)

    async def _probe() -> AgentReplyResult:
        return await agent.generate_assistant_reply(user_message="x", session_id="y")

    got = asyncio.run(_probe())
    assert isinstance(got, AgentReplyResult)


def test_error_hierarchy() -> None:
    assert issubclass(AgentProtocolError, IntegrationError)
    assert issubclass(BriefInjectionError, IntegrationError)
    assert issubclass(AdapterRuntimeError, IntegrationError)


def test_integration_package_sources_no_vendor_vector_defaults() -> None:
    """契约层不出现特定云厂商或向量库的默认接入字样。"""
    root = Path(__file__).resolve().parents[1] / "memory_garden" / "integrations"
    blobs = "".join((root / fn).read_text(encoding="utf-8").lower() for fn in sorted(p.name for p in root.glob("*.py")))
    forbidden = ("openai", "anthropic", "faiss", "chroma", "vector", "rerank")
    for token in forbidden:
        assert token not in blobs, token


def test_package_exports_integration_contracts() -> None:
    from memory_garden.integrations import (
        BriefInjectionMode,
        IntegrationResult,
    )

    assert BriefInjectionMode is not None
    assert IntegrationResult.model_fields
