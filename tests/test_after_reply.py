"""第二层 Stage 2E：after_reply 钩子。"""

import inspect

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.core.models import GardenEventType
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    TemplateBriefWriter,
)


@pytest.fixture
def core() -> MemoryGardenCore:
    return MemoryGardenCore()


@pytest.fixture
def manager() -> GardenSessionManager:
    return GardenSessionManager()


@pytest.fixture
def hooks(core: MemoryGardenCore, manager: GardenSessionManager) -> RuntimeHooks:
    return RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)


def test_closed_does_not_observe(hooks: RuntimeHooks, manager: GardenSessionManager, core: MemoryGardenCore) -> None:
    sid = manager.current_session().session_id
    hooks.after_reply(sid, "我以后都喜欢简洁回复", "助手回复占位")
    assert len(core.repository.list_seeds()) == 0


def test_open_observe_user_message_only(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    r = hooks.after_reply(sid, "我以后都喜欢深色模式，希望界面默认深色", "这里是助手回复")
    assert len(r.seeds) >= 1
    assert core.repository.list_seeds()[0].content.startswith("我以后")


def test_assistant_reply_not_observed_alone(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    """observe 仅以用户消息为主文本；不把助手全文当作用户偏好种子。"""
    manager.open_session()
    sid = manager.current_session().session_id
    hooks.after_reply(sid, "嗯", "我以后都喜欢把助手回复写进记忆里")  # 用户消息极短，通常无种子
    seeds = core.repository.list_seeds()
    if seeds:
        assert "我以后都喜欢把助手" not in seeds[0].content


def test_adoption_signal_adds_context(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    user_text = "我以后都喜欢简洁回复，我认可你的方案"
    ar = "建议使用列表呈现"
    r = hooks.after_reply(sid, user_text, ar)
    assert r.adoption_context.get("adoption_or_correction_signal") is True
    assert "assistant_reply_excerpt" in r.adoption_context
    if r.seeds:
        ctx = r.seeds[0].context
        assert ctx.get("adoption_or_correction_signal") is True


def test_turn_count_increments_after_open_round(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    assert manager.current_session().turn_count == 0
    hooks.after_reply(sid, "我希望少用感叹号", "好的")
    assert manager.current_session().turn_count == 1


def test_no_auto_court_or_dream(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    hooks.after_reply(sid, "我以后都喜欢本地存储", "明白")
    types = {e.event_type for e in core.repository.list_garden_events()}
    assert GardenEventType.court_opened not in types
    assert GardenEventType.dream_completed not in types


def test_after_reply_user_visible_feedback_none_by_default(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    r = hooks.after_reply(sid, "你好", "嗨")
    assert r.user_visible_feedback is None


def test_before_reply_body_has_no_tick_runner() -> None:
    """before_reply 不编排 tick（tick 仅在 after_reply）。"""
    import memory_garden.runtime.hooks as h

    src = inspect.getsource(h.RuntimeHooks.before_reply)
    assert "run_garden_tick" not in src
