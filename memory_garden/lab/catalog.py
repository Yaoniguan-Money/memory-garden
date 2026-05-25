"""Seventh layer Stage 7A: Lab Catalog / Coverage Manifest (read-only, no execution, no Runner)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.lab.models import LabSuite

_META_SKIP_KEY = "lab_fixture_example_actual"


class LabCaseCatalogEntry(BaseModel):
    """Read-only summary of a single LabCase (no actual_data, no fixture snapshot)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    case_id: str = Field(..., min_length=1)
    name: str = Field(default="", max_length=512)
    primary_target: str = Field(default="")
    assertion_count: int = Field(ge=0)
    assertion_types: list[str] = Field(default_factory=list)
    metadata_keys: list[str] = Field(default_factory=list)
    severity: str | None = Field(default=None)


class LabSuiteCatalogEntry(BaseModel):
    """Read-only summary of a single LabSuite."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    suite_id: str = Field(..., min_length=1)
    name: str = Field(default="", max_length=512)
    fixture_kind: str = Field(default="")
    case_count: int = Field(ge=0)
    case_ids: list[str] = Field(default_factory=list)


class LabCatalog(BaseModel):
    """Aggregate catalog of all suites and cases (no execution, no Runner calls)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    suite_count: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    suites: list[LabSuiteCatalogEntry] = Field(default_factory=list)
    entries: list[LabCaseCatalogEntry] = Field(default_factory=list)
    case_ids_global: list[str] = Field(default_factory=list)


def _build_case_entry(case: Any, suite_meta: dict[str, Any]) -> LabCaseCatalogEntry:
    """Build a case catalog entry from a LabCase, stripping large snapshot data."""
    case_meta: dict[str, Any] = dict(case.metadata)
    case_meta.pop(_META_SKIP_KEY, None)

    assertion_types: list[str] = sorted({a.assertion_type.value for a in case.assertions})
    metadata_keys: list[str] = sorted(k for k in case_meta.keys() if k != _META_SKIP_KEY)

    primary_target_raw = case_meta.get("primary_target", "")
    primary_target = str(primary_target_raw) if primary_target_raw is not None else ""

    severity_raw = case_meta.get("severity")
    severity = str(severity_raw) if severity_raw is not None else None

    name = case.name if case.name else ""

    return LabCaseCatalogEntry(
        case_id=case.case_id,
        name=name,
        primary_target=primary_target,
        assertion_count=len(case.assertions),
        assertion_types=assertion_types,
        metadata_keys=metadata_keys,
        severity=severity,
    )


def build_lab_catalog(suites: list[LabSuite]) -> LabCatalog:
    """Build a read-only catalog from a list of LabSuites (no Runner, no actual_data)."""
    suite_entries: list[LabSuiteCatalogEntry] = []
    case_entries: list[LabCaseCatalogEntry] = []
    all_case_ids: list[str] = []

    for s in suites:
        suite_meta: dict[str, Any] = dict(s.metadata)
        fixture_kind = str(suite_meta.get("fixture_kind", ""))
        case_ids = [c.case_id for c in s.cases]

        suite_entries.append(
            LabSuiteCatalogEntry(
                suite_id=s.suite_id,
                name=s.name,
                fixture_kind=fixture_kind,
                case_count=len(s.cases),
                case_ids=case_ids,
            )
        )

        for c in s.cases:
            case_entries.append(_build_case_entry(c, suite_meta))
            all_case_ids.append(c.case_id)

    return LabCatalog(
        suite_count=len(suites),
        total_cases=len(case_entries),
        suites=suite_entries,
        entries=case_entries,
        case_ids_global=all_case_ids,
    )


def build_default_lab_catalog() -> LabCatalog:
    """Build a catalog from default_lab_suites() without running any cases."""
    from memory_garden.lab.fixtures import default_lab_suites

    suites = default_lab_suites()
    return build_lab_catalog(suites)


__all__ = [
    "LabCaseCatalogEntry",
    "LabSuiteCatalogEntry",
    "LabCatalog",
    "build_lab_catalog",
    "build_default_lab_catalog",
]