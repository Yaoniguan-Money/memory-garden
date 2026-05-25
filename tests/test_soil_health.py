"""Tests for garden health checks."""

import os

from memory_garden.soil.health import check_garden_health
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.models import GardenHealthStatus


def test_health_check_healthy(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    report = check_garden_health(home.root)
    assert report.status == GardenHealthStatus.healthy
    assert report.issues == []
    assert report.garden_home == str(home.root)


def test_health_check_directory_missing(tmp_path):
    missing = tmp_path / "nonexistent"
    report = check_garden_health(missing)
    assert report.status == GardenHealthStatus.unhealthy
    assert any(i.code == "directory_missing" for i in report.issues)


def test_health_check_not_a_directory(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("not a dir", encoding="utf-8")
    report = check_garden_health(f)
    assert report.status == GardenHealthStatus.unhealthy
    assert any(i.code == "not_a_directory" for i in report.issues)


def test_health_check_manifest_missing(tmp_path):
    empty = tmp_path / "empty_garden"
    empty.mkdir()
    report = check_garden_health(empty)
    assert report.status == GardenHealthStatus.degraded
    assert any(i.code == "manifest_missing" for i in report.issues)


def test_health_check_manifest_not_file(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    manifest_dir = home / "manifest.json"
    manifest_dir.mkdir()
    report = check_garden_health(home)
    assert report.status == GardenHealthStatus.unhealthy
    assert any(i.code == "manifest_not_file" for i in report.issues)


def test_health_check_manifest_invalid_json(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    (home / "manifest.json").write_text("not valid json {{{", encoding="utf-8")
    report = check_garden_health(home)
    assert report.status == GardenHealthStatus.unhealthy
    assert any(i.code == "manifest_invalid_json" for i in report.issues)


def test_health_check_manifest_not_object(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    (home / "manifest.json").write_text("[1, 2, 3]", encoding="utf-8")
    report = check_garden_health(home)
    assert report.status == GardenHealthStatus.unhealthy
    assert any(i.code == "manifest_not_object" for i in report.issues)


def test_health_check_manifest_missing_fields(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    (home / "manifest.json").write_text('{"unknown": true}', encoding="utf-8")
    report = check_garden_health(home)
    assert report.status == GardenHealthStatus.degraded
    assert any(i.code == "manifest_missing_garden_name" for i in report.issues)
    assert any(i.code == "manifest_missing_schema_version" for i in report.issues)


def test_health_report_has_checked_at(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    report = check_garden_health(home.root)
    assert report.checked_at is not None


def test_health_check_does_not_create_files(tmp_path):
    """Health check must not create or modify files."""
    home = initialize_garden_home(tmp_path / "garden")
    mtime_before = os.path.getmtime(home.root / "manifest.json")
    check_garden_health(home.root)
    mtime_after = os.path.getmtime(home.root / "manifest.json")
    assert mtime_before == mtime_after
