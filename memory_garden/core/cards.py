"""记忆卡片生长动作：种植（plant）等，不包含检索与合并。"""

from __future__ import annotations

from datetime import datetime, timezone

from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.journal import GardenJournal
from memory_garden.core.growth.pruning import max_sensitivity
from memory_garden.core.models import (
    CourtCase,
    GardenEventType,
    GardenObjectType,
    MemoryCard,
    MemoryType,
    PruningRecord,
    Seed,
    SeedSignalType,
    SeedStatus,
)
from memory_garden.storage.base import GardenRepository

# 注意：Seed 状态阻塞集分布在多个模块中，修改 SeedStatus 时需同步更新：
#   cards.py: _SEED_BLOCKED_FOR_PLANT / _SEED_BLOCKED_FOR_MERGE
#   growth/compost.py: _seed_blocked_for_compost
#   dream/engine.py: _ACTIVE_SEED_STATUSES
_SEED_BLOCKED_FOR_PLANT: frozenset[SeedStatus] = frozenset(
    {
        SeedStatus.planted,
        SeedStatus.composted,
        SeedStatus.greenhoused,
        SeedStatus.forgotten,
        SeedStatus.merged,
    }
)

# greenhoused 种子可被合并（见 dream/engine.py 梦境周期步骤3），
# 因此 MERGE 阻塞集不包含 greenhoused。
_SEED_BLOCKED_FOR_MERGE: frozenset[SeedStatus] = frozenset(
    {
        SeedStatus.planted,
        SeedStatus.composted,
        SeedStatus.forgotten,
        SeedStatus.merged,
    }
)

_TARGET_BLOCKED_FOR_MERGE: frozenset[MemoryLifecycle] = frozenset(
    {MemoryLifecycle.pruned, MemoryLifecycle.composted}
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _dedupe_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _merge_distinct_short_text(a: str, b: str) -> str:
    """合并两段说明文字，去重相同片段，否则用分号并列。"""
    sa, sb = a.strip(), b.strip()
    if not sb:
        return sa
    if not sa:
        return sb
    if sa == sb:
        return sa
    return f"{sa}；{sb}"


def _memory_type_from_seed(seed: Seed) -> MemoryType:
    mapping: dict[SeedSignalType, MemoryType] = {
        SeedSignalType.preference: MemoryType.preference,
        SeedSignalType.constraint: MemoryType.boundary,
        SeedSignalType.decision: MemoryType.reflection,
        SeedSignalType.negative_self_talk: MemoryType.avoidance,
        SeedSignalType.sensitive_info: MemoryType.boundary,
        SeedSignalType.correction: MemoryType.boundary,
        SeedSignalType.ephemeral: MemoryType.reflection,
        SeedSignalType.unknown: MemoryType.unknown,
    }
    return mapping.get(seed.signal_type, MemoryType.unknown)


def _combined_confidence(seed: Seed, court_case: CourtCase) -> float:
    """保守组合：取两者最小值再略微下调，避免过度自信。"""
    s = float(seed.confidence)
    v = float(court_case.judge_verdict.confidence)
    base = min(s, v)
    return round(max(0.0, min(1.0, base * 0.96)), 4)


def _validate_plant(seed: Seed, court_case: CourtCase) -> None:
    if court_case.seed_id != seed.id:
        raise ValueError("CourtCase.seed_id 与 Seed.id 不一致，拒绝种植")
    if court_case.judge_verdict.verdict != CourtVerdictType.plant:
        raise ValueError("仅当法庭判决为 PLANT 时方可种植")
    if seed.status in _SEED_BLOCKED_FOR_PLANT:
        raise ValueError(f"种子状态为 {seed.status.value}，不允许再次种植")


def _build_memory_card(seed: Seed, court_case: CourtCase) -> MemoryCard:
    raw = seed.content.strip()
    title = raw[:100] if len(raw) > 100 else raw
    essence = raw[:600] if len(raw) > 600 else raw
    return MemoryCard(
        title=title,
        essence=essence,
        memory_type=_memory_type_from_seed(seed),
        lifecycle=MemoryLifecycle.sprout,
        tags=list(seed.tags),
        # 新种植记忆卡的默认使用指引（合并或梦境周期中可通过外部来源更新）
        fragrance="温柔引用该片段以保持一致性与尊重用户偏好。",
        thorns="避免在语境未核实前将偏好强加为事实或身份断言。",
        confidence=_combined_confidence(seed, court_case),
        importance=min(1.0, max(0.0, (seed.confidence + court_case.judge_verdict.confidence) / 2)),
        source_seed_ids=[seed.id],
        court_case_ids=[court_case.id],
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


def plant(
    seed: Seed,
    court_case: CourtCase,
    repository: GardenRepository,
    journal: GardenJournal,
) -> MemoryCard:
    """将已通过 PLANT 判决的种子写成长期记忆卡，并记录领域事件。"""
    current_seed = repository.get_seed(seed.id)
    _validate_plant(current_seed, court_case)
    card = _build_memory_card(current_seed, court_case)
    repository.save_memory_card(card)
    planted_seed = current_seed.model_copy(update={"status": SeedStatus.planted})
    repository.update_seed(planted_seed)
    journal.record_event(
        event_type=GardenEventType.memory_planted,
        object_type=GardenObjectType.memory_card,
        object_id=card.id,
        summary=f"种子 {current_seed.id} 已种植为记忆卡 {card.id}",
        metadata={
            "seed_id": current_seed.id,
            "court_case_id": court_case.id,
            "memory_card_id": card.id,
        },
    )
    return card


def merge_seed_into_memory(
    seed: Seed,
    target_memory_id: str,
    reason: str,
    repository: GardenRepository,
    journal: GardenJournal,
    court_case: CourtCase | None = None,
) -> MemoryCard:
    """将候选种子并入既有记忆卡：不新建 MemoryCard，仅扩展溯源字段。"""
    if not reason.strip():
        raise ValueError("合并理由不能为空")
    current = repository.get_seed(seed.id)
    if current.status in _SEED_BLOCKED_FOR_MERGE:
        raise ValueError(f"种子状态为 {current.status.value}，不可并入记忆")
    if court_case is not None and court_case.seed_id != current.id:
        raise ValueError("CourtCase 与种子不匹配")

    target = repository.get_memory_card(target_memory_id)
    if target.lifecycle in _TARGET_BLOCKED_FOR_MERGE:
        raise ValueError("目标记忆已修剪或堆肥，不可作为并入目标")

    now = _utc_now()
    seed_ids = _dedupe_ids(list(target.source_seed_ids) + [current.id])
    tags = _dedupe_ids(list(target.tags) + list(current.tags))
    court_ids = list(target.court_case_ids)
    if court_case is not None:
        court_ids = _dedupe_ids(court_ids + [court_case.id])

    branch_line = f"[并入种子 {current.id}] {current.content.strip()[:280]}"
    branches = list(target.branches)
    if branch_line not in branches:
        branches.append(branch_line)

    updated = target.model_copy(
        update={
            "source_seed_ids": seed_ids,
            "court_case_ids": court_ids,
            "tags": tags,
            "branches": branches,
            "updated_at": now,
        }
    )
    repository.update_memory_card(updated)

    merged_seed = current.model_copy(update={"status": SeedStatus.merged})
    repository.update_seed(merged_seed)

    journal.record_event(
        event_type=GardenEventType.memory_merged,
        object_type=GardenObjectType.memory_card,
        object_id=updated.id,
        summary=f"种子 {current.id} 已并入记忆卡 {updated.id}",
        metadata={
            "source_type": "seed",
            "source_id": current.id,
            "target_memory_id": updated.id,
            "source_seed_ids": updated.source_seed_ids,
            "court_case_ids": updated.court_case_ids,
            "dream_record_ids": updated.dream_record_ids,
            "reason": reason.strip(),
        },
    )
    return updated


def merge_memory_into_memory(
    source_memory_id: str,
    target_memory_id: str,
    reason: str,
    repository: GardenRepository,
    journal: GardenJournal,
) -> MemoryCard:
    """将源记忆卡并入目标：源修剪为 PRUNED，目标汇总溯源与文本线索。"""
    if not reason.strip():
        raise ValueError("合并理由不能为空")
    if source_memory_id == target_memory_id:
        raise ValueError("源与目标不能相同")

    source = repository.get_memory_card(source_memory_id)
    target = repository.get_memory_card(target_memory_id)
    if target.lifecycle in _TARGET_BLOCKED_FOR_MERGE:
        raise ValueError("目标记忆已修剪或堆肥，不可并入")
    if source.lifecycle in _TARGET_BLOCKED_FOR_MERGE:
        raise ValueError("源记忆已修剪或堆肥，不可作为并入来源")

    now = _utc_now()
    merged_seed_ids = _dedupe_ids(list(target.source_seed_ids) + list(source.source_seed_ids))
    merged_courts = _dedupe_ids(list(target.court_case_ids) + list(source.court_case_ids))
    merged_dreams = _dedupe_ids(list(target.dream_record_ids) + list(source.dream_record_ids))
    merged_tags = _dedupe_ids(list(target.tags) + list(source.tags))
    merged_roots = _dedupe_ids(list(target.roots) + list(source.roots))

    branch_note = f"[并入记忆 {source.id}] {source.essence.strip()[:280]}"
    branches = list(target.branches)
    if branch_note not in branches:
        branches.append(branch_note)

    fragrance = _merge_distinct_short_text(target.fragrance, source.fragrance)
    thorns = _merge_distinct_short_text(target.thorns, source.thorns)
    sens = max_sensitivity(target.sensitivity, source.sensitivity)
    imp = max(float(target.importance), float(source.importance))
    imp = min(1.0, max(0.0, imp))

    updated_target = target.model_copy(
        update={
            "source_seed_ids": merged_seed_ids,
            "court_case_ids": merged_courts,
            "dream_record_ids": merged_dreams,
            "tags": merged_tags,
            "roots": merged_roots,
            "branches": branches,
            "fragrance": fragrance,
            "thorns": thorns,
            "sensitivity": sens,
            "importance": imp,
            "updated_at": now,
        }
    )
    repository.update_memory_card(updated_target)

    old_src_lifecycle = source.lifecycle
    pruned_source = source.model_copy(
        update={
            "lifecycle": MemoryLifecycle.pruned,
            "updated_at": now,
        }
    )
    repository.update_memory_card(pruned_source)

    pr = PruningRecord(
        memory_id=source.id,
        reason=f"已并入记忆卡 {target_memory_id}：{reason.strip()}",
        old_lifecycle=old_src_lifecycle,
        new_lifecycle=MemoryLifecycle.pruned,
        created_at=now,
    )
    repository.save_pruning_record(pr)

    journal.record_event(
        event_type=GardenEventType.memory_merged,
        object_type=GardenObjectType.memory_card,
        object_id=updated_target.id,
        summary=f"记忆卡 {source.id} 已并入 {updated_target.id}",
        metadata={
            "source_type": "memory_card",
            "source_id": source.id,
            "target_memory_id": updated_target.id,
            "source_seed_ids": updated_target.source_seed_ids,
            "court_case_ids": updated_target.court_case_ids,
            "dream_record_ids": updated_target.dream_record_ids,
            "pruning_record_id": pr.id,
            "reason": reason.strip(),
        },
    )
    return updated_target
