from memory_garden.sdk import MemoryGarden
from memory_garden.skill import (
    SkillAuditView,
    SkillErrorCode,
    SkillHarvestResult,
    SkillOperationResult,
    SkillWriteMode,
)


def test_skill_stable_session_contract(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        opened = skill.open_session()
        assert isinstance(opened, SkillOperationResult)
        assert opened.ok is True
        assert opened.session_id

        closed = skill.close_session()
        assert isinstance(closed, SkillOperationResult)
        assert closed.ok is True
    finally:
        garden.close()


def test_skill_remember_preview_contract(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        result = skill.remember("我喜欢深色模式", mode=SkillWriteMode.PREVIEW)

        assert result.ok is True
        assert result.operation == "remember"
        assert result.preview is True
        assert "write_mode_preview" in result.skipped_reasons
        assert result.error is None
    finally:
        garden.close()


def test_skill_harvest_contract_returns_stable_model(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        result = skill.harvest("深色模式")

        assert isinstance(result, SkillHarvestResult)
        assert result.ok is True
        assert result.mode == "rules_only"
        assert result.brief is not None
    finally:
        garden.close()


def test_skill_error_contract_for_invalid_input(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()

        result = skill.remember("")

        assert result.ok is False
        assert result.error is not None
        assert result.error.code == SkillErrorCode.INVALID_INPUT
    finally:
        garden.close()


def test_skill_audit_contract(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()
        skill.remember("我喜欢深色模式", mode=SkillWriteMode.PREVIEW)

        audit = skill.audit()

        assert isinstance(audit, SkillAuditView)
        assert audit.event_count >= 1
        assert "provider_mode" in audit.config
    finally:
        garden.close()
