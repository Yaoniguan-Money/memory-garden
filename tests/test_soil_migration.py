"""Tests for Garden Soil migration planning and execution."""


from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.manifest import load_manifest
from memory_garden.soil.migration import migrate_garden, plan_garden_migration
from memory_garden.soil.models import GardenMigrationStatus


# ── Plan tests ─────────────────────────────────────────────────────


def test_plan_noop_when_versions_equal(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    plan = plan_garden_migration(home.root, target_schema_version=1)
    assert plan.status == GardenMigrationStatus.noop
    assert plan.steps == []
    assert plan.current_schema_version == 1
    assert plan.target_schema_version == 1


def test_plan_generates_steps_when_upgrading(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    plan = plan_garden_migration(home.root, target_schema_version=3)
    assert plan.status == GardenMigrationStatus.plan_ready
    assert len(plan.steps) == 2
    assert plan.steps[0].sequence == 1
    assert plan.steps[0].from_version == 1
    assert plan.steps[0].to_version == 2
    assert plan.steps[1].sequence == 2
    assert plan.steps[1].from_version == 2
    assert plan.steps[1].to_version == 3


def test_plan_blocked_on_downgrade(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    plan = plan_garden_migration(home.root, target_schema_version=0)
    assert plan.status == GardenMigrationStatus.blocked
    assert plan.steps == []
    assert "Downgrade" in plan.notes


def test_plan_raises_on_missing_manifest(tmp_path):
    import pytest

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        plan_garden_migration(empty, target_schema_version=2)


def test_plan_does_not_modify_manifest(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    mtime_before = (home.root / "manifest.json").stat().st_mtime
    plan_garden_migration(home.root, target_schema_version=5)
    mtime_after = (home.root / "manifest.json").stat().st_mtime
    assert mtime_before == mtime_after


# ── Migrate tests ──────────────────────────────────────────────────


def test_migrate_noop_when_versions_equal(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    result = migrate_garden(home.root, target_schema_version=1, dry_run=True)
    assert result.status == GardenMigrationStatus.noop
    assert result.dry_run is True


def test_migrate_dry_run_does_not_change_manifest(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    assert load_manifest(home.root).schema_version == 1
    result = migrate_garden(home.root, target_schema_version=3, dry_run=True)
    assert result.status == GardenMigrationStatus.completed
    assert result.dry_run is True
    # Manifest must still be at version 1
    assert load_manifest(home.root).schema_version == 1


def test_migrate_non_dry_run_updates_manifest_version(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    result = migrate_garden(home.root, target_schema_version=3, dry_run=False)
    assert result.status == GardenMigrationStatus.completed
    assert result.dry_run is False
    assert result.steps_applied == [1, 2]
    assert load_manifest(home.root).schema_version == 3


def test_migrate_raises_on_missing_manifest(tmp_path):
    import pytest

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        migrate_garden(empty, target_schema_version=2)


def test_migrate_blocked_on_downgrade(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    result = migrate_garden(home.root, target_schema_version=0)
    assert result.status == GardenMigrationStatus.blocked


def test_migration_models_json_roundtrip():
    from memory_garden.soil.models import (
        GardenMigrationPlan,
        GardenMigrationResult,
        GardenMigrationStatus,
        GardenMigrationStep,
    )

    step = GardenMigrationStep(sequence=1, from_version=1, to_version=2, description="test")
    data = step.model_dump(mode="json")
    step2 = GardenMigrationStep(**data)
    assert step2.sequence == 1
    assert step2.from_version == 1

    plan = GardenMigrationPlan(
        garden_home="/tmp/x",
        current_schema_version=1,
        target_schema_version=2,
        steps=[step],
        status=GardenMigrationStatus.plan_ready,
    )
    data2 = plan.model_dump(mode="json")
    plan2 = GardenMigrationPlan(**data2)
    assert plan2.status == GardenMigrationStatus.plan_ready
    assert len(plan2.steps) == 1

    result = GardenMigrationResult(
        garden_home="/tmp/x",
        current_schema_version=1,
        target_schema_version=2,
        status=GardenMigrationStatus.completed,
        steps_applied=[1],
    )
    data3 = result.model_dump(mode="json")
    result2 = GardenMigrationResult(**data3)
    assert result2.status == GardenMigrationStatus.completed
