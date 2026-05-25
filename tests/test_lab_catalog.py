"""Seventh layer Stage 7A: Lab Catalog unit tests (read-only, no Runner, no Core/Runtime/Harvest/Observatory)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from memory_garden.lab.catalog import (
    LabCaseCatalogEntry,
    LabSuiteCatalogEntry,
    LabCatalog,
    build_lab_catalog,
    build_default_lab_catalog,
)
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.models import LabCase, LabSuite


# ---------------------------------------------------------------------------
# 1. catalog model_dump(mode="json") and model_validate round-trip
# ---------------------------------------------------------------------------

def test_catalog_model_dump_json() -> None:
    cat = build_default_lab_catalog()
    blob = cat.model_dump(mode="json")
    assert isinstance(blob, dict)
    assert blob["suite_count"] == 5
    assert blob["total_cases"] == 10
    assert isinstance(blob["suites"], list)
    assert isinstance(blob["entries"], list)
    assert isinstance(blob["case_ids_global"], list)
    json.dumps(blob)


def test_catalog_model_validate_round_trip() -> None:
    cat = build_default_lab_catalog()
    blob = cat.model_dump(mode="json")
    restored = LabCatalog.model_validate(blob)
    assert restored.suite_count == cat.suite_count
    assert restored.total_cases == cat.total_cases
    assert restored.case_ids_global == cat.case_ids_global


def test_case_entry_model_dump_json() -> None:
    entry = LabCaseCatalogEntry(
        case_id="test.1",
        name="Test Case",
        primary_target="runtime",
        assertion_count=3,
        assertion_types=["equals", "is_true"],
        metadata_keys=["primary_target", "scenario_hint"],
        severity=None,
    )
    blob = entry.model_dump(mode="json")
    assert blob["case_id"] == "test.1"
    assert blob["severity"] is None
    json.dumps(blob)


def test_suite_entry_model_dump_json() -> None:
    entry = LabSuiteCatalogEntry(
        suite_id="s.test",
        name="Test Suite",
        fixture_kind="test",
        case_count=2,
        case_ids=["a", "b"],
    )
    blob = entry.model_dump(mode="json")
    assert blob["suite_id"] == "s.test"
    json.dumps(blob)


# ---------------------------------------------------------------------------
# 2. default catalog suite order stable
# ---------------------------------------------------------------------------

def test_default_catalog_suite_order_stable() -> None:
    cat1 = build_default_lab_catalog()
    cat2 = build_default_lab_catalog()
    assert [s.suite_id for s in cat1.suites] == [s.suite_id for s in cat2.suites]
    assert cat1.case_ids_global == cat2.case_ids_global


def test_default_catalog_suite_count_and_fixture_kinds() -> None:
    cat = build_default_lab_catalog()
    assert cat.suite_count == 5
    kinds = {s.fixture_kind for s in cat.suites}
    assert kinds == {
        "seed_extraction",
        "runtime_command",
        "court_verdict",
        "harvest_brief",
        "observatory_redaction",
    }


# ---------------------------------------------------------------------------
# 3. case ids globally unique
# ---------------------------------------------------------------------------

def test_case_ids_globally_unique() -> None:
    cat = build_default_lab_catalog()
    assert len(cat.case_ids_global) == len(set(cat.case_ids_global))
    assert len(cat.entries) == len(cat.case_ids_global)


def test_case_ids_in_suites_match_entries() -> None:
    cat = build_default_lab_catalog()
    suite_cids: set[str] = set()
    for s in cat.suites:
        suite_cids.update(s.case_ids)
    entry_cids = {e.case_id for e in cat.entries}
    assert suite_cids == entry_cids


# ---------------------------------------------------------------------------
# 4. assertion_count correct
# ---------------------------------------------------------------------------

def test_assertion_count_matches() -> None:
    suites = default_lab_suites()
    cat = build_lab_catalog(suites)
    for s in suites:
        for c in s.cases:
            entry = next(e for e in cat.entries if e.case_id == c.case_id)
            assert entry.assertion_count == len(c.assertions)


# ---------------------------------------------------------------------------
# 5. metadata_keys contains key names but NOT large object content
# ---------------------------------------------------------------------------

def test_metadata_keys_excludes_fixture_actual() -> None:
    cat = build_default_lab_catalog()
    for entry in cat.entries:
        assert "lab_fixture_example_actual" not in entry.metadata_keys


def test_metadata_keys_are_key_names_not_values() -> None:
    cat = build_default_lab_catalog()
    for entry in cat.entries:
        for key in entry.metadata_keys:
            assert isinstance(key, str)
            assert len(key) < 128
    # Verify we have the expected keys
    all_keys: set[str] = set()
    for entry in cat.entries:
        all_keys.update(entry.metadata_keys)
    assert "primary_target" in all_keys
    assert "scenario_hint" in all_keys


def test_catalog_does_not_contain_actual_data_blobs() -> None:
    cat = build_default_lab_catalog()
    raw = cat.model_dump_json().lower()
    # The lab_fixture_example_actual blob should not appear in catalog JSON
    assert "example_actual" not in raw


# ---------------------------------------------------------------------------
# 6. source bans external infra tokens
# ---------------------------------------------------------------------------

def test_catalog_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/catalog.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"catalog.py must not contain token: {token}"


# ---------------------------------------------------------------------------
# 7. build_default_lab_catalog does not create .memory_garden / garden.db
# ---------------------------------------------------------------------------

def test_catalog_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    build_default_lab_catalog()
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


# ---------------------------------------------------------------------------
# 8. catalog does not call SnapshotLabRunner
# ---------------------------------------------------------------------------

def test_catalog_does_not_import_or_call_runner() -> None:
    raw = Path("memory_garden/lab/catalog.py").read_text(encoding="utf-8-sig")
    assert "SnapshotLabRunner" not in raw
    assert "run_suite" not in raw
    assert "run_suites" not in raw
    assert "evaluate_case" not in raw


# ---------------------------------------------------------------------------
# 9. test module does not import forbidden modules
# ---------------------------------------------------------------------------

def test_catalog_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_catalog.py").read_text(encoding="utf-8-sig"))
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
# 10. additional: empty suites and case-level details
# ---------------------------------------------------------------------------

def test_empty_suite_list_yields_empty_catalog() -> None:
    cat = build_lab_catalog([])
    assert cat.suite_count == 0
    assert cat.total_cases == 0
    assert cat.suites == []
    assert cat.entries == []
    assert cat.case_ids_global == []


def test_single_suite_catalog() -> None:
    c1 = LabCase(
        case_id="sc1",
        name="Case 1",
        assertions=[],
        metadata={"primary_target": "seed", "scenario_hint": "test"},
    )
    suite = LabSuite(
        suite_id="ss",
        name="Single Suite",
        cases=[c1],
        metadata={"fixture_kind": "unit_test"},
    )
    cat = build_lab_catalog([suite])
    assert cat.suite_count == 1
    assert cat.total_cases == 1
    assert cat.suites[0].fixture_kind == "unit_test"
    assert cat.entries[0].case_id == "sc1"
    assert cat.entries[0].primary_target == "seed"
    assert cat.entries[0].assertion_count == 0


def test_severity_from_metadata() -> None:
    c1 = LabCase(
        case_id="sev1",
        assertions=[],
        metadata={"primary_target": "runtime", "severity": "critical"},
    )
    suite = LabSuite(suite_id="ss_sev", cases=[c1], metadata={"fixture_kind": "test"})
    cat = build_lab_catalog([suite])
    assert cat.entries[0].severity == "critical"


def test_severity_none_when_absent() -> None:
    c1 = LabCase(
        case_id="no_sev",
        assertions=[],
        metadata={"primary_target": "runtime"},
    )
    suite = LabSuite(suite_id="ss_no_sev", cases=[c1], metadata={"fixture_kind": "test"})
    cat = build_lab_catalog([suite])
    assert cat.entries[0].severity is None