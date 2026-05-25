"""第二层：before_reply / after_reply 编排钩子（不实现周期性 garden 编排 tick）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from memory_garden.core.garden import MemoryGardenCore
from memory_garden.core.models import Seed
from memory_garden.runtime.interfaces import BriefWriterProtocol, HarvesterProtocol, TurnHooksProtocol
from memory_garden.runtime.policies import RuntimePolicy
from memory_garden.runtime.session import GardenBrief, GardenTickResult, TurnContext
from memory_garden.runtime.session_manager import GardenSessionManager
from memory_garden.runtime.state import RuntimeState
from memory_garden.runtime.tick import garden_tick as run_garden_tick
from memory_garden.runtime.triggers import TriggerEngine

_ADOPTION_MARKERS: tuple[str, ...] = (
    "我认可",
    "按这个来",
    "就这样",
    "这个很好",
)

_REJECTION_OR_CORRECTION_MARKERS: tuple[str, ...] = (
    "这个不要",
    "你理解错了",
)


def _has_adoption_signal(user_message: str) -> bool:
    t = user_message.strip()
    return any(m in t for m in _ADOPTION_MARKERS)


def _has_rejection_or_correction_signal(user_message: str) -> bool:
    t = user_message.strip()
    return any(m in t for m in _REJECTION_OR_CORRECTION_MARKERS)


class RuntimeBeforeReplyResult(BaseModel):
    """回答前阶段结果：简报与 tick 占位（本阶段不执行 Court / Dream）。"""

    brief: GardenBrief | None = None
    skipped_reasons: list[str] = Field(default_factory=list)
    tick_skipped: bool = True
    tick_notes: list[str] = Field(
        default_factory=lambda: ["court_and_dream_skipped_in_before_reply"],
        description="说明：before_reply 阶段不执行 Court/Dream tick，tick 由 after_reply 或显式调用触发",
    )


class RuntimeAfterReplyResult(BaseModel):
    """回答后阶段结果：观察用户表达后的种子列表与回合计数。"""

    turn_count: int
    seeds: list[Seed] = Field(default_factory=list)
    adoption_context: dict[str, Any] = Field(default_factory=dict)
    user_visible_feedback: str | None = Field(default=None, description="普通轮次为 None")
    tick_placeholder: str | None = Field(default=None, description="兼容占位；请优先使用 tick_result")
    tick_result: GardenTickResult | None = Field(default=None, description="after_reply 末尾 garden_tick 结果")


class RuntimeHooks(TurnHooksProtocol):
    """编排钩子：先简报（不 observe）、回复后再 observe 用户消息。

    ``assistant_reply`` 永不单独作为 observe 输入；采纳类信号仅写入 context / 结果元数据。
    """

    __slots__ = ("_session_manager", "_harvester", "_brief_writer", "_core", "_policy", "_trigger_engine")

    def __init__(
        self,
        session_manager: GardenSessionManager,
        harvester: HarvesterProtocol,
        brief_writer: BriefWriterProtocol,
        core: MemoryGardenCore,
        policy: RuntimePolicy | None = None,
        trigger_engine: TriggerEngine | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._harvester = harvester
        self._brief_writer = brief_writer
        self._core = core
        self._policy = policy or RuntimePolicy()
        self._trigger_engine = trigger_engine or TriggerEngine(core)

    def before_reply(
        self,
        session_id: str,
        user_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeBeforeReplyResult:
        """OPEN：Harvester → BriefWriter；其它状态：不采摘、无简报。

        不在此阶段调用第一层种子观察入口，不把当前用户句写成 Seed。
        """
        self._session_manager.assert_session_id(session_id)
        sess = self._session_manager.current_session()

        if sess.state != RuntimeState.OPEN:
            return RuntimeBeforeReplyResult(
                brief=None,
                skipped_reasons=[f"harvest_skipped_state_{sess.state.value}"],
                tick_skipped=True,
            )

        turn_ctx = TurnContext(
            session_id=session_id,
            turn_index=sess.turn_count,
            user_message=user_message,
            assistant_reply=None,
            metadata=dict(metadata or {}),
        )
        harvested = self._harvester.harvest(turn_ctx)
        selected_ids: list[Any] = list(harvested.source_memory_ids)
        refined = self._brief_writer.write(selected_ids, turn_ctx)
        # BriefWriter 仅用于规范化溯源 id（去重、截断等）；正文以 Harvester 产出为准，避免模板二次覆盖真实采摘语义。
        brief = harvested.model_copy(update={"source_memory_ids": refined.source_memory_ids})
        return RuntimeBeforeReplyResult(brief=brief, skipped_reasons=[], tick_skipped=True)

    def after_reply(
        self,
        session_id: str,
        user_message: str,
        assistant_reply: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeAfterReplyResult:
        """CLOSED/CLOSING：不 observe；OPEN：仅对 ``user_message`` 调用 ``Core.observe``。

        ``assistant_reply`` 只能在采纳/纠正信号命中时进入种子 context 或结果字段，不得单独 observe。
        """
        self._session_manager.assert_session_id(session_id)
        sess = self._session_manager.current_session()

        adoption_hit = _has_adoption_signal(user_message)
        correction_hit = _has_rejection_or_correction_signal(user_message)
        adoption_ctx: dict[str, Any] = {}
        safe_reply = (assistant_reply or "").strip()
        if adoption_hit:
            adoption_ctx["adoption_or_correction_signal"] = True
            adoption_ctx["user_adopted"] = True
            if safe_reply:
                adoption_ctx["assistant_reply_excerpt"] = safe_reply[:480]
        if correction_hit:
            adoption_ctx["rejection_or_correction_signal"] = True
            adoption_ctx["user_adopted"] = False
            if safe_reply:
                adoption_ctx["assistant_reply_excerpt"] = safe_reply[:480]

        if sess.state != RuntimeState.OPEN:
            return RuntimeAfterReplyResult(
                turn_count=sess.turn_count,
                seeds=[],
                adoption_context=adoption_ctx,
                user_visible_feedback=None,
                tick_result=None,
            )

        observe_ctx: dict[str, Any] = dict(metadata or {})
        observe_ctx.update(adoption_ctx)

        seeds = self._core.observe(user_message, observe_ctx if observe_ctx else None)
        self._session_manager.increment_turn_count()
        updated = self._session_manager.current_session()

        tick_ctx = TurnContext(
            session_id=session_id,
            turn_index=updated.turn_count,
            user_message=user_message,
            assistant_reply=None,
            metadata=dict(metadata or {}),
        )
        tick_out = run_garden_tick(
            self._core,
            self._session_manager,
            self._policy,
            tick_ctx,
            self._trigger_engine,
            created_seed_ids=[s.id for s in seeds],
        )

        return RuntimeAfterReplyResult(
            turn_count=updated.turn_count,
            seeds=seeds,
            adoption_context=adoption_ctx,
            user_visible_feedback=None,
            tick_result=tick_out,
        )
