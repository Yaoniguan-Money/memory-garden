"""Tests for Garden Soil bundle export and import."""

import pytest

from memory_garden.soil.bundle import export_garden_bundle, import_garden_bundle
from memory_garden.soil.home import initialize_garden_home


# ── Export tests ───────────────────────────────────────────────────


def test_export_creates_expected_files(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    bundle_dir = tmp_path / "bundle"

    result = export_garden_bundle(home.root, bundle_dir, notes="test export")

    assert bundle_dir.is_dir()
    assert (bundle_dir / "bundle_manifest.json").is_file()
    assert (bundle_dir / "garden_manifest.json").is_file()
    assert (bundle_dir / "snapshot.json").is_file()
    assert set(result.files_written) == {
        "bundle_manifest.json",
        "garden_manifest.json",
        "snapshot.json",
    }
    assert result.manifest.garden_name == "memory-garden"
    assert result.manifest.notes == "test export"


def test_export_does_not_modify_source_manifest(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    mtime_before = (home.root / "manifest.json").stat().st_mtime

    export_garden_bundle(home.root, tmp_path / "bundle")

    mtime_after = (home.root / "manifest.json").stat().st_mtime
    assert mtime_before == mtime_after


def test_export_bundle_manifest_stable_json(tmp_path):
    """Bundle manifest content is stable except for the ``exported_at`` timestamp."""
    home = initialize_garden_home(tmp_path / "garden")

    result = export_garden_bundle(home.root, tmp_path / "bundle")

    import json
    raw = (tmp_path / "bundle" / "bundle_manifest.json").read_text(encoding="utf-8")
    data = json.loads(raw)

    # All keys present
    assert "bundle_version" in data
    assert "garden_name" in data
    assert "source_garden_home" in data
    assert "schema_version" in data
    assert "exported_at" in data
    assert "notes" in data

    # Non-timestamp fields are deterministic
    assert data["bundle_version"] == result.manifest.bundle_version
    assert data["garden_name"] == result.manifest.garden_name
    assert data["schema_version"] == result.manifest.schema_version
    assert data["notes"] == result.manifest.notes


def test_export_snapshot_is_included(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    import json
    snap = json.loads((bundle_dir / "snapshot.json").read_text(encoding="utf-8"))
    assert "manifest_summary" in snap
    assert snap["manifest_summary"]["garden_name"] == "memory-garden"


# ── Import tests ───────────────────────────────────────────────────


def test_import_to_empty_dir_succeeds(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    target = tmp_path / "target"
    result = import_garden_bundle(bundle_dir, target)

    assert result.status == "ok"
    assert target.is_dir()
    assert (target / "bundle_manifest.json").is_file()
    assert (target / "garden_manifest.json").is_file()
    assert (target / "snapshot.json").is_file()
    assert "bundle_manifest.json" in result.files_imported


def test_import_to_dir_with_existing_manifest_is_blocked(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    # Create a target that already has a manifest.json
    existing = initialize_garden_home(tmp_path / "target")
    result = import_garden_bundle(bundle_dir, existing.root)

    assert result.status == "blocked"


def test_import_to_non_empty_dir_is_blocked(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    target = tmp_path / "target"
    target.mkdir()
    (target / "some_file.txt").write_text("hello", encoding="utf-8")

    result = import_garden_bundle(bundle_dir, target)
    assert result.status == "blocked"


def test_import_missing_bundle_manifest_fails(tmp_path):
    empty = tmp_path / "empty_bundle"
    empty.mkdir()

    target = tmp_path / "target"
    result = import_garden_bundle(empty, target)
    assert result.status == "failed"


def test_import_invalid_bundle_manifest_fails(tmp_path):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "bundle_manifest.json").write_text("{not-json", encoding="utf-8")

    result = import_garden_bundle(bundle_dir, tmp_path / "target")

    assert result.status == "failed"


def test_import_rejects_symlinked_bundle_manifest(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    outside = tmp_path / "outside.json"
    outside.write_text((bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8"), encoding="utf-8")
    (bundle_dir / "bundle_manifest.json").unlink()
    try:
        (bundle_dir / "bundle_manifest.json").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available on this platform")

    result = import_garden_bundle(bundle_dir, tmp_path / "target")

    assert result.status == "failed"


def test_import_rejects_symlinked_optional_bundle_file_without_partial_target(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    outside = tmp_path / "outside_snapshot.json"
    outside.write_text((bundle_dir / "snapshot.json").read_text(encoding="utf-8"), encoding="utf-8")
    (bundle_dir / "snapshot.json").unlink()
    try:
        (bundle_dir / "snapshot.json").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available on this platform")

    target = tmp_path / "target"
    result = import_garden_bundle(bundle_dir, target)

    assert result.status == "failed"
    assert not target.exists()


def test_import_nonexistent_bundle_dir_fails(tmp_path):
    target = tmp_path / "target"
    result = import_garden_bundle(tmp_path / "does_not_exist", target)
    assert result.status == "failed"


def test_import_preserves_garden_name(tmp_path):
    home = initialize_garden_home(tmp_path / "src")
    bundle_dir = tmp_path / "bundle"
    export_garden_bundle(home.root, bundle_dir)

    target = tmp_path / "target"
    result = import_garden_bundle(bundle_dir, target)

    assert result.manifest is not None
    assert result.manifest.garden_name == "memory-garden"


def test_bundle_models_json_roundtrip():
    from memory_garden.soil.models import (
        GardenBundleExportResult,
        GardenBundleImportResult,
        GardenBundleManifest,
    )

    bm = GardenBundleManifest(garden_name="test", source_garden_home="/tmp/x", notes="n")
    data = bm.model_dump(mode="json")
    bm2 = GardenBundleManifest(**data)
    assert bm2.garden_name == "test"
    assert bm2.notes == "n"

    export_result = GardenBundleExportResult(
        bundle_path="/tmp/b",
        manifest=bm,
        files_written=["a.json", "b.json"],
    )
    data2 = export_result.model_dump(mode="json")
    er2 = GardenBundleExportResult(**data2)
    assert er2.files_written == ["a.json", "b.json"]

    import_result = GardenBundleImportResult(
        target_garden_home="/tmp/t",
        bundle_path="/tmp/b",
        manifest=bm,
        files_imported=["c.json"],
        status="ok",
    )
    data3 = import_result.model_dump(mode="json")
    ir2 = GardenBundleImportResult(**data3)
    assert ir2.status == "ok"
