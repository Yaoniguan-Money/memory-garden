"""Seventh layer Stage 7F: Lab coverage / gap report tests."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from memory_garden.lab.coverage import (
    LabCoverageReport,
    LabCoverageStatus,
    build_default_lab_coverage_report,
    build_lab_coverage_report,
)
from memory_garden.lab.fixtures import default_lab_suites


def _by_mechanism(report: LabCoverageReport) -> dict[str, str]:
    return {m.mechanism: m.status.value for m in report.mechanisms}


def test_default_coverage_json_round_trip() -> None:
    report = build_default_lab_coverage_report()
    blob = report.model_dump(mode="json")
    json.dumps(blob)
    restored = LabCoverageReport.model_validate(blob)
    assert restored.report_id == report.report_id
    assert restored.catalog_total_cases == report.catalog_total_cases


def test_default_coverage_counts_match_default_suites() -> None:
    suites = default_lab_suites()
    report = build_default_lab_coverage_report()
    assert report.suite_count == len(suites)
    assert report.catalog_total_cases == sum(len(s.cases) for s in suites)


def test_covered_mechanisms_are_marked_covered() -> None:
    statuses = _by_mechanism(build_default_lab_coverage_report())
    assert statuses["seed_capture_contract"] == LabCoverageStatus.covered.value
    assert statuses["court_verdict_contract"] == LabCoverageStatus.covered.value
    assert statuses["growth_safety_contract"] == LabCoverageStatus.covered.value
    assert statuses["runtime_command_contract"] == LabCoverageStatus.covered.value
    assert statuses["harvest_brief_contract"] == LabCoverageStatus.covered.value
    assert statuses["observatory_public_contract"] == LabCoverageStatus.covered.value


def test_gaps_are_marked_missing_or_snapshot_only() -> None:
    statuses = _by_mechanism(build_default_lab_coverage_report())
    assert statuses["dream_cycle_contract"] == LabCoverageStatus.missing.value
    assert statuses["end_to_end_adapter_contract"] == LabCoverageStatus.missing.value
    assert statuses["hard_forget_no_leak_contract"] == LabCoverageStatus.snapshot_only.value


def test_hard_forget_placeholder_is_traceable_to_safety_pack() -> None:
    report = build_default_lab_coverage_report()
    entry = next(m for m in report.mechanisms if m.mechanism == "hard_forget_no_leak_contract")
    assert entry.case_ids == ["lab.7d.hard_forget_no_leak.placeholder"]
    assert entry.pack_names == ["safety"]
    assert entry.suite_ids == []


def test_report_has_stable_order() -> None:
    first = build_default_lab_coverage_report()
    second = build_default_lab_coverage_report()
    assert [m.mechanism for m in first.mechanisms] == [m.mechanism for m in second.mechanisms]
    assert first.covered_targets == second.covered_targets
    assert first.missing_targets == second.missing_targets


def test_report_does_not_include_fixture_snapshot_body() -> None:
    raw = build_default_lab_coverage_report().model_dump_json()
    assert "lab_fixture_example_actual" not in raw
    assert "actual_data" not in raw
    assert "pending_preference_signals" not in raw


def test_build_from_explicit_suites() -> None:
    suites = default_lab_suites()[:1]
    report = build_lab_coverage_report(suites)
    statuses = _by_mechanism(report)
    assert report.suite_count == 1
    assert statuses["seed_capture_contract"] == LabCoverageStatus.covered.value
    assert statuses["court_verdict_contract"] == LabCoverageStatus.missing.value


def test_missing_targets_include_dream_and_integration() -> None:
    report = build_default_lab_coverage_report()
    assert "dream" in report.missing_targets
    assert "integration" in report.missing_targets


def test_covered_targets_include_current_fixture_domains() -> None:
    report = build_default_lab_coverage_report()
    for target in ("seed", "court", "growth", "runtime", "harvest", "observatory"):
        assert target in report.covered_targets


def test_report_warnings_are_short_and_json_safe() -> None:
    report = build_default_lab_coverage_report()
    assert report.warnings
    assert all(len(w) < 160 for w in report.warnings)
    json.dumps(report.model_dump(mode="json"))


def test_coverage_module_does_not_import_runner() -> None:
    raw = Path("memory_garden/lab/coverage.py").read_text(encoding="utf-8-sig")
    assert "SnapshotLabRunner" not in raw
    assert "run_suite" not in raw
    assert "run_suites" not in raw
    assert "evaluate_case" not in raw


def test_coverage_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/coverage.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"coverage.py must not contain token: {token}"


def test_coverage_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    build_default_lab_coverage_report()
    build_lab_coverage_report(default_lab_suites())
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


def test_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_coverage.py").read_text(encoding="utf-8-sig"))
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


def test_public_init_exports_coverage_symbols() -> None:
    import memory_garden.lab as lab

    assert lab.LabCoverageReport is LabCoverageReport
    assert lab.LabCoverageStatus is LabCoverageStatus
    assert callable(lab.build_default_lab_coverage_report)
    assert callable(lab.build_lab_coverage_report)
