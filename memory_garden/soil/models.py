"""Pydantic models for Garden Soil: home, manifest, snapshot, health."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class GardenHealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"


class GardenHealthIssue(BaseModel):
    code: str = Field(description="Machine-readable issue code, e.g. 'manifest_missing'")
    message: str = Field(description="Human-readable description")
    severity: GardenHealthStatus = Field(default=GardenHealthStatus.unhealthy)


class GardenHealthReport(BaseModel):
    garden_home: str = Field(description="Absolute path to the garden home directory")
    status: GardenHealthStatus = Field(description="Overall health status")
    issues: list[GardenHealthIssue] = Field(default_factory=list)
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the health check was performed",
    )


class GardenManifest(BaseModel):
    garden_name: str = Field(default="memory-garden", description="Human-readable garden name")
    schema_version: int = Field(default=1, description="Reserved for future schema migration")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the garden home was first initialized",
    )
    description: str = Field(default="", description="Optional garden description")


class GardenHome(BaseModel):
    root: Path = Field(description="Absolute path to the garden home root directory")
    manifest: GardenManifest = Field(default_factory=GardenManifest)

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"


# ── Migration models ──────────────────────────────────────────────


class GardenMigrationStatus(str, Enum):
    noop = "noop"
    plan_ready = "plan_ready"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"


class GardenMigrationStep(BaseModel):
    sequence: int = Field(description="Step order, 1-indexed")
    from_version: int = Field(description="Schema version this step upgrades from")
    to_version: int = Field(description="Schema version this step upgrades to")
    description: str = Field(default="", description="Human-readable step description")
    reversible: bool = Field(default=False, description="Whether this step can be undone")


class GardenMigrationPlan(BaseModel):
    garden_home: str = Field(description="Absolute path to the garden home")
    current_schema_version: int = Field(description="Current schema_version from manifest")
    target_schema_version: int = Field(description="Requested target schema_version")
    steps: list[GardenMigrationStep] = Field(default_factory=list)
    status: GardenMigrationStatus = Field(default=GardenMigrationStatus.noop)
    notes: str = Field(default="")


class GardenMigrationResult(BaseModel):
    garden_home: str = Field(description="Absolute path to the garden home")
    current_schema_version: int
    target_schema_version: int
    status: GardenMigrationStatus
    steps_applied: list[int] = Field(default_factory=list, description="Sequence numbers of applied steps")
    steps_skipped: list[int] = Field(default_factory=list, description="Sequence numbers of skipped steps")
    dry_run: bool = Field(default=True, description="True if no changes were actually applied")
    notes: str = Field(default="")


# ── Bundle models ─────────────────────────────────────────────────


class GardenBundleManifest(BaseModel):
    bundle_version: str = Field(default="1.0", description="Bundle format version")
    garden_name: str = Field(default="", description="Original garden name")
    source_garden_home: str = Field(default="", description="Path to the garden that was exported")
    schema_version: int = Field(default=1, description="Schema version at export time")
    exported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    notes: str = Field(default="")


class GardenBundleExportResult(BaseModel):
    bundle_path: str = Field(description="Absolute path to the exported bundle directory")
    manifest: GardenBundleManifest = Field(description="Bundle manifest written to the bundle")
    files_written: list[str] = Field(default_factory=list, description="Relative paths of files in the bundle")


class GardenBundleImportResult(BaseModel):
    target_garden_home: str = Field(description="Absolute path to the target garden home")
    bundle_path: str = Field(description="Absolute path to the source bundle directory")
    manifest: GardenBundleManifest | None = Field(default=None, description="Bundle manifest that was imported")
    files_imported: list[str] = Field(default_factory=list, description="Relative paths of files imported")
    status: str = Field(default="ok", description="ok, blocked, or failed")


# ── FTS5 Index / Search models ──────────────────────────────────────


class GardenIndexIssue(BaseModel):
    code: str = Field(description="Machine-readable issue code, e.g. 'fts_table_missing'")
    message: str = Field(description="Human-readable description")
    severity: GardenHealthStatus = Field(default=GardenHealthStatus.degraded)


class GardenIndexStatus(BaseModel):
    exists: bool = Field(default=False, description="Whether the FTS index table exists")
    healthy: bool = Field(default=False, description="Whether the index is usable")
    indexed_count: int = Field(default=0, description="Approximate number of indexed rows")
    target_types: list[str] = Field(default_factory=list, description="Target types present in the index")
    issues: list[GardenIndexIssue] = Field(default_factory=list)


class GardenReindexResult(BaseModel):
    status: str = Field(default="ok", description="ok, failed, or skipped")
    indexed_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    target_types: list[str] = Field(default_factory=list)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    finished_at: datetime | None = Field(default=None)
    dry_run: bool = Field(default=True)
    issues: list[GardenIndexIssue] = Field(default_factory=list)


class GardenSearchHit(BaseModel):
    target_type: str = Field(description="e.g. memory_card, seed")
    target_id: str = Field(description="ID of the matching entity")
    title: str = Field(default="", description="Short title from the entity")
    snippet: str = Field(default="", description="Relevant text snippet")
    rank: float = Field(default=0.0, description="FTS rank score, lower is better")
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Forget models ───────────────────────────────────────────────────


class ContentHashProbe(BaseModel):
    """不可逆内容片段摘要（不含明文）。"""

    label: str = Field(default="")
    hash_hex: str = Field(min_length=64, max_length=64)
    fragment_length: int = Field(default=0, ge=0)


class ContentProbeSet(BaseModel):
    """Hard forget 内容探针集；match_tokens 仅运行时用于扫描，禁止持久化。"""

    probe_fingerprint: str = Field(default="")
    token_probe_count: int = Field(default=0, ge=0)
    hash_probe_count: int = Field(default=0, ge=0)
    salt_id: str = Field(default="")
    hash_probes: list[ContentHashProbe] = Field(default_factory=list)
    match_tokens: list[str] = Field(default_factory=list, exclude=True)
    redacted_tokens: list[str] = Field(default_factory=list)


class GardenForgetPlan(BaseModel):
    memory_id: str = Field(description="MemoryCard id to be forgotten")
    mode: str = Field(default="hard", description="soft or hard")
    affected_entities: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of entity type to list of ids that will be affected",
    )
    fts_entries: int = Field(default=0, description="Number of FTS entries to remove")
    notes: str = Field(default="")
    content_probes: ContentProbeSet | None = Field(
        default=None,
        description="Pre-forget content probes for content-level proof",
    )


class GardenForgetResult(BaseModel):
    memory_id: str
    mode: str
    status: str = Field(default="ok", description="ok, partial, or failed")
    memory_deleted: bool = Field(default=False)
    fts_entries_removed: int = Field(default=0)
    seed_ids_cleaned: list[str] = Field(default_factory=list)
    case_ids_cleaned: list[str] = Field(default_factory=list)
    dry_run: bool = Field(default=False)
    issues: list[GardenIndexIssue] = Field(default_factory=list)
    content_probe_fingerprint: str = Field(default="")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ── Forget Proof models ────────────────────────────────────────────


class ForgetProofVerdict(str, Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"


class ForgetProofCheck(BaseModel):
    surface: str = Field(description="Garden surface being checked, e.g. 'fts_search', 'db_row'")
    verdict: ForgetProofVerdict = Field(default=ForgetProofVerdict.skipped)
    detail: str = Field(default="", description="Human-readable result")
    evidence: dict[str, Any] = Field(default_factory=dict)


class ForgetProof(BaseModel):
    memory_id: str = Field(description="The forgotten memory ID being verified")
    garden_home: str = Field(description="Garden home path where the proof was run")
    checks: list[ForgetProofCheck] = Field(default_factory=list)
    passed: int = Field(default=0)
    failed: int = Field(default=0)
    skipped: int = Field(default=0)
    proven: bool = Field(default=False, description="True when all checks pass (skipped is not failed)")
    content_probe_fingerprint: str = Field(default="")
    proof_level: Literal["id_only", "content"] = Field(default="id_only")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ── Snapshot model (existing) ──────────────────────────────────────


class GardenSnapshot(BaseModel):
    garden_home: str = Field(description="Absolute path to the garden home directory at snapshot time")
    manifest_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Key manifest fields captured at snapshot time",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the snapshot was created",
    )
    schema_version: int = Field(default=1)
    notes: str = Field(default="")

    @classmethod
    def from_home(cls, home: GardenHome, *, notes: str = "") -> GardenSnapshot:
        return cls(
            garden_home=str(home.root),
            manifest_summary={
                "garden_name": home.manifest.garden_name,
                "schema_version": home.manifest.schema_version,
                "created_at": home.manifest.created_at.isoformat(),
            },
            schema_version=home.manifest.schema_version,
            notes=notes,
        )
