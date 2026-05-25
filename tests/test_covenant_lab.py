"""Stage 8G: Covenant-generated Lab contracts."""

from __future__ import annotations

import json

import pytest

from memory_garden.covenant import (
    CovenantValidationError,
    GardenCovenant,
    build_covenant_hard_baseline_assertions,
    build_covenant_safety_lab_suite,
    default_garden_covenant,
    default_garden_covenant_dict,
)
from memory_garden.lab.assertions import evaluate_case
from memory_garden.lab.models import LabTarget


def test_build_hard_baseline_assertions() -> None:
    assertions = build_covenant_hard_baseline_assertions(default_garden_covenant())
    assert len(assertions) == 7
    ids = {a.assertion_id for a in assertions}
    assert "covenant.commands_never_memorized" in ids
    assert "covenant.hard_forgotten_never_visible" in ids
    assert "covenant.api_keys_never_exported" in ids


def test_assertions_cover_expected_lab_targets() -> None:
    assertions = build_covenant_hard_baseline_assertions(default_garden_covenant())
    targets = {a.target for a in assertions}
    assert LabTarget.seed in targets
    assert LabTarget.harvest in targets
    assert LabTarget.observatory in targets
    assert LabTarget.growth in targets


def test_build_covenant_safety_suite_json_safe() -> None:
    suite = build_covenant_safety_lab_suite(default_garden_covenant())
    blob = suite.model_dump(mode="json")
    json.dumps(blob)
    assert suite.suite_id == "lab_suite_covenant_hard_baselines_8g_v1"
    assert suite.cases[0].metadata["snapshot_contract"] is True
    assert "covenant_hash" in suite.metadata


def test_covenant_safety_suite_passes_with_good_snapshot() -> None:
    suite = build_covenant_safety_lab_suite(default_garden_covenant())
    case = suite.cases[0]
    result = evaluate_case(
        case,
        {
            "seed": {
                "commands_memorized_count": 0,
                "assistant_memory_without_adoption_count": 0,
            },
            "harvest": {
                "unsupported_preference_instruction_count": 0,
                "full_garden_context_model_call_count": 0,
            },
            "observatory": {
                "hard_forgotten_text_leak_count": 0,
                "api_key_export_count": 0,
            },
            "growth": {
                "hard_forget_overrode_compost": True,
            },
        },
    )
    assert result.status == "passed"


def test_covenant_safety_suite_fails_with_bad_snapshot() -> None:
    suite = build_covenant_safety_lab_suite(default_garden_covenant())
    case = suite.cases[0]
    result = evaluate_case(
        case,
        {
            "seed": {
                "commands_memorized_count": 1,
                "assistant_memory_without_adoption_count": 0,
            },
            "harvest": {
                "unsupported_preference_instruction_count": 0,
                "full_garden_context_model_call_count": 0,
            },
            "observatory": {
                "hard_forgotten_text_leak_count": 0,
                "api_key_export_count": 0,
            },
            "growth": {
                "hard_forget_overrode_compost": True,
            },
        },
    )
    assert result.status == "failed"
    assert result.failures[0].field_path == "commands_memorized_count"


def test_unsafe_covenant_cannot_generate_lab_contracts() -> None:
    data = default_garden_covenant_dict()
    data["hard_baselines"]["commands_never_memorized"] = False
    with pytest.raises(CovenantValidationError):
        build_covenant_safety_lab_suite(GardenCovenant.model_validate(data))
