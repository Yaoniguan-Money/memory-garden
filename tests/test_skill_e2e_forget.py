import pytest

from memory_garden.sdk import MemoryGarden
from memory_garden.storage.base import NotFoundError


def test_skill_e2e_explicit_forget_removes_harvestable_memory(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()
        remembered = skill.remember("我喜欢深色模式，以后界面相关回答请优先考虑这一点")
        assert remembered.memory_ids
        memory_id = remembered.memory_ids[0]
        assert memory_id in skill.harvest("深色模式").source_memory_ids

        forgotten = skill.forget("深色模式", reason="用户显式要求忘记深色模式偏好")

        assert forgotten.ok is True
        assert forgotten.memory_ids == [memory_id]
        assert memory_id not in skill.harvest("深色模式").source_memory_ids
        with pytest.raises(NotFoundError):
            garden.core.repository.get_memory_card(memory_id)
    finally:
        garden.close()
