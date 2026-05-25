"""Default Garden Covenant."""

from __future__ import annotations

from memory_garden.covenant.models import GardenCovenant


def default_garden_covenant() -> GardenCovenant:
    """Return a fresh default covenant instance."""
    return GardenCovenant(metadata={"source": "default", "layer": "garden_covenant"})


def default_garden_covenant_dict() -> dict:
    """Return the default covenant as a JSON-safe dictionary."""
    return default_garden_covenant().model_dump(mode="json")


__all__ = ["default_garden_covenant", "default_garden_covenant_dict"]
