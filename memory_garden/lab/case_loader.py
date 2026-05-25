"""Seventh layer Stage 7B: JSON EvalCase Loader (dict/JSON to LabCase/LabSuite, no execution)."""

from __future__ import annotations

import json
from typing import Any

from memory_garden.lab.models import (
    LabAssertion,
    LabAssertionType,
    LabCase,
    LabSuite,
    LabTarget,
)


# ---------------------------------------------------------------------------
# loader errors
# ---------------------------------------------------------------------------

class CaseLoaderError(ValueError):
    """Base error for case loader operations."""


class InvalidJSONError(CaseLoaderError):
    """JSON parse failed."""


class MissingFieldError(CaseLoaderError):
    """Required field is missing."""


class InvalidAssertionTypeError(CaseLoaderError):
    """Unknown assertion_type value."""


class InvalidTargetError(CaseLoaderError):
    """Unknown target value."""


class InvalidAssertionsError(CaseLoaderError):
    """assertions is not a list."""


class InvalidCasesError(CaseLoaderError):
    """cases is not a list."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidJSONError(f"Invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise InvalidJSONError(f"Expected a JSON object, got {type(data).__name__}")
    return data


def _resolve_key(data: dict[str, Any], *keys: str) -> Any:
    """Return the value for the first key that exists in data, or raise."""
    for k in keys:
        if k in data:
            return data[k]
    return None


def _require_key(data: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in data:
            return data[k]
    label = " / ".join(keys)
    raise MissingFieldError(f"Missing required field: {label}")


def _parse_assertion_type(value: str) -> LabAssertionType:
    valid = {e.value for e in LabAssertionType}
    if value not in valid:
        raise InvalidAssertionTypeError(
            f"Unknown assertion_type {value!r}. Valid: {sorted(valid)}"
        )
    return LabAssertionType(value)


def _parse_target(value: str) -> LabTarget:
    valid = {e.value for e in LabTarget}
    if value not in valid:
        raise InvalidTargetError(
            f"Unknown target {value!r}. Valid: {sorted(valid)}"
        )
    return LabTarget(value)


def _build_assertion(raw: dict[str, Any]) -> LabAssertion:
    if not isinstance(raw, dict):
        raise CaseLoaderError(f"Each assertion must be a dict, got {type(raw).__name__}")

    at_raw = _require_key(raw, "assertion_type")
    target_raw = _require_key(raw, "target")

    if not isinstance(at_raw, str):
        raise CaseLoaderError(f"assertion_type must be a string, got {type(at_raw).__name__}")
    if not isinstance(target_raw, str):
        raise CaseLoaderError(f"target must be a string, got {type(target_raw).__name__}")

    at = _parse_assertion_type(at_raw)
    target = _parse_target(target_raw)

    field_path = raw.get("field_path", "")
    if not isinstance(field_path, str):
        raise CaseLoaderError(f"field_path must be a string, got {type(field_path).__name__}")

    expected = raw.get("expected")
    assertion_id = raw.get("assertion_id")

    return LabAssertion(
        assertion_id=assertion_id,
        assertion_type=at,
        target=target,
        field_path=field_path,
        expected=expected,
    )


def _build_assertions(raw_assertions: Any) -> list[LabAssertion]:
    if not isinstance(raw_assertions, list):
        raise InvalidAssertionsError(
            f"assertions must be a list, got {type(raw_assertions).__name__}"
        )
    return [_build_assertion(a) for a in raw_assertions]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def load_lab_case_from_dict(data: dict[str, Any]) -> LabCase:
    """Load a LabCase from a dict (no Runner execution)."""
    if not isinstance(data, dict):
        raise CaseLoaderError(f"Expected a dict, got {type(data).__name__}")

    case_id = str(_require_key(data, "case_id", "id"))
    name = str(data.get("name") or data.get("title") or "")
    description = str(data.get("description") or "")

    raw_assertions = data.get("assertions", [])
    assertions = _build_assertions(raw_assertions)

    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise CaseLoaderError(f"metadata must be a dict, got {type(metadata).__name__}")

    return LabCase(
        case_id=case_id,
        name=name,
        description=description,
        assertions=assertions,
        metadata=dict(metadata) if metadata else {},
    )


def load_lab_case_from_json(text: str) -> LabCase:
    """Load a LabCase from a JSON string (no Runner execution)."""
    data = _parse_json(text)
    return load_lab_case_from_dict(data)


def load_lab_suite_from_dict(data: dict[str, Any]) -> LabSuite:
    """Load a LabSuite from a dict (no Runner execution)."""
    if not isinstance(data, dict):
        raise CaseLoaderError(f"Expected a dict, got {type(data).__name__}")

    suite_id = str(_require_key(data, "suite_id", "id"))
    name = str(data.get("name") or "")

    raw_cases = data.get("cases", [])
    if not isinstance(raw_cases, list):
        raise InvalidCasesError(
            f"cases must be a list, got {type(raw_cases).__name__}"
        )

    cases = [load_lab_case_from_dict(c) for c in raw_cases]

    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise CaseLoaderError(f"metadata must be a dict, got {type(metadata).__name__}")

    return LabSuite(
        suite_id=suite_id,
        name=name,
        cases=cases,
        metadata=dict(metadata) if metadata else {},
    )


def load_lab_suite_from_json(text: str) -> LabSuite:
    """Load a LabSuite from a JSON string (no Runner execution)."""
    data = _parse_json(text)
    return load_lab_suite_from_dict(data)


__all__ = [
    "CaseLoaderError",
    "InvalidAssertionsError",
    "InvalidAssertionTypeError",
    "InvalidCasesError",
    "InvalidJSONError",
    "InvalidTargetError",
    "MissingFieldError",
    "load_lab_case_from_dict",
    "load_lab_case_from_json",
    "load_lab_suite_from_dict",
    "load_lab_suite_from_json",
]