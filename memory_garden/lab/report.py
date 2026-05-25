"""Sixth layer Stage 6D: Lab Report / Regression Summary (pure memory, no Core/Runtime/Harvest/Observatory calls)"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.lab.models import LabRun, LabStatus

_TOP_FAILURE_MAX = 5
_MESSAGE_TRUNCATE_LENGTH = 160


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LabRunSummary(BaseModel):
    """Structured summary of a LabRun (pure read from LabRun, no re-execution of assertions)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    run_id: str = Field(..., min_length=1)
    suite_id: str = Field(default="")
    suite_ids: list[str] = Field(default_factory=list)
    status: LabStatus
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    skipped_cases: int = Field(ge=0)
    total_failures: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    failed_case_ids: list[str] = Field(default_factory=list)
    top_failure_messages: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


def summarize_lab_run(run: LabRun) -> LabRunSummary:
    """Generate a summary from LabRun structured results (no re-execution of assertions)."""
    case_results = run.case_results
    total = len(case_results)
    passed = sum(1 for r in case_results if r.status == LabStatus.passed)
    failed = sum(1 for r in case_results if r.status in (LabStatus.failed, LabStatus.errored))
    skipped = sum(1 for r in case_results if r.status == LabStatus.skipped)
    total_failures = sum(len(r.failures) for r in case_results)
    pass_rate = round(passed / total, 6) if total > 0 else 0.0

    failed_case_ids: list[str] = [
        r.case_id for r in case_results if r.status in (LabStatus.failed, LabStatus.errored)
    ]

    all_failure_messages: list[str] = []
    for r in case_results:
        if r.status in (LabStatus.failed, LabStatus.errored):
            for f in r.failures:
                all_failure_messages.append(f.message)
    top_messages: list[str] = []
    for msg in all_failure_messages:
        if len(top_messages) >= _TOP_FAILURE_MAX:
            break
        truncated = msg if len(msg) <= _MESSAGE_TRUNCATE_LENGTH else msg[:_MESSAGE_TRUNCATE_LENGTH] + "..."
        top_messages.append(truncated)

    suite_ids: list[str] = run.metadata.get("suite_ids", [])
    if not isinstance(suite_ids, list):
        suite_ids = []

    return LabRunSummary(
        run_id=run.run_id,
        suite_id=run.suite_id,
        suite_ids=suite_ids,
        status=run.status,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        skipped_cases=skipped,
        total_failures=total_failures,
        pass_rate=pass_rate,
        failed_case_ids=failed_case_ids,
        top_failure_messages=top_messages,
        metadata=dict(run.metadata),
    )


def format_lab_run_summary(summary: LabRunSummary) -> str:
    """Format LabRunSummary as a short text report (suitable for terminal or PR comment)."""
    lines: list[str] = []
    lines.append(f"Lab Run: {summary.run_id}")
    lines.append(f"Status:  {summary.status.value}")
    lines.append(f"Total:   {summary.total_cases}  Passed: {summary.passed_cases}  "
                  f"Failed: {summary.failed_cases}  Skipped: {summary.skipped_cases}")
    lines.append(f"Pass Rate: {summary.pass_rate:.4f}  Total Failures: {summary.total_failures}")

    if summary.failed_case_ids:
        lines.append(f"Failed Cases ({len(summary.failed_case_ids)}):")
        for cid in summary.failed_case_ids:
            lines.append(f"  - {cid}")
    if summary.top_failure_messages:
        lines.append("Failure Messages:")
        for idx, msg in enumerate(summary.top_failure_messages, start=1):
            lines.append(f"  [{idx}] {msg}")

    return "\n".join(lines)


def format_lab_run_report(run: LabRun) -> str:
    """Convenience: directly generate text report from LabRun (internally summarize then format)."""
    summary = summarize_lab_run(run)
    return format_lab_run_summary(summary)


def lab_run_passed(run: LabRun) -> bool:
    """Return True only when run.status is passed, False otherwise."""
    return run.status == LabStatus.passed


__all__ = [
    "LabRunSummary",
    "lab_run_passed",
    "format_lab_run_report",
    "format_lab_run_summary",
    "summarize_lab_run",
]
