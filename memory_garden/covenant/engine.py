"""Garden Covenant policy engine.

The engine is read-only: it returns PolicyDecision objects and never mutates
objects from earlier Memory Garden layers.
"""

from __future__ import annotations

from typing import Any

from memory_garden.covenant.decisions import PolicyDecision, PolicySeverity
from memory_garden.covenant.models import GardenCovenant
from memory_garden.covenant.validator import validate_covenant


def _read(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _read_any(obj: Any, keys: list[str], default: Any = None) -> Any:
    for key in keys:
        value = _read(obj, key, None)
        if value is not None:
            return value
    return default


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _tags(obj: Any) -> set[str]:
    raw = _read(obj, "tags", [])
    return {_as_str(v).casefold() for v in raw or []}


def _metadata(obj: Any) -> dict[str, Any]:
    raw = _read(obj, "metadata", {})
    return raw if isinstance(raw, dict) else {}


def _truthy_flag(obj: Any, keys: list[str]) -> bool:
    meta = _metadata(obj)
    for key in keys:
        if bool(_read(obj, key, False)) or bool(meta.get(key, False)):
            return True
    return False


class PolicyEngine:
    """Central policy engine for Memory Garden."""

    def __init__(self, covenant: GardenCovenant):
        self.covenant = validate_covenant(covenant)

    def _decision(
        self,
        *,
        policy_name: str,
        action: str,
        allowed: bool,
        reason: str,
        matched_rules: list[str],
        severity: PolicySeverity = PolicySeverity.info,
        object_type: str | None = None,
        object_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        return PolicyDecision(
            policy_name=policy_name,
            action=action,
            allowed=allowed,
            reason=reason,
            matched_rules=matched_rules,
            severity=severity,
            object_type=object_type,
            object_id=object_id,
            metadata=dict(metadata or {}),
        )

    def _matches_command(self, text: str, commands: list[str]) -> str | None:
        normalized = text.strip()
        for command in commands:
            if normalized == command:
                return command
            if command.startswith("/") and normalized.casefold() == command.casefold():
                return command
        return None

    def is_open_command(self, text: str) -> PolicyDecision:
        matched = self._matches_command(text, self.covenant.consent.open_commands)
        return self._decision(
            policy_name="consent",
            action="is_open_command",
            allowed=matched is not None,
            reason="Text matches an open command." if matched else "Text is not an open command.",
            matched_rules=["consent.open_commands"] if matched else [],
            metadata={"matched_alias": matched},
        )

    def is_close_command(self, text: str) -> PolicyDecision:
        matched = self._matches_command(text, self.covenant.consent.close_commands)
        return self._decision(
            policy_name="consent",
            action="is_close_command",
            allowed=matched is not None,
            reason="Text matches a close command." if matched else "Text is not a close command.",
            matched_rules=["consent.close_commands"] if matched else [],
            metadata={"matched_alias": matched},
        )

    def should_memorize_command(self, text: str) -> PolicyDecision:
        command = self.is_open_command(text)
        if not command.allowed:
            command = self.is_close_command(text)
        if command.allowed:
            return self._decision(
                policy_name="consent",
                action="ignore_command",
                allowed=False,
                reason="Control commands must not become user memory.",
                matched_rules=["hard_baselines.commands_never_memorized", "consent.memorize_commands"],
                severity=PolicySeverity.critical,
                metadata={"matched_alias": command.metadata.get("matched_alias")},
            )
        return self._decision(
            policy_name="consent",
            action="allow_regular_text",
            allowed=True,
            reason="Text is not a control command; regular memory policy may evaluate it.",
            matched_rules=[],
            severity=PolicySeverity.info,
        )

    def can_admit_seed(self, seed: Any, context: dict[str, Any] | None = None) -> PolicyDecision:
        context = dict(context or {})
        content = _as_str(_read_any(seed, ["content", "source_excerpt", "text"], ""))
        seed_id = _as_str(_read(seed, "id", "")) or None
        signal_type = _as_str(_read(seed, "signal_type", "")).casefold()
        source_role = _as_str(context.get("source_role") or _read(seed, "source_role", "")).casefold()
        adopted = bool(context.get("user_adopted") or _read(seed, "user_adopted", False))

        if self.is_open_command(content).allowed or self.is_close_command(content).allowed:
            return self._decision(
                policy_name="memory_admission",
                action="admit_seed",
                allowed=False,
                reason="Control commands are excluded from memory admission.",
                matched_rules=[
                    "hard_baselines.commands_never_memorized",
                    "memory_admission.control_commands_never_memorized",
                ],
                severity=PolicySeverity.critical,
                object_type="seed",
                object_id=seed_id,
            )
        if source_role == "assistant" and not adopted:
            return self._decision(
                policy_name="memory_admission",
                action="admit_seed",
                allowed=False,
                reason="Assistant statements require explicit user adoption before becoming user memory.",
                matched_rules=["hard_baselines.ai_self_memory_requires_user_adoption"],
                severity=PolicySeverity.warning,
                object_type="seed",
                object_id=seed_id,
            )
        if signal_type == "negative_self_talk":
            return self._decision(
                policy_name="memory_admission",
                action="admit_seed",
                allowed=False,
                reason="Negative self-talk should not be admitted as a stable memory seed.",
                matched_rules=["emotional_safety.prevent_negative_identity_lock"],
                severity=PolicySeverity.warning,
                object_type="seed",
                object_id=seed_id,
            )
        return self._decision(
            policy_name="memory_admission",
            action="admit_seed",
            allowed=True,
            reason="Seed does not violate admission policy.",
            matched_rules=["memory_admission.default_allow"],
            object_type="seed",
            object_id=seed_id,
        )

    def should_prevent_negative_identity_lock(self, text: str) -> PolicyDecision:
        lowered = text.casefold()
        matched = [
            phrase
            for phrase in self.covenant.emotional_safety.forbidden_identity_phrases
            if phrase.casefold() in lowered
        ]
        if matched:
            return self._decision(
                policy_name="emotional_safety",
                action="prevent_negative_identity_lock",
                allowed=False,
                reason="Negative self-description must not become stable identity memory.",
                matched_rules=["emotional_safety.prevent_negative_identity_lock"],
                severity=PolicySeverity.critical,
                metadata={"matched_phrases": matched},
            )
        return self._decision(
            policy_name="emotional_safety",
            action="prevent_negative_identity_lock",
            allowed=True,
            reason="No negative identity lock phrase matched.",
            matched_rules=[],
        )

    def route_sensitive_memory(self, seed_or_memory: Any) -> PolicyDecision:
        sensitivity = _as_str(_read(seed_or_memory, "sensitivity", "")).casefold()
        signal_type = _as_str(_read(seed_or_memory, "signal_type", "")).casefold()
        tags = _tags(seed_or_memory)
        object_id = _as_str(_read(seed_or_memory, "id", "")) or None
        sensitive = (
            sensitivity in {"medium", "high"}
            or signal_type == "sensitive_info"
            or bool(tags & {"sensitive", "private", "greenhouse"})
        )
        if sensitive and self.covenant.sensitive_memory.greenhouse_default_for_sensitive:
            return self._decision(
                policy_name="sensitive_memory",
                action="route_to_greenhouse",
                allowed=True,
                reason="Sensitive memory should be routed to greenhouse.",
                matched_rules=["sensitive_memory.greenhouse_default_for_sensitive"],
                object_type="memory",
                object_id=object_id,
                metadata={"route": "greenhouse"},
            )
        return self._decision(
            policy_name="sensitive_memory",
            action="route_to_greenhouse",
            allowed=False,
            reason="No sensitive memory signal matched.",
            matched_rules=[],
            object_type="memory",
            object_id=object_id,
            metadata={"route": "ordinary"},
        )

    def can_harvest_memory(self, memory: Any, purpose: str = "brief") -> PolicyDecision:
        memory_id = _as_str(_read(memory, "id", "")) or None
        lifecycle = _as_str(_read(memory, "lifecycle", "")).casefold()
        sensitivity = _as_str(_read(memory, "sensitivity", "")).casefold()
        tags = _tags(memory)

        if _truthy_flag(memory, ["hard_forgotten", "hard_forgotten_text"]):
            return self._decision(
                policy_name="harvest",
                action="exclude_from_harvest",
                allowed=False,
                reason="Hard forgotten memory cannot be harvested.",
                matched_rules=["hard_baselines.hard_forgotten_never_visible"],
                severity=PolicySeverity.critical,
                object_type="memory_card",
                object_id=memory_id,
            )
        if lifecycle in {"greenhouse", "greenhoused"} or sensitivity in {"medium", "high"} or "greenhouse" in tags:
            allowed = purpose in self.covenant.harvest.greenhouse_allowed_slots
            return self._decision(
                policy_name="harvest",
                action="exclude_from_harvest" if not allowed else "allow_harvest",
                allowed=allowed,
                reason="Greenhouse memory is excluded from ordinary harvest."
                if not allowed
                else "Greenhouse memory is allowed for an explicitly configured slot.",
                matched_rules=["sensitive_memory.greenhouse_excluded_from_harvest"],
                severity=PolicySeverity.warning if not allowed else PolicySeverity.info,
                object_type="memory_card",
                object_id=memory_id,
                metadata={"allowed_slots": list(self.covenant.harvest.greenhouse_allowed_slots)},
            )
        if lifecycle in {"pruned", "prune"}:
            allowed = purpose in self.covenant.harvest.pruned_memory_allowed_slots
            return self._decision(
                policy_name="harvest",
                action="allow_harvest" if allowed else "exclude_from_harvest",
                allowed=allowed,
                reason="Pruned memory is only allowed in configured slots.",
                matched_rules=["harvest.pruned_memory_allowed_slots"],
                object_type="memory_card",
                object_id=memory_id,
                metadata={"allowed_slots": list(self.covenant.harvest.pruned_memory_allowed_slots)},
            )
        if lifecycle in {"compost", "composted"}:
            allowed = purpose in self.covenant.harvest.compost_allowed_slots
            return self._decision(
                policy_name="harvest",
                action="allow_harvest" if allowed else "exclude_from_harvest",
                allowed=allowed,
                reason="Compost memory is only allowed in configured slots.",
                matched_rules=["harvest.compost_allowed_slots"],
                object_type="memory_card",
                object_id=memory_id,
                metadata={"allowed_slots": list(self.covenant.harvest.compost_allowed_slots)},
            )
        return self._decision(
            policy_name="harvest",
            action="allow_harvest",
            allowed=True,
            reason="Memory is eligible for ordinary harvest.",
            matched_rules=["harvest.default_allow"],
            object_type="memory_card",
            object_id=memory_id,
        )

    def allowed_brief_slots(self, memory: Any) -> PolicyDecision:
        lifecycle = _as_str(_read(memory, "lifecycle", "")).casefold()
        memory_id = _as_str(_read(memory, "id", "")) or None
        if lifecycle in {"greenhouse", "greenhoused"}:
            slots = list(self.covenant.harvest.greenhouse_allowed_slots)
        elif lifecycle in {"pruned", "prune"}:
            slots = list(self.covenant.harvest.pruned_memory_allowed_slots)
        elif lifecycle in {"compost", "composted"}:
            slots = list(self.covenant.harvest.compost_allowed_slots)
        else:
            slots = ["intent", "use", "style", "avoid", "safety", "nudge"]
        return self._decision(
            policy_name="harvest",
            action="allow_brief_instruction",
            allowed=bool(slots),
            reason="Allowed brief slots were derived from memory lifecycle.",
            matched_rules=["harvest.allowed_slots"],
            object_type="memory_card",
            object_id=memory_id,
            metadata={"allowed_slots": slots},
        )

    def can_write_brief_instruction(self, instruction: str, source_memory_ids: list[str]) -> PolicyDecision:
        looks_like_preference = any(
            token in instruction.casefold()
            for token in ["prefer", "preference", "likes", "喜欢", "偏好", "默认", "always"]
        )
        if self.covenant.harvest.require_source_memory_ids and looks_like_preference and not source_memory_ids:
            return self._decision(
                policy_name="harvest",
                action="reject_brief_instruction",
                allowed=False,
                reason="User preference instructions require source_memory_ids.",
                matched_rules=[
                    "hard_baselines.unsupported_user_preference_never_in_brief",
                    "harvest.require_source_memory_ids",
                ],
                severity=PolicySeverity.critical,
            )
        return self._decision(
            policy_name="harvest",
            action="allow_brief_instruction",
            allowed=True,
            reason="Brief instruction has sufficient support.",
            matched_rules=["harvest.require_source_memory_ids"] if source_memory_ids else [],
        )

    def can_send_to_model(
        self,
        payload: Any,
        purpose: str,
        model_provider: str | None = None,
    ) -> PolicyDecision:
        policy = self.covenant.model_calls
        allowed_purposes = {p.value if hasattr(p, "value") else str(p) for p in policy.allowed_model_call_purposes}
        metadata = {"purpose": purpose, "model_provider": model_provider}
        if purpose not in allowed_purposes:
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="Model call purpose is not allowed by covenant.",
                matched_rules=["model_calls.allowed_model_call_purposes"],
                severity=PolicySeverity.warning,
                metadata=metadata,
            )
        if not policy.allow_external_llm:
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="External model calls are disabled.",
                matched_rules=["model_calls.allow_external_llm"],
                severity=PolicySeverity.warning,
                metadata=metadata,
            )
        if _truthy_flag(payload, ["full_garden_context"]):
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="External model calls cannot receive full garden context.",
                matched_rules=["hard_baselines.external_model_never_receives_full_garden_by_default"],
                severity=PolicySeverity.critical,
                metadata=metadata,
            )
        if _truthy_flag(payload, ["greenhouse_raw_text"]):
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="External model calls cannot receive greenhouse raw text by default.",
                matched_rules=["model_calls.allow_greenhouse_raw_text"],
                severity=PolicySeverity.critical,
                metadata=metadata,
            )
        if _truthy_flag(payload, ["hard_forgotten_text", "hard_forgotten"]):
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="External model calls cannot receive hard forgotten text.",
                matched_rules=["model_calls.allow_hard_forgotten_text"],
                severity=PolicySeverity.critical,
                metadata=metadata,
            )
        if _truthy_flag(payload, ["api_key", "contains_api_key"]):
            return self._decision(
                policy_name="model_calls",
                action="block_model_call",
                allowed=False,
                reason="API keys must not be included in model payloads.",
                matched_rules=["hard_baselines.api_keys_never_exported"],
                severity=PolicySeverity.critical,
                metadata=metadata,
            )
        return self._decision(
            policy_name="model_calls",
            action="allow_model_call",
            allowed=True,
            reason="Model call payload satisfies covenant constraints.",
            matched_rules=["model_calls.require_selected_context_only"],
            metadata=metadata,
        )

    def can_display_memory(self, memory: Any, surface: str, debug: bool = False) -> PolicyDecision:
        memory_id = _as_str(_read(memory, "id", "")) or None
        lifecycle = _as_str(_read(memory, "lifecycle", "")).casefold()
        if _truthy_flag(memory, ["hard_forgotten", "hard_forgotten_text"]):
            return self._decision(
                policy_name="visibility",
                action="redact_report_display",
                allowed=False,
                reason="Hard forgotten text is never visible.",
                matched_rules=["hard_baselines.hard_forgotten_never_visible"],
                severity=PolicySeverity.critical,
                object_type="memory_card",
                object_id=memory_id,
                metadata={"surface": surface, "debug": debug},
            )
        if _truthy_flag(memory, ["redacted_text", "redacted"]):
            return self._decision(
                policy_name="visibility",
                action="redact_report_display",
                allowed=debug and self.covenant.visibility.debug_can_show_redacted_text,
                reason="Redacted text is hidden by default.",
                matched_rules=["visibility.report_hide_redacted_text"],
                severity=PolicySeverity.warning,
                object_type="memory_card",
                object_id=memory_id,
                metadata={"surface": surface, "debug": debug},
            )
        if lifecycle in {"greenhouse", "greenhoused"} and self.covenant.visibility.report_hide_greenhouse_raw_text:
            return self._decision(
                policy_name="visibility",
                action="redact_report_display",
                allowed=False,
                reason="Greenhouse raw text is hidden on report surfaces.",
                matched_rules=["visibility.report_hide_greenhouse_raw_text"],
                severity=PolicySeverity.warning,
                object_type="memory_card",
                object_id=memory_id,
                metadata={"surface": surface, "debug": debug},
            )
        return self._decision(
            policy_name="visibility",
            action="allow_report_display",
            allowed=True,
            reason="Memory can be displayed on the requested surface.",
            matched_rules=["visibility.default_allow"],
            object_type="memory_card",
            object_id=memory_id,
            metadata={"surface": surface, "debug": debug},
        )

    def can_export_record(self, record: Any, export_mode: str) -> PolicyDecision:
        record_id = _as_str(_read(record, "id", "")) or None
        metadata = {"export_mode": export_mode}
        if _truthy_flag(record, ["api_key", "contains_api_key"]):
            return self._decision(
                policy_name="portability",
                action="block_export",
                allowed=False,
                reason="API keys must never be exported.",
                matched_rules=["hard_baselines.api_keys_never_exported", "portability.export_api_keys"],
                severity=PolicySeverity.critical,
                object_type="record",
                object_id=record_id,
                metadata=metadata,
            )
        if _truthy_flag(record, ["hard_forgotten", "hard_forgotten_text"]):
            return self._decision(
                policy_name="portability",
                action="block_export",
                allowed=False,
                reason="Hard forgotten text must not be exported.",
                matched_rules=["hard_baselines.hard_forgotten_never_visible", "portability.export_hard_forgotten_text"],
                severity=PolicySeverity.critical,
                object_type="record",
                object_id=record_id,
                metadata=metadata,
            )
        if _truthy_flag(record, ["greenhouse_raw_text"]):
            return self._decision(
                policy_name="portability",
                action="block_export",
                allowed=False,
                reason="Greenhouse raw text is excluded from export by default.",
                matched_rules=["portability.export_greenhouse_raw_text"],
                severity=PolicySeverity.warning,
                object_type="record",
                object_id=record_id,
                metadata=metadata,
            )
        if _truthy_flag(record, ["redacted_text", "redacted"]):
            return self._decision(
                policy_name="portability",
                action="block_export",
                allowed=False,
                reason="Redacted text is excluded from export by default.",
                matched_rules=["portability.export_redacted_text"],
                severity=PolicySeverity.warning,
                object_type="record",
                object_id=record_id,
                metadata=metadata,
            )
        return self._decision(
            policy_name="portability",
            action="allow_export",
            allowed=True,
            reason="Record can be exported under the requested mode.",
            matched_rules=["portability.default_allow"],
            object_type="record",
            object_id=record_id,
            metadata=metadata,
        )

    def can_hard_forget(self, target: Any) -> PolicyDecision:
        target_id = _as_str(_read(target, "id", "")) or None
        if not target_id:
            return self._decision(
                policy_name="portability",
                action="allow_hard_forget",
                allowed=False,
                reason="Hard forget requires a target id.",
                matched_rules=["portability.keep_minimal_forget_audit"],
                severity=PolicySeverity.warning,
            )
        return self._decision(
            policy_name="portability",
            action="allow_hard_forget",
            allowed=True,
            reason="Hard forget is allowed and must override compost.",
            matched_rules=[
                "hard_baselines.hard_forget_overrides_compost",
                "portability.hard_forget_redacts_traces",
            ],
            object_type="record",
            object_id=target_id,
        )


__all__ = ["PolicyEngine"]
