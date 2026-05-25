from memory_garden.sdk import MemoryGarden


def test_skill_e2e_long_term_preference_memory(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        remembered = skill.remember("我喜欢深色模式，以后界面相关回答请优先考虑这一点")
        harvested = skill.harvest("深色模式")

        assert remembered.ok is True
        assert remembered.verdicts == ["plant"]
        assert len(remembered.memory_ids) == 1
        assert harvested.ok is True
        assert harvested.brief is not None
        assert remembered.memory_ids[0] in harvested.source_memory_ids
        assert remembered.memory_ids[0] in harvested.brief.source_memory_ids
    finally:
        garden.close()
