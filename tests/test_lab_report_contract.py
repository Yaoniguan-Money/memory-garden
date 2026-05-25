"""Seventh layer Stage 7E: CI Report Contract unit tests (read-only, no re-execution)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from memory_garden.lab.models import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabCaseResult,
    LabFailure,
    LabRun,
    LabSeverity,
    LabStatus,
    LabSuite,
    LabTarget,
)
from memory_garden.lab.report import summarize_lab_run
from memory_garden.lab.report_contract import (
    LabCIFailure,
    LabCIReport,
    build_ci_report,
    build_ci_report_from_summary,
    lab_ci_report_passed,
)
from memory_garden.lab.runner import SnapshotLabRunner


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_passed_run() -> LabRun:
    runner = SnapshotLabRunner()
    c = LabCase(
        case_id="c_pass",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="x",
                expected=1,
            )
        ],
    )
    suite = LabSuite(suite_id="s_pass", cases=[c])
    return runner.run_suite(suite, {"c_pass": {"runtime": {"x": 1}}})


def _make_failed_run() -> LabRun:
    runner = SnapshotLabRunner()
    c1 = LabCase(
        case_id="c_a",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="x",
                expected=1,
            )
        ],
    )
    c2 = LabCase(
        case_id="c_b",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="y",
                expected=99,
            )
        ],
    )
    suite = LabSuite(suite_id="s_fail", cases=[c1, c2])
    return runner.run_suite(suite, {"c_a": {"runtime": {"x": 1}}, "c_b": {"runtime": {"y": 0}}})


# ---------------------------------------------------------------------------
# 1. build_ci_report from LabRun
# ---------------------------------------------------------------------------

def test_build_ci_report_from_passed_run() -> None:
    run = _make_passed_run()
    report = build_ci_report(run)
    assert isinstance(report, LabCIReport)
    assert report.status == "passed"
    assert report.total_cases == 1
    assert report.passed_cases == 1
    assert report.failed_case_ids == []
    assert report.critical_failures == []
    assert report.pass_rate == 1.0


def test_build_ci_report_from_failed_run() -> None:
    run = _make_failed_run()
    report = build_ci_report(run)
    assert report.status == "failed"
    assert report.total_cases == 2
    assert report.failed_cases == 1
    assert report.failed_case_ids == ["c_b"]
    assert len(report.critical_failures) == 0  # default severity is "error", not "critical"


# ---------------------------------------------------------------------------
# 2. build_ci_report_from_summary
# ---------------------------------------------------------------------------

def test_build_ci_report_from_summary() -> None:
    run = _make_failed_run()
    summary = summarize_lab_run(run)
    report = build_ci_report_from_summary(summary)
    assert isinstance(report, LabCIReport)
    assert report.status == "failed"
    assert report.total_cases == 2
    assert report.failed_case_ids == ["c_b"]


# ---------------------------------------------------------------------------
# 3. LabCIReport model_dump / model_validate round-trip
# ---------------------------------------------------------------------------

def test_lab_ci_report_model_dump_json() -> None:
    run = _make_failed_run()
    report = build_ci_report(run)
    blob = report.model_dump(mode="json")
    assert isinstance(blob, dict)
    assert blob["status"] == "failed"
    assert isinstance(blob["metrics"], list)
    json.dumps(blob)


def test_lab_ci_report_model_validate_round_trip() -> None:
    run = _make_passed_run()
    report = build_ci_report(run)
    blob = report.model_dump(mode="json")
    restored = LabCIReport.model_validate(blob)
    assert restored.status == report.status
    assert restored.total_cases == report.total_cases


def test_lab_ci_failure_model_dump() -> None:
    f = LabCIFailure(
        case_id="c",
        target="runtime",
        field_path="x",
        assertion_type="equals",
        severity="error",
        message="mismatch",
        expected_preview="1",
        actual_preview="2",
    )
    blob = f.model_dump(mode="json")
    json.dumps(blob)


# ---------------------------------------------------------------------------
# 4. lab_ci_report_passed
# ---------------------------------------------------------------------------

def test_lab_ci_report_passed_true() -> None:
    run = _make_passed_run()
    report = build_ci_report(run)
    assert lab_ci_report_passed(report) is True


def test_lab_ci_report_passed_false() -> None:
    run = _make_failed_run()
    report = build_ci_report(run)
    assert lab_ci_report_passed(report) is False


# ---------------------------------------------------------------------------
# 5. failed_case_ids stable
# ---------------------------------------------------------------------------

def test_failed_case_ids_stable() -> None:
    r1 = build_ci_report(_make_failed_run())
    r2 = build_ci_report(_make_failed_run())
    assert r1.failed_case_ids == r2.failed_case_ids


# ---------------------------------------------------------------------------
# 6. critical_failures only contains critical severity
# ---------------------------------------------------------------------------

def test_critical_failures_only_critical() -> None:
    runner = SnapshotLabRunner()
    c = LabCase(
        case_id="crit",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.is_false,
                target=LabTarget.runtime,
                field_path="ok",
                expected=None,
            )
        ],
    )
    suite = LabSuite(suite_id="s_crit", cases=[c])
    run = runner.run_suite(suite, {"crit": {"runtime": {"ok": True}}})
    # Default severity is error, so no critical failures
    report = build_ci_report(run)
    assert report.critical_failures == []


def test_critical_failure_with_critical_severity() -> None:
    """When a failure has severity==critical, it should appear in critical_failures."""
    cr = LabCaseResult(
        case_id="crit_case",
        status=LabStatus.failed,
        failures=[
            LabFailure(
                case_id="crit_case",
                target=LabTarget.runtime,
                field_path="field",
                expected=True,
                actual=False,
                message="critical failure",
                assertion_type=LabAssertionType.is_true,
                severity=LabSeverity.critical,
            )
        ],
    )
    run = LabRun(
        run_id="r_crit",
        status=LabStatus.failed,
        case_results=[cr],
        metadata={"suite_ids": ["s_crit"], "metric_results": []},
    )
    report = build_ci_report(run)
    assert len(report.critical_failures) == 1
    assert report.critical_failures[0].severity == "critical"


# ---------------------------------------------------------------------------
# 7. expected_preview / actual_preview are truncated
# ---------------------------------------------------------------------------

def test_preview_fields_are_truncated() -> None:
    long_val = "x" * 200
    cr = LabCaseResult(
        case_id="big",
        status=LabStatus.failed,
        failures=[
            LabFailure(
                case_id="big",
                target=LabTarget.runtime,
                field_path="f",
                expected=long_val,
                actual=long_val,
                message="big values",
                assertion_type=LabAssertionType.equals,
                severity=LabSeverity.error,
            )
        ],
    )
    run = LabRun(
        run_id="r_big",
        status=LabStatus.failed,
        case_results=[cr],
        metadata={"suite_ids": ["s_big"], "metric_results": []},
    )
    report = build_ci_report(run)
    # We can't directly access individual failures from the report easily,
    # but the report JSON should not contain the full 200-char string
    raw = report.model_dump_json()
    assert long_val not in raw


# ---------------------------------------------------------------------------
# 8. metrics from metadata, not recomputed
# ---------------------------------------------------------------------------

def test_metrics_from_metadata() -> None:
    run = _make_passed_run()
    report = build_ci_report(run)
    assert len(report.metrics) >= 1
    names = {m.name for m in report.metrics}
    assert "passed_cases" in names
    assert "total_cases" in names


def test_metrics_not_recomputed() -> None:
    """The CI report must read metrics from metadata, not recalculate them."""
    # Build a run with specific metadata metric_results
    cr = LabCaseResult(case_id="m", status=LabStatus.passed, failures=[], metrics=[])
    run = LabRun(
        run_id="rm",
        status=LabStatus.passed,
        case_results=[cr],
        metadata={
            "suite_ids": ["sm"],
            "metric_results": [
                {"name": "custom_metric", "value": 42.0, "unit": "ms"},
            ],
        },
    )
    report = build_ci_report(run)
    assert any(m.name == "custom_metric" for m in report.metrics)


# ---------------------------------------------------------------------------
# 9. metadata does not contain actual_data / lab_fixture_example_actual
# ---------------------------------------------------------------------------

def test_metadata_strips_fixture_actual() -> None:
    run = LabRun(
        run_id="r_clean",
        status=LabStatus.passed,
        case_results=[],
        metadata={
            "suite_ids": ["sx"],
            "metric_results": [],
            "lab_fixture_example_actual": {"big": "data"},
            "actual_data": {"sensitive": True},
            "debug_artifacts": ["log"],
        },
    )
    report = build_ci_report(run)
    assert "lab_fixture_example_actual" not in report.metadata
    assert "actual_data" not in report.metadata
    assert "debug_artifacts" not in report.metadata


# ---------------------------------------------------------------------------
# 10. source does not import SnapshotLabRunner
# ---------------------------------------------------------------------------

def test_report_contract_does_not_import_runner() -> None:
    raw = Path("memory_garden/lab/report_contract.py").read_text(encoding="utf-8-sig")
    assert "SnapshotLabRunner" not in raw
    assert "run_suite" not in raw
    assert "evaluate_assertion" not in raw
    assert "evaluate_case" not in raw


# ---------------------------------------------------------------------------
# 11. source bans external infra tokens
# ---------------------------------------------------------------------------

def test_report_contract_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/report_contract.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"report_contract.py must not contain token: {token}"


# ---------------------------------------------------------------------------
# 12. no .memory_garden / garden.db created
# ---------------------------------------------------------------------------

def test_report_contract_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run = _make_passed_run()
    build_ci_report(run)
    summary = summarize_lab_run(run)
    build_ci_report_from_summary(summary)
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


# ---------------------------------------------------------------------------
# 13. test module does not import forbidden modules
# ---------------------------------------------------------------------------

def test_report_contract_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_report_contract.py").read_text(encoding="utf-8-sig"))
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