"""第二层：GardenRuntime 最小编排闭环（供外部对话系统调用，非 CLI / Web）。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.core.garden import MemoryGardenCore
from memory_garden.runtime.commands import CommandType, parse_runtime_command
from memory_garden.runtime.feedback import FeedbackPhase, RuntimeFeedbackBuilder
from memory_garden.runtime.hooks import (
    RuntimeAfterReplyResult,
    RuntimeBeforeReplyResult,
    RuntimeHooks,
)
from memory_garden.runtime.policies import RuntimePolicy
from memory_garden.runtime.session import GardenSession, GardenTickResult, RuntimeFeedback
from memory_garden.runtime.session_manager import GardenSessionManager
from memory_garden.runtime.state import RuntimeState


class RuntimeCommandResult(BaseModel):
    """控制口令处理结果：与对话正文路由区分，可序列化交给外层编排。"""

    model_config = ConfigDict(validate_assignment=True)

    command: str | None = Field(
        default=None,
        description="open / close；非控制口令时为 None",
    )
    session_id: str = Field(..., min_length=1)
    state: RuntimeState
    handled: bool = Field(default=False, description="是否为花花开 / 花花关类精确口令")
    feedback: RuntimeFeedback | None = Field(default=None, description="花花关收尾反馈")
    message: str | None = Field(default=None, description="口令解析附带的简短提示")
    created_seed_ids: list[str] = Field(default_factory=list, description="口令路径恒为空列表")


@dataclass
class GardenRuntimeAfterReplyResult:
    """``RuntimeHooks.after_reply`` 结果加上策略驱动的可见反馈摘要。"""

    hook_result: RuntimeAfterReplyResult
    user_visible_feedback: str | None


class GardenRuntime:
    """串起会话生命周期、控制口令短路、before/after 钩子与收尾反馈的最小 Python API。

    约定：对用户输入优先调用 ``handle_command``；仅当返回 ``handled=False`` 时再走
    ``before_reply`` / ``after_reply``。勿将 ``assistant_reply`` 当作 observe 主文本。
    """

    __slots__ = ("_core", "_session_manager", "_hooks", "_policy", "_feedback_builder")

    def __init__(
        self,
        core: MemoryGardenCore,
        session_manager: GardenSessionManager,
        hooks: RuntimeHooks,
        policy: RuntimePolicy | None = None,
        feedback_builder: RuntimeFeedbackBuilder | None = None,
    ) -> None:
        self._core = core
        self._session_manager = session_manager
        self._hooks = hooks
        self._policy = policy or RuntimePolicy()
        self._feedback_builder = feedback_builder or RuntimeFeedbackBuilder()

    def current_session(self, session_id: str | None = None) -> GardenSession:
        """返回当前会话快照；传入 ``session_id`` 时校验与绑定会话一致。"""
        if session_id is not None:
            self._session_manager.assert_session_id(session_id)
        return self._session_manager.current_session()

    def open_session(self, session_id: str | None = None, metadata: dict | None = None) -> GardenSession:
        """打开或延续会话（参见 ``GardenSessionManager.open_session``）。"""
        if session_id is not None:
            self._session_manager.assert_session_id(session_id)
        return self._session_manager.open_session(metadata)

    def close_session(self, session_id: str | None = None) -> RuntimeFeedback:
        """将会话收尾为 ``CLOSED`` 并返回结构化收尾反馈（幂等：已关闭则仅重建反馈对象）。"""
        if session_id is not None:
            self._session_manager.assert_session_id(session_id)
        sess = self._session_manager.current_session()
        tick_like = self._tick_snapshot_from_session(sess)
        recent = self._core.recent_events(limit=80)

        if sess.state == RuntimeState.CLOSED:
            return self._feedback_builder.build_closing_feedback(
                sess,
                tick_result=tick_like,
                recent_events=recent,
            )

        fb = self._feedback_builder.build_closing_feedback(
            sess,
            tick_result=tick_like,
            recent_events=recent,
        )
        self._session_manager.close_session(feedback=fb)
        return fb

    def handle_command(self, text: str, session_id: str | None = None) -> RuntimeCommandResult:
        """识别「花花开 / 花花关」精确口令：命中则短路打开或关闭会话，不触发 observe / Seed。"""
        parsed = parse_runtime_command(text)

        if parsed is None:
            if session_id is not None:
                self._session_manager.assert_session_id(session_id)
            cur = self._session_manager.current_session()
            return RuntimeCommandResult(
                command=None,
                session_id=cur.session_id,
                state=cur.state,
                handled=False,
                feedback=None,
                message=None,
                created_seed_ids=[],
            )

        if session_id is not None:
            self._session_manager.assert_session_id(session_id)

        if parsed.command_type == CommandType.OPEN:
            self.open_session(session_id, metadata=None)
            s = self._session_manager.current_session()
            return RuntimeCommandResult(
                command="open",
                session_id=s.session_id,
                state=s.state,
                handled=True,
                feedback=None,
                message=parsed.user_visible_message,
                created_seed_ids=[],
            )

        if parsed.command_type == CommandType.CLOSE:
            fb = self.close_session(session_id)
            s = self._session_manager.current_session()
            return RuntimeCommandResult(
                command="close",
                session_id=s.session_id,
                state=s.state,
                handled=True,
                feedback=fb,
                message=parsed.user_visible_message,
                created_seed_ids=[],
            )

        raise AssertionError(f"未处理的口令分支：{parsed.command_type}")

    def try_close_control_command(self, user_message: str) -> RuntimeFeedback | None:
        """兼容 Stage 2G：等价于 ``handle_command`` 仅处理关闭类口令。"""
        res = self.handle_command(user_message)
        if res.handled and res.command == "close":
            return res.feedback
        return None

    def before_reply(
        self,
        session_id: str,
        user_message: str,
        metadata: dict | None = None,
    ) -> RuntimeBeforeReplyResult:
        """OPEN：Harvester → BriefWriter；CLOSED：无简报、不 observe。"""
        return self._hooks.before_reply(session_id, user_message, metadata)

    def after_reply(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        metadata: dict | None = None,
    ) -> GardenRuntimeAfterReplyResult:
        """OPEN：observe 用户句并 ``garden_tick``；CLOSED：空操作。可见反馈由策略控制。"""
        inner = self._hooks.after_reply(session_id, user_message, assistant_reply, metadata)
        visible: str | None = None
        if self._feedback_builder.should_emit_feedback(self._policy, FeedbackPhase.AFTER_REPLY):
            tf = self._feedback_builder.build_turn_feedback(
                self._session_manager.current_session(),
                tick_result=inner.tick_result,
            )
            visible = tf.summary if tf is not None else None
        return GardenRuntimeAfterReplyResult(hook_result=inner, user_visible_feedback=visible)

    def _tick_snapshot_from_session(self, session: GardenSession) -> GardenTickResult | None:
        md = session.metadata
        oc = list(md.get("last_tick_court_case_ids") or [])
        dr = list(md.get("last_tick_dream_record_ids") or [])
        dream_id = dr[-1] if dr else None
        if not oc and not dream_id:
            return None
        return GardenTickResult(
            opened_court_case_ids=oc,
            dream_record_id=dream_id,
            skipped_reasons=list(md.get("last_tick_skipped_reasons") or []),
        )


__all__ = [
    "GardenRuntime",
    "GardenRuntimeAfterReplyResult",
    "RuntimeCommandResult",
    "RuntimeAfterReplyResult",
    "RuntimeBeforeReplyResult",
    "RuntimeHooks",
]
