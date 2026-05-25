"""JSON export renderer for Observatory views.

Produces stable, sorted-key JSON output suitable for file export,
CI artifact storage, and downstream tool consumption.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from memory_garden.observatory.views import (
    GardenMapData,
    GardenSummaryView,
    MemoryCardView,
    SeedJourneyView,
)


def export_garden_summary_json(view: GardenSummaryView) -> str:
    """Export a GardenSummaryView as a stable JSON string."""
    payload = view.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def export_memory_card_json(card: MemoryCardView) -> str:
    """Export a single MemoryCardView as a stable JSON string."""
    payload = card.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def export_seed_journey_json(seed: SeedJourneyView) -> str:
    """Export a single SeedJourneyView as a stable JSON string."""
    payload = seed.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def export_map_json(garden_map: GardenMapData) -> str:
    """Export a GardenMapData as a stable JSON string."""
    payload = garden_map.model_dump(mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def build_export_payload(view: GardenSummaryView) -> dict[str, Any]:
    """Build a dict suitable for writing to an ``observatory_export.json`` file."""
    return {
        "export_format": "memory-garden-observatory/v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "garden_map": view.map.model_dump(mode="json"),
        "recent_memories": [m.model_dump(mode="json") for m in view.recent_memories],
        "recent_seeds": [s.model_dump(mode="json") for s in view.recent_seeds],
        "recent_cases": [c.model_dump(mode="json") for c in view.recent_cases],
        "recent_dreams": [d.model_dump(mode="json") for d in view.recent_dreams],
    }
