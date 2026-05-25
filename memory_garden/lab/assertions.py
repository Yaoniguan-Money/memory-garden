"""第六层 Stage 6A：对内存 dict 快照执行 LabAssertion（无 Core/Runtime 调用）。"""

from __future__ import annotations

from typing import Any

from memory_garden.lab.models import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabCaseResult,
    LabFailure,
    LabMetricResult,
    LabSeverity,
    LabStatus,
)

_MISSING = object()


def _get_path(obj: Any, field_path: str) -> tuple[Any, bool]:
    """返回 (value, resolved)。resolved=False 表示路径不存在。"""
    if field_path.strip() == "":
        return obj, True

    cur: Any = obj
    for part in field_path.split("."):
        part = part.strip()
        if part == "":
            continue
        if isinstance(cur, dict):
            if part not in cur:
                return _MISSING, False
            cur = cur[part]
        else:
            return _MISSING, False

    return cur, True


def _fail(
    *,
    case_id: str,
    assertion: LabAssertion,
    actual: Any,
    expected: Any,
    message: str,
) -> LabFailure:
    return LabFailure(
        case_id=case_id,
        target=assertion.target,
        field_path=assertion.field_path,
        expected=expected,
        actual=actual,
        message=message,
        assertion_type=assertion.assertion_type,
        severity=LabSeverity.error,
    )


def evaluate_assertion(
    assertion: LabAssertion,
    *,
    case_id: str,
    actual_data: dict[str, Any],
) -> LabFailure | None:
    """对 ``actual_data[target]`` 为根的子树做断言；不满足则返回 ``LabFailure``。"""
    key = assertion.target.value
    if key not in actual_data:
        blob: Any = _MISSING
        root_present = False
    else:
        blob = actual_data[key]
        root_present = True

    if assertion.field_path.strip() == "":
        resolved = root_present
        value = blob if resolved else _MISSING
    else:
        if not root_present or blob is _MISSING:
            value, resolved = _MISSING, False
        else:
            value, resolved = _get_path(blob, assertion.field_path)

    at_type = assertion.assertion_type

    if at_type == LabAssertionType.field_present:
        if not resolved:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=None,
                expected="present",
                message=f"路径 {assertion.field_path!r} 在 target={assertion.target.value} 下不存在",
            )
        return None

    if at_type == LabAssertionType.field_absent:
        if resolved:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=value,
                expected="absent",
                message=f"路径 {assertion.field_path!r} 在 target={assertion.target.value} 下仍存在",
            )
        return None

    if not root_present:
        return _fail(
            case_id=case_id,
            assertion=assertion,
            actual=None,
            expected=assertion.expected,
            message=f"target 键 {key!r} 在 actual_data 中缺失",
        )

    if assertion.field_path.strip() != "" and not resolved:
        return _fail(
            case_id=case_id,
            assertion=assertion,
            actual=None,
            expected=assertion.expected,
            message=f"无法解析字段路径 {assertion.field_path!r}",
        )

    act = value

    def _equals() -> bool:
        return act == assertion.expected

    if at_type == LabAssertionType.equals:
        if not _equals():
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=assertion.expected,
                message="值与 expected 不相等（equals）",
            )
        return None

    if at_type == LabAssertionType.not_equals:
        if _equals():
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=assertion.expected,
                message="值与 expected 相等，违反 not_equals",
            )
        return None

    if at_type == LabAssertionType.contains:
        exp = assertion.expected
        ok = False
        if isinstance(act, str) and isinstance(exp, str):
            ok = exp in act
        elif isinstance(act, (list, tuple, set)):
            ok = exp in act
        elif isinstance(act, dict):
            ok = exp in act.values()
        if not ok:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=exp,
                message="contains 未满足（字符串子串或容器成员）",
            )
        return None

    if at_type == LabAssertionType.not_contains:
        exp = assertion.expected
        bad = False
        if isinstance(act, str) and isinstance(exp, str):
            bad = exp in act
        elif isinstance(act, (list, tuple, set)):
            bad = exp in act
        elif isinstance(act, dict):
            bad = exp in act.values()
        if bad:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=exp,
                message="not_contains 未满足",
            )
        return None

    if at_type == LabAssertionType.is_true:
        if not bool(act):
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=True,
                message="期望为真（is_true）",
            )
        return None

    if at_type == LabAssertionType.is_false:
        if bool(act):
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=False,
                message="期望为假（is_false）",
            )
        return None

    if at_type in (LabAssertionType.count_equals, LabAssertionType.count_at_most):
        try:
            n = len(act)  # type: ignore[arg-type]
        except TypeError:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=act,
                expected=assertion.expected,
                message="count 类断言要求路径指向有 len 的对象",
            )
        exp = assertion.expected
        if not isinstance(exp, int):
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=n,
                expected=exp,
                message="count 断言的 expected 须为 int",
            )
        if at_type == LabAssertionType.count_equals and n != exp:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=n,
                expected=exp,
                message=f"元素数量 {n} != expected {exp}",
            )
        if at_type == LabAssertionType.count_at_most and n > exp:
            return _fail(
                case_id=case_id,
                assertion=assertion,
                actual=n,
                expected=exp,
                message=f"元素数量 {n} 超过上界 {exp}",
            )
        return None

    raise RuntimeError(f"未覆盖的断言类型：{at_type!r}")


def evaluate_case(
    lab_case: LabCase,
    actual_data: dict[str, Any],
    *,
    metrics: list[LabMetricResult] | None = None,
) -> LabCaseResult:
    """执行用例内全部断言，返回聚合结果（纯函数）。"""
    failures: list[LabFailure] = []
    for a in lab_case.assertions:
        f = evaluate_assertion(a, case_id=lab_case.case_id, actual_data=actual_data)
        if f is not None:
            failures.append(f)

    status = LabStatus.failed if failures else LabStatus.passed
    return LabCaseResult(
        case_id=lab_case.case_id,
        status=status,
        failures=failures,
        metrics=list(metrics or []),
    )


def evaluate_suite_cases(
    cases: list[LabCase],
    actual_per_case: dict[str, dict[str, Any]],
) -> list[LabCaseResult]:
    """按 ``case_id`` 映射各用例的 actual_data。"""
    out: list[LabCaseResult] = []
    for c in cases:
        blob = actual_per_case.get(c.case_id, {})
        out.append(evaluate_case(c, blob))
    return out
