"""第二层 Stage 2H：GardenRuntime 最小编排闭环。"""

import inspect
import json
from unittest.mock import MagicMock

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    TemplateBriefWriter,
)
from memory_garden.runtime.policies import FeedbackMode, RuntimePolicy
from memory_garden.runtime.runtime import GardenRuntime, RuntimeCommandResult
from memory_garden.runtime.state import RuntimeState


@pytest.fixture
def core() -> MemoryGardenCore:
    return MemoryGardenCore()


@pytest.fixture
def manager() -> GardenSessionManager:
    return GardenSessionManager()


@pytest.fixture
def hooks(core: MemoryGardenCore, manager: GardenSessionManager) -> RuntimeHooks:
    return RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)


@pytest.fixture
def runtime(core: MemoryGardenCore, manager: GardenSessionManager, hooks: RuntimeHooks) -> GardenRuntime:
    return GardenRuntime(core, manager, hooks)


def test_handle_huahua_open_session(runtime: GardenRuntime, manager: GardenSessionManager) -> None:
    r = runtime.handle_command("花花开")
    assert r.handled is True
    assert r.command == "open"
    assert manager.current_session().state == RuntimeState.OPEN


def test_handle_huahua_open_does_not_create_seed(core: MemoryGardenCore, runtime: GardenRuntime) -> None:
    runtime.handle_command("花花开")
    assert len(core.repository.list_seeds()) == 0


def test_handle_huahua_close_returns_feedback_and_closes(
    runtime: GardenRuntime,
    manager: GardenSessionManager,
) -> None:
    runtime.handle_command("花花开")
    r = runtime.handle_command("花花关")
    assert r.handled is True
    assert r.command == "close"
    assert r.feedback is not None
    assert manager.current_session().state == RuntimeState.CLOSED
    raw = r.feedback.model_dump(mode="json")
    json.dumps(raw)


def test_handle_huahua_close_no_seed(core: MemoryGardenCore, runtime: GardenRuntime) -> None:
    runtime.handle_command("花花开")
    runtime.handle_command("花花关")
    assert len(core.repository.list_seeds()) == 0


def test_closed_plain_message_no_observe(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    observe = MagicMock()
    core.observe = observe  # type: ignore[method-assign]
    sid = manager.current_session().session_id
    runtime.before_reply(sid, "普通闲聊一句")
    observe.assert_not_called()
    out = runtime.after_reply(sid, "普通闲聊一句", "助手占位回复")
    observe.assert_not_called()
    assert out.user_visible_feedback is None


def test_open_plain_before_reply_has_garden_brief(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    before = runtime.before_reply(sid, "开启花园后的用户句")
    assert before.brief is not None


def test_before_reply_does_not_call_observe(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    observe = MagicMock()
    core.observe = observe  # type: ignore[method-assign]
    runtime.before_reply(sid, "仅用于简报的一句话")
    observe.assert_not_called()


def test_after_reply_observes_user_message_only(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    runtime.before_reply(sid, "preflight")
    real_observe = core.observe
    core.observe = MagicMock(wraps=real_observe)  # type: ignore[method-assign]
    runtime.after_reply(sid, "把我这句写进记忆偏好", "助手不应单独被 observe")
    core.observe.assert_called()
    assert core.observe.call_args[0][0] == "把我这句写进记忆偏好"


def test_assistant_reply_not_observed_as_user_memory(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    runtime.before_reply(sid, "我希望界面默认深色模式以便护眼")
    runtime.after_reply(
        sid,
        "我希望界面默认深色模式以便护眼",
        "这句助手回复不应单独变成种子正文",
    )
    seeds = core.repository.list_seeds()
    assert seeds
    for s in seeds:
        assert "这句助手回复不应单独变成种子正文" not in (s.content or "")


def test_after_reply_open_has_tick_result_without_direct_growth(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    runtime.before_reply(sid, "用户消息")
    out = runtime.after_reply(sid, "用户消息用于 observe", "助手")
    assert out.hook_result.tick_result is not None
    assert manager.current_session().state == RuntimeState.OPEN
    import memory_garden.runtime.tick as tick_mod

    src = inspect.getsource(tick_mod.garden_tick)
    for needle in ("plant(", "compost(", "greenhouse(", "prune(", "forget(", "merge("):
        assert needle not in src


def test_normal_turn_user_visible_feedback_none_default_policy(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    runtime.before_reply(sid, "hi")
    out = runtime.after_reply(sid, "hi", "hello")
    assert out.user_visible_feedback is None


def test_runtime_command_result_json_roundtrip() -> None:
    r = RuntimeCommandResult(
        command="open",
        session_id="sid-1",
        state=RuntimeState.OPEN,
        handled=True,
        feedback=None,
        message=None,
        created_seed_ids=[],
    )
    data = r.model_dump(mode="json")
    r2 = RuntimeCommandResult.model_validate(data)
    assert r2.command == "open"


def test_runtime_module_has_no_cli_web_llm_search_imports() -> None:
    import memory_garden.runtime.runtime as rtmod

    src = inspect.getsource(rtmod)
    lowered = src.lower()
    for needle in ("flask", "fastapi", "django", "click", "openai", "anthropic", "chromadb", "embed"):
        assert needle not in lowered


def test_non_command_handle_returns_not_handled(runtime: GardenRuntime) -> None:
    r = runtime.handle_command("今天花花关不上水龙头")
    assert r.handled is False
    assert r.command is None


def test_current_session_with_session_id(runtime: GardenRuntime, manager: GardenSessionManager) -> None:
    runtime.handle_command("花花开")
    sid = manager.current_session().session_id
    s = runtime.current_session(session_id=sid)
    assert s.session_id == sid


def test_every_turn_policy_can_emit_feedback_summary(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    hooks: RuntimeHooks,
) -> None:
    policy = RuntimePolicy(feedback_mode=FeedbackMode.every_turn)
    rt = GardenRuntime(core, manager, hooks, policy=policy)
    rt.handle_command("花花开")
    sid = manager.current_session().session_id
    rt.before_reply(sid, "x")
    out = rt.after_reply(sid, "x", "y")
    assert out.user_visible_feedback is not None
