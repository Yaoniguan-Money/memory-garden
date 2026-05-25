"""Lab helpers generated from Garden Covenant.

These helpers create snapshot assertions only. They do not run Lab suites or
call Memory Garden product layers.
"""

from __future__ import annotations

from memory_garden.covenant.audit import covenant_hash
from memory_garden.covenant.models import GardenCovenant
from memory_garden.covenant.validator import validate_covenant
from memory_garden.lab.models import LabAssertion, LabAssertionType, LabCase, LabSuite, LabTarget


def build_covenant_hard_baseline_assertions(covenant: GardenCovenant) -> list[LabAssertion]:
    """Build deterministic Lab assertions from covenant hard baselines."""
    validate_covenant(covenant)
    return [
        LabAssertion(
            assertion_id="covenant.commands_never_memorized",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.seed,
            field_path="commands_memorized_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.ai_self_memory_requires_user_adoption",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.seed,
            field_path="assistant_memory_without_adoption_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.unsupported_user_preference_never_in_brief",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.harvest,
            field_path="unsupported_preference_instruction_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.external_model_never_receives_full_garden_by_default",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.harvest,
            field_path="full_garden_context_model_call_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.hard_forgotten_never_visible",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.observatory,
            field_path="hard_forgotten_text_leak_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.api_keys_never_exported",
            assertion_type=LabAssertionType.equals,
            target=LabTarget.observatory,
            field_path="api_key_export_count",
            expected=0,
        ),
        LabAssertion(
            assertion_id="covenant.hard_forget_overrides_compost",
            assertion_type=LabAssertionType.is_true,
            target=LabTarget.growth,
            field_path="hard_forget_overrode_compost",
            expected=None,
        ),
    ]


def build_covenant_safety_lab_suite(covenant: GardenCovenant) -> LabSuite:
    """Build a snapshot-contract LabSuite from a covenant."""
    assertions = build_covenant_hard_baseline_assertions(covenant)
    return LabSuite(
        suite_id="lab_suite_covenant_hard_baselines_8g_v1",
        name="Lab Covenant Hard Baselines",
        cases=[
            LabCase(
                case_id="lab.8g.covenant.hard_baselines.snapshot_contract.v1",
                name="Covenant hard baselines snapshot contract",
                description="Snapshot contract for non-overridable Memory Garden hard baselines.",
                assertions=assertions,
                metadata={
                    "primary_target": "covenant",
                    "fixture_kind": "covenant_hard_baselines",
                    "snapshot_contract": True,
                    "covenant_hash": covenant_hash(covenant),
                },
            )
        ],
        metadata={
            "fixture_kind": "covenant_hard_baselines",
            "version": "8g",
            "snapshot_contract": True,
            "covenant_hash": covenant_hash(covenant),
        },
    )


__all__ = ["build_covenant_hard_baseline_assertions", "build_covenant_safety_lab_suite"]
