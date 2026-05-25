"""Seventh layer Stage 7F: Lab coverage and gap report.

This module builds a read-only coverage view from LabSuite metadata. It does not
run cases or call any Memory Garden product layer.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.lab.catalog import LabCatalog, build_lab_catalog
from memory_garden.lab.models import LabSuite
from memory_garden.lab.suite_packs import SAFETY, get_lab_suite_pack, list_lab_suite_packs


class LabCoverageStatus(str, Enum):
    """Coverage state for a Memory Garden mechanism."""

    covered = "covered"
    partial = "partial"
    snapshot_only = "snapshot_only"
    missing = "missing"


class LabMechanismCoverage(BaseModel):
    """Coverage entry for one Memory Garden mechanism."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    mechanism: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    status: LabCoverageStatus
    case_ids: list[str] = Field(default_factory=list)
    suite_ids: list[str] = Field(default_factory=list)
    pack_names: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    recommended_next: str | None = Field(default=None)


class LabCoverageReport(BaseModel):
    """Stable, JSON-safe Lab coverage report."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    report_id: str = Field(default="lab_coverage_7f_v1", min_length=1)
    suite_count: int = Field(ge=0)
    catalog_total_cases: int = Field(ge=0)
    mechanisms: list[LabMechanismCoverage] = Field(default_factory=list)
    covered_targets: list[str] = Field(default_factory=list)
    snapshot_only_targets: list[str] = Field(default_factory=list)
    missing_targets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _case_ids_for_target(catalog: LabCatalog, target: str) -> list[str]:
    return [e.case_id for e in catalog.entries if e.primary_target == target]


def _suite_ids_for_cases(catalog: LabCatalog, case_ids: list[str]) -> list[str]:
    selected = set(case_ids)
    suite_ids: list[str] = []
    for suite in catalog.suites:
        if any(cid in selected for cid in suite.case_ids):
            suite_ids.append(suite.suite_id)
    return suite_ids


def _pack_names_for_cases(case_ids: list[str]) -> list[str]:
    selected = set(case_ids)
    names: list[str] = []
    for pack in list_lab_suite_packs():
        if any(cid in selected for cid in pack.case_ids):
            names.append(pack.pack_name)
    return names


def _entry(
    catalog: LabCatalog,
    *,
    mechanism: str,
    target: str,
    status: LabCoverageStatus | None = None,
    case_ids: list[str] | None = None,
    notes: list[str] | None = None,
    recommended_next: str | None = None,
) -> LabMechanismCoverage:
    ids = list(case_ids) if case_ids is not None else _case_ids_for_target(catalog, target)
    resolved_status = status
    if resolved_status is None:
        resolved_status = LabCoverageStatus.covered if ids else LabCoverageStatus.missing

    return LabMechanismCoverage(
        mechanism=mechanism,
        target=target,
        status=resolved_status,
        case_ids=ids,
        suite_ids=_suite_ids_for_cases(catalog, ids),
        pack_names=_pack_names_for_cases(ids),
        notes=list(notes or []),
        recommended_next=recommended_next,
    )


def _hard_forget_placeholder_ids() -> list[str]:
    pack = get_lab_suite_pack(SAFETY)
    return [cid for cid in pack.case_ids if "hard_forget" in cid]


def build_lab_coverage_report(suites: list[LabSuite]) -> LabCoverageReport:
    """Build a coverage and gap report from explicit LabSuite objects."""
    catalog = build_lab_catalog(suites)
    hard_forget_ids = _hard_forget_placeholder_ids()

    mechanisms = [
        _entry(
            catalog,
            mechanism="seed_capture_contract",
            target="seed",
            notes=["Covers command filtering and pending preference signals."],
        ),
        _entry(
            catalog,
            mechanism="court_verdict_contract",
            target="court",
            notes=["Covers negative identity plant blocking."],
        ),
        _entry(
            catalog,
            mechanism="growth_safety_contract",
            target="growth",
            notes=["Covers greenhouse routing as a snapshot contract."],
        ),
        _entry(
            catalog,
            mechanism="runtime_command_contract",
            target="runtime",
            notes=["Covers command short-circuit snapshots."],
        ),
        _entry(
            catalog,
            mechanism="harvest_brief_contract",
            target="harvest",
            notes=["Covers source ids and short-form brief constraints."],
        ),
        _entry(
            catalog,
            mechanism="observatory_public_contract",
            target="observatory",
            notes=["Covers public redaction snapshots."],
        ),
        _entry(
            catalog,
            mechanism="dream_cycle_contract",
            target="dream",
            notes=["No default fixture currently covers dream-cycle semantics."],
            recommended_next="Add snapshot cases for composting short-term negative fragments and traceable transformations.",
        ),
        _entry(
            catalog,
            mechanism="hard_forget_no_leak_contract",
            target="observatory",
            status=LabCoverageStatus.snapshot_only,
            case_ids=hard_forget_ids,
            notes=["Safety pack contains a placeholder contract; integrators must provide their own snapshot."],
            recommended_next="Add concrete local snapshots after a caller supplies redacted forget outputs.",
        ),
        _entry(
            catalog,
            mechanism="end_to_end_adapter_contract",
            target="integration",
            status=LabCoverageStatus.missing,
            case_ids=[],
            notes=["The Lab layer intentionally stays snapshot-based and does not drive full product flows."],
            recommended_next="Add adapter-provided snapshots without invoking product layers from Lab.",
        ),
    ]

    covered_targets = sorted({m.target for m in mechanisms if m.status in {LabCoverageStatus.covered, LabCoverageStatus.partial}})
    snapshot_only_targets = sorted({m.target for m in mechanisms if m.status == LabCoverageStatus.snapshot_only})
    missing_targets = sorted({m.target for m in mechanisms if m.status == LabCoverageStatus.missing})

    return LabCoverageReport(
        suite_count=catalog.suite_count,
        catalog_total_cases=catalog.total_cases,
        mechanisms=mechanisms,
        covered_targets=covered_targets,
        snapshot_only_targets=snapshot_only_targets,
        missing_targets=missing_targets,
        warnings=[
            "Coverage is metadata-level and snapshot-level; it does not execute Memory Garden flows.",
            "Placeholder contracts require caller-supplied snapshots before they prove behavior.",
        ],
    )


def build_default_lab_coverage_report() -> LabCoverageReport:
    """Build the default Lab coverage report without executing any cases."""
    from memory_garden.lab.fixtures import default_lab_suites

    return build_lab_coverage_report(default_lab_suites())


__all__ = [
    "LabCoverageStatus",
    "LabMechanismCoverage",
    "LabCoverageReport",
    "build_lab_coverage_report",
    "build_default_lab_coverage_report",
]
