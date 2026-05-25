"""规则版梦境周期引擎：夜间整理种子与非温室记忆卡，不调用 LLM。"""

from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

from memory_garden.core.cards import merge_seed_into_memory, plant
from memory_garden.core.court.engine import MemoryCourtEngine
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.dream.record import (
    build_morning_garden,
    build_observation,
    build_reflection,
    build_transformation,
    cluster_essence_from_seeds,
    cluster_roots_branches,
)
from memory_garden.core.dream.interfaces import DreamCycleEngineProtocol
from memory_garden.core.growth.compost import compost_seed
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    DreamRecord,
    GardenEventType,
    GardenObjectType,
    MemoryCard,
    Seed,
    SeedSignalType,
    SeedStatus,
)
from memory_garden.core.policies import NEGATIVE_SELF_TALK_MARKERS, text_matches_marker_set
from memory_garden.storage.base import GardenRepository, NotFoundError

_ACTIVE_SEED_STATUSES: frozenset[SeedStatus] = frozenset(
    {
        SeedStatus.pending,
        SeedStatus.held,
        SeedStatus.in_court,
    }
)

_MERGE_TARGET_BLOCKED: frozenset[MemoryLifecycle] = frozenset(
    {MemoryLifecycle.pruned, MemoryLifecycle.composted}
)

_DREAM_COMPOST_REASON = "梦境堆肥：负面短期自评不固化为身份标签"
_DREAM_COMPOST_NUTRIENT = (
    "短期情绪与自我苛责可作泥土回望，但不提炼为稳定身份叙事；保留情境养分而不固化评判。"
)
_MERGE_REASON = "梦境周期：种子并入相似记忆枝"
_CLUSTER_MERGE_REASON = "梦境周期：聚类种子并入同一张新记忆卡"

# 相似度阈值（基于 SequenceMatcher.ratio 的文本相似度判断）
_SEED_SIMILARITY_THRESHOLD = 0.35   # 种子间判定为相似的最小文本相似度
_MEMORY_MERGE_THRESHOLD = 0.18      # 种子并入记忆的最小匹配分数


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _text_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().casefold(), b.strip().casefold()).ratio()


def _is_negative_surface(seed: Seed) -> bool:
    return seed.signal_type == SeedSignalType.negative_self_talk or text_matches_marker_set(
        seed.content,
        NEGATIVE_SELF_TALK_MARKERS,
    )


def _is_short_term_ephemeral(seed: Seed) -> bool:
    return seed.signal_type == SeedSignalType.ephemeral or len(seed.content.strip()) <= 120


def _should_compost_negative_short(seed: Seed) -> bool:
    """负面且偏短期的种子：进入梦境堆肥分支（与法庭 compost 规则对齐）。"""
    return _is_negative_surface(seed) and _is_short_term_ephemeral(seed)


# 标签聚类最小文本相似度：避免仅凭通用标签（如 "temporal"）合并不相关内容
_TAG_CLUSTER_MIN_TEXT_RATIO = 0.12


def _seeds_similar(a: Seed, b: Seed) -> bool:
    if a.signal_type != b.signal_type:
        return False
    ta, tb = set(a.tags), set(b.tags)
    text_sim = _text_ratio(a.content, b.content)
    if ta and tb and (ta & tb):
        return text_sim >= _TAG_CLUSTER_MIN_TEXT_RATIO
    return text_sim >= _SEED_SIMILARITY_THRESHOLD


def _find_clusters(seeds: list[Seed]) -> list[list[Seed]]:
    """并查集聚类：同信号且（标签交叠或文本相似）。"""
    n = len(seeds)
    if n < 2:
        return []
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _seeds_similar(seeds[i], seeds[j]):
                union(i, j)
    buckets: dict[int, list[Seed]] = {}
    for i in range(n):
        r = find(i)
        buckets.setdefault(r, []).append(seeds[i])
    return [g for g in buckets.values() if len(g) >= 2]


def _dedupe_ids(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _best_memory_for_seed(seed: Seed, memories: list[MemoryCard]) -> tuple[MemoryCard | None, float]:
    best: MemoryCard | None = None
    best_score = 0.0
    for m in memories:
        if m.lifecycle in _MERGE_TARGET_BLOCKED:
            continue
        ts, tt = set(seed.tags), set(m.tags)
        union = ts | tt
        tag_jacc = len(ts & tt) / len(union) if union else 0.0
        text_score = max(_text_ratio(seed.content, m.essence), _text_ratio(seed.content, m.title))
        score = 0.5 * tag_jacc + 0.5 * text_score
        if score > best_score:
            best_score, best = score, m
    if best is None or best_score < _MEMORY_MERGE_THRESHOLD:
        return None, best_score
    return best, best_score


def _attach_dream_record(
    repository: GardenRepository,
    memory_ids: list[str],
    dream_record_id: str,
) -> None:
    now = _utc_now()
    for mid in _dedupe_ids(memory_ids):
        try:
            m = repository.get_memory_card(mid)
        except NotFoundError:
            # 梦境周期中新建的记忆卡不应缺失；若是旧卡被后续动作处理掉则忽略
            continue
        dr = _dedupe_ids(list(m.dream_record_ids) + [dream_record_id])
        repository.update_memory_card(m.model_copy(update={"dream_record_ids": dr, "updated_at": now}))


def _restore_seed_status(repository: GardenRepository, seed_id: str, status: SeedStatus) -> None:
    seed = repository.get_seed(seed_id)
    if seed.status != status:
        repository.update_seed(seed.model_copy(update={"status": status}))


class DreamCycleEngine(DreamCycleEngineProtocol):
    """规则版梦境周期：堆肥、聚类种植、朴素并入。"""

    def __init__(self, repository: GardenRepository, journal: GardenJournal | None = None) -> None:
        self._repository = repository
        self._journal = journal if journal is not None else GardenJournal(repository)

    def dream(
        self,
        seed_ids: list[str] | None = None,
        memory_ids: list[str] | None = None,
    ) -> DreamRecord | None:
        seeds, memories = self._resolve_seed_memory(seed_ids, memory_ids)
        input_seed_ids = [s.id for s in seeds]
        input_memory_ids = [m.id for m in memories]
        if not input_seed_ids and not input_memory_ids:
            return None

        court = MemoryCourtEngine(self._repository, self._journal)

        created_memory_ids: list[str] = []
        merged_memory_ids: list[str] = []
        composted_seed_ids: list[str] = []
        pruned_memory_ids: list[str] = []

        seeds_work = [self._repository.get_seed(s.id) for s in seeds]
        seeds_work.sort(key=lambda x: x.id)

        self._repository.begin()
        # 1) 负面短期 → 堆肥
        i = 0
        while i < len(seeds_work):
            cur = self._repository.get_seed(seeds_work[i].id)
            if _should_compost_negative_short(cur):
                if cur.status == SeedStatus.in_court:
                    i += 1
                    continue
                status_before_case = cur.status
                case = court.open_case(cur)
                fresh = self._repository.get_seed(cur.id)
                if case.judge_verdict.verdict != CourtVerdictType.compost:
                    _restore_seed_status(self._repository, cur.id, status_before_case)
                    self._repository.delete_court_case(case.id)
                    i += 1
                    continue
                compost_seed(
                    fresh,
                    case,
                    reason=_DREAM_COMPOST_REASON,
                    nutrient=_DREAM_COMPOST_NUTRIENT,
                    repository=self._repository,
                    journal=self._journal,
                )
                composted_seed_ids.append(cur.id)
                seeds_work.pop(i)
                continue
            i += 1

        # 2) 相似种子聚类 → 一张新记忆卡（首颗 PLANTED，其余 MERGED）
        seeds_work.sort(key=lambda x: x.id)
        clustered_ids: set[str] = set()
        cluster_groups = _find_clusters(seeds_work)
        cluster_ops = 0
        for group in cluster_groups:
            grp = sorted(group, key=lambda x: x.id)
            first = self._repository.get_seed(grp[0].id)
            if first.status == SeedStatus.in_court:
                continue
            status_before_case = first.status
            case = court.open_case(first)
            first_fresh = self._repository.get_seed(first.id)
            if case.judge_verdict.verdict != CourtVerdictType.plant:
                _restore_seed_status(self._repository, first.id, status_before_case)
                self._repository.delete_court_case(case.id)
                continue
            card = plant(first_fresh, case, self._repository, self._journal)
            cluster_ops += 1
            created_memory_ids.append(card.id)

            essence = cluster_essence_from_seeds(grp)
            roots, _ = cluster_roots_branches(grp)
            planted_card = self._repository.get_memory_card(card.id)
            planted_card = planted_card.model_copy(
                update={
                    "essence": essence,
                    "roots": roots,
                    "updated_at": _utc_now(),
                }
            )
            self._repository.update_memory_card(planted_card)

            for s_extra in grp[1:]:
                s_extra = self._repository.get_seed(s_extra.id)
                merge_seed_into_memory(
                    s_extra,
                    planted_card.id,
                    _CLUSTER_MERGE_REASON,
                    self._repository,
                    self._journal,
                    court_case=None,
                )
                merged_memory_ids.append(planted_card.id)
            for s in grp:
                clustered_ids.add(s.id)

        # 3) 落单种子 → 朴素并入已有记忆
        merge_ops = 0
        pool_memories = [
            self._repository.get_memory_card(m.id) for m in memories
        ]
        # 包含本轮新建的记忆，供并入匹配
        for mid in created_memory_ids:
            try:
                pool_memories.append(self._repository.get_memory_card(mid))
            except NotFoundError:
                # 梦境整理允许新建后被后续动作处理掉的记忆缺席。
                pass
        pool_memories = [m for m in pool_memories if m.lifecycle not in _MERGE_TARGET_BLOCKED]
        seen_mid = {m.id for m in pool_memories}

        for s in seeds_work:
            if s.id in clustered_ids or s.id in composted_seed_ids:
                continue
            cur = self._repository.get_seed(s.id)
            if cur.status not in _ACTIVE_SEED_STATUSES:
                continue
            if cur.status == SeedStatus.planted:
                continue
            target, score = _best_memory_for_seed(cur, pool_memories)
            if target is None:
                continue
            merge_seed_into_memory(
                cur,
                target.id,
                _MERGE_REASON,
                self._repository,
                self._journal,
                court_case=None,
            )
            merged_memory_ids.append(target.id)
            merge_ops += 1
            # 新建卡可能未在 memories 列表中，首次并入后加入池
            updated = self._repository.get_memory_card(target.id)
            if updated.id not in seen_mid:
                pool_memories.append(updated)
                seen_mid.add(updated.id)

        merged_memory_ids = _dedupe_ids(merged_memory_ids)

        record = DreamRecord(
            input_seed_ids=_dedupe_ids(input_seed_ids),
            input_memory_ids=_dedupe_ids(input_memory_ids),
            observation=build_observation(
                _dedupe_ids(input_seed_ids),
                _dedupe_ids(input_memory_ids),
            ),
            reflection=build_reflection(composted_seed_ids, cluster_ops, merge_ops),
            transformation="夜间整理占位，将在写入 id 后替换为含实体 id 的变换说明。",
            morning_garden=build_morning_garden(
                created_memory_ids,
                merged_memory_ids,
                composted_seed_ids,
            ),
            created_memory_ids=created_memory_ids,
            merged_memory_ids=merged_memory_ids,
            composted_seed_ids=composted_seed_ids,
            pruned_memory_ids=pruned_memory_ids,
        )
        record = record.model_copy(
            update={
                "transformation": build_transformation(
                    record.id,
                    created_memory_ids,
                    merged_memory_ids,
                    composted_seed_ids,
                    pruned_memory_ids,
                ),
            }
        )

        self._repository.save_dream_record(record)

        touch_memories = _dedupe_ids(created_memory_ids + merged_memory_ids)
        _attach_dream_record(self._repository, touch_memories, record.id)

        self._journal.record_event(
            event_type=GardenEventType.dream_completed,
            object_type=GardenObjectType.dream_record,
            object_id=record.id,
            summary=f"规则梦境周期完成（记录 {record.id}）",
            metadata={
                "input_seed_ids": record.input_seed_ids,
                "input_memory_ids": record.input_memory_ids,
                "created_memory_ids": record.created_memory_ids,
                "merged_memory_ids": record.merged_memory_ids,
                "composted_seed_ids": record.composted_seed_ids,
                "pruned_memory_ids": record.pruned_memory_ids,
                "engine": "rule_based",
            },
        )
        self._repository.commit()
        return record
        # 若上述任何一步抛出异常，begin() 开启的事务将在 close() 时自动回滚

    def _resolve_seed_memory(
        self,
        seed_ids: list[str] | None,
        memory_ids: list[str] | None,
    ) -> tuple[list[Seed], list[MemoryCard]]:
        seeds: list[Seed] = []
        memories: list[MemoryCard] = []
        if seed_ids is None:
            for s in self._repository.list_seeds():
                if s.status in _ACTIVE_SEED_STATUSES:
                    seeds.append(s)
        else:
            for sid in seed_ids:
                seeds.append(self._repository.get_seed(sid))
        if memory_ids is None:
            memories = self._repository.list_memory_cards(include_greenhouse=False)
        else:
            for mid in memory_ids:
                memories.append(self._repository.get_memory_card(mid))
        seeds.sort(key=lambda x: x.id)
        memories.sort(key=lambda x: x.id)
        return seeds, memories
