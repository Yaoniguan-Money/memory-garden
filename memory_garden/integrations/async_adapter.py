"""第五层 Stage 5D：异步 Chat 集成包装器（编排 GardenRuntime + AsyncChatAgentProtocol）。"""

from __future__ import annotations

import uuid
from typing import Any

from memory_garden.integrations.config import GardenAdapterConfig
from memory_garden.integrations.errors import IntegrationAgentError, IntegrationRuntimeError
from memory_garden.integrations.models import IntegrationDebugInfo, IntegrationResult
from memory_garden.integrations.protocols import AsyncChatAgentProtocol
from memory_garden.integrations.sync import (
    _build_extra_context,
    _normalize_agent_reply,
)
from memory_garden.runtime.runtime import GardenRuntime


class AsyncGardenChatAdapter:
    """与 ``SyncGardenChatAdapter`` 语义一致；宿主 agent 为异步协议，Runtime 仍为同步 API 直调。"""

    __slots__ = ("_agent", "_runtime", "_config")

    def __init__(
        self,
        *,
        agent: AsyncChatAgentProtocol,
        runtime: GardenRuntime,
        config: GardenAdapterConfig | None = None,
    ) -> None:
        self._agent = agent
        self._runtime = runtime
        self._config = config if config is not None else GardenAdapterConfig()

    @property
    def config(self) -> GardenAdapterConfig:
        return self._config

    async def reply(
        self,
        user_message: str,
        *,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> IntegrationResult:
        correlation = uuid.uuid4().hex[:16]
        events: list[dict[str, Any]] = [{"phase": "turn_start", "correlation": correlation}]
        dbg = self._config.debug

        try:
            cmd_res = self._runtime.handle_command(user_message, session_id=session_id)
        except Exception as e:
            raise IntegrationRuntimeError(str(e) or "runtime.handle_command 失败") from e

        if cmd_res.handled:
            events.append({"phase": "command_short_circuit", "command": cmd_res.command})
            return self._result_from_command(
                cmd_res=cmd_res,
                events=events,
                correlation=correlation,
                debug_enabled=dbg,
            )

        sid = cmd_res.session_id
        self._runtime.current_session(sid)

        try:
            before = self._runtime.before_reply(sid, user_message, metadata=metadata)
        except Exception as e:
            raise IntegrationRuntimeError(str(e) or "runtime.before_reply 失败") from e

        brief = before.brief
        skipped_reasons = list(before.skipped_reasons or [])
        brief_source_count = len(brief.source_memory_ids) if brief is not None else 0

        extra_ctx = _build_extra_context(brief, self._config.brief_injection_mode)

        try:
            raw_reply = await self._agent.generate_assistant_reply(
                user_message=user_message,
                session_id=sid,
                extra_context=extra_ctx,
            )
        except Exception as e:
            raise IntegrationAgentError(str(e) or "agent.generate_assistant_reply 失败") from e

        assistant_text, agent_meta = _normalize_agent_reply(raw_reply)
        if agent_meta:
            events.append({"phase": "agent_metadata", **{k: agent_meta[k] for k in list(agent_meta)[:32]}})

        try:
            after_bundle = self._runtime.after_reply(sid, user_message, assistant_text, metadata=metadata)
        except Exception as e:
            raise IntegrationRuntimeError(str(e) or "runtime.after_reply 失败") from e

        events.append(
            {
                "phase": "after_reply",
                "turn_count": after_bundle.hook_result.turn_count,
                "seed_count": len(after_bundle.hook_result.seeds),
            }
        )

        session_after = self._runtime.current_session(sid)
        debug_inf = (
            self._make_debug(
                command_handled=False,
                before_reply_skipped=bool(skipped_reasons),
                brief_source_count=brief_source_count,
                feedback_present=False,
                session_state=session_after.state.value,
            )
            if dbg
            else None
        )

        return IntegrationResult(
            reply=assistant_text,
            garden_brief=brief,
            feedback=None,
            trace_id=f"igr_async_{correlation}",
            session_id=sid,
            debug=debug_inf,
            events=events,
        )

    def _result_from_command(
        self,
        *,
        cmd_res: RuntimeCommandResult,
        events: list[dict[str, Any]],
        correlation: str,
        debug_enabled: bool,
    ) -> IntegrationResult:
        msg = cmd_res.message
        fb = cmd_res.feedback
        reply_text = (msg.strip() if isinstance(msg, str) and msg.strip() else None) or (
            fb.summary.strip() if fb is not None and fb.summary else None
        )
        if not reply_text:
            reply_text = "。"

        sess = self._runtime.current_session(cmd_res.session_id)

        dbg = (
            self._make_debug(
                command_handled=True,
                before_reply_skipped=True,
                brief_source_count=0,
                feedback_present=fb is not None,
                session_state=sess.state.value,
            )
            if debug_enabled
            else None
        )

        return IntegrationResult(
            reply=reply_text,
            garden_brief=None,
            feedback=fb,
            trace_id=f"igr_cmd_async_{correlation}",
            session_id=cmd_res.session_id,
            debug=dbg,
            events=events,
        )

    def _make_debug(
        self,
        *,
        command_handled: bool,
        before_reply_skipped: bool,
        brief_source_count: int,
        feedback_present: bool,
        session_state: str,
    ) -> IntegrationDebugInfo:
        return IntegrationDebugInfo(
            adapter_name="AsyncGardenChatAdapter",
            phases_completed=["async_reply"],
            notes=[
                f"command_handled={command_handled}",
                f"before_reply_skipped={before_reply_skipped}",
                f"brief_source_count={brief_source_count}",
                f"feedback_present={feedback_present}",
                f"session_state={session_state}",
            ],
            timings_ms={},
            observation_trace_id=(
                uuid.uuid4().hex[:14] if self._config.attach_observation_trace_to_debug else None
            ),
        )
