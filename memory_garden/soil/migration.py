"""Garden Migration: schema version planning and dry-run execution.

This is a **skeleton** for v0.10.1.  It plans and reports migration steps
but does **not** modify SQLite tables, columns, or indexes.  Real schema
migration is deferred to a future version.
"""

from __future__ import annotations

from pathlib import Path

from memory_garden.soil.manifest import load_manifest
from memory_garden.soil.models import (
    GardenManifest,
    GardenMigrationPlan,
    GardenMigrationResult,
    GardenMigrationStatus,
    GardenMigrationStep,
)


def plan_garden_migration(
    garden_home: str | Path,
    target_schema_version: int,
) -> GardenMigrationPlan:
    """Read the current manifest and produce a migration plan.

    Returns a no-op plan when *current_schema_version* equals
    *target_schema_version*.

    Raises ``FileNotFoundError`` when ``manifest.json`` is missing.
    """
    root = Path(garden_home).resolve()
    manifest: GardenManifest = load_manifest(root)

    current = manifest.schema_version
    target = target_schema_version

    if current == target:
        return GardenMigrationPlan(
            garden_home=str(root),
            current_schema_version=current,
            target_schema_version=target,
            status=GardenMigrationStatus.noop,
            notes="Already at target schema version.",
        )

    if current > target:
        return GardenMigrationPlan(
            garden_home=str(root),
            current_schema_version=current,
            target_schema_version=target,
            status=GardenMigrationStatus.blocked,
            notes="Downgrade migrations are not supported in this skeleton.",
        )

    # Produce placeholder steps: one per version increment.
    steps: list[GardenMigrationStep] = []
    for seq, ver in enumerate(range(current + 1, target + 1), start=1):
        steps.append(
            GardenMigrationStep(
                sequence=seq,
                from_version=ver - 1,
                to_version=ver,
                description=f"Placeholder migration step: v{ver - 1} -> v{ver}",
                reversible=False,
            )
        )

    return GardenMigrationPlan(
        garden_home=str(root),
        current_schema_version=current,
        target_schema_version=target,
        steps=steps,
        status=GardenMigrationStatus.plan_ready,
        notes=f"Skeleton plan: {len(steps)} placeholder step(s). Real migration is not implemented.",
    )


def migrate_garden(
    garden_home: str | Path,
    target_schema_version: int,
    *,
    dry_run: bool = True,
) -> GardenMigrationResult:
    """Plan and (optionally) execute a migration.

    When *dry_run* is ``True`` (the default) the manifest is **never**
    modified.  When *dry_run* is ``False`` and the plan contains steps,
    this records the result and updates ``manifest.schema_version``
    to the target version.  Real database schema changes are not
    implemented yet — only the manifest version bump is performed.

    Raises ``FileNotFoundError`` when ``manifest.json`` is missing.
    """
    plan = plan_garden_migration(garden_home, target_schema_version)

    if plan.status == GardenMigrationStatus.noop:
        return GardenMigrationResult(
            garden_home=plan.garden_home,
            current_schema_version=plan.current_schema_version,
            target_schema_version=plan.target_schema_version,
            status=GardenMigrationStatus.noop,
            dry_run=dry_run,
            notes=plan.notes,
        )

    if plan.status == GardenMigrationStatus.blocked:
        return GardenMigrationResult(
            garden_home=plan.garden_home,
            current_schema_version=plan.current_schema_version,
            target_schema_version=plan.target_schema_version,
            status=GardenMigrationStatus.blocked,
            dry_run=dry_run,
            notes=plan.notes,
        )

    applied = [s.sequence for s in plan.steps]
    skipped: list[int] = []

    if not dry_run and plan.status == GardenMigrationStatus.plan_ready:
        root = Path(garden_home).resolve()
        manifest = load_manifest(root)
        from memory_garden.soil.manifest import save_manifest

        manifest.schema_version = target_schema_version
        save_manifest(root, manifest)

    return GardenMigrationResult(
        garden_home=plan.garden_home,
        current_schema_version=plan.current_schema_version,
        target_schema_version=plan.target_schema_version,
        status=GardenMigrationStatus.completed,
        steps_applied=applied,
        steps_skipped=skipped,
        dry_run=dry_run,
        notes=plan.notes,
    )
