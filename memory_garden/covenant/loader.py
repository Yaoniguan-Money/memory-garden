"""Garden Covenant loaders.

Loaders are explicit: importing this module never reads or writes files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from memory_garden.covenant.defaults import default_garden_covenant_dict
from memory_garden.covenant.errors import CovenantLoaderError, CovenantValidationError
from memory_garden.covenant.models import GardenCovenant
from memory_garden.covenant.validator import validate_covenant


_ROOT_KEY = "garden_covenant"


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _bool_from_env(value: str) -> bool:
    key = value.strip().casefold()
    if key in {"1", "true", "yes", "on"}:
        return True
    if key in {"0", "false", "no", "off"}:
        return False
    raise CovenantLoaderError(f"Invalid boolean env value: {value!r}")


def _env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}

    def set_path(path: tuple[str, ...], value: Any) -> None:
        cur = overrides
        for part in path[:-1]:
            cur = cur.setdefault(part, {})
        cur[path[-1]] = value

    if "MEMORY_GARDEN_FEEDBACK_MODE" in env:
        set_path(("visibility", "feedback_mode"), env["MEMORY_GARDEN_FEEDBACK_MODE"])
    if "MEMORY_GARDEN_ALLOW_EXTERNAL_LLM" in env:
        set_path(("model_calls", "allow_external_llm"), _bool_from_env(env["MEMORY_GARDEN_ALLOW_EXTERNAL_LLM"]))
    if "MEMORY_GARDEN_BRIEF_TOKEN_BUDGET" in env:
        set_path(("harvest", "brief_token_budget"), int(env["MEMORY_GARDEN_BRIEF_TOKEN_BUDGET"]))
    if "MEMORY_GARDEN_MAX_SELECTED_MEMORIES" in env:
        set_path(("harvest", "max_selected_memories"), int(env["MEMORY_GARDEN_MAX_SELECTED_MEMORIES"]))

    return overrides


def _extract_root(data: Mapping[str, Any]) -> Mapping[str, Any]:
    root = data.get(_ROOT_KEY, data)
    if not isinstance(root, Mapping):
        raise CovenantLoaderError("garden_covenant must be an object.")
    return root


def load_covenant_from_dict(
    data: Mapping[str, Any] | None = None,
    *,
    explicit_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> GardenCovenant:
    """Load a covenant from dictionaries and optional env overrides."""
    try:
        merged = default_garden_covenant_dict()
        if data:
            merged = _deep_merge(merged, _extract_root(data))
        if explicit_overrides:
            merged = _deep_merge(merged, _extract_root(explicit_overrides))
        if env:
            merged = _deep_merge(merged, _env_overrides(env))
        covenant = GardenCovenant.model_validate(merged)
        return validate_covenant(covenant)
    except CovenantValidationError:
        raise
    except ValidationError as exc:
        raise CovenantLoaderError(f"Invalid covenant schema: {exc}") from exc
    except CovenantLoaderError:
        raise
    except Exception as exc:
        raise CovenantLoaderError(f"Could not load covenant: {exc}") from exc


def load_covenant_from_yaml_text(
    text: str,
    *,
    explicit_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> GardenCovenant:
    """Load a covenant from YAML text."""
    try:
        raw = yaml.safe_load(text) if text.strip() else {}
    except yaml.YAMLError as exc:
        raise CovenantLoaderError(f"Invalid covenant YAML: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise CovenantLoaderError("Covenant YAML must contain an object.")
    return load_covenant_from_dict(raw, explicit_overrides=explicit_overrides, env=env)


def load_covenant_from_yaml_file(
    path: str | Path,
    *,
    explicit_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> GardenCovenant:
    """Load a covenant from an explicit YAML file path."""
    text = Path(path).read_text(encoding="utf-8")
    return load_covenant_from_yaml_text(text, explicit_overrides=explicit_overrides, env=env)


def load_covenant_from_memory_garden_yaml(
    path: str | Path = "memory_garden.yaml",
    *,
    explicit_overrides: Mapping[str, Any] | None = None,
    include_env: bool = True,
) -> GardenCovenant:
    """Load a covenant from a local memory_garden.yaml file if present."""
    p = Path(path)
    env = os.environ if include_env else None
    if not p.exists():
        return load_covenant_from_dict({}, explicit_overrides=explicit_overrides, env=env)
    return load_covenant_from_yaml_file(p, explicit_overrides=explicit_overrides, env=env)


__all__ = [
    "load_covenant_from_dict",
    "load_covenant_from_memory_garden_yaml",
    "load_covenant_from_yaml_file",
    "load_covenant_from_yaml_text",
]
