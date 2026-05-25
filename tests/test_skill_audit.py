from memory_garden.core.models import MemoryCard
from memory_garden.sdk import MemoryGarden
from memory_garden.skill import SkillConfig, SkillProviderMode


def test_skill_audit_includes_events_memory_count_and_config(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        card = MemoryCard(
            title="审计记忆",
            essence="用于测试 Skill audit",
            fragrance="可追溯",
            thorns="无",
        )
        garden.core.repository.save_memory_card(card)
        skill = garden.as_skill(SkillConfig(provider_mode=SkillProviderMode.DISABLED))
        skill.open_session()

        audit = skill.audit(limit=10)

        assert audit.memory_count == 1
        assert audit.event_count >= 0
        assert audit.config["provider_mode"] == "disabled"
    finally:
        garden.close()


def test_skill_audit_events_are_serializable(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()
        skill.remember("我喜欢深色模式")

        dumped = skill.audit().model_dump(mode="json")

        assert isinstance(dumped["events"], list)
        assert isinstance(dumped["config"], dict)
    finally:
        garden.close()
