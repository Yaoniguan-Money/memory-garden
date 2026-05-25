"""Seventh layer Stage 7C: Rule Templates unit tests (assertion factories, no Runner execution)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_garden.lab.assertions import evaluate_case
from memory_garden.lab.models import LabAssertion, LabCase, LabStatus
from memory_garden.lab.rule_templates import (
    assistant_reply_must_not_be_user_memory,
    brief_must_not_expose_full_memory_text,
    brief_requires_source_ids,
    command_must_short_circuit,
    court_allows_verdicts,
    court_forbids_verdicts,
    greenhouse_must_not_enter_positive_brief,
    hard_forget_must_not_leak_text,
    negative_emotion_must_not_plant,
    observatory_public_must_redact_long_text,
    seed_forbids_control_command_memory,
    seed_min_count,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _assertions(obj: LabAssertion | list[LabAssertion]) -> list[LabAssertion]:
    if isinstance(obj, LabAssertion):
        return [obj]
    return list(obj)


def _asserts(obj: LabAssertion | list[LabAssertion]) -> None:
    assertions = _assertions(obj)
    assert len(assertions) >= 1
    for a in assertions:
        assert isinstance(a, LabAssertion)


def _pass(case_id: str, assertions: list[LabAssertion], actual: dict) -> None:
    lc = LabCase(case_id=case_id, assertions=assertions)
    result = evaluate_case(lc, actual)
    assert result.status == LabStatus.passed, f"Expected pass: {[f.message for f in result.failures]}"


def _fail(case_id: str, assertions: list[LabAssertion], actual: dict) -> None:
    lc = LabCase(case_id=case_id, assertions=assertions)
    result = evaluate_case(lc, actual)
    assert result.status == LabStatus.failed, "Expected fail but passed"


# ---------------------------------------------------------------------------
# seed_min_count
# ---------------------------------------------------------------------------

def test_seed_min_count_returns_lab_assertion() -> None:
    a = seed_min_count(3)
    assert isinstance(a, LabAssertion)
    assert a.assertion_type.value == "count_equals"
    assert a.target.value == "seed"
    assert a.field_path == "pending_preference_signals"


def test_seed_min_count_model_dump() -> None:
    a = seed_min_count(2)
    d = a.model_dump(mode="json")
    assert d["expected"] == 2


def test_seed_min_count_pass() -> None:
    a = seed_min_count(2)
    _pass("sp", [a], {"seed": {"pending_preference_signals": ["s1", "s2"]}})


def test_seed_min_count_fail() -> None:
    a = seed_min_count(2)
    _fail("sf", [a], {"seed": {"pending_preference_signals": []}})


# ---------------------------------------------------------------------------
# seed_forbids_control_command_memory
# ---------------------------------------------------------------------------

def test_seed_forbids_returns_list() -> None:
    assertions = seed_forbids_control_command_memory()
    _asserts(assertions)


def test_seed_forbids_model_dump() -> None:
    for a in seed_forbids_control_command_memory():
        a.model_dump(mode="json")


def test_seed_forbids_pass() -> None:
    _pass(
        "sc",
        seed_forbids_control_command_memory(),
        {"seed": {"pending_preference_signals": [], "control_command_only_events": ["cmd_open"]}},
    )


def test_seed_forbids_fail() -> None:
    _fail(
        "sc_f",
        seed_forbids_control_command_memory(),
        {"seed": {"pending_preference_signals": ["bad"], "control_command_echo_as_preference_seed": True}},
    )


# ---------------------------------------------------------------------------
# court_allows_verdicts / court_forbids_verdicts
# ---------------------------------------------------------------------------

def test_court_allows_verdicts_returns_list() -> None:
    assertions = court_allows_verdicts(["plant", "defer"])
    _asserts(assertions)
    assert len(assertions) == 2


def test_court_allows_verdicts_pass() -> None:
    _pass(
        "ca",
        court_allows_verdicts(["plant", "defer"]),
        {"court": {"verdict": ["plant", "defer", "ignore"]}},
    )


def test_court_allows_verdicts_fail() -> None:
    _fail(
        "ca_f",
        court_allows_verdicts(["plant"]),
        {"court": {"verdict": ["defer"]}},
    )


def test_court_forbids_verdicts_returns_list() -> None:
    assertions = court_forbids_verdicts(["reject", "ban"])
    _asserts(assertions)
    assert len(assertions) == 2


def test_court_forbids_verdicts_pass() -> None:
    _pass(
        "cf",
        court_forbids_verdicts(["reject", "ban"]),
        {"court": {"verdict": ["defer", "plant"]}},
    )


def test_court_forbids_verdicts_fail() -> None:
    _fail(
        "cf_f",
        court_forbids_verdicts(["reject"]),
        {"court": {"verdict": ["reject", "defer"]}},
    )


# ---------------------------------------------------------------------------
# negative_emotion_must_not_plant
# ---------------------------------------------------------------------------

def test_negative_emotion_uses_court_targets() -> None:
    assertions = negative_emotion_must_not_plant()
    targets = {a.target.value for a in assertions}
    assert "court" in targets


def test_negative_emotion_pass() -> None:
    _pass(
        "ne",
        negative_emotion_must_not_plant(),
        {
            "court": {
                "allow_plant_as_stable_identity_trait": False,
                "safety_escalations": ["defer_identity_planting"],
            }
        },
    )


def test_negative_emotion_fail() -> None:
    _fail(
        "ne_f",
        negative_emotion_must_not_plant(),
        {
            "court": {
                "allow_plant_as_stable_identity_trait": True,
                "safety_escalations": ["none"],
            }
        },
    )


# ---------------------------------------------------------------------------
# greenhouse_must_not_enter_positive_brief
# ---------------------------------------------------------------------------

def test_greenhouse_uses_harvest_target() -> None:
    assertions = greenhouse_must_not_enter_positive_brief()
    targets = {a.target.value for a in assertions}
    assert targets == {"harvest"}


def test_greenhouse_pass() -> None:
    _pass(
        "gh",
        greenhouse_must_not_enter_positive_brief(),
        {"harvest": {"greenhouse_leak_count": 0}},
    )


def test_greenhouse_fail() -> None:
    _fail(
        "gh_f",
        greenhouse_must_not_enter_positive_brief(),
        {"harvest": {"greenhouse_leak_count": 3, "greenhouse_leaked_to_brief": True}},
    )


# ---------------------------------------------------------------------------
# command_must_short_circuit
# ---------------------------------------------------------------------------

def test_command_short_circuit_uses_runtime_target() -> None:
    assertions = command_must_short_circuit()
    targets = {a.target.value for a in assertions}
    assert targets == {"runtime"}


def test_command_short_circuit_pass() -> None:
    _pass(
        "cmd",
        command_must_short_circuit(),
        {
            "runtime": {
                "command_handled": True,
                "after_reply_called": False,
                "agent_called": False,
            }
        },
    )


def test_command_short_circuit_fail() -> None:
    _fail(
        "cmd_f",
        command_must_short_circuit(),
        {
            "runtime": {
                "command_handled": False,
                "after_reply_called": True,
                "agent_called": True,
            }
        },
    )


# ---------------------------------------------------------------------------
# assistant_reply_must_not_be_user_memory
# ---------------------------------------------------------------------------

def test_assistant_reply_uses_seed_target() -> None:
    assertions = assistant_reply_must_not_be_user_memory()
    assert assertions[0].target.value == "seed"


def test_assistant_reply_pass() -> None:
    _pass(
        "ar",
        assistant_reply_must_not_be_user_memory(),
        {"seed": {"assistant_reply_recorded_as_user_input": False}},
    )


def test_assistant_reply_fail() -> None:
    _fail(
        "ar_f",
        assistant_reply_must_not_be_user_memory(),
        {"seed": {"assistant_reply_recorded_as_user_input": True}},
    )


# ---------------------------------------------------------------------------
# brief_requires_source_ids
# ---------------------------------------------------------------------------

def test_brief_source_ids_pass() -> None:
    _pass(
        "br",
        brief_requires_source_ids(max_count=32),
        {"harvest": {"source_memory_ids": ["m1", "m2"]}},
    )


def test_brief_source_ids_fail_too_many() -> None:
    _fail(
        "br_f",
        brief_requires_source_ids(max_count=2),
        {"harvest": {"source_memory_ids": ["m1", "m2", "m3", "m4"]}},
    )


def test_brief_source_ids_fail_missing() -> None:
    _fail("br_m", brief_requires_source_ids(), {"harvest": {}})


# ---------------------------------------------------------------------------
# brief_must_not_expose_full_memory_text
# ---------------------------------------------------------------------------

def test_brief_no_full_text_pass() -> None:
    _pass(
        "bn",
        brief_must_not_expose_full_memory_text(),
        {"harvest": {"brief_embeds_complete_memory_card_plaintext": False}},
    )


def test_brief_no_full_text_fail() -> None:
    _fail(
        "bn_f",
        brief_must_not_expose_full_memory_text(),
        {"harvest": {"brief_embeds_complete_memory_card_plaintext": True, "serialised_full_cards_bodies_dump": {}}},
    )


# ---------------------------------------------------------------------------
# observatory_public_must_redact_long_text
# ---------------------------------------------------------------------------

def test_observatory_redact_pass() -> None:
    _pass(
        "op",
        observatory_public_must_redact_long_text(),
        {
            "observatory": {
                "public_sections_include_entire_user_message": False,
                "public_sections_include_entire_assistant_reply": False,
            }
        },
    )


def test_observatory_redact_fail() -> None:
    _fail(
        "op_f",
        observatory_public_must_redact_long_text(),
        {
            "observatory": {
                "public_sections_include_entire_user_message": True,
                "public_sections_include_entire_assistant_reply": False,
            }
        },
    )


# ---------------------------------------------------------------------------
# hard_forget_must_not_leak_text
# ---------------------------------------------------------------------------

def test_hard_forget_uses_observatory_target() -> None:
    assertions = hard_forget_must_not_leak_text()
    assert assertions[0].target.value == "observatory"
    assert assertions[0].field_path == "hard_forgotten_text_leak_count"


def test_hard_forget_uses_equals_not_count() -> None:
    """hard_forgotten_text_leak_count is an int, asserted via equals not count_equals."""
    assertions = hard_forget_must_not_leak_text()
    assert assertions[0].assertion_type.value == "equals"


def test_hard_forget_no_real_sensitive_text_in_template() -> None:
    """Template must only check leak count / flag, never carry real sensitive text."""
    assertions = hard_forget_must_not_leak_text()
    for a in assertions:
        # expected should be 0 (int), never a string of sensitive text
        if a.expected is not None:
            assert isinstance(a.expected, int)


def test_hard_forget_pass() -> None:
    _pass(
        "hf",
        hard_forget_must_not_leak_text(),
        {"observatory": {"hard_forgotten_text_leak_count": 0}},
    )


def test_hard_forget_fail() -> None:
    _fail(
        "hf_f",
        hard_forget_must_not_leak_text(),
        {"observatory": {"hard_forgotten_text_leak_count": 1}},
    )


# ---------------------------------------------------------------------------
# model_dump on all templates
# ---------------------------------------------------------------------------

_ALL_TEMPLATES = [
    ("seed_min_count", seed_min_count(1)),
    ("seed_forbids_control_command_memory", seed_forbids_control_command_memory()),
    ("court_allows_verdicts", court_allows_verdicts(["plant"])),
    ("court_forbids_verdicts", court_forbids_verdicts(["ban"])),
    ("negative_emotion_must_not_plant", negative_emotion_must_not_plant()),
    ("greenhouse_must_not_enter_positive_brief", greenhouse_must_not_enter_positive_brief()),
    ("command_must_short_circuit", command_must_short_circuit()),
    ("assistant_reply_must_not_be_user_memory", assistant_reply_must_not_be_user_memory()),
    ("brief_requires_source_ids", brief_requires_source_ids()),
    ("brief_must_not_expose_full_memory_text", brief_must_not_expose_full_memory_text()),
    ("observatory_public_must_redact_long_text", observatory_public_must_redact_long_text()),
    ("hard_forget_must_not_leak_text", hard_forget_must_not_leak_text()),
]


@pytest.mark.parametrize("name,template_output", _ALL_TEMPLATES)
def test_all_templates_model_dump_json(name: str, template_output: LabAssertion | list[LabAssertion]) -> None:
    assertions = _assertions(template_output)
    for a in assertions:
        d = a.model_dump(mode="json")
        assert isinstance(d, dict), f"{name}: model_dump failed"
        import json
        json.dumps(d)


# ---------------------------------------------------------------------------
# source code checks
# ---------------------------------------------------------------------------

def test_templates_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/rule_templates.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"rule_templates.py must not contain token: {token}"


def test_templates_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for _, output in _ALL_TEMPLATES:
        _assertions(output)
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


def test_templates_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_rule_templates.py").read_text(encoding="utf-8-sig"))
    forbidden = (
        "memory_garden.core",
        "memory_garden.runtime",
        "memory_garden.harvest",
        "memory_garden.observatory",
    )
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    for mod in imported:
        for prefix in forbidden:
            assert not (mod == prefix or mod.startswith(prefix + ".")), f"Forbidden import: {mod}"