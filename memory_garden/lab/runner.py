"""第六层 Stage 6C：纯快照 LabRunner（不调 Core/Runtime/Observatory）。

套件内对每个用例逐一调用 ``evaluate_case``，以便断言异常可隔离为失败而不中断套件；
项目中 ``evaluate_suite_cases`` 仍可被其它调用方用于「已齐全 case_id→快照」的批量评估。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memory_garden.lab.assertions import evaluate_case
from memory_garden.lab.models import (
    LabCase,
    LabCaseResult,
    LabFailure,
    LabMetricResult,
    LabRun,
    LabSeverity,
    LabStatus,
    LabSuite,
    LabTarget,
)

_METRIC_NAMES_ORDER = (
    "failed_cases",
    "passed_cases",
    "pass_rate",
    "total_cases",
    "total_failures",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _shallow_copy_blob(data: dict[str, Any]) -> dict[str, Any]:
    import copy
    return copy.deepcopy(data)


def resolve_case_actual_blobs(suite: LabSuite, data: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    """解析各用例快照；值为 None 表示缺快照（不抛 KeyError）。"""
    case_ids = [c.case_id for c in suite.cases]
    if not case_ids:
        return {}
    sset = set(case_ids)
    dkeys = set(data.keys())
    if sset <= dkeys:
        return {cid: (data[cid] if isinstance(data.get(cid), dict) else None) for cid in case_ids}
    if sset & dkeys:
        out: dict[str, dict[str, Any] | None] = {}
        for cid in case_ids:
            if cid not in data:
                out[cid] = None
            else:
                v = data[cid]
                out[cid] = v if isinstance(v, dict) else None
        return out
    shared = _shallow_copy_blob(data)
    return {cid: shared for cid in case_ids}


def _missing_actual_failure(case: LabCase) -> LabFailure:
    return LabFailure(
        case_id=case.case_id,
        target=LabTarget.runtime,
        field_path="",
        expected="per_case_or_shared_actual_data",
        actual=None,
        message="缺少该用例的快照数据（runner.snapshot_missing）；请提供 case_id 映射或共享快照。",
        assertion_type=None,
        severity=LabSeverity.error,
    )


class SnapshotLabRunner:
    """对已有 ``LabCase`` / ``LabSuite`` 与内存 dict 快照做评估，不产生真实业务副作用。"""

    __slots__ = ()

    def _execute_suite(self, suite: LabSuite, data: dict[str, Any]) -> list[LabCaseResult]:
        blobs = resolve_case_actual_blobs(suite, data)
        case_results: list[LabCaseResult] = []
        for c in suite.cases:
            blob = blobs.get(c.case_id)
            if blob is None:
                cr = LabCaseResult(
                    case_id=c.case_id,
                    status=LabStatus.failed,
                    failures=[_missing_actual_failure(c)],
                    metrics=[],
                    notes=["runner.missing_actual_data"],
                )
                case_results.append(self._decorate_case_metrics(c, cr))
            else:
                case_results.append(self.run_case(c, blob))
        return case_results

    def run_case(self, case: LabCase, actual_data: dict[str, Any]) -> LabCaseResult:
        snap = _shallow_copy_blob(actual_data)
        try:
            base = evaluate_case(case, snap)
        except Exception as e:  # noqa: BLE001 — 单例失败不中断上层套件
            fb = LabFailure(
                case_id=case.case_id,
                target=LabTarget.runtime,
                field_path="",
                expected=None,
                actual=None,
                message=f"runner.evaluate_exception: {type(e).__name__}: {e}",
                assertion_type=None,
                severity=LabSeverity.error,
            )
            base = LabCaseResult(
                case_id=case.case_id,
                status=LabStatus.failed,
                failures=[fb],
                metrics=[],
                notes=[],
            )
        return self._decorate_case_metrics(case, base)

    def run_suite(self, suite: LabSuite, actual_data_by_case_id: dict[str, Any]) -> LabRun:
        started = _utc_now()
        case_results = self._execute_suite(suite, actual_data_by_case_id)
        ended = _utc_now()
        rollup = _rollup_metrics(case_results)
        status = _aggregate_status(case_results)
        meta: dict[str, Any] = {
            "suite_ids": [suite.suite_id],
            "metric_results": [m.model_dump(mode="json") for m in rollup],
            "runner": "snapshot_v6c",
        }
        return LabRun(
            suite_id=suite.suite_id,
            status=status,
            case_results=case_results,
            started_at=started,
            ended_at=ended,
            metadata=meta,
        )

    def run_suites(self, suites: list[LabSuite], actual_data_by_case_id: dict[str, Any]) -> LabRun:
        started = _utc_now()
        all_results: list[LabCaseResult] = []
        suite_ids: list[str] = []
        for suite in suites:
            suite_ids.append(suite.suite_id)
            all_results.extend(self._execute_suite(suite, actual_data_by_case_id))
        ended = _utc_now()
        rollup = _rollup_metrics(all_results)
        status = _aggregate_status(all_results)
        meta: dict[str, Any] = {
            "suite_ids": suite_ids,
            "metric_results": [m.model_dump(mode="json") for m in rollup],
            "runner": "snapshot_v6c",
        }
        return LabRun(
            suite_id="",
            status=status,
            case_results=all_results,
            started_at=started,
            ended_at=ended,
            metadata=meta,
        )

    @staticmethod
    def _decorate_case_metrics(case: LabCase, base: LabCaseResult) -> LabCaseResult:
        extra = [
            LabMetricResult(name="runner.assertion_count", value=len(case.assertions)),
            LabMetricResult(name="runner.failure_count", value=len(base.failures)),
        ]
        merged = sorted([*base.metrics, *extra], key=lambda m: m.name)
        notes = [*base.notes, f"runner.assertions_executed={len(case.assertions)}"]
        return base.model_copy(update={"metrics": merged, "notes": notes})


def _rollup_metrics(case_results: list[LabCaseResult]) -> list[LabMetricResult]:
    total = len(case_results)
    passed = sum(1 for r in case_results if r.status == LabStatus.passed)
    failed = sum(1 for r in case_results if r.status == LabStatus.failed)
    total_failures = sum(len(r.failures) for r in case_results)
    rate = round(passed / total, 6) if total > 0 else 0.0
    metrics = [
        LabMetricResult(name="failed_cases", value=failed),
        LabMetricResult(name="passed_cases", value=passed),
        LabMetricResult(name="pass_rate", value=rate),
        LabMetricResult(name="total_cases", value=total),
        LabMetricResult(name="total_failures", value=total_failures),
    ]
    metrics.sort(key=lambda m: _METRIC_NAMES_ORDER.index(m.name))
    return metrics


def _aggregate_status(case_results: list[LabCaseResult]) -> LabStatus:
    if not case_results:
        return LabStatus.skipped
    if any(r.status == LabStatus.failed for r in case_results):
        return LabStatus.failed
    return LabStatus.passed


__all__ = [
    "SnapshotLabRunner",
    "resolve_case_actual_blobs",
]
