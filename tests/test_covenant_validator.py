"""Stage 8B: Covenant validation and hard baselines."""

from __future__ import annotations

import pytest

from memory_garden.covenant import (
    CovenantValidationError,
    GardenCovenant,
    default_garden_covenant,
    default_garden_covenant_dict,
    validate_covenant,
)


def _covenant_with(path: str, value: object) -> GardenCovenant:
    data = default_garden_covenant_dict()
    cur = data
    parts = path.split(".")
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = value
    return GardenCovenant.model_validate(data)


def _fails(path: str, value: object) -> CovenantValidationError:
    with pytest.raises(CovenantValidationError) as exc:
        validate_covenant(_covenant_with(path, value))
    return exc.value


def test_default_covenant_validates() -> None:
    covenant = default_garden_covenant()
    assert validate_covenant(covenant) is covenant


def test_unsupported_version_fails() -> None:
    err = _fails("version", 99)
    assert err.field_path == "version"
    assert "Unsupported" in str(err)


@pytest.mark.parametrize(
    "field",
    [
        "hard_baselines.hard_forgotten_never_visible",
        "hard_baselines.commands_never_memorized",
        "hard_baselines.unsupported_user_preference_never_in_brief",
        "hard_baselines.hard_forget_overrides_compost",
        "hard_baselines.ai_self_memory_requires_user_adoption",
        "hard_baselines.external_model_never_receives_full_garden_by_default",
        "hard_baselines.api_keys_never_exported",
    ],
)
def test_hard_baselines_cannot_be_disabled(field: str) -> None:
    err = _fails(field, False)
    assert err.field_path == field
    assert "Hard baselines" in str(err)


def test_open_commands_cannot_be_empty() -> None:
    err = _fails("consent.open_commands", [])
    assert err.field_path == "consent.open_commands"


def test_close_commands_cannot_be_empty() -> None:
    err = _fails("consent.close_commands", [])
    assert err.field_path == "consent.close_commands"


def test_open_close_commands_cannot_overlap() -> None:
    data = default_garden_covenant_dict()
    data["consent"]["close_commands"] = ["花花开"]
    with pytest.raises(CovenantValidationError) as exc:
        validate_covenant(GardenCovenant.model_validate(data))
    assert exc.value.field_path == "consent.open_commands"


@pytest.mark.parametrize(
    "field",
        [
            "consent.memorize_commands",
            "model_calls.allow_full_garden_context",
        "model_calls.allow_greenhouse_raw_text",
        "model_calls.allow_hard_forgotten_text",
        "harvest.allow_unsupported_user_preference_instruction",
        "sensitive_memory.allow_greenhouse_raw_text_in_debug",
        "portability.export_api_keys",
        "portability.export_hard_forgotten_text",
        "portability.export_greenhouse_raw_text",
    ],
)
def test_dangerous_true_switches_fail(field: str) -> None:
    err = _fails(field, True)
    assert err.field_path == field
    assert err.suggestion


def test_ai_self_memory_requires_user_adoption_signal() -> None:
    data = default_garden_covenant_dict()
    data["memory_admission"]["allow_ai_self_memory"] = True
    data["memory_admission"]["require_user_adoption_signal"] = False
    with pytest.raises(CovenantValidationError) as exc:
        validate_covenant(GardenCovenant.model_validate(data))
    assert exc.value.field_path == "memory_admission.require_user_adoption_signal"


@pytest.mark.parametrize(
    "field",
    [
        "memory_admission.control_commands_never_memorized",
        "emotional_safety.prevent_negative_identity_lock",
        "emotional_safety.hard_forget_overrides_compost",
        "model_calls.require_selected_context_only",
        "harvest.require_source_memory_ids",
        "sensitive_memory.greenhouse_excluded_from_harvest",
        "visibility.report_hide_hard_forgotten_text",
        "visibility.report_hide_greenhouse_raw_text",
    ],
)
def test_dangerous_false_switches_fail(field: str) -> None:
    err = _fails(field, False)
    assert err.field_path == field
    assert err.suggestion


def test_brief_budget_too_large_fails() -> None:
    err = _fails("harvest.brief_token_budget", 4001)
    assert err.field_path == "harvest.brief_token_budget"


def test_max_selected_memories_too_large_fails() -> None:
    err = _fails("harvest.max_selected_memories", 65)
    assert err.field_path == "harvest.max_selected_memories"


def test_model_memory_count_cannot_exceed_harvest_limit() -> None:
    data = default_garden_covenant_dict()
    data["harvest"]["max_selected_memories"] = 3
    data["model_calls"]["max_memories_per_model_call"] = 4
    with pytest.raises(CovenantValidationError) as exc:
        validate_covenant(GardenCovenant.model_validate(data))
    assert exc.value.field_path == "model_calls.max_memories_per_model_call"
