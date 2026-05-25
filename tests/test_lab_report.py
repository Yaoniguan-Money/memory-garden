"""Sixth layer Stage 6D: Lab Report unit tests (pure memory, no Core/Runtime/Harvest/Observatory)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_garden.lab.fixtures import default_lab_suites, fixture_example_actual_from_case
from memory_garden.lab.models import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabCaseResult,
    LabFailure,
    LabRun,
    LabStatus,
    LabSuite,
    LabTarget,
)
from memory_garden.lab.report import (
    format_lab_run_report,
    format_lab_run_summary,
    lab_run_passed,
    summarize_lab_run,
)
from memory_garden.lab.runner import SnapshotLabRunner


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_passed_run() -> LabRun:
    runner = SnapshotLabRunner()
    c = LabCase(
        case_id="ok",
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
    return runner.run_suite(suite, {"ok": {"runtime": {"x": 1}}})


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
# 1. summarize passed LabRun
# ---------------------------------------------------------------------------

def test_summarize_passed_lab_run() -> None:
    run = _make_passed_run()
    summary = summarize_lab_run(run)
    assert summary.status == LabStatus.passed
    assert summary.total_cases == 1
    assert summary.passed_cases == 1
    assert summary.failed_cases == 0
    assert summary.skipped_cases == 0
    assert summary.total_failures == 0
    assert summary.pass_rate == 1.0
    assert summary.failed_case_ids == []
    assert summary.top_failure_messages == []


# ---------------------------------------------------------------------------
# 2. summarize failed LabRun
# ---------------------------------------------------------------------------

def test_summarize_failed_lab_run() -> None:
    run = _make_failed_run()
    summary = summarize_lab_run(run)
    assert summary.status == LabStatus.failed
    assert summary.total_cases == 2
    assert summary.passed_cases == 1
    assert summary.failed_cases == 1
    assert summary.total_failures >= 1
    assert summary.pass_rate == 0.5
    assert summary.failed_case_ids == ["c_b"]


# ---------------------------------------------------------------------------
# 3. failed_case_ids order stable
# ---------------------------------------------------------------------------

def test_failed_case_ids_order_stable() -> None:
    runner = SnapshotLabRunner()
    c_a = LabCase(
        case_id="a",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="v",
                expected=999,
            )
        ],
    )
    c_b = LabCase(
        case_id="b",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="v",
                expected=999,
            )
        ],
    )
    c_c = LabCase(
        case_id="c",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="v",
                expected=999,
            )
        ],
    )
    suite = LabSuite(suite_id="order", cases=[c_a, c_b, c_c])
    run = runner.run_suite(suite, {"a": {"runtime": {"v": 0}}, "b": {"runtime": {"v": 0}}, "c": {"runtime": {"v": 0}}})
    summary = summarize_lab_run(run)
    assert summary.failed_case_ids == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# 4. top_failure_messages limit and truncation
# ---------------------------------------------------------------------------

def test_top_failure_messages_limit_and_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    """top_failure_messages capped at 5, each truncated to <= 160 chars."""
    import memory_garden.lab.runner as runner_mod

    long_msg = "x" * 300
    original = runner_mod.evaluate_case

    def patched_eval(lc: LabCase, data: dict) -> LabCaseResult:  # type: ignore[no-untyped-def]
        result = original(lc, data)
        if result.status == LabStatus.failed and lc.case_id == "fc_0":
            result = result.model_copy(update={"failures": [
                LabFailure(
                    case_id=lc.case_id,
                    target=LabTarget.runtime,
                    field_path="",
                    expected=False,
                    actual=True,
                    message=long_msg,
                    assertion_type=LabAssertionType.is_false,
                )
            ]})
        return result

    monkeypatch.setattr(runner_mod, "evaluate_case", patched_eval)

    runner = SnapshotLabRunner()
    cases: list[LabCase] = []
    for i in range(10):
        c = LabCase(
            case_id=f"fc_{i}",
            assertions=[
                LabAssertion(
                    assertion_type=LabAssertionType.is_false,
                    target=LabTarget.runtime,
                    field_path="ok",
                    expected=None,
                )
            ],
        )
        cases.append(c)
    suite = LabSuite(suite_id="limit", cases=cases)
    data = {f"fc_{i}": {"runtime": {"ok": True}} for i in range(10)}
    run = runner.run_suite(suite, data)

    summary = summarize_lab_run(run)
    assert len(summary.top_failure_messages) <= 5
    for msg in summary.top_failure_messages:
        assert len(msg) <= 163  # 160 + "..." suffix


def test_top_failure_messages_capped_at_five() -> None:
    """Test that top_failure_messages respects the maximum of 5."""
    runner = SnapshotLabRunner()
    cases: list[LabCase] = []
    for i in range(8):
        c = LabCase(
            case_id=f"many_{i}",
            assertions=[
                LabAssertion(
                    assertion_type=LabAssertionType.is_false,
                    target=LabTarget.runtime,
                    field_path="flag",
                    expected=None,
                )
            ],
        )
        cases.append(c)
    suite = LabSuite(suite_id="many", cases=cases)
    data = {f"many_{i}": {"runtime": {"flag": True}} for i in range(8)}
    run = runner.run_suite(suite, data)
    summary = summarize_lab_run(run)
    assert len(summary.top_failure_messages) == 5
    assert summary.failed_cases == 8


# ---------------------------------------------------------------------------
# 5. format_lab_run_summary output contains status / pass_rate / failed case
# ---------------------------------------------------------------------------

def test_format_lab_run_summary_output() -> None:
    run = _make_failed_run()
    summary = summarize_lab_run(run)
    text = format_lab_run_summary(summary)
    assert "Status:" in text
    assert "failed" in text.lower()
    assert "Pass Rate:" in text
    assert "0.5000" in text
    assert "c_b" in text


def test_format_passed_summary_output() -> None:
    run = _make_passed_run()
    summary = summarize_lab_run(run)
    text = format_lab_run_summary(summary)
    assert "passed" in text.lower()
    assert "Pass Rate: 1.0000" in text
    assert "Failed Cases" not in text


def test_format_summary_deterministic() -> None:
    run = _make_failed_run()
    s1 = summarize_lab_run(run)
    s2 = summarize_lab_run(run)
    assert format_lab_run_summary(s1) == format_lab_run_summary(s2)


# ---------------------------------------------------------------------------
# 6. format_lab_run_report directly from LabRun
# ---------------------------------------------------------------------------

def test_format_lab_run_report_from_lab_run() -> None:
    run = _make_failed_run()
    report = format_lab_run_report(run)
    assert isinstance(report, str)
    assert "Lab Run:" in report
    assert "Status:" in report
    assert "c_b" in report


# ---------------------------------------------------------------------------
# 7. lab_run_passed behavior for passed / failed / skipped
# ---------------------------------------------------------------------------

def test_lab_run_passed_true() -> None:
    run = _make_passed_run()
    assert lab_run_passed(run) is True


def test_lab_run_passed_false_for_failed() -> None:
    run = _make_failed_run()
    assert lab_run_passed(run) is False


def test_lab_run_passed_false_for_skipped() -> None:
    run = LabRun(suite_id="sk", status=LabStatus.skipped, case_results=[])
    assert lab_run_passed(run) is False


def test_lab_run_passed_false_for_errored() -> None:
    cr = LabCaseResult(
        case_id="e",
        status=LabStatus.errored,
        failures=[
            LabFailure(
                case_id="e",
                target=LabTarget.runtime,
                field_path="",
                expected=None,
                actual=None,
                message="simulated error",
                assertion_type=None,
            )
        ],
    )
    run = LabRun(suite_id="err", status=LabStatus.errored, case_results=[cr])
    assert lab_run_passed(run) is False


# ---------------------------------------------------------------------------
# 8. summary model_dump(mode="json")
# ---------------------------------------------------------------------------

def test_summary_model_dump_json() -> None:
    run = _make_failed_run()
    summary = summarize_lab_run(run)
    blob = summary.model_dump(mode="json")
    assert isinstance(blob, dict)
    assert blob["status"] == "failed"
    assert blob["total_cases"] == 2
    assert blob["pass_rate"] == 0.5
    assert isinstance(blob["failed_case_ids"], list)
    assert isinstance(blob["top_failure_messages"], list)
    assert "generated_at" in blob
    import json
    json.dumps(blob)


# ---------------------------------------------------------------------------
# 9. full pass with SnapshotLabRunner + default_lab_suites + fixture actuals
# ---------------------------------------------------------------------------

def test_full_pass_with_snapshot_runner_and_default_suites() -> None:
    runner = SnapshotLabRunner()
    suites = default_lab_suites()
    data: dict[str, dict] = {}
    for s in suites:
        for c in s.cases:
            data[c.case_id] = fixture_example_actual_from_case(c)
    lr = runner.run_suites(suites, data)
    assert lr.status == LabStatus.passed
    summary = summarize_lab_run(lr)
    assert summary.status == LabStatus.passed
    assert summary.failed_cases == 0
    assert summary.pass_rate == 1.0
    assert lab_run_passed(lr) is True


# ---------------------------------------------------------------------------
# 10. failed report does NOT contain full actual_data or extra-long fields
# ---------------------------------------------------------------------------

def test_failed_report_excludes_full_actual_data() -> None:
    run = _make_failed_run()
    report = format_lab_run_report(run)
    assert len(report) < 2000, "Report should be short, not contain large dumps"
    summary = summarize_lab_run(run)
    for msg in summary.top_failure_messages:
        assert len(msg) <= 163
    assert "model_dump" not in report.lower()


# ---------------------------------------------------------------------------
# 11. report.py source bans external infra tokens
# ---------------------------------------------------------------------------

def test_report_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/report.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"report.py must not contain token: {token}"


# ---------------------------------------------------------------------------
# 12. report does not create .memory_garden / garden.db
# ---------------------------------------------------------------------------

def test_report_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run = _make_passed_run()
    summarize_lab_run(run)
    format_lab_run_report(run)
    lab_run_passed(run)
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


# ---------------------------------------------------------------------------
# 13. report test module does not import Core / Runtime / Harvest / Observatory
# ---------------------------------------------------------------------------

def test_report_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_report.py").read_text(encoding="utf-8-sig"))
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
# additional: summary fields
# ---------------------------------------------------------------------------

def test_summary_suite_ids_from_metadata() -> None:
    runner = SnapshotLabRunner()
    s1 = LabSuite(suite_id="sida", cases=[LabCase(case_id="c1", assertions=[])])
    s2 = LabSuite(suite_id="sidb", cases=[LabCase(case_id="c2", assertions=[])])
    run = runner.run_suites([s1, s2], {"c1": {}, "c2": {}})
    summary = summarize_lab_run(run)
    assert summary.suite_ids == ["sida", "sidb"]


def test_summary_metadata_preserved() -> None:
    run = _make_passed_run()
    summary = summarize_lab_run(run)
    assert isinstance(summary.metadata, dict)
    assert "metric_results" in summary.metadata


def test_summary_run_id_matches() -> None:
    run = _make_passed_run()
    summary = summarize_lab_run(run)
    assert summary.run_id == run.run_id


def test_summary_empty_run() -> None:
    run = LabRun(suite_id="empty", status=LabStatus.skipped, case_results=[])
    summary = summarize_lab_run(run)
    assert summary.total_cases == 0
    assert summary.passed_cases == 0
    assert summary.failed_cases == 0
    assert summary.skipped_cases == 0
    assert summary.total_failures == 0
    assert summary.pass_rate == 0.0