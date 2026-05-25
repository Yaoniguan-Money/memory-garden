"""第六层 Stage 6C：SnapshotLabRunner（纯快照、无 Core/存储）单元测试。"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from memory_garden.lab.assertions import evaluate_case as _evaluate_case_builtin
from memory_garden.lab.fixtures import default_lab_suites, fixture_example_actual_from_case
from memory_garden.lab.models import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabFailure,
    LabStatus,
    LabSuite,
    LabTarget,
)
from memory_garden.lab.runner import SnapshotLabRunner


def test_run_case_passes() -> None:
    runner = SnapshotLabRunner()
    c = LabCase(
        case_id="c_ok",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="x",
                expected=1,
            )
        ],
    )
    r = runner.run_case(c, {"runtime": {"x": 1}})
    assert r.case_id == "c_ok"
    assert r.status == LabStatus.passed
    assert r.failures == []
    metric_names = {m.name for m in r.metrics}
    assert "runner.assertion_count" in metric_names
    assert "runner.failure_count" in metric_names


def test_run_case_fails_returns_lab_failure() -> None:
    runner = SnapshotLabRunner()
    c = LabCase(
        case_id="c_bad",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="x",
                expected=99,
            )
        ],
    )
    r = runner.run_case(c, {"runtime": {"x": 1}})
    assert r.case_id == "c_bad"
    assert r.status == LabStatus.failed
    assert len(r.failures) == 1
    assert isinstance(r.failures[0], LabFailure)


def test_run_suite_per_case_id_actual_data() -> None:
    runner = SnapshotLabRunner()
    c1 = LabCase(
        case_id="id_a",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.seed,
                field_path="k",
                expected=1,
            )
        ],
    )
    c2 = LabCase(
        case_id="id_b",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.seed,
                field_path="k",
                expected=2,
            )
        ],
    )
    suite = LabSuite(suite_id="suite_map", cases=[c1, c2])
    data = {
        "id_a": {"seed": {"k": 1}},
        "id_b": {"seed": {"k": 2}},
    }
    lr = runner.run_suite(suite, data)
    assert lr.status == LabStatus.passed
    assert [x.case_id for x in lr.case_results] == ["id_a", "id_b"]
    assert all(x.status == LabStatus.passed for x in lr.case_results)


def test_run_suite_shared_actual_data_when_keys_not_case_ids() -> None:
    runner = SnapshotLabRunner()
    c1 = LabCase(
        case_id="xa",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="v",
                expected=42,
            )
        ],
    )
    c2 = LabCase(
        case_id="xb",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.runtime,
                field_path="v",
                expected=42,
            )
        ],
    )
    suite = LabSuite(suite_id="suite_shared", cases=[c1, c2])
    shared = {"runtime": {"v": 42}}
    lr = runner.run_suite(suite, shared)
    assert lr.status == LabStatus.passed
    assert len(lr.case_results) == 2


def test_missing_actual_data_yields_failure_not_keyerror() -> None:
    runner = SnapshotLabRunner()
    c1 = LabCase(case_id="has_data", assertions=[])
    c2 = LabCase(
        case_id="no_data",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.is_true,
                target=LabTarget.runtime,
                field_path="ok",
                expected=None,
            )
        ],
    )
    suite = LabSuite(suite_id="partial", cases=[c1, c2])
    # 部分 case_id 命中：缺 no_data
    data = {"has_data": {"runtime": {"ok": True}}}
    lr = runner.run_suite(suite, data)
    assert lr.status == LabStatus.failed
    res_by_id = {r.case_id: r for r in lr.case_results}
    assert res_by_id["has_data"].status == LabStatus.passed
    assert res_by_id["no_data"].status == LabStatus.failed
    assert any("缺少" in f.message for f in res_by_id["no_data"].failures)


def _court_case(cid: str) -> LabCase:
    return LabCase(
        case_id=cid,
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.equals,
                target=LabTarget.court,
                field_path="n",
                expected=1,
            )
        ],
    )


def test_run_suites_multi_suite_order_stable() -> None:
    runner = SnapshotLabRunner()
    s1 = LabSuite(suite_id="suite_order_1", cases=[_court_case("u1")])
    s2 = LabSuite(suite_id="suite_order_2", cases=[_court_case("u2")])
    blob = {"court": {"n": 1}}
    data = {"u1": blob, "u2": blob}
    lr = runner.run_suites([s1, s2], data)
    assert lr.metadata["suite_ids"] == ["suite_order_1", "suite_order_2"]
    assert [r.case_id for r in lr.case_results] == ["u1", "u2"]


def test_metric_results_rollup_fields() -> None:
    runner = SnapshotLabRunner()
    pass_c = LabCase(case_id="p", assertions=[])
    fail_c = LabCase(
        case_id="f",
        assertions=[
            LabAssertion(
                assertion_type=LabAssertionType.is_false,
                target=LabTarget.runtime,
                field_path="x",
                expected=None,
            )
        ],
    )
    suite = LabSuite(suite_id="m", cases=[pass_c, fail_c])
    lr = runner.run_suite(suite, {"p": {"runtime": {"x": True}}, "f": {"runtime": {"x": True}}})
    names = {m["name"]: m["value"] for m in lr.metadata["metric_results"]}
    assert names["total_cases"] == 2
    assert names["passed_cases"] == 1
    assert names["failed_cases"] == 1
    assert names["total_failures"] >= 1
    assert names["pass_rate"] == 0.5


def test_lab_run_model_dump_json() -> None:
    runner = SnapshotLabRunner()
    c = LabCase(case_id="j", assertions=[])
    suite = LabSuite(suite_id="js", cases=[c])
    lr = runner.run_suite(suite, {"j": {}})
    blob = lr.model_dump(mode="json")
    assert isinstance(blob, dict)
    assert blob["status"] == "passed"
    assert "case_results" in blob


def test_default_lab_suites_with_fixture_actuals_all_pass() -> None:
    runner = SnapshotLabRunner()
    suites = default_lab_suites()
    data: dict[str, dict] = {}
    for s in suites:
        for c in s.cases:
            data[c.case_id] = fixture_example_actual_from_case(c)
    lr = runner.run_suites(suites, data)
    assert lr.status == LabStatus.passed


def test_empty_suite_is_skipped() -> None:
    runner = SnapshotLabRunner()
    suite = LabSuite(suite_id="empty_suite_6c", cases=[])
    lr = runner.run_suite(suite, {})
    assert lr.status == LabStatus.skipped
    assert lr.case_results == []
    mr = lr.metadata["metric_results"]
    assert {x["name"]: x["value"] for x in mr}["total_cases"] == 0


def test_runner_does_not_mutate_inputs() -> None:
    runner = SnapshotLabRunner()
    a = LabAssertion(
        assertion_type=LabAssertionType.equals,
        target=LabTarget.seed,
        field_path="deep.v",
        expected=9,
    )
    c = LabCase(case_id="mut", assertions=[a])
    suite = LabSuite(suite_id="mut_s", cases=[c])
    snap = {"seed": {"deep": {"v": 9}}}
    suite_dump = suite.model_dump()
    snap_before = copy.deepcopy(snap)
    runner.run_suite(suite, {"mut": snap})
    assert suite.model_dump() == suite_dump
    assert snap == snap_before


def test_evaluate_case_exception_single_case_failure_does_not_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = SnapshotLabRunner()

    def selective(lc: LabCase, data: dict) -> LabCase:  # type: ignore[no-untyped-def]
        if lc.case_id == "boom":
            raise RuntimeError("simulate broken evaluator")
        return _evaluate_case_builtin(lc, data)

    monkeypatch.setattr("memory_garden.lab.runner.evaluate_case", selective)
    c = LabCase(case_id="boom", assertions=[])
    suite = LabSuite(suite_id="two", cases=[c, LabCase(case_id="ok", assertions=[])])

    lr = runner.run_suite(suite, {"boom": {}, "ok": {}})
    assert lr.status == LabStatus.failed
    by_id = {r.case_id: r for r in lr.case_results}
    assert "evaluate_exception" in by_id["boom"].failures[0].message


def test_metric_result_name_order_fixed() -> None:
    runner = SnapshotLabRunner()
    c = LabCase(case_id="only", assertions=[])
    suite = LabSuite(suite_id="ord", cases=[c])
    lr = runner.run_suite(suite, {"only": {}})
    names = [m["name"] for m in lr.metadata["metric_results"]]
    assert names == ["failed_cases", "passed_cases", "pass_rate", "total_cases", "total_failures"]


def test_runner_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/runner.py").read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw


def test_runner_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = SnapshotLabRunner()
    suite = LabSuite(suite_id="fs", cases=[LabCase(case_id="x", assertions=[])])
    runner.run_suite(suite, {"x": {}})
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


def test_test_module_does_not_import_forbidden_lab_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_runner.py").read_text(encoding="utf-8"))
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
            assert not (mod == prefix or mod.startswith(prefix + "."))
