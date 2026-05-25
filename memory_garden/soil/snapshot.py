"""Garden Snapshot: point-in-time metadata capture."""

from __future__ import annotations

from pathlib import Path

from memory_garden.soil.manifest import load_manifest
from memory_garden.soil.models import GardenSnapshot


def create_garden_snapshot(
    garden_home: str | Path,
    *,
    include_manifest: bool = True,
    notes: str = "",
) -> GardenSnapshot:
    """Create a lightweight metadata snapshot of the garden home.

    The snapshot captures manifest fields and directory metadata.
    It does **not** copy the database file or any large payloads.

    If *include_manifest* is True (default), the current manifest is
    loaded and its key fields are included in the snapshot summary.
    """
    root = Path(garden_home).resolve()

    try:
        manifest = load_manifest(root) if include_manifest else None
    except FileNotFoundError:
        manifest = None

    return GardenSnapshot(
        garden_home=str(root),
        manifest_summary=(
            {
                "garden_name": manifest.garden_name,
                "schema_version": manifest.schema_version,
                "created_at": manifest.created_at.isoformat(),
            }
            if manifest
            else {}
        ),
        notes=notes,
    )
