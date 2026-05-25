"""第五层 Stage 5B：SyncGardenChatAdapter 集成测试。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_garden.core import MemoryGardenCore
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.errors import IntegrationAgentError, IntegrationError, IntegrationRuntimeError
from memory_garden.integrations.models import AgentReplyResult
from memory_garden.integrations.sync import SyncGardenChatAdapter
from memory_garden.runtime import GardenSessionManager, NullHarvester, RuntimeHooks, TemplateBriefWriter
from memory_garden.runtime.runtime import GardenRuntime


class _RecordingAgent:
    """记录调用并返回可配置结果。"""

    def __init__(self, reply_text: str | AgentReplyResult = "助手占位") -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self._reply_text = reply_text

    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str | AgentReplyResult:
        self.calls.append((user_message, session_id, extra_context))
        return self._reply_text


def _make_runtime() -> tuple[MemoryGardenCore, GardenSessionManager, GardenRuntime]:
    core = MemoryGardenCore()
    manager = GardenSessionManager()
    hooks = RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)
    rt = GardenRuntime(core, manager, hooks)
    return core, manager, rt


def test_huahua_open_short_circuit_no_agent_no_after_no_seed() -> None:
    core, _, runtime = _make_runtime()
    agent = _RecordingAgent()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]

    adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime)
    res = adapter.reply("花花开")
    json.dumps(res.model_dump(mode="json"))

    assert agent.calls == []
    observe.assert_not_called()
    assert len(core.repository.list_seeds()) == 0
    assert res.feedback is None
    assert res.garden_brief is None


def test_huahua_close_returns_feedback_no_agent_no_after_reply() -> None:
    core, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id

    agent = _RecordingAgent()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]

    adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime)
    res = adapter.reply("花花关", session_id=sid)

    assert agent.calls == []
    observe.assert_not_called()
    assert res.feedback is not None
    assert len(res.reply) >= 1


def test_closed_plain_message_before_noop_no_observe_but_agent_after_run() -> None:
    core, manager, runtime = _make_runtime()
    observe = MagicMock()
    core.observe = observe  # type: ignore[method-assign]
    sid = manager.current_session().session_id
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime)
    adapter.reply("普通一句", session_id=sid)

    observe.assert_not_called()


def test_open_plain_runs_before_agent_after_chain() -> None:
    core, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id

    hits: list[str] = []

    class _TracingAgent:
        def generate_assistant_reply(
            self, *, user_message: str, session_id: str, extra_context: str | None = None
        ) -> str:
            hits.append(f"agent:{session_id}:{user_message}")
            return "答"

    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]

    adapter = SyncGardenChatAdapter(agent=_TracingAgent(), runtime=runtime)
    adapter.reply("OPEN 下用户句", session_id=sid)

    observe.assert_called()
    assert hits and "agent:" in hits[0]


def test_brief_injected_per_context_argument_mode() -> None:
    _, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    agent = _RecordingAgent()
    cfg = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.context_argument)
    adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime, config=cfg)
    adapter.reply("需要简报的句子", session_id=sid)
    assert agent.calls
    ctx = agent.calls[0][2]
    assert ctx is not None
    assert "intent:" in ctx


def test_brief_injection_none_skips_extra_context() -> None:
    _, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    agent = _RecordingAgent()
    cfg = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.none)
    adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime, config=cfg)
    adapter.reply("带简报但仍不注入", session_id=sid)
    assert agent.calls[0][2] is None


def test_assistant_reply_not_alone_in_seed_memory() -> None:
    core, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent("唯一助手答句"), runtime=runtime)
    adapter.reply("用户只观察我", session_id=sid)
    for s in core.repository.list_seeds():
        assert "唯一助手答句" not in (s.content or "")


def test_agent_string_reply_wrapped_in_integration_result() -> None:
    _, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent("纯文本"), runtime=runtime)
    res = adapter.reply("u", session_id=sid)
    assert res.reply == "纯文本"


def test_agent_agent_reply_result_preserves_metadata_in_events() -> None:
    _, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    ar = AgentReplyResult(content="正文", metadata={"tier": "alpha"})
    agent = _RecordingAgent(ar)
    adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime)
    res = adapter.reply("u2", session_id=sid)
    assert res.reply == "正文"
    assert any(e.get("tier") == "alpha" for e in res.events)


def test_debug_default_off() -> None:
    _, _, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = runtime.current_session().session_id
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime)
    res = adapter.reply("x", session_id=sid)
    assert res.debug is None


def test_debug_on_has_short_notes() -> None:
    _, _, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = runtime.current_session().session_id
    cfg = GardenAdapterConfig(debug=True)
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime, config=cfg)
    res = adapter.reply("y", session_id=sid)
    assert res.debug is not None
    blob = " ".join(res.debug.notes)
    assert "session_state=" in blob
    assert "brief_source_count=" in blob


def test_agent_error_wraps_integration_agent_error() -> None:
    _, _, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = runtime.current_session().session_id

    class _BadAgent:
        def generate_assistant_reply(self, **kwargs: object) -> str:
            raise RuntimeError("模拟 agent 失败")

    adapter = SyncGardenChatAdapter(agent=_BadAgent(), runtime=runtime)
    try:
        adapter.reply("z", session_id=sid)
    except IntegrationAgentError as e:
        assert isinstance(e, IntegrationError)
        assert "模拟" in str(e) or "失败" in str(e)
    else:
        raise AssertionError("expected IntegrationAgentError")


def test_runtime_error_wraps_integration_runtime_error() -> None:
    _, _, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = runtime.current_session().session_id

    def _boom(
        self: GardenRuntime,
        session_id: str,
        user_message: str,
        metadata: dict | None = None,
    ) -> object:
        del self, session_id, user_message, metadata
        raise ValueError("before 崩")

    adapter = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime)
    with patch.object(GardenRuntime, "before_reply", _boom):
        try:
            adapter.reply("w", session_id=sid)
        except IntegrationRuntimeError as e:
            assert isinstance(e, IntegrationError)
        else:
            raise AssertionError("expected IntegrationRuntimeError")


def test_metadata_not_mutated() -> None:
    _, manager, runtime = _make_runtime()
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    md = {"marker": 1, "nested": {"a": 1}}
    snap = json.dumps(md, sort_keys=True)
    adapter = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime)
    adapter.reply("u", session_id=sid, metadata=md)
    assert json.dumps(md, sort_keys=True) == snap


def test_sync_module_no_vendor_defaults() -> None:
    p = Path(__file__).resolve().parents[1] / "memory_garden" / "integrations" / "sync.py"
    low = p.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "deepseek", "sqlite", "faiss", "chroma"):
        assert token not in low, token


def test_package_exports_sync_adapter() -> None:
    from memory_garden.integrations import SyncGardenChatAdapter as S

    assert S is SyncGardenChatAdapter


def test_command_and_chat_results_json_dump() -> None:
    core, manager, runtime = _make_runtime()
    a1 = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime).reply("花花开")
    json.dumps(a1.model_dump(mode="json"))
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    a2 = SyncGardenChatAdapter(agent=_RecordingAgent(), runtime=runtime).reply("hi", session_id=sid)
    json.dumps(a2.model_dump(mode="json"))
    assert len(core.repository.list_seeds()) == 0
