"""Tests for Garden Soil Pydantic models."""

from memory_garden.soil.models import (
    GardenHealthIssue,
    GardenHealthReport,
    GardenHealthStatus,
    GardenHome,
    GardenManifest,
    GardenSnapshot,
)


def test_garden_manifest_defaults():
    m = GardenManifest()
    assert m.garden_name == "memory-garden"
    assert m.schema_version == 1
    assert m.description == ""


def test_garden_manifest_custom():
    m = GardenManifest(garden_name="test-garden", schema_version=3, description="a test")
    assert m.garden_name == "test-garden"
    assert m.schema_version == 3
    assert m.description == "a test"


def test_garden_manifest_json_roundtrip():
    m = GardenManifest(garden_name="demo")
    data = m.model_dump(mode="json")
    m2 = GardenManifest(**data)
    assert m2.garden_name == m.garden_name
    assert m2.schema_version == m.schema_version


def test_garden_home_manifest_path(tmp_path):
    m = GardenManifest(garden_name="home-test")
    home = GardenHome(root=tmp_path, manifest=m)
    assert home.manifest_path == tmp_path / "manifest.json"


def test_garden_health_issue():
    issue = GardenHealthIssue(code="TEST", message="test message", severity=GardenHealthStatus.degraded)
    assert issue.code == "TEST"
    assert issue.message == "test message"
    assert issue.severity == GardenHealthStatus.degraded


def test_garden_health_report_default():
    report = GardenHealthReport(garden_home="/tmp/test", status=GardenHealthStatus.healthy)
    assert report.status == GardenHealthStatus.healthy
    assert report.issues == []
    assert report.garden_home == "/tmp/test"


def test_garden_health_report_with_issues():
    issues = [GardenHealthIssue(code="E1", message="bad", severity=GardenHealthStatus.unhealthy)]
    report = GardenHealthReport(garden_home="/x", status=GardenHealthStatus.unhealthy, issues=issues)
    assert report.status == GardenHealthStatus.unhealthy
    assert len(report.issues) == 1


def test_garden_snapshot_from_home(tmp_path):
    home = GardenHome(root=tmp_path, manifest=GardenManifest(garden_name="snap-test"))
    snap = GardenSnapshot.from_home(home, notes="test note")
    assert snap.garden_home == str(tmp_path)
    assert snap.manifest_summary["garden_name"] == "snap-test"
    assert snap.manifest_summary["schema_version"] == 1
    assert "created_at" in snap.manifest_summary
    assert snap.notes == "test note"


def test_garden_snapshot_json_roundtrip():
    snap = GardenSnapshot(garden_home="/tmp/x", manifest_summary={"garden_name": "g"}, notes="n")
    data = snap.model_dump(mode="json")
    snap2 = GardenSnapshot(**data)
    assert snap2.garden_home == "/tmp/x"
    assert snap2.manifest_summary == {"garden_name": "g"}
    assert snap2.notes == "n"


def test_garden_health_status_enum():
    assert GardenHealthStatus.healthy.value == "healthy"
    assert GardenHealthStatus.degraded.value == "degraded"
    assert GardenHealthStatus.unhealthy.value == "unhealthy"
