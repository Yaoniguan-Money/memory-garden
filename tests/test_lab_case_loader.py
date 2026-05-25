"""Seventh layer Stage 7B: Case Loader unit tests (dict/JSON loading, no execution, no Runner)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_garden.lab.case_loader import (
    CaseLoaderError,
    InvalidAssertionsError,
    InvalidAssertionTypeError,
    InvalidCasesError,
    InvalidJSONError,
    InvalidTargetError,
    MissingFieldError,
    load_lab_case_from_dict,
    load_lab_case_from_json,
    load_lab_suite_from_dict,
    load_lab_suite_from_json,
)
from memory_garden.lab.models import LabAssertion, LabCase, LabSuite


# ---------------------------------------------------------------------------
# 1. dict -> LabCase
# ---------------------------------------------------------------------------

def test_load_case_from_dict_minimal() -> None:
    data = {
        "case_id": "c.minimal",
        "assertions": [],
    }
    case = load_lab_case_from_dict(data)
    assert isinstance(case, LabCase)
    assert case.case_id == "c.minimal"


def test_load_case_from_dict_full() -> None:
    data = {
        "case_id": "c.full",
        "name": "Full Case",
        "description": "A full case description",
        "assertions": [
            {
                "assertion_type": "equals",
                "target": "runtime",
                "field_path": "x",
                "expected": 1,
            },
            {
                "assertion_type": "is_true",
                "target": "seed",
                "field_path": "flag",
                "expected": None,
            },
        ],
        "metadata": {"primary_target": "runtime", "severity": "error"},
    }
    case = load_lab_case_from_dict(data)
    assert case.case_id == "c.full"
    assert case.name == "Full Case"
    assert case.description == "A full case description"
    assert len(case.assertions) == 2
    assert case.assertions[0].assertion_type.value == "equals"
    assert case.assertions[0].target.value == "runtime"
    assert case.assertions[0].field_path == "x"
    assert case.assertions[0].expected == 1
    assert case.assertions[1].assertion_type.value == "is_true"
    assert case.metadata == {"primary_target": "runtime", "severity": "error"}


# ---------------------------------------------------------------------------
# 2. JSON string -> LabCase
# ---------------------------------------------------------------------------

def test_load_case_from_json() -> None:
    text = '{"case_id": "c.json", "name": "JSON Case", "assertions": []}'
    case = load_lab_case_from_json(text)
    assert isinstance(case, LabCase)
    assert case.case_id == "c.json"
    assert case.name == "JSON Case"


# ---------------------------------------------------------------------------
# 3. dict -> LabSuite
# ---------------------------------------------------------------------------

def test_load_suite_from_dict() -> None:
    data = {
        "suite_id": "s.basic",
        "name": "Basic Suite",
        "cases": [
            {
                "case_id": "c1",
                "assertions": [
                    {"assertion_type": "equals", "target": "runtime", "field_path": "x", "expected": 1}
                ],
            },
            {
                "case_id": "c2",
                "assertions": [
                    {"assertion_type": "is_false", "target": "seed", "field_path": "y", "expected": None}
                ],
            },
        ],
        "metadata": {"fixture_kind": "test", "version": "7b"},
    }
    suite = load_lab_suite_from_dict(data)
    assert isinstance(suite, LabSuite)
    assert suite.suite_id == "s.basic"
    assert suite.name == "Basic Suite"
    assert len(suite.cases) == 2
    assert suite.cases[0].case_id == "c1"
    assert suite.cases[1].case_id == "c2"
    assert suite.metadata == {"fixture_kind": "test", "version": "7b"}


# ---------------------------------------------------------------------------
# 4. JSON string -> LabSuite
# ---------------------------------------------------------------------------

def test_load_suite_from_json() -> None:
    text = '{"suite_id": "s.json", "cases": [{"case_id": "cj", "assertions": []}]}'
    suite = load_lab_suite_from_json(text)
    assert isinstance(suite, LabSuite)
    assert suite.suite_id == "s.json"
    assert len(suite.cases) == 1


# ---------------------------------------------------------------------------
# 5. id / title alias mapping
# ---------------------------------------------------------------------------

def test_id_alias_for_case_id() -> None:
    data = {"id": "alias_id", "assertions": []}
    case = load_lab_case_from_dict(data)
    assert case.case_id == "alias_id"


def test_id_alias_for_suite_id() -> None:
    data = {"id": "s_alias", "cases": []}
    suite = load_lab_suite_from_dict(data)
    assert suite.suite_id == "s_alias"


def test_title_alias_for_name() -> None:
    data = {"case_id": "ct", "title": "Title Name", "assertions": []}
    case = load_lab_case_from_dict(data)
    assert case.name == "Title Name"


def test_name_preferred_over_title() -> None:
    data = {"case_id": "ct", "name": "Preferred", "title": "Fallback", "assertions": []}
    case = load_lab_case_from_dict(data)
    assert case.name == "Preferred"


# ---------------------------------------------------------------------------
# 6. invalid JSON raises clear error
# ---------------------------------------------------------------------------

def test_invalid_json_raises_error() -> None:
    with pytest.raises(InvalidJSONError, match="Invalid JSON"):
        load_lab_case_from_json("not json at all {{{")


def test_json_not_an_object_raises_error() -> None:
    with pytest.raises(InvalidJSONError, match="Expected a JSON object"):
        load_lab_case_from_json("[1, 2, 3]")


# ---------------------------------------------------------------------------
# 7. unknown assertion_type raises clear error
# ---------------------------------------------------------------------------

def test_unknown_assertion_type_raises_error() -> None:
    data = {
        "case_id": "c_bad",
        "assertions": [
            {"assertion_type": "fuzzy_match", "target": "runtime", "field_path": "x", "expected": "hi"}
        ],
    }
    with pytest.raises(InvalidAssertionTypeError, match="Unknown assertion_type"):
        load_lab_case_from_dict(data)


# ---------------------------------------------------------------------------
# 8. unknown target raises clear error
# ---------------------------------------------------------------------------

def test_unknown_target_raises_error() -> None:
    data = {
        "case_id": "c_bad_target",
        "assertions": [
            {"assertion_type": "equals", "target": "cloud", "field_path": "x", "expected": 1}
        ],
    }
    with pytest.raises(InvalidTargetError, match="Unknown target"):
        load_lab_case_from_dict(data)


# ---------------------------------------------------------------------------
# 9. assertions not a list raises clear error
# ---------------------------------------------------------------------------

def test_assertions_not_list_raises_error() -> None:
    data = {"case_id": "c_bad", "assertions": "not_a_list"}
    with pytest.raises(InvalidAssertionsError, match="assertions must be a list"):
        load_lab_case_from_dict(data)


# ---------------------------------------------------------------------------
# 10. cases not a list raises clear error
# ---------------------------------------------------------------------------

def test_cases_not_list_raises_error() -> None:
    data = {"suite_id": "s_bad", "cases": "not_a_list"}
    with pytest.raises(InvalidCasesError, match="cases must be a list"):
        load_lab_suite_from_dict(data)


# ---------------------------------------------------------------------------
# 11. loader does not import SnapshotLabRunner
# ---------------------------------------------------------------------------

def test_loader_does_not_import_runner() -> None:
    raw = Path("memory_garden/lab/case_loader.py").read_text(encoding="utf-8-sig")
    assert "SnapshotLabRunner" not in raw
    assert "run_suite" not in raw
    assert "run_suites" not in raw


# ---------------------------------------------------------------------------
# 12. loader does not create .memory_garden / garden.db
# ---------------------------------------------------------------------------

def test_loader_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    load_lab_case_from_dict({"case_id": "c_g", "assertions": []})
    load_lab_suite_from_dict({"suite_id": "s_g", "cases": []})
    load_lab_case_from_json('{"case_id": "c_j", "assertions": []}')
    load_lab_suite_from_json('{"suite_id": "s_j", "cases": []}')
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


# ---------------------------------------------------------------------------
# 13. source code has no forbidden tokens
# ---------------------------------------------------------------------------

def test_loader_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/case_loader.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"case_loader.py must not contain token: {token}"


# ---------------------------------------------------------------------------
# 14. test module does not import forbidden modules
# ---------------------------------------------------------------------------

def test_loader_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_case_loader.py").read_text(encoding="utf-8-sig"))
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


# ---------------------------------------------------------------------------
# additional: missing required fields, edge cases
# ---------------------------------------------------------------------------

def test_missing_case_id_raises_error() -> None:
    data = {"assertions": []}
    with pytest.raises(MissingFieldError, match="Missing required field"):
        load_lab_case_from_dict(data)


def test_missing_suite_id_raises_error() -> None:
    data = {"cases": []}
    with pytest.raises(MissingFieldError, match="Missing required field"):
        load_lab_suite_from_dict(data)


def test_missing_assertion_type_in_assertion_raises_error() -> None:
    data = {
        "case_id": "c_ma",
        "assertions": [
            {"target": "runtime", "field_path": "x", "expected": 1}
        ],
    }
    with pytest.raises(MissingFieldError, match="Missing required field"):
        load_lab_case_from_dict(data)


def test_missing_target_in_assertion_raises_error() -> None:
    data = {
        "case_id": "c_mt",
        "assertions": [
            {"assertion_type": "equals", "field_path": "x", "expected": 1}
        ],
    }
    with pytest.raises(MissingFieldError, match="Missing required field"):
        load_lab_case_from_dict(data)


def test_assertion_without_field_path_defaults_empty() -> None:
    data = {
        "case_id": "c_nf",
        "assertions": [
            {"assertion_type": "is_true", "target": "runtime"}
        ],
    }
    case = load_lab_case_from_dict(data)
    assert case.assertions[0].field_path == ""


def test_case_without_metadata_defaults_empty() -> None:
    data = {"case_id": "c_nm", "assertions": []}
    case = load_lab_case_from_dict(data)
    assert case.metadata == {}


def test_suite_without_metadata_defaults_empty() -> None:
    data = {"suite_id": "s_nm", "cases": []}
    suite = load_lab_suite_from_dict(data)
    assert suite.metadata == {}


def test_load_case_not_dict_raises_error() -> None:
    with pytest.raises(CaseLoaderError, match="Expected a dict"):
        load_lab_case_from_dict(42)  # type: ignore[arg-type]


def test_load_suite_not_dict_raises_error() -> None:
    with pytest.raises(CaseLoaderError, match="Expected a dict"):
        load_lab_suite_from_dict(42)  # type: ignore[arg-type]


def test_assertion_not_a_dict_raises_error() -> None:
    data = {
        "case_id": "c_bad_assertion",
        "assertions": ["not_a_dict"],
    }
    with pytest.raises(CaseLoaderError, match="must be a dict"):
        load_lab_case_from_dict(data)


def test_loaded_case_has_correct_type() -> None:
    data = {
        "case_id": "c.typed",
        "assertions": [
            {"assertion_type": "count_equals", "target": "harvest", "field_path": "items", "expected": 5}
        ],
    }
    case = load_lab_case_from_dict(data)
    assert isinstance(case, LabCase)
    assert isinstance(case.assertions[0], LabAssertion)


def test_loaded_case_does_not_auto_run() -> None:
    """Loaded cases should not be executed - they are pure data objects."""
    data = {
        "case_id": "c.no_run",
        "assertions": [
            {"assertion_type": "equals", "target": "dream", "field_path": "done", "expected": True}
        ],
    }
    case = load_lab_case_from_dict(data)
    assert case.case_id == "c.no_run"
    assert len(case.assertions) == 1
    # No evaluation took place - no LabCaseResult, no failures field
    assert not hasattr(case, "failures")