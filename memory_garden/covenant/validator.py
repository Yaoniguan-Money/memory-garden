"""Garden Covenant validation."""

from __future__ import annotations


from memory_garden.covenant.errors import CovenantValidationError
from memory_garden.covenant.models import GardenCovenant


class CovenantValidator:
    """Validate hard baselines and dangerous policy combinations."""

    supported_versions: tuple[int, ...] = (1,)

    def validate(self, covenant: GardenCovenant) -> GardenCovenant:
        self._errors: list[CovenantValidationError] = []
        if covenant.version not in self.supported_versions:
            self._record("version", f"Unsupported covenant version: {covenant.version}", "Use version=1.")

        self._validate_all_true(
            "hard_baselines",
            covenant.hard_baselines.model_dump(),
            "Hard baselines cannot be disabled.",
        )
        self._validate_commands(covenant)
        self._validate_dangerous_switches(covenant)
        self._validate_budgets(covenant)
        self._raise_if_errors()
        return covenant

    def _record(self, field_path: str, message: str, suggestion: str) -> None:
        self._errors.append(CovenantValidationError(message, field_path=field_path, suggestion=suggestion))

    def _raise_if_errors(self) -> None:
        if not self._errors:
            return
        first = self._errors[0]
        details = "; ".join(f"{e.field_path}: {e}" for e in self._errors)
        raise CovenantValidationError(
            f"{first} ({len(self._errors)} violation(s): {details})",
            field_path=first.field_path,
            suggestion=first.suggestion,
            violations=self._errors,
        )

    def _validate_all_true(self, prefix: str, values: dict[str, object], message: str) -> None:
        for name, value in values.items():
            if value is not True:
                self._record(f"{prefix}.{name}", message, f"Set {prefix}.{name}=true.")

    def _validate_commands(self, covenant: GardenCovenant) -> None:
        open_commands = [c.strip() for c in covenant.consent.open_commands if c.strip()]
        close_commands = [c.strip() for c in covenant.consent.close_commands if c.strip()]
        if not open_commands:
            self._record("consent.open_commands", "Open commands cannot be empty.", "Keep at least one open command.")
        if not close_commands:
            self._record("consent.close_commands", "Close commands cannot be empty.", "Keep at least one close command.")
        if set(open_commands) & set(close_commands):
            self._record(
                "consent.open_commands",
                "Open and close commands must not overlap.",
                "Use distinct command aliases.",
            )

    def _validate_dangerous_switches(self, covenant: GardenCovenant) -> None:
        if covenant.consent.memorize_commands:
            self._record(
                "consent.memorize_commands",
                "Control commands cannot be memorized.",
                "Set consent.memorize_commands=false.",
            )
        if not covenant.memory_admission.control_commands_never_memorized:
            self._record(
                "memory_admission.control_commands_never_memorized",
                "Control commands must stay outside memory.",
                "Set memory_admission.control_commands_never_memorized=true.",
            )
        if covenant.memory_admission.allow_ai_self_memory and covenant.memory_admission.require_user_adoption_signal is False:
            self._record(
                "memory_admission.require_user_adoption_signal",
                "AI self-memory requires explicit user adoption.",
                "Keep require_user_adoption_signal=true.",
            )
        if not covenant.emotional_safety.prevent_negative_identity_lock:
            self._record(
                "emotional_safety.prevent_negative_identity_lock",
                "Negative identity lock prevention cannot be disabled.",
                "Set emotional_safety.prevent_negative_identity_lock=true.",
            )
        if not covenant.emotional_safety.hard_forget_overrides_compost:
            self._record(
                "emotional_safety.hard_forget_overrides_compost",
                "Hard forget must override compost.",
                "Set emotional_safety.hard_forget_overrides_compost=true.",
            )
        if covenant.model_calls.allow_full_garden_context:
            self._record(
                "model_calls.allow_full_garden_context",
                "External model calls cannot receive the full garden by default.",
                "Set model_calls.allow_full_garden_context=false.",
            )
        if covenant.model_calls.allow_greenhouse_raw_text:
            self._record(
                "model_calls.allow_greenhouse_raw_text",
                "External model calls cannot receive greenhouse raw text by default.",
                "Set model_calls.allow_greenhouse_raw_text=false.",
            )
        if covenant.model_calls.allow_hard_forgotten_text:
            self._record(
                "model_calls.allow_hard_forgotten_text",
                "Hard forgotten text must never be sent to external models.",
                "Set model_calls.allow_hard_forgotten_text=false.",
            )
        if not covenant.model_calls.require_selected_context_only:
            self._record(
                "model_calls.require_selected_context_only",
                "Model calls must use selected context only.",
                "Set model_calls.require_selected_context_only=true.",
            )
        if covenant.harvest.allow_unsupported_user_preference_instruction:
            self._record(
                "harvest.allow_unsupported_user_preference_instruction",
                "Unsupported user preference instructions cannot enter Garden Brief.",
                "Set harvest.allow_unsupported_user_preference_instruction=false.",
            )
        if covenant.harvest.require_source_memory_ids is False:
            self._record(
                "harvest.require_source_memory_ids",
                "Garden Brief preference instructions require source memory ids.",
                "Set harvest.require_source_memory_ids=true.",
            )
        if covenant.sensitive_memory.greenhouse_excluded_from_harvest is False:
            self._record(
                "sensitive_memory.greenhouse_excluded_from_harvest",
                "Greenhouse memories must be excluded from ordinary harvest by default.",
                "Set sensitive_memory.greenhouse_excluded_from_harvest=true.",
            )
        if covenant.sensitive_memory.allow_greenhouse_raw_text_in_debug:
            self._record(
                "sensitive_memory.allow_greenhouse_raw_text_in_debug",
                "Debug mode cannot bypass greenhouse raw text protection.",
                "Set sensitive_memory.allow_greenhouse_raw_text_in_debug=false.",
            )
        if covenant.visibility.report_hide_hard_forgotten_text is False:
            self._record(
                "visibility.report_hide_hard_forgotten_text",
                "Reports must hide hard forgotten text.",
                "Set visibility.report_hide_hard_forgotten_text=true.",
            )
        if covenant.visibility.report_hide_greenhouse_raw_text is False:
            self._record(
                "visibility.report_hide_greenhouse_raw_text",
                "Reports must hide greenhouse raw text by default.",
                "Set visibility.report_hide_greenhouse_raw_text=true.",
            )
        if covenant.portability.export_api_keys:
            self._record(
                "portability.export_api_keys",
                "API keys must never be exported.",
                "Set portability.export_api_keys=false.",
            )
        if covenant.portability.export_hard_forgotten_text:
            self._record(
                "portability.export_hard_forgotten_text",
                "Hard forgotten text must never be exported.",
                "Set portability.export_hard_forgotten_text=false.",
            )
        if covenant.portability.export_greenhouse_raw_text:
            self._record(
                "portability.export_greenhouse_raw_text",
                "Greenhouse raw text must not be exported by default.",
                "Set portability.export_greenhouse_raw_text=false.",
            )

    def _validate_budgets(self, covenant: GardenCovenant) -> None:
        if not 1 <= covenant.harvest.brief_token_budget <= 4000:
            self._record(
                "harvest.brief_token_budget",
                "Brief token budget is outside the supported range.",
                "Use a value between 1 and 4000.",
            )
        if not 0 <= covenant.harvest.max_selected_memories <= 64:
            self._record(
                "harvest.max_selected_memories",
                "max_selected_memories is outside the supported range.",
                "Use a value between 0 and 64.",
            )
        if covenant.model_calls.max_memories_per_model_call > covenant.harvest.max_selected_memories:
            self._record(
                "model_calls.max_memories_per_model_call",
                "Model calls cannot receive more memories than harvest may select.",
                "Keep model call memory count within harvest.max_selected_memories.",
            )


def validate_covenant(covenant: GardenCovenant) -> GardenCovenant:
    """Validate and return the covenant if it is safe."""
    return CovenantValidator().validate(covenant)


def assert_covenant_safe(covenant: GardenCovenant) -> None:
    """Raise CovenantValidationError if a covenant is unsafe."""
    validate_covenant(covenant)


__all__ = ["CovenantValidator", "assert_covenant_safe", "validate_covenant"]
