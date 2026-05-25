"""第四层 Stage 4D：第二层 Runtime 交互快照 → Observatory（只读、不调 Core / 不执行业务）。"""

from __future__ import annotations

from typing import Any, cast

from memory_garden.observatory.models import (
    ObservationEvent,
    ObservationKind,
    ObservationLink,
    ObservationSourceRef,
    ObservationSpan,
    ObservationStatus,
    ObservationTrace,
    ObservationView,
    RedactionLevel,
)
from memory_garden.runtime.hooks import RuntimeAfterReplyResult, RuntimeBeforeReplyResult
from memory_garden.runtime.runtime import RuntimeCommandResult
from memory_garden.runtime.session import (
    GardenBrief,
    GardenSession,
    GardenTickResult,
    RuntimeFeedback,
    TurnContext,
)
from memory_garden.runtime.state import RuntimeState

_EXCERPT_LEN = 120
_MAX_IDS = 64

_CHILD_SPANS = (
    "command_check",
    "before_reply",
    "harvest_brief",
    "after_reply",
    "garden_tick",
    "closing_feedback",
)


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _remember_ref(ref: ObservationSourceRef, seen: set[tuple[tuple[str, Any], ...]], out: list[ObservationSourceRef]) -> None:
    rs = ref.model_dump(exclude_none=True)
    if not rs:
        return
    key = tuple(sorted(rs.items()))
    if key not in seen:
        seen.add(key)
        out.append(ref)


def _effective_tick(
    tick_result: GardenTickResult | None,
    after_result: RuntimeAfterReplyResult | None,
) -> GardenTickResult | None:
    if tick_result is not None:
        return tick_result
    if after_result is not None and after_result.tick_result is not None:
        return after_result.tick_result
    return None


class RuntimeObservationAdapter:
    """第二层 Runtime 结果结构的只读观测映射。"""

    def trace_from_turn(
        self,
        *,
        session: GardenSession | None = None,
        turn_context: TurnContext | None = None,
        before_result: RuntimeBeforeReplyResult | None = None,
        after_result: RuntimeAfterReplyResult | None = None,
        tick_result: GardenTickResult | None = None,
        feedback: RuntimeFeedback | None = None,
        command_result: Any | None = None,
        trace_name: str = "runtime_turn",
    ) -> ObservationTrace:
        events: list[ObservationEvent] = []
        spans: list[ObservationSpan] = []
        links: list[ObservationLink] = []
        refs: list[ObservationSourceRef] = []
        seen: set[tuple[tuple[str, Any], ...]] = set()

        root = ObservationSpan(
            name="runtime_turn",
            parent_span_id=None,
            kind=ObservationKind.TRACE_ROOT,
            status=ObservationStatus.OK,
            attributes={"runtime_trace_name": trace_name},
        )
        spans.append(root)
        child_by_name: dict[str, ObservationSpan] = {}
        for nm in _CHILD_SPANS:
            sp = ObservationSpan(
                name=nm,
                parent_span_id=root.span_id,
                kind=ObservationKind.RUNTIME,
                status=ObservationStatus.UNKNOWN,
                attributes={"phase": nm, "provided": False},
            )
            child_by_name[nm] = sp
            spans.append(sp)

        meta_runtime: dict[str, Any] = {
            "trace_name": trace_name,
            "has_session": session is not None,
            "has_turn_context": turn_context is not None,
            "has_before": before_result is not None,
            "has_after": after_result is not None,
            "has_tick_arg": tick_result is not None,
            "has_feedback": feedback is not None,
            "has_command": command_result is not None,
        }

        if session is not None:
            root.attributes.update(
                {
                    "session_id": session.session_id,
                    "state": session.state.value,
                    "turn_count": session.turn_count,
                }
            )
            meta_runtime["session_id"] = session.session_id
            meta_runtime["session_state"] = session.state.value
            meta_runtime["turn_count_snapshot"] = session.turn_count

        if turn_context is not None:
            child_by_name["before_reply"].attributes["provided"] = True
            meta_runtime.update(
                {
                    "turn_session_id_turn": turn_context.session_id[:128],
                    "turn_index": turn_context.turn_index,
                    "user_message_chars": len(turn_context.user_message or ""),
                    "assistant_reply_chars": len((turn_context.assistant_reply or "")),
                }
            )

        events.append(
            ObservationEvent(
                name="runtime_turn_started",
                kind=ObservationKind.RUNTIME,
                attributes={
                    **({} if session is None else {"session_id": session.session_id, "state": session.state.value}),
                },
            )
        )

        if command_result is not None:
            cmd = command_result if isinstance(command_result, RuntimeCommandResult) else RuntimeCommandResult.model_validate(command_result)  # type: ignore[arg-type]
            child_by_name["command_check"].attributes.update(
                {
                    "provided": True,
                    "handled": cmd.handled,
                    "command": cmd.command,
                    "session_id_cmd": cmd.session_id,
                    "state_cmd": cmd.state.value,
                    "seed_ids_created_count": len(cmd.created_seed_ids or []),
                    "message_len": len((cmd.message or "")),
                    "message_excerpt": _clip(cmd.message or "", _EXCERPT_LEN),
                }
            )
            child_by_name["command_check"].status = ObservationStatus.OK
            nm = "command_handled" if cmd.handled else "command_not_handled"
            events.append(
                ObservationEvent(
                    name=nm,
                    kind=ObservationKind.RUNTIME,
                    attributes={
                        "handled": cmd.handled,
                        "command": cmd.command,
                        "session_id": cmd.session_id,
                        "created_seed_paths_count": len(cmd.created_seed_ids or []),
                    },
                )
            )
            meta_runtime["_cmd_handled"] = cmd.handled
            meta_runtime["_cmd_command"] = cmd.command
            meta_runtime["_cmd_message_excerpt"] = _clip(cmd.message or "", _EXCERPT_LEN)

        brief: GardenBrief | None = None
        if before_result is not None:
            child_by_name["before_reply"].attributes["provided"] = True
            child_by_name["before_reply"].status = ObservationStatus.OK
            skipped_br = bool(before_result.skipped_reasons)
            brief = before_result.brief
            attrs_br = {
                "tick_skipped": before_result.tick_skipped,
                "skipped_reason_count": len(before_result.skipped_reasons),
                "has_brief_object": brief is not None,
            }
            skip_hint_raw = "; ".join(str(x) for x in (before_result.skipped_reasons or [])[:12])
            meta_runtime["_before_skipped_reason_count"] = len(before_result.skipped_reasons)
            meta_runtime["_before_skipped_hint"] = _clip(skip_hint_raw, _EXCERPT_LEN)
            events.append(
                ObservationEvent(
                    name="before_reply_skipped" if skipped_br else "before_reply_completed",
                    kind=ObservationKind.RUNTIME,
                    status=ObservationStatus.SKIPPED if skipped_br else ObservationStatus.OK,
                    attributes={
                        **attrs_br,
                        "skipped_reason_hints": _clip(skip_hint_raw, _EXCERPT_LEN),
                    },
                )
            )
            child_by_name["harvest_brief"].attributes["provided"] = True
            brief_empty = brief is None or not (brief.source_memory_ids or [])
            if brief_empty:
                child_by_name["harvest_brief"].status = ObservationStatus.SKIPPED
                events.append(
                    ObservationEvent(
                        name="harvest_brief_empty",
                        kind=ObservationKind.RUNTIME,
                        status=ObservationStatus.SKIPPED,
                        attributes={"source_memory_count": len(brief.source_memory_ids) if brief else 0},
                    )
                )
            elif brief is not None:
                child_by_name["harvest_brief"].status = ObservationStatus.OK
                n_mid = len(brief.source_memory_ids)
                meta_runtime["brief_source_memory_ids_count"] = n_mid
                events.append(
                    ObservationEvent(
                        name="harvest_brief_available",
                        kind=ObservationKind.RUNTIME,
                        attributes={
                            "source_memory_ids_count": n_mid,
                            "intent_len": len(brief.intent or ""),
                            "use_len": len(brief.use or ""),
                        },
                    )
                )
                sess_hint = session.session_id if session is not None else (turn_context.session_id if turn_context else "")
                for mid in brief.source_memory_ids[:_MAX_IDS]:
                    r = ObservationSourceRef(memory_id=mid)
                    _remember_ref(r, seen, refs)
                    links.append(
                        ObservationLink(
                            relation="brief_used_memory",
                            source_ref=None,
                            target_ref=ObservationSourceRef(memory_id=mid),
                            attributes={"runtime_session_hint": sess_hint[:128], "brief_source_slot": True},
                        )
                    )

        if after_result is not None:
            child_by_name["after_reply"].attributes["provided"] = True
            child_by_name["after_reply"].status = ObservationStatus.OK
            seed_ids = [str(s.id) for s in after_result.seeds][: _MAX_IDS]
            closed_like = session is not None and session.state in (RuntimeState.CLOSED, RuntimeState.CLOSING)
            skip_after = closed_like and len(after_result.seeds) == 0
            after_ev = "after_reply_skipped" if skip_after else "after_reply_observed"
            events.append(
                ObservationEvent(
                    name=after_ev,
                    kind=ObservationKind.RUNTIME,
                    status=ObservationStatus.SKIPPED if skip_after else ObservationStatus.OK,
                    attributes={
                        "turn_count": after_result.turn_count,
                        "seed_count": len(after_result.seeds),
                        "seed_ids_preview": seed_ids[:16],
                        "tick_result_present_after": after_result.tick_result is not None,
                        "user_visible_feedback_len": len(after_result.user_visible_feedback or ""),
                        "after_reply_semantic_skip": skip_after,
                    },
                )
            )
            meta_runtime.update(
                {
                    "after_turn_count": after_result.turn_count,
                    "seed_count": len(after_result.seeds),
                    "after_reply_skipped": skip_after,
                }
            )

        tick_effective = _effective_tick(tick_result, after_result)
        if tick_effective is not None:
            child_by_name["garden_tick"].attributes["provided"] = True
            crs = tick_effective.opened_court_case_ids or []
            dr = tick_effective.dream_record_id
            has_work = bool(crs) or bool(dr) or bool(tick_effective.applied_action_ids) or bool(tick_effective.event_ids)
            purely_skipped = bool(tick_effective.skipped_reasons) and not has_work

            sess_hint2 = session.session_id if session is not None else ""
            if purely_skipped and not crs and not dr:
                child_by_name["garden_tick"].status = ObservationStatus.SKIPPED
                events.append(
                    ObservationEvent(
                        name="garden_tick_skipped",
                        kind=ObservationKind.RUNTIME,
                        status=ObservationStatus.SKIPPED,
                        attributes={
                            "skipped_reason_count": len(tick_effective.skipped_reasons),
                            "skipped_hint": _clip("; ".join(tick_effective.skipped_reasons), _EXCERPT_LEN),
                        },
                    )
                )
            else:
                child_by_name["garden_tick"].status = ObservationStatus.OK
                events.append(
                    ObservationEvent(
                        name="garden_tick_ran",
                        kind=ObservationKind.RUNTIME,
                        attributes={
                            "opened_court_case_count": len(crs),
                            "has_dream_record": bool(dr),
                            "applied_action_ids_count": len(tick_effective.applied_action_ids),
                            "event_ids_count": len(tick_effective.event_ids),
                        },
                    )
                )
            meta_runtime.update(
                {
                    "tick_court_cases": len(crs),
                    "tick_dream_present": bool(dr),
                }
            )
            for cid in crs[:_MAX_IDS]:
                _remember_ref(ObservationSourceRef(court_case_id=cid), seen, refs)
                links.append(
                    ObservationLink(
                        relation="tick_opened_court_case",
                        source_ref=None,
                        target_ref=ObservationSourceRef(court_case_id=cid),
                        attributes={"runtime_session_hint": sess_hint2[:128]},
                    )
                )
            if dr:
                _remember_ref(ObservationSourceRef(dream_record_id=dr), seen, refs)
                links.append(
                    ObservationLink(
                        relation="tick_completed_dream",
                        source_ref=None,
                        target_ref=ObservationSourceRef(dream_record_id=dr),
                        attributes={"runtime_session_hint": sess_hint2[:128]},
                    )
                )

        if feedback is not None:
            child_by_name["closing_feedback"].attributes["provided"] = True
            child_by_name["closing_feedback"].status = ObservationStatus.OK
            events.append(
                ObservationEvent(
                    name="feedback_created",
                    kind=ObservationKind.RUNTIME,
                    attributes={
                        "feedback_id": feedback.feedback_id,
                        "feedback_session_id": feedback.session_id,
                        "summary_len": len(feedback.summary or ""),
                        "summary_excerpt_short": _clip(feedback.summary, _EXCERPT_LEN),
                        "bullets_count": len(feedback.bullets or []),
                        "note": "feedback_id_only_no_source_ref_specialization",
                    },
                )
            )
            meta_runtime["feedback_id"] = feedback.feedback_id
            meta_runtime["feedback_summary_len"] = len(feedback.summary or "")

        events.append(ObservationEvent(name="runtime_turn_completed", kind=ObservationKind.RUNTIME))

        iex: dict[str, Any] = {}
        if turn_context is not None:
            iex["user"] = _clip(turn_context.user_message, _EXCERPT_LEN)
            iex["assistant"] = _clip(turn_context.assistant_reply or "", _EXCERPT_LEN)
        meta_runtime["_internal_turn_excerpts"] = iex
        meta_runtime["_internal_feedback_summary"] = (
            _clip(feedback.summary, _EXCERPT_LEN) if feedback is not None else None
        )

        return ObservationTrace(
            root_span_id=root.span_id,
            spans=spans,
            events=events,
            links=links,
            source_refs=refs,
            title=trace_name,
            metadata={"runtime": meta_runtime},
        )

    def view_from_trace(self, trace: ObservationTrace, redaction_level: RedactionLevel = RedactionLevel.PUBLIC) -> ObservationView:
        raw_rm = trace.metadata.get("runtime")
        rm = cast(dict[str, Any], raw_rm if isinstance(raw_rm, dict) else {})

        sess: dict[str, Any] = {}
        sid = rm.get("session_id")
        if sid is not None:
            sess["session_id"] = sid
        if rm.get("session_state") is not None:
            sess["state"] = rm["session_state"]
        if rm.get("turn_count_snapshot") is not None:
            sess["turn_count"] = rm["turn_count_snapshot"]
        if rm.get("has_turn_context"):
            sess["turn_index"] = rm.get("turn_index")
            sess["user_message_chars"] = rm.get("user_message_chars")
            sess["assistant_reply_chars"] = rm.get("assistant_reply_chars")

        cmd: dict[str, Any] = {"has_command": bool(rm.get("has_command"))}
        if rm.get("has_command"):
            cmd.update(
                {
                    "handled": rm.get("_cmd_handled"),
                    "command": rm.get("_cmd_command"),
                }
            )
            if redaction_level == RedactionLevel.INTERNAL:
                cmd["message_excerpt"] = rm.get("_cmd_message_excerpt")
            else:
                cmd["message_excerpt_truncated"] = rm.get("_cmd_message_excerpt")

        before_reply: dict[str, Any] = {
            "has_before_result": bool(rm.get("has_before")),
            "skipped_reason_count": rm.get("_before_skipped_reason_count"),
            "brief_source_memory_ids_count": rm.get("brief_source_memory_ids_count"),
        }
        if redaction_level == RedactionLevel.INTERNAL:
            before_reply["skipped_hint"] = rm.get("_before_skipped_hint")

        tick_blk = {
            "opened_court_case_count": rm.get("tick_court_cases"),
            "dream_record_present": rm.get("tick_dream_present"),
        }
        after_blk = {
            "turn_count_after": rm.get("after_turn_count"),
            "seed_count": rm.get("seed_count"),
            "after_reply_semantic_skip": rm.get("after_reply_skipped"),
        }
        feedback_blk: dict[str, Any] = {
            "has_feedback": bool(rm.get("has_feedback")),
        }
        if rm.get("has_feedback"):
            feedback_blk["feedback_id"] = rm.get("feedback_id")
            feedback_blk["summary_len"] = rm.get("feedback_summary_len")
        if redaction_level == RedactionLevel.INTERNAL:
            feedback_blk["summary_preview_truncated"] = rm.get("_internal_feedback_summary")

        sections: dict[str, Any] = {
            "session": {k: v for k, v in sess.items() if v is not None},
            "command": cmd,
            "before_reply": {k: v for k, v in before_reply.items() if v is not None},
            "after_reply": after_blk,
            "tick": tick_blk,
            "feedback": feedback_blk,
            "safety": {"notes": ["Runtime 观测；不含完整对话与 HarvestTrace 大对象。"]},
        }

        internal_ex = rm.get("_internal_turn_excerpts") if isinstance(rm.get("_internal_turn_excerpts"), dict) else {}
        if redaction_level == RedactionLevel.INTERNAL and internal_ex:
            sections["turn_excerpts_internal"] = {
                "user_message_excerpt_truncated": internal_ex.get("user"),
                "assistant_reply_excerpt_truncated": internal_ex.get("assistant"),
            }

        summary_text = _clip(_build_summary_runtime(rm, trace.title), 900)
        return ObservationView(
            redaction_level=redaction_level,
            summary=summary_text,
            sections=sections,
            source_trace_id=trace.trace_id,
            metadata={"observation_adapter": "runtime_v4d"},
        )


def _build_summary_runtime(rm: dict[str, Any], title: str) -> str:
    parts = [
        title or rm.get("trace_name") or "runtime_turn",
        f"会话 {rm.get('session_state','?')}",
        f"简报溯源 id 数≈ {rm.get('brief_source_memory_ids_count', 'n/a')}",
    ]
    return " · ".join(str(p) for p in parts if p)

