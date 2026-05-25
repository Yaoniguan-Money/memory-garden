"""Garden Health Check: structural integrity report."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from memory_garden.soil.models import (
    GardenHealthIssue,
    GardenHealthReport,
    GardenHealthStatus,
)


def check_garden_health(garden_home: str | Path) -> GardenHealthReport:
    """Inspect a garden home directory and return a health report.

    Checks performed:
    - Directory exists and is a directory
    - ``manifest.json`` exists
    - ``manifest.json`` is valid JSON and parseable
    - Manifest contains a ``garden_name`` and ``schema_version`` field
    """
    root = Path(garden_home).resolve()
    issues: list[GardenHealthIssue] = []

    if not root.exists():
        issues.append(
            GardenHealthIssue(
                code="directory_missing",
                message=f"Garden home directory does not exist: {root}",
                severity=GardenHealthStatus.unhealthy,
            )
        )
        return _build_report(root, issues)

    if not root.is_dir():
        issues.append(
            GardenHealthIssue(
                code="not_a_directory",
                message=f"Path exists but is not a directory: {root}",
                severity=GardenHealthStatus.unhealthy,
            )
        )
        return _build_report(root, issues)

    manifest_path = root / "manifest.json"

    if not manifest_path.exists():
        issues.append(
            GardenHealthIssue(
                code="manifest_missing",
                message=f"manifest.json not found in {root}",
                severity=GardenHealthStatus.degraded,
            )
        )
        return _build_report(root, issues)

    if not manifest_path.is_file():
        issues.append(
            GardenHealthIssue(
                code="manifest_not_file",
                message=f"manifest.json exists but is not a regular file: {manifest_path}",
                severity=GardenHealthStatus.unhealthy,
            )
        )
        return _build_report(root, issues)

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(
            GardenHealthIssue(
                code="manifest_invalid_json",
                message=f"manifest.json is not valid JSON: {exc}",
                severity=GardenHealthStatus.unhealthy,
            )
        )
        return _build_report(root, issues)

    if not isinstance(data, dict):
        issues.append(
            GardenHealthIssue(
                code="manifest_not_object",
                message="manifest.json root is not a JSON object",
                severity=GardenHealthStatus.unhealthy,
            )
        )
        return _build_report(root, issues)

    if "garden_name" not in data:
        issues.append(
            GardenHealthIssue(
                code="manifest_missing_garden_name",
                message="manifest.json is missing the 'garden_name' field",
                severity=GardenHealthStatus.degraded,
            )
        )

    if "schema_version" not in data:
        issues.append(
            GardenHealthIssue(
                code="manifest_missing_schema_version",
                message="manifest.json is missing the 'schema_version' field",
                severity=GardenHealthStatus.degraded,
            )
        )

    _check_index_health(root, issues)

    return _build_report(root, issues)


def _check_index_health(root: Path, issues: list[GardenHealthIssue]) -> None:
    """Append FTS index issues to *issues* without modifying the index.

    Also detects stale FTS entries that reference deleted MemoryCards
    (incomplete hard forget cleanup).
    """
    from memory_garden.soil.index import DB_FILENAME, FTS_TABLE, _open_db, check_garden_index

    db_path = root / DB_FILENAME
    if not db_path.is_file():
        return

    index_status = check_garden_index(str(root))
    for issue in index_status.issues:
        issues.append(GardenHealthIssue(
            code=issue.code,
            message=issue.message,
            severity=issue.severity,
        ))

    # Check for stale FTS entries (orphaned references to deleted rows)
    if index_status.exists and index_status.healthy:
        conn = _open_db(str(root))
        try:
            stale = conn.execute(
                f"""
                SELECT f.target_id FROM {FTS_TABLE} f
                WHERE f.target_type = 'memory_card'
                AND f.target_id NOT IN (SELECT id FROM memory_cards)
                """
            ).fetchall()
            if stale:
                stale_ids = [r["target_id"] for r in stale]
                issues.append(GardenHealthIssue(
                    code="fts_stale_entries",
                    message=f"FTS index has {len(stale_ids)} stale entries for deleted MemoryCards: {', '.join(stale_ids[:5])}",
                    severity=GardenHealthStatus.degraded,
                ))
        except Exception as exc:
            logger.debug("FTS stale entry check failed (non-critical): %s", exc)
        finally:
            conn.close()


def _build_report(root: Path, issues: list[GardenHealthIssue]) -> GardenHealthReport:
    if not issues:
        status = GardenHealthStatus.healthy
    elif any(i.severity == GardenHealthStatus.unhealthy for i in issues):
        status = GardenHealthStatus.unhealthy
    else:
        status = GardenHealthStatus.degraded
    return GardenHealthReport(garden_home=str(root), status=status, issues=issues)
