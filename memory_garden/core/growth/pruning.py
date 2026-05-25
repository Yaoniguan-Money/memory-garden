"""修剪与遗忘：高风险生命周期动作（不含检索与合并逻辑）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    GardenEventType,
    GardenObjectType,
    MemoryCard,
    PruningRecord,
    SensitivityLevel,
)
from memory_garden.storage.base import GardenRepository

_BLOCKED_PRUNE_LIFECYCLE: frozenset[MemoryLifecycle] = frozenset(
    {MemoryLifecycle.pruned, MemoryLifecycle.composted}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _get_card_or_raise(repository: GardenRepository, memory_id: str) -> MemoryCard:
    """找不到记忆卡时透传 NotFoundError。"""
    return repository.get_memory_card(memory_id)


def prune_memory(
    memory_id: str,
    reason: str,
    repository: GardenRepository,
    journal: GardenJournal,
) -> PruningRecord:
    """将记忆卡修剪为 PRUNED，写入修剪记录与领域事件（不删除行）。"""
    if not reason.strip():
        raise ValueError("修剪理由不能为空")
    card = _get_card_or_raise(repository, memory_id)
    if card.lifecycle in _BLOCKED_PRUNE_LIFECYCLE:
        raise ValueError("已修剪或已堆肥的记忆不可再次修剪")
    old = card.lifecycle
    now = _utc_now()
    updated = card.model_copy(
        update={
            "lifecycle": MemoryLifecycle.pruned,
            "updated_at": now,
        }
    )
    repository.update_memory_card(updated)
    record = PruningRecord(
        memory_id=memory_id,
        reason=reason.strip(),
        old_lifecycle=old,
        new_lifecycle=MemoryLifecycle.pruned,
        created_at=now,
    )
    repository.save_pruning_record(record)
    journal.record_event(
        event_type=GardenEventType.memory_pruned,
        object_type=GardenObjectType.pruning_record,
        object_id=record.id,
        summary=f"记忆卡 {memory_id} 已修剪（{record.id}）",
        metadata={
            "memory_id": memory_id,
            "pruning_record_id": record.id,
            "old_lifecycle": old.value,
            "new_lifecycle": MemoryLifecycle.pruned.value,
        },
    )
    return record


def forget_memory(
    memory_id: str,
    mode: Literal["soft", "hard"],
    reason: str,
    repository: GardenRepository,
    journal: GardenJournal,
) -> PruningRecord | None:
    """软遗忘：等价修剪为 PRUNED；硬遗忘：真实删除记忆卡行。"""
    if mode not in ("soft", "hard"):
        raise ValueError("mode 必须是 soft 或 hard")
    if not reason.strip():
        raise ValueError("遗忘理由不能为空")

    if mode == "soft":
        card = _get_card_or_raise(repository, memory_id)
        if card.lifecycle in _BLOCKED_PRUNE_LIFECYCLE:
            raise ValueError("已修剪或已堆肥的记忆不可执行软遗忘")
        old = card.lifecycle
        now = _utc_now()
        updated = card.model_copy(
            update={
                "lifecycle": MemoryLifecycle.pruned,
                "updated_at": now,
            }
        )
        repository.update_memory_card(updated)
        record = PruningRecord(
            memory_id=memory_id,
            reason=f"[soft forget] {reason.strip()}",
            old_lifecycle=old,
            new_lifecycle=MemoryLifecycle.pruned,
            created_at=now,
        )
        repository.save_pruning_record(record)
        journal.record_event(
            event_type=GardenEventType.memory_forgotten,
            object_type=GardenObjectType.memory_card,
            object_id=memory_id,
            summary=f"记忆卡 {memory_id} 软遗忘（修剪留存）",
            metadata={
                "memory_id": memory_id,
                "mode": "soft",
                "pruning_record_id": record.id,
                "old_lifecycle": old.value,
            },
        )
        return record

    # hard：物理删除。级联清理（FTS、种子、案件、修剪/温室记录）由 Soil 层
    # execute_hard_forget 统一负责，此处仅执行核心的 memory_card 行删除。
    card = _get_card_or_raise(repository, memory_id)
    old = card.lifecycle
    repository.delete_memory_card(memory_id)
    meta = {
        "memory_id": memory_id,
        "mode": "hard",
        "hard_deleted": True,
        "content_retained": False,
        "old_lifecycle": old.value,
    }
    journal.record_event(
        event_type=GardenEventType.memory_forgotten,
        object_type=GardenObjectType.memory_card,
        object_id=memory_id,
        summary=f"记忆卡 {memory_id} 已硬删除",
        metadata=meta,
    )
    return None


def max_sensitivity(a: SensitivityLevel, b: SensitivityLevel) -> SensitivityLevel:
    """取更保守（更高）的敏感级别。"""
    order = {
        SensitivityLevel.none: 0,
        SensitivityLevel.low: 1,
        SensitivityLevel.medium: 2,
        SensitivityLevel.high: 3,
    }
    return a if order[a] >= order[b] else b
