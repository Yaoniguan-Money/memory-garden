from pathlib import Path

from memory_garden.sdk import MemoryGarden
from memory_garden.skill import (
    SkillConfig,
    SkillProviderMode,
    SkillRedactionLevel,
    SkillWriteMode,
)


def test_skill_config_defaults_are_local_first() -> None:
    cfg = SkillConfig(
        provider_mode=SkillProviderMode.DISABLED,
        enable_cognitive_harvest=False,
    )

    assert cfg.provider_mode == SkillProviderMode.DISABLED
    assert cfg.default_write_mode == SkillWriteMode.COURT
    assert cfg.redaction_level == SkillRedactionLevel.BASIC
    assert cfg.enable_cognitive_harvest is False
    assert cfg.enable_court_shadow is False
    assert cfg.enable_dream is False


def test_skill_config_coerces_garden_home() -> None:
    cfg = SkillConfig(garden_home="garden-home")

    assert isinstance(cfg.garden_home, Path)


def test_as_skill_accepts_config(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill(SkillConfig(default_write_mode=SkillWriteMode.PREVIEW))

        assert skill.config.default_write_mode == SkillWriteMode.PREVIEW
        assert skill.config.garden_home == garden.home.root
    finally:
        garden.close()
