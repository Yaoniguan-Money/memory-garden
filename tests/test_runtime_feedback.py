"""第二层 Stage 2G：RuntimeFeedbackBuilder 与 close_session 收尾反馈。"""

import inspect
import json

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeFeedbackBuilder,
    RuntimeHooks,
    RuntimePolicy,
    RuntimeState,
    TemplateBriefWriter,
)
from memory_garden.runtime.feedback import FeedbackPhase
from memory_garden.runtime.policies import FeedbackMode
from memory_garden.runtime.runtime import GardenRuntime
from memory_garden.runtime.session import RuntimeFeedback


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


def test_closing_only_after_reply_has_no_user_visible_feedback(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    sid = manager.current_session().session_id
    out = runtime.after_reply(sid, "你好", "嗨")
    assert out.user_visible_feedback is None


def test_every_turn_after_reply_has_minimal_visible_feedback(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    hooks: RuntimeHooks,
) -> None:
    policy = RuntimePolicy(feedback_mode=FeedbackMode.every_turn)
    rt = GardenRuntime(core, manager, hooks, policy=policy)
    manager.open_session()
    sid = manager.current_session().session_id
    out = rt.after_reply(sid, "一轮用户内容", "助手")
    assert out.user_visible_feedback is not None
    assert "回合计数" in (out.user_visible_feedback or "")


def test_close_session_returns_runtime_feedback(runtime: GardenRuntime, manager: GardenSessionManager) -> None:
    manager.open_session()
    fb = runtime.close_session()
    assert isinstance(fb, RuntimeFeedback)
    raw = fb.model_dump(mode="json")
    json.dumps(raw)
    assert raw["session_id"]


def test_close_session_sets_state_closed(runtime: GardenRuntime, manager: GardenSessionManager) -> None:
    manager.open_session()
    runtime.close_session()
    assert manager.current_session().state == RuntimeState.CLOSED
    assert manager.current_session().closed_at is not None


def test_close_session_is_idempotent_on_feedback_history(
    runtime: GardenRuntime,
    manager: GardenSessionManager,
) -> None:
    manager.open_session()
    runtime.close_session()
    hist_len = len(manager.current_session().metadata.get("feedback_history", []))
    runtime.close_session()
    assert len(manager.current_session().metadata.get("feedback_history", [])) == hist_len


def test_feedback_history_survives_reopen(
    runtime: GardenRuntime,
    manager: GardenSessionManager,
) -> None:
    manager.open_session()
    runtime.close_session()
    closed = manager.current_session()
    hist = list(closed.metadata.get("feedback_history", []))

    reopened = manager.open_session(metadata={"workspace": "next"})

    assert reopened.state == RuntimeState.OPEN
    assert reopened.metadata.get("feedback_history") == hist
    assert reopened.metadata.get("last_close_feedback_id") == closed.metadata.get("last_close_feedback_id")
    assert reopened.metadata.get("workspace") == "next"


def test_feedback_counts_follow_session_metadata(
    manager: GardenSessionManager,
) -> None:
    manager.open_session()
    manager.record_tick_summary(
        court_case_ids=["cc-1"],
        dream_record_ids=["dr-1"],
        skipped_reasons=[],
        decision_reasons=[],
    )
    builder = RuntimeFeedbackBuilder()
    fb = builder.build_closing_feedback(manager.current_session())
    assert fb.metadata.get("counts", {}).get("court_case_id_count") == 1
    assert fb.metadata.get("counts", {}).get("dream_record_id_count") == 1


def test_no_court_dream_ids_no_positive_claims(manager: GardenSessionManager) -> None:
    manager.open_session()
    fb = RuntimeFeedbackBuilder().build_closing_feedback(manager.current_session())
    blob = fb.summary + "\n" + "\n".join(fb.bullets)
    assert "已审判" not in blob
    assert "已做梦" not in blob
    assert "已记住" not in blob


def test_feedback_module_has_no_llm_keywords() -> None:
    import memory_garden.runtime.feedback as fb

    src = inspect.getsource(fb)
    lowered = src.lower()
    for needle in ("openai", "anthropic", "llm", "chatgpt"):
        assert needle not in lowered


def test_runtime_feedback_sources_do_not_invoke_growth_actions() -> None:
    import memory_garden.runtime.feedback as fb
    import memory_garden.runtime.runtime as rt
    import memory_garden.runtime.session_manager as sm

    for mod in (fb, rt, sm):
        src = inspect.getsource(mod)
        for needle in ("plant(", "compost(", "greenhouse(", "prune(", "forget(", "merge("):
            assert needle not in src


def test_should_emit_closing_only_matches_phase() -> None:
    pol = RuntimePolicy(feedback_mode=FeedbackMode.closing_only)
    assert RuntimeFeedbackBuilder.should_emit_feedback(pol, FeedbackPhase.CLOSING) is True
    assert RuntimeFeedbackBuilder.should_emit_feedback(pol, FeedbackPhase.AFTER_REPLY) is False

