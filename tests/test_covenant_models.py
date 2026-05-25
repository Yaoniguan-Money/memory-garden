"""Stage 8A: Garden Covenant models and defaults."""

from __future__ import annotations

import json

from pydantic import ValidationError

from memory_garden.covenant import (
    ConsentDefaultState,
    FeedbackMode,
    GardenCovenant,
    ModelCallPurpose,
    default_garden_covenant,
    default_garden_covenant_dict,
)


def test_default_covenant_loads() -> None:
    covenant = default_garden_covenant()
    assert covenant.version == 1
    assert covenant.consent.default_state == ConsentDefaultState.closed
    assert covenant.visibility.feedback_mode == FeedbackMode.closing_only


def test_default_covenant_json_round_trip() -> None:
    covenant = default_garden_covenant()
    blob = covenant.model_dump(mode="json")
    json.dumps(blob)
    restored = GardenCovenant.model_validate(blob)
    assert restored == covenant


def test_default_covenant_dict_is_json_safe() -> None:
    blob = default_garden_covenant_dict()
    json.dumps(blob)
    assert blob["hard_baselines"]["commands_never_memorized"] is True


def test_default_commands_include_primary_and_aliases() -> None:
    covenant = default_garden_covenant()
    assert "花花开" in covenant.consent.open_commands
    assert "/garden on" in covenant.consent.open_commands
    assert "花花关" in covenant.consent.close_commands
    assert "/garden off" in covenant.consent.close_commands


def test_default_hard_baselines_are_true() -> None:
    baselines = default_garden_covenant().hard_baselines.model_dump()
    assert baselines
    assert all(v is True for v in baselines.values())


def test_default_external_model_policy_is_selected_context_only() -> None:
    policy = default_garden_covenant().model_calls
    assert policy.allow_external_llm is True
    assert policy.allow_full_garden_context is False
    assert policy.allow_greenhouse_raw_text is False
    assert policy.allow_hard_forgotten_text is False
    assert policy.require_selected_context_only is True
    assert policy.record_model_calls is True


def test_default_model_purposes_include_required_values() -> None:
    purposes = set(default_garden_covenant().model_calls.allowed_model_call_purposes)
    assert ModelCallPurpose.memory_lens in purposes
    assert ModelCallPurpose.brief_writer in purposes
    assert ModelCallPurpose.llm_judge in purposes
    assert ModelCallPurpose.rerank in purposes
    assert ModelCallPurpose.seed_extraction in purposes
    assert ModelCallPurpose.dream_reflection in purposes
    assert ModelCallPurpose.court_argument in purposes


def test_unknown_top_level_field_rejected() -> None:
    data = default_garden_covenant_dict()
    data["unknown"] = True
    try:
        GardenCovenant.model_validate(data)
    except ValidationError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown field should be rejected")


def test_unknown_nested_field_rejected() -> None:
    data = default_garden_covenant_dict()
    data["consent"]["unknown"] = True
    try:
        GardenCovenant.model_validate(data)
    except ValidationError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown nested field should be rejected")
