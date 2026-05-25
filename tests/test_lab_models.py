"""第六层 Stage 6A：Garden Lab 模型与断言单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from memory_garden.lab import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabCaseResult,
    LabFailure,
    LabMetricResult,
    LabRun,
    LabSeverity,
    LabStatus,
    LabSuite,
    LabTarget,
    evaluate_assertion,
    evaluate_case,
    evaluate_suite_cases,
)


def test_models_json_round_trip() -> None:
    assertion = LabAssertion(
        assertion_type=LabAssertionType.equals,
        target=LabTarget.runtime,
        field_path="state",
        expected="open",
    )
    case = LabCase(case_id="c1", name="n", assertions=[assertion])
    suite = LabSuite(name="suite-a", cases=[case])
    failure = LabFailure(
        case_id="c1",
        target=LabTarget.runtime,
        field_path="state",
        expected="open",
        actual="closed",
        message="不匹配",
    )
    mr = LabMetricResult(name="latency_ms", value=12, unit="ms")
    cr = LabCaseResult(case_id="c1", status=LabStatus.failed, failures=[failure], metrics=[mr])
    run = LabRun(suite_id=suite.suite_id, status=LabStatus.failed, case_results=[cr])

    for obj in (assertion, case, suite, failure, mr, cr, run):
        blob = json.dumps(obj.model_dump(mode="json"))
        assert json.loads(blob)


def test_lab_assertion_type_enum_complete() -> None:
    names = {m.value for m in LabAssertionType}
    assert names == {
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "is_true",
        "is_false",
        "count_equals",
        "count_at_most",
        "field_present",
        "field_absent",
    }


def test_lab_target_enum() -> None:
    assert {t.value for t in LabTarget} == {
        "seed",
        "court",
        "growth",
        "dream",
        "harvest",
        "runtime",
        "observatory",
    }


def test_equals_pass_and_fail() -> None:
    a = LabAssertion(assertion_type=LabAssertionType.equals, target=LabTarget.runtime, field_path="x", expected=1)
    data = {"runtime": {"x": 1}}
    assert evaluate_assertion(a, case_id="cid", actual_data=data) is None
    data2 = {"runtime": {"x": 2}}
    f = evaluate_assertion(a, case_id="cid", actual_data=data2)
    assert f is not None
    _assert_failure_shape(f, case_id="cid")


def test_not_equals() -> None:
    a = LabAssertion(assertion_type=LabAssertionType.not_equals, target=LabTarget.seed, field_path="k", expected=0)
    assert evaluate_assertion(a, case_id="x", actual_data={"seed": {"k": 1}}) is None
    assert evaluate_assertion(a, case_id="x", actual_data={"seed": {"k": 0}}) is not None


def test_contains_string_and_list() -> None:
    a = LabAssertion(
        assertion_type=LabAssertionType.contains,
        target=LabTarget.observatory,
        field_path="summary",
        expected="hi",
    )
    assert evaluate_assertion(a, case_id="z", actual_data={"observatory": {"summary": "ahi there"}}) is None
    lst = LabAssertion(
        assertion_type=LabAssertionType.contains,
        target=LabTarget.observatory,
        field_path="tags",
        expected="a",
    )
    assert evaluate_assertion(lst, case_id="z", actual_data={"observatory": {"tags": ["a", "b"]}}) is None


def test_not_contains() -> None:
    a = LabAssertion(assertion_type=LabAssertionType.not_contains, target=LabTarget.harvest, field_path="t", expected="bad")
    assert evaluate_assertion(a, case_id="z", actual_data={"harvest": {"t": "good"}}) is None
    assert evaluate_assertion(a, case_id="z", actual_data={"harvest": {"t": "badluck"}}) is not None


def test_is_true_is_false() -> None:
    t = LabAssertion(assertion_type=LabAssertionType.is_true, target=LabTarget.runtime, field_path="ok", expected=None)
    f = LabAssertion(assertion_type=LabAssertionType.is_false, target=LabTarget.runtime, field_path="ok", expected=None)
    assert evaluate_assertion(t, case_id="c", actual_data={"runtime": {"ok": True}}) is None
    assert evaluate_assertion(t, case_id="c", actual_data={"runtime": {"ok": False}}) is not None
    assert evaluate_assertion(f, case_id="c", actual_data={"runtime": {"ok": False}}) is None
    assert evaluate_assertion(f, case_id="c", actual_data={"runtime": {"ok": True}}) is not None


def test_count_equals_and_at_most() -> None:
    ce = LabAssertion(assertion_type=LabAssertionType.count_equals, target=LabTarget.seed, field_path="items", expected=2)
    cm = LabAssertion(assertion_type=LabAssertionType.count_at_most, target=LabTarget.seed, field_path="items", expected=3)
    d = {"seed": {"items": [1, 2]}}
    assert evaluate_assertion(ce, case_id="c", actual_data=d) is None
    assert evaluate_assertion(cm, case_id="c", actual_data=d) is None
    assert evaluate_assertion(ce, case_id="c", actual_data={"seed": {"items": [1]}}) is not None
    assert evaluate_assertion(cm, case_id="c", actual_data={"seed": {"items": [1, 2, 3, 4]}}) is not None


def test_field_present_absent_root() -> None:
    pres = LabAssertion(assertion_type=LabAssertionType.field_present, target=LabTarget.runtime, field_path="", expected=None)
    assert evaluate_assertion(pres, case_id="c", actual_data={"runtime": {"x": 1}}) is None
    assert evaluate_assertion(pres, case_id="c", actual_data={}) is not None

    ab = LabAssertion(assertion_type=LabAssertionType.field_absent, target=LabTarget.runtime, field_path="", expected=None)
    assert evaluate_assertion(ab, case_id="c", actual_data={}) is None
    assert evaluate_assertion(ab, case_id="c", actual_data={"runtime": {}}) is not None


def test_field_present_nested_path() -> None:
    pr = LabAssertion(
        assertion_type=LabAssertionType.field_present,
        target=LabTarget.runtime,
        field_path="nested.k",
        expected=None,
    )
    assert evaluate_assertion(pr, case_id="i", actual_data={"runtime": {"nested": {"k": 9}}}) is None
    assert evaluate_assertion(pr, case_id="i", actual_data={"runtime": {"nested": {}}}) is not None


def test_evaluate_case_aggregate() -> None:
    lc = LabCase(
        case_id="agg",
        assertions=[
            LabAssertion(assertion_type=LabAssertionType.equals, target=LabTarget.dream, field_path="done", expected=True),
        ],
    )
    ok = evaluate_case(lc, {"dream": {"done": True}})
    assert ok.status == LabStatus.passed
    bad = evaluate_case(lc, {"dream": {"done": False}})
    assert bad.status == LabStatus.failed
    assert len(bad.failures) == 1


def test_evaluate_suite_cases_mapping() -> None:
    ca = LabCase(case_id="a", assertions=[])

    cb = LabCase(
        case_id="b",
        assertions=[
            LabAssertion(assertion_type=LabAssertionType.equals, target=LabTarget.growth, field_path="v", expected=3),
        ],
    )
    results = evaluate_suite_cases(
        [ca, cb],
        {"a": {}, "b": {"growth": {"v": 3}}},
    )
    assert results[0].status == LabStatus.passed
    assert results[1].status == LabStatus.passed


def test_lab_module_sources_no_vendor_tokens() -> None:
    root = Path(__file__).resolve().parents[1] / "memory_garden" / "lab"
    text = "".join(p.read_text(encoding="utf-8").lower() for p in sorted(root.glob("*.py")))
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search"):
        assert token not in text


def test_package_exports() -> None:
    import memory_garden.lab as lab

    assert hasattr(lab, "LabSuite")


def _assert_failure_shape(f: LabFailure, *, case_id: str) -> None:
    assert f.case_id == case_id
    assert isinstance(f.target, LabTarget)
    assert isinstance(f.field_path, str)
    assert "message" in f.model_dump()
    assert f.message


def test_failure_contains_assertion_meta() -> None:
    f = LabFailure(
        case_id="c",
        target=LabTarget.seed,
        field_path="p",
        expected=1,
        actual=2,
        message="m",
        assertion_type=LabAssertionType.equals,
        severity=LabSeverity.warning,
    )
    d = f.model_dump(mode="json")
    assert d["severity"] == "warning"
    json.dumps(d)
