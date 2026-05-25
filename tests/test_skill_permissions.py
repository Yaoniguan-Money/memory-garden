from memory_garden.core.models import MemoryCard
from memory_garden.sdk import MemoryGarden
from memory_garden.skill import SkillConfig, SkillErrorCode


def test_skill_forget_can_be_disabled(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill(SkillConfig(allow_hard_forget=False))

        result = skill.forget("anything")

        assert result.ok is False
        assert result.error is not None
        assert result.error.code == SkillErrorCode.PERMISSION_DENIED
    finally:
        garden.close()


def test_skill_forget_requires_matching_memory(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        result = skill.forget("missing memory")

        assert result.ok is False
        assert result.error is not None
        assert result.error.code == SkillErrorCode.NOT_FOUND
    finally:
        garden.close()


def test_skill_forget_uses_soil_hard_forget_without_provider(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        card = MemoryCard(
            title="深色模式",
            essence="用户喜欢深色模式",
            fragrance="保持界面一致",
            thorns="不要过度推断",
            tags=["preference"],
        )
        garden.core.repository.save_memory_card(card)
        skill = garden.as_skill()

        result = skill.forget("深色模式", reason="用户要求忘记")

        assert result.ok is True
        assert result.memory_ids == [card.id]
        assert result.metadata["memory_deleted"] is True
    finally:
        garden.close()
