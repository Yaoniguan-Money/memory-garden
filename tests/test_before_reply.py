"""第二层 Stage 2E：before_reply 钩子。"""

import inspect

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.core.models import GardenEventType
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    RuntimeState,
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


def test_closed_no_brief(hooks: RuntimeHooks, manager: GardenSessionManager) -> None:
    sid = manager.current_session().session_id
    r = hooks.before_reply(sid, "hello")
    assert r.brief is None
    assert len(r.skipped_reasons) >= 1


def test_open_returns_brief(hooks: RuntimeHooks, manager: GardenSessionManager) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    r = hooks.before_reply(sid, "你好")
    assert r.brief is not None
    assert r.tick_skipped is True


def test_closing_skips_harvest(hooks: RuntimeHooks, manager: GardenSessionManager) -> None:
    manager.open_session()
    manager.enter_closing()
    sid = manager.current_session().session_id
    assert manager.current_session().state == RuntimeState.CLOSING
    r = hooks.before_reply(sid, "x")
    assert r.brief is None


def test_before_reply_does_not_observe_or_create_seed(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    before = len(core.repository.list_seeds())
    hooks.before_reply(sid, "我以后都喜欢深色模式，希望默认深色")
    assert len(core.repository.list_seeds()) == before


def test_before_reply_calls_harvester_path(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    r = hooks.before_reply(sid, "hi")
    assert r.brief is not None
    assert r.brief.intent  # TemplateBriefWriter 固定模板


def test_before_reply_impl_does_not_invoke_core_observe() -> None:
    src = inspect.getsource(RuntimeHooks.before_reply)
    assert "_core.observe" not in src
    assert ".observe(" not in src


def test_session_id_mismatch_raises(hooks: RuntimeHooks, manager: GardenSessionManager) -> None:
    manager.open_session()
    with pytest.raises(ValueError, match="不一致"):
        hooks.before_reply("wrong-id", "hi")


def test_no_court_or_dream_events_from_before_reply(
    hooks: RuntimeHooks,
    manager: GardenSessionManager,
    core: MemoryGardenCore,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    hooks.before_reply(sid, "hello")
    evs = core.repository.list_garden_events()
    types = {e.event_type for e in evs}
    assert GardenEventType.court_opened not in types
    assert GardenEventType.dream_completed not in types
