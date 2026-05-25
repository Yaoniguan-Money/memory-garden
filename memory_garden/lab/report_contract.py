"""Seventh layer Stage 7E: CI-Friendly Report Contract (read from LabRun/Summary, no re-execution)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.lab.models import LabRun, LabStatus
from memory_garden.lab.report import LabRunSummary

_PREVIEW_TRUNCATE = 80


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate_preview(value: Any) -> str:
    """Return a short string preview of *value*, truncated to _PREVIEW_TRUNCATE chars."""
    if value is None:
        return ""
    s = str(value)
    if len(s) <= _PREVIEW_TRUNCATE:
        return s
    return s[:_PREVIEW_TRUNCATE] + "..."


def _strip_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Remove known heavy or debug keys from metadata."""
    skip = {
        "lab_fixture_example_actual",
        "actual_data",
        "debug_artifacts",
    }
    return {k: v for k, v in meta.items() if k not in skip}


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

class LabCIFailure(BaseModel):
    """Lightweight CI failure entry with truncated preview fields."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    case_id: str = Field(..., min_length=1)
    target: str = Field(default="")
    field_path: str = Field(default="")
    assertion_type: str | None = Field(default=None)
    severity: str = Field(default="error")
    message: str = Field(default="")
    expected_preview: str = Field(default="")
    actual_preview: str = Field(default="")


class LabCIMetric(BaseModel):
    """A single named metric from the run metadata."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str = Field(..., min_length=1)
    value: float
    unit: str | None = Field(default=None)


class LabCIReport(BaseModel):
    """CI-friendly report contract built from LabRun or LabRunSummary.

    All preview fields are truncated.  No actual_data or large objects.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    report_id: str = Field(default="")
    run_id: str = Field(default="")
    status: str = Field(default="pending")
    suite_id: str = Field(default="")
    suite_ids: list[str] = Field(default_factory=list)
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    skipped_cases: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    failed_case_ids: list[str] = Field(default_factory=list)
    critical_failures: list[LabCIFailure] = Field(default_factory=list)
    metrics: list[LabCIMetric] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

def _build_failures_from_run(run: LabRun) -> list[LabCIFailure]:
    failures: list[LabCIFailure] = []
    for cr in run.case_results:
        if cr.status in (LabStatus.failed, LabStatus.errored):
            for f in cr.failures:
                failures.append(LabCIFailure(
                    case_id=f.case_id,
                    target=f.target.value if f.target else "",
                    field_path=f.field_path,
                    assertion_type=f.assertion_type.value if f.assertion_type else None,
                    severity=f.severity.value if f.severity else "error",
                    message=f.message,
                    expected_preview=_truncate_preview(f.expected),
                    actual_preview=_truncate_preview(f.actual),
                ))
    return failures


def _build_metrics_from_metadata(meta: dict[str, Any]) -> list[LabCIMetric]:
    raw = meta.get("metric_results")
    if not isinstance(raw, list):
        return []
    metrics: list[LabCIMetric] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not isinstance(name, str) or value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        unit = item.get("unit")
        metrics.append(LabCIMetric(
            name=name,
            value=num,
            unit=unit if isinstance(unit, str) else None,
        ))
    return metrics


def _build_from_results(
    run_id: str,
    suite_id: str,
    status: LabStatus,
    case_results: list[Any],
    meta: dict[str, Any],
    suite_ids: list[str],
) -> LabCIReport:
    total = len(case_results)
    passed = sum(1 for r in case_results if r.status == LabStatus.passed)
    failed = sum(1 for r in case_results if r.status in (LabStatus.failed, LabStatus.errored))
    skipped = sum(1 for r in case_results if r.status == LabStatus.skipped)
    total_failures = sum(len(getattr(r, "failures", [])) for r in case_results)
    pass_rate = round(passed / total, 6) if total > 0 else 0.0

    failed_case_ids = [
        r.case_id for r in case_results if r.status in (LabStatus.failed, LabStatus.errored)
    ]

    all_failures = _build_failures_from_results(case_results)
    critical_failures = [f for f in all_failures if f.severity == "critical"]

    metrics = _build_metrics_from_metadata(meta)

    warnings: list[str] = []
    if not meta.get("metric_results"):
        warnings.append("metric_results missing from metadata")

    clean_meta = _strip_metadata(dict(meta))
    clean_meta.pop("metric_results", None)  # already extracted as metrics

    return LabCIReport(
        report_id=f"ci_{run_id}",
        run_id=run_id,
        status=status.value,
        suite_id=suite_id,
        suite_ids=suite_ids,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        skipped_cases=skipped,
        total_failures=total_failures,
        pass_rate=pass_rate,
        failed_case_ids=failed_case_ids,
        critical_failures=critical_failures,
        metrics=metrics,
        warnings=warnings,
        metadata=clean_meta,
    )


def _build_failures_from_results(case_results: list[Any]) -> list[LabCIFailure]:
    failures: list[LabCIFailure] = []
    for cr in case_results:
        if cr.status in (LabStatus.failed, LabStatus.errored):
            for f in getattr(cr, "failures", []):
                failures.append(LabCIFailure(
                    case_id=f.case_id,
                    target=f.target.value if f.target else "",
                    field_path=f.field_path,
                    assertion_type=f.assertion_type.value if f.assertion_type else None,
                    severity=f.severity.value if f.severity else "error",
                    message=f.message,
                    expected_preview=_truncate_preview(f.expected),
                    actual_preview=_truncate_preview(f.actual),
                ))
    return failures


def build_ci_report(run: LabRun) -> LabCIReport:
    """Build a CI report from a LabRun.  No re-execution of assertions."""
    suite_ids: list[str] = run.metadata.get("suite_ids", [])
    if not isinstance(suite_ids, list):
        suite_ids = []
    return _build_from_results(
        run_id=run.run_id,
        suite_id=run.suite_id,
        status=run.status,
        case_results=run.case_results,
        meta=dict(run.metadata),
        suite_ids=suite_ids,
    )


def build_ci_report_from_summary(summary: LabRunSummary) -> LabCIReport:
    """Build a CI report from a LabRunSummary.  No re-execution of assertions."""
    all_failures = _build_failures_from_summary(summary)
    critical_failures = [f for f in all_failures if f.severity == "critical"]

    metrics = _build_metrics_from_metadata(summary.metadata)

    warnings: list[str] = []
    if not summary.metadata.get("metric_results"):
        warnings.append("metric_results missing from metadata")

    clean_meta = _strip_metadata(dict(summary.metadata))
    clean_meta.pop("metric_results", None)

    return LabCIReport(
        report_id=f"ci_{summary.run_id}",
        run_id=summary.run_id,
        status=summary.status.value,
        suite_id=summary.suite_id,
        suite_ids=summary.suite_ids,
        total_cases=summary.total_cases,
        passed_cases=summary.passed_cases,
        failed_cases=summary.failed_cases,
        skipped_cases=summary.skipped_cases,
        total_failures=summary.total_failures,
        pass_rate=summary.pass_rate,
        failed_case_ids=summary.failed_case_ids,
        critical_failures=critical_failures,
        metrics=metrics,
        warnings=warnings,
        metadata=clean_meta,
    )


def _build_failures_from_summary(summary: LabRunSummary) -> list[LabCIFailure]:
    """Summary itself doesn't carry full LabFailure objects, so we build empty list.

    CI reports from summaries only get the failed_case_ids and top_failure_messages,
    not full failure detail.  Critical failures are determined by summary data.
    """
    failures: list[LabCIFailure] = []
    for idx, cid in enumerate(summary.failed_case_ids):
        # Summary 不含逐 case 的失败详情，仅在单失败时安全关联消息
        if len(summary.failed_case_ids) == 1 and summary.top_failure_messages:
            msg = summary.top_failure_messages[0]
        else:
            msg = ""
        failures.append(LabCIFailure(
            case_id=cid,
            target="",
            field_path="",
            assertion_type=None,
            severity="error",
            message=msg,
            expected_preview="",
            actual_preview="",
        ))
    return failures


def lab_ci_report_passed(report: LabCIReport) -> bool:
    """Return True only when the CI report status is passed."""
    return report.status == LabStatus.passed.value


__all__ = [
    "LabCIFailure",
    "LabCIMetric",
    "LabCIReport",
    "build_ci_report",
    "build_ci_report_from_summary",
    "lab_ci_report_passed",
]