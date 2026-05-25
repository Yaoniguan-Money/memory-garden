"""堆肥动作：仅支持种子级堆肥（Stage 5A-1），不做记忆卡堆肥。"""

from __future__ import annotations

from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    GardenEventType,
    GardenObjectType,
    Seed,
    SeedStatus,
)
from memory_garden.core.policies import FORGET_OR_PURGE_PHRASES
from memory_garden.storage.base import GardenRepository

# 与法庭引擎保持一致的扩展遗忘片段（避免堆肥替代硬遗忘）
_EXTRA_FORGET_FRAGMENTS: tuple[str, ...] = (
    "别记",
    "不要保存",
    "do not remember",
)

_DEFAULT_RETAINED_NUTRIENT = (
    "温和养分：可回顾事件脉络与情绪强度，但不上升为稳定身份标签。"
)


def _explicit_forget_in_text(text: str) -> bool:
    lower = text.casefold()
    for phrase in FORGET_OR_PURGE_PHRASES:
        if phrase.casefold() in lower:
            return True
    for frag in _EXTRA_FORGET_FRAGMENTS:
        if frag.casefold() in lower:
            return True
    return False


# greenhoused 不在阻塞集中：梦境周期可通过堆肥处理温室种子（与 plant 阻塞集不同）
_COMPOST_BLOCKED: frozenset[SeedStatus] = frozenset({
    SeedStatus.planted,
    SeedStatus.composted,
    SeedStatus.forgotten,
    SeedStatus.merged,
})


def _seed_blocked_for_compost(seed: Seed) -> bool:
    return seed.status in _COMPOST_BLOCKED


def _validate_compost_seed(
    seed: Seed,
    court_case: CourtCase | None,
    reason: str,
) -> None:
    if not reason.strip():
        raise ValueError("堆肥理由不能为空")
    if court_case is None:
        raise ValueError("规则版堆肥须提供与之对应的 CourtCase")
    if court_case.seed_id != seed.id:
        raise ValueError("CourtCase.seed_id 与 Seed.id 不一致")
    if court_case.judge_verdict.verdict != CourtVerdictType.compost:
        raise ValueError("仅当法庭判决为 COMPOST 时方可对种子执行堆肥")
    if _seed_blocked_for_compost(seed):
        raise ValueError(f"种子状态为 {seed.status.value}，不可堆肥")
    if seed.context.get("user_requested_hard_forget") is True:
        raise ValueError("用户明确要求彻底遗忘时不得使用堆肥路径")
    if _explicit_forget_in_text(seed.content):
        raise ValueError("检测到明确遗忘请求，堆肥不能替代硬遗忘流程")


def compost_seed(
    seed: Seed,
    court_case: CourtCase | None,
    reason: str,
    nutrient: str | None,
    repository: GardenRepository,
    journal: GardenJournal,
) -> CompostRecord:
    """将种子堆肥：写入 CompostRecord、更新种子状态、记录领域事件（不删除种子行）。"""
    current_seed = repository.get_seed(seed.id)
    _validate_compost_seed(current_seed, court_case, reason)
    assert court_case is not None

    retained = (nutrient.strip() if nutrient and nutrient.strip() else _DEFAULT_RETAINED_NUTRIENT)
    record = CompostRecord(
        source_seed_id=current_seed.id,
        source_memory_id=None,
        discarded_surface=current_seed.content.strip(),
        retained_nutrient=retained,
        reason=reason.strip(),
        user_requested_hard_forget=False,
    )
    repository.save_compost_record(record)
    updated = current_seed.model_copy(update={"status": SeedStatus.composted})
    repository.update_seed(updated)
    journal.record_event(
        event_type=GardenEventType.memory_composted,
        object_type=GardenObjectType.compost_record,
        object_id=record.id,
        summary=f"种子 {current_seed.id} 已堆肥（记录 {record.id}）",
        metadata={
            "seed_id": current_seed.id,
            "compost_record_id": record.id,
            "court_case_id": court_case.id,
        },
    )
    return record


def compost_memory_card(**kwargs: object) -> CompostRecord:
    """记忆卡堆肥未实现；占位以避免误用种子 API。"""
    raise NotImplementedError("记忆卡堆肥未在 Stage 5A-2 之前实现")
