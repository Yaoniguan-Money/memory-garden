"""温室动作：将记忆卡移入温室生命周期并记录隔离原因。"""

from __future__ import annotations

from datetime import datetime, timezone

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    GardenEventType,
    GardenObjectType,
    GreenhouseAccessPolicy,
    GreenhouseRecord,
    MemoryCard,
    SensitivityLevel,
)
from memory_garden.storage.base import GardenRepository

_BLOCKED_LIFECYCLE_FOR_GREENHOUSE: frozenset[MemoryLifecycle] = frozenset(
    {MemoryLifecycle.pruned, MemoryLifecycle.composted}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def greenhouse_memory(
    memory_id: str,
    reason: str,
    sensitivity_level: SensitivityLevel,
    access_policy: GreenhouseAccessPolicy,
    repository: GardenRepository,
    journal: GardenJournal,
) -> tuple[MemoryCard, GreenhouseRecord]:
    """读取记忆卡，将其生命周期设为温室并写入 GreenhouseRecord 与领域事件。"""
    if not reason.strip():
        raise ValueError("进入温室的理由不能为空")
    card = repository.get_memory_card(memory_id)
    if card.lifecycle in _BLOCKED_LIFECYCLE_FOR_GREENHOUSE:
        raise ValueError("已修剪或已堆肥的记忆卡不可再进入温室流程")

    now = _utc_now()
    updated = card.model_copy(
        update={
            "lifecycle": MemoryLifecycle.greenhouse,
            "sensitivity": sensitivity_level,
            "updated_at": now,
        }
    )
    repository.update_memory_card(updated)

    record = GreenhouseRecord(
        memory_id=memory_id,
        reason=reason.strip(),
        sensitivity_level=sensitivity_level,
        access_policy=access_policy,
        created_at=now,
    )
    repository.save_greenhouse_record(record)

    journal.record_event(
        event_type=GardenEventType.memory_greenhoused,
        object_type=GardenObjectType.greenhouse_record,
        object_id=record.id,
        summary=f"记忆卡 {memory_id} 已转入温室（记录 {record.id}）",
        metadata={
            "memory_id": memory_id,
            "greenhouse_record_id": record.id,
            "access_policy": access_policy.value,
        },
    )
    return updated, record
