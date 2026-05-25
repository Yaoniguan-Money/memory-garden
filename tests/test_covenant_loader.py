"""Stage 8E: Covenant loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_garden.covenant import (
    CovenantLoaderError,
    CovenantValidationError,
    GardenCovenant,
    load_covenant_from_dict,
    load_covenant_from_memory_garden_yaml,
    load_covenant_from_yaml_file,
    load_covenant_from_yaml_text,
)


def test_load_empty_dict_uses_defaults() -> None:
    covenant = load_covenant_from_dict({})
    assert isinstance(covenant, GardenCovenant)
    assert covenant.consent.default_state == "closed"


def test_load_nested_garden_covenant_dict() -> None:
    covenant = load_covenant_from_dict(
        {"garden_covenant": {"harvest": {"brief_token_budget": 300}}}
    )
    assert covenant.harvest.brief_token_budget == 300


def test_load_plain_dict_without_root_key() -> None:
    covenant = load_covenant_from_dict({"visibility": {"feedback_mode": "debug_only"}})
    assert covenant.visibility.feedback_mode == "debug_only"


def test_explicit_overrides_win_over_config() -> None:
    covenant = load_covenant_from_dict(
        {"harvest": {"brief_token_budget": 300}},
        explicit_overrides={"harvest": {"brief_token_budget": 200}},
    )
    assert covenant.harvest.brief_token_budget == 200


def test_env_overrides_win_over_explicit() -> None:
    covenant = load_covenant_from_dict(
        {"harvest": {"brief_token_budget": 300}},
        explicit_overrides={"harvest": {"brief_token_budget": 200}},
        env={"MEMORY_GARDEN_BRIEF_TOKEN_BUDGET": "100"},
    )
    assert covenant.harvest.brief_token_budget == 100


def test_yaml_text_loader() -> None:
    text = """
garden_covenant:
  harvest:
    brief_token_budget: 250
  visibility:
    feedback_mode: debug_only
"""
    covenant = load_covenant_from_yaml_text(text)
    assert covenant.harvest.brief_token_budget == 250
    assert covenant.visibility.feedback_mode == "debug_only"


def test_yaml_file_loader(tmp_path: Path) -> None:
    path = tmp_path / "memory_garden.yaml"
    path.write_text(
        """
garden_covenant:
  harvest:
    max_selected_memories: 4
  model_calls:
    max_memories_per_model_call: 4
""",
        encoding="utf-8",
    )
    covenant = load_covenant_from_yaml_file(path)
    assert covenant.harvest.max_selected_memories == 4


def test_memory_garden_yaml_missing_uses_defaults(tmp_path: Path) -> None:
    covenant = load_covenant_from_memory_garden_yaml(tmp_path / "missing.yaml", include_env=False)
    assert covenant.version == 1
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


def test_memory_garden_yaml_present_loads(tmp_path: Path) -> None:
    path = tmp_path / "memory_garden.yaml"
    path.write_text("garden_covenant:\n  model_calls:\n    allow_external_llm: false\n", encoding="utf-8")
    covenant = load_covenant_from_memory_garden_yaml(path, include_env=False)
    assert covenant.model_calls.allow_external_llm is False


def test_unknown_field_fails() -> None:
    with pytest.raises(CovenantLoaderError, match="Invalid covenant schema"):
        load_covenant_from_dict({"garden_covenant": {"unknown": True}})


def test_invalid_yaml_fails() -> None:
    with pytest.raises(CovenantLoaderError, match="Invalid covenant YAML"):
        load_covenant_from_yaml_text("garden_covenant: [")


def test_dangerous_yaml_fails_validation() -> None:
    text = """
garden_covenant:
  portability:
    export_api_keys: true
"""
    with pytest.raises(CovenantValidationError) as exc:
        load_covenant_from_yaml_text(text)
    assert exc.value.field_path == "portability.export_api_keys"


def test_env_boolean_override() -> None:
    covenant = load_covenant_from_dict({}, env={"MEMORY_GARDEN_ALLOW_EXTERNAL_LLM": "false"})
    assert covenant.model_calls.allow_external_llm is False


def test_invalid_env_boolean_fails() -> None:
    with pytest.raises(CovenantLoaderError, match="Invalid boolean"):
        load_covenant_from_dict({}, env={"MEMORY_GARDEN_ALLOW_EXTERNAL_LLM": "maybe"})


def test_loader_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    load_covenant_from_dict({})
    load_covenant_from_yaml_text("")
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


def test_default_yaml_example_loads() -> None:
    covenant = load_covenant_from_yaml_file(Path("examples/garden_covenant_default.yaml"))
    assert covenant.version == 1
    assert covenant.hard_baselines.commands_never_memorized is True
