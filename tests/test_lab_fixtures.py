"""第六层 Stage 6B：Lab fixtures 样例库测试。"""

from __future__ import annotations

import json
from pathlib import Path

from memory_garden.lab import (
    default_lab_suites,
    evaluate_case,
    evaluate_suite_cases,
    fixture_example_actual_from_case,
)
from memory_garden.lab.fixtures import (
    court_verdict_fixture_suite,
    harvest_brief_fixture_suite,
    observatory_redaction_fixture_suite,
    runtime_command_fixture_suite,
    seed_extraction_fixture_suite,
)
from memory_garden.lab.models import LabStatus


def test_default_lab_suites_nonempty_stable_order() -> None:
    suites = default_lab_suites()
    assert len(suites) == 5
    kinds = [s.metadata.get("fixture_kind") for s in suites]
    assert kinds == [
        "seed_extraction",
        "runtime_command",
        "court_verdict",
        "harvest_brief",
        "observatory_redaction",
    ]


def test_each_suite_has_cases_with_assertions() -> None:
    for s in default_lab_suites():
        assert s.cases, s.suite_id
        for c in s.cases:
            assert c.assertions, c.case_id


def test_global_unique_case_and_suite_ids() -> None:
    seen_cases: set[str] = set()
    seen_suites: set[str] = set()
    for s in default_lab_suites():
        assert s.suite_id not in seen_suites
        seen_suites.add(s.suite_id)
        for c in s.cases:
            assert c.case_id not in seen_cases
            seen_cases.add(c.case_id)


def test_all_suites_json_dump() -> None:
    for s in default_lab_suites():
        json.dumps(s.model_dump(mode="json"))


def test_fixtures_evaluate_with_bundled_actual_data() -> None:
    for suite in default_lab_suites():
        mapping = {c.case_id: fixture_example_actual_from_case(c) for c in suite.cases}
        results = evaluate_suite_cases(suite.cases, mapping)
        assert len(results) == len(suite.cases)
        for r in results:
            assert r.status == LabStatus.passed, (r.case_id, r.failures)


def test_individual_evaluate_case_pass() -> None:
    s = seed_extraction_fixture_suite()
    c = s.cases[0]
    res = evaluate_case(c, fixture_example_actual_from_case(c))
    assert res.status == LabStatus.passed


def test_seed_suite_covers_control_commands_no_preference() -> None:
    s = seed_extraction_fixture_suite()
    titles = {c.name for c in s.cases}
    assert any("花花开" in t or "花花关" in t for t in titles)


def test_harvest_observatory_no_long_body_fixtures() -> None:
    h = harvest_brief_fixture_suite()
    blob = "".join(c.description + c.name for c in h.cases).lower()
    assert "memorycard" in blob.replace(" ", "")
    assert "plaintext" in blob or "摘录" in blob or "truncat" in blob
    o = observatory_redaction_fixture_suite()
    o_blob = "".join(c.name + c.description for c in o.cases).lower()
    assert "user_message" in o_blob
    assert "assistant" in o_blob


def test_runtime_short_circuit_fixture_labels() -> None:
    r = runtime_command_fixture_suite()
    sc = next(x for x in r.cases if "short_circuit" in x.case_id)
    assert "花花开" in sc.metadata.get("scenario_hint", "")


def test_fixture_module_source_heuristics() -> None:
    p = Path(__file__).resolve().parents[1] / "memory_garden" / "lab" / "fixtures.py"
    text = p.read_text(encoding="utf-8")
    low = text.lower()
    for token in (
        "openai",
        "anthropic",
        "embedding",
        "vector",
        "rerank",
        "search",
        "sqlite",
        "repository",
        "memory_garden.core",
        "gardenruntime",
        "memorygardencore",
    ):
        assert token not in low, token


def test_evaluation_fails_when_snapshot_empty() -> None:
    suite = observatory_redaction_fixture_suite()
    c = suite.cases[0]
    bad = evaluate_case(c, {})
    assert bad.status == LabStatus.failed
    assert bad.failures


def test_named_fixture_functions_match_default_order() -> None:
    ordered = [
        seed_extraction_fixture_suite(),
        runtime_command_fixture_suite(),
        court_verdict_fixture_suite(),
        harvest_brief_fixture_suite(),
        observatory_redaction_fixture_suite(),
    ]
    for a, b in zip(ordered, default_lab_suites(), strict=True):
        assert a.suite_id == b.suite_id
