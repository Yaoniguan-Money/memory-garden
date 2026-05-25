"""第五层 Stage 5D：AsyncGardenChatAdapter 集成测试。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from memory_garden.core import MemoryGardenCore
from memory_garden.integrations.async_adapter import AsyncGardenChatAdapter
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.errors import IntegrationAgentError, IntegrationError, IntegrationRuntimeError
from memory_garden.integrations.models import AgentReplyResult
from memory_garden.integrations.protocols import AsyncChatAgentProtocol
from memory_garden.runtime import GardenSessionManager, NullHarvester, RuntimeHooks, TemplateBriefWriter
from memory_garden.runtime.runtime import GardenRuntime


class _RecordingAsyncAgent:
    def __init__(self, reply_text: str | AgentReplyResult = "助手占位") -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self._reply_text = reply_text

    async def generate_assistant_reply(
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


def _run(coro):
    return asyncio.run(coro)


async def _open(adapter: AsyncGardenChatAdapter) -> str:
    r = await adapter.reply("花花开")
    return r.session_id


def test_huahua_open_async_short_circuit_no_agent_no_observe_no_seed() -> None:
    core, _, runtime = _make_runtime()
    agent = _RecordingAsyncAgent()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]
    adapter = AsyncGardenChatAdapter(agent=agent, runtime=runtime)

    _run(adapter.reply("花花开"))
    assert len(agent.calls) == 0
    observe.assert_not_called()
    assert len(core.repository.list_seeds()) == 0


def test_huahua_close_returns_feedback_no_agent() -> None:
    core, manager, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = manager.current_session().session_id
    agent = _RecordingAsyncAgent()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]
    adapter = AsyncGardenChatAdapter(agent=agent, runtime=runtime)
    res = _run(adapter.reply("花花关", session_id=sid))
    assert len(agent.calls) == 0
    observe.assert_not_called()
    assert res.feedback is not None


def test_closed_plain_before_noop_no_observe_but_agent_after_run() -> None:
    core, manager, runtime = _make_runtime()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]
    sid = manager.current_session().session_id
    adapter = AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)
    _run(adapter.reply("普通一句", session_id=sid))
    observe.assert_not_called()


def test_open_plain_runs_before_await_agent_after() -> None:
    core, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))

    class _Trace(AsyncChatAgentProtocol):
        def __init__(self) -> None:
            self.hit = False

        async def generate_assistant_reply(
            self,
            *,
            user_message: str,
            session_id: str,
            extra_context: str | None = None,
        ) -> str:
            del extra_context
            self.hit = True
            return "答"

    agent = _Trace()
    observe = MagicMock(wraps=core.observe)
    core.observe = observe  # type: ignore[method-assign]
    adapter2 = AsyncGardenChatAdapter(agent=agent, runtime=runtime)
    sid = runtime.current_session().session_id
    _run(adapter2.reply("OPEN 下一句", session_id=sid))
    observe.assert_called()
    assert agent.hit


def test_brief_injected_into_async_agent() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    agent = _RecordingAsyncAgent()
    cfg = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.context_argument)
    adapter = AsyncGardenChatAdapter(agent=agent, runtime=runtime, config=cfg)
    _run(adapter.reply("要带简报的句子", session_id=sid))
    assert agent.calls
    assert agent.calls[0][2] is not None and "intent:" in str(agent.calls[0][2])


def test_brief_injection_none_skips_extra_context() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    agent = _RecordingAsyncAgent()
    cfg = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.none)
    adapter = AsyncGardenChatAdapter(agent=agent, runtime=runtime, config=cfg)
    _run(adapter.reply("不注入", session_id=sid))
    assert agent.calls[0][2] is None


def test_assistant_reply_not_alone_in_seed() -> None:
    core, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    adapter = AsyncGardenChatAdapter(agent=_RecordingAsyncAgent("唯一助手异步句"), runtime=runtime)
    _run(adapter.reply("用户唯一观察句", session_id=sid))
    for s in core.repository.list_seeds():
        assert "唯一助手异步句" not in (s.content or "")


def test_async_agent_string_to_integration_result() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    res = _run(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent("异步纯文本"), runtime=runtime).reply("u", session_id=sid))
    assert res.reply == "异步纯文本"


def test_async_agent_agent_reply_result_events() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    ar = AgentReplyResult(content="异步正文", metadata={"tier": "beta"})
    agent = _RecordingAsyncAgent(ar)
    res = _run(AsyncGardenChatAdapter(agent=agent, runtime=runtime).reply("u2", session_id=sid))
    assert res.reply == "异步正文"
    assert any(e.get("tier") == "beta" for e in res.events)


def test_debug_default_off() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    res = _run(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime).reply("x", session_id=sid))
    assert res.debug is None


def test_debug_on_short_notes() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    cfg = GardenAdapterConfig(debug=True)
    res = _run(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime, config=cfg).reply("y", session_id=sid))
    assert res.debug is not None and "brief_source_count=" in " ".join(res.debug.notes)


def test_agent_error_wraps() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id

    class _Bad(AsyncChatAgentProtocol):
        async def generate_assistant_reply(self, **kwargs: object) -> str:
            del kwargs
            raise RuntimeError("async agent 失败")

    async def _boom() -> None:
        await AsyncGardenChatAdapter(agent=_Bad(), runtime=runtime).reply("z", session_id=sid)

    try:
        _run(_boom())
    except IntegrationAgentError as e:
        assert isinstance(e, IntegrationError)
    else:
        raise AssertionError


def test_runtime_error_wraps() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id

    def _boom(self: GardenRuntime, session_id: str, user_message: str, metadata: dict | None = None) -> object:
        del self, session_id, user_message, metadata
        raise ValueError("before 崩")

    async def _probe() -> None:
        with patch.object(GardenRuntime, "before_reply", _boom):
            await AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime).reply("w", session_id=sid)

    try:
        _run(_probe())
    except IntegrationRuntimeError as e:
        assert isinstance(e, IntegrationError)
    else:
        raise AssertionError


def test_metadata_immutable() -> None:
    _, _, runtime = _make_runtime()
    _run(_open(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)))
    sid = runtime.current_session().session_id
    md = {"k": 2}
    snap = json.dumps(md, sort_keys=True)
    _run(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime).reply("u", session_id=sid, metadata=md))
    assert json.dumps(md, sort_keys=True) == snap


def test_async_module_no_vendor_sqlite_tokens() -> None:
    p = Path(__file__).resolve().parents[1] / "memory_garden" / "integrations" / "async_adapter.py"
    low = p.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "deepseek", "to_thread", "faiss", "chroma"):
        assert token not in low, token


def test_package_exports_async_adapter() -> None:
    from memory_garden.integrations import AsyncGardenChatAdapter as A

    assert A is AsyncGardenChatAdapter


def test_results_json_dump() -> None:
    _, _, runtime = _make_runtime()
    adapter = AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime)
    r1 = _run(adapter.reply("花花开"))
    json.dumps(r1.model_dump(mode="json"))
    sid = r1.session_id
    r2 = _run(AsyncGardenChatAdapter(agent=_RecordingAsyncAgent(), runtime=runtime).reply("嗨", session_id=sid))
    json.dumps(r2.model_dump(mode="json"))
