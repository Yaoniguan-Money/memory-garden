"""第一层 MemoryGardenCore：编排仓储与既有引擎，不重写业务规则。"""

from __future__ import annotations

from typing import Any, Literal

from memory_garden.core.cards import merge_memory_into_memory, merge_seed_into_memory, plant as plant_memory_card
from memory_garden.core.court.engine import MemoryCourtEngine
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.dream.engine import DreamCycleEngine
from memory_garden.core.growth.compost import compost_seed
from memory_garden.core.growth.greenhouse import greenhouse_memory
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.growth.pruning import forget_memory, prune_memory
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    DreamRecord,
    GardenEvent,
    GreenhouseAccessPolicy,
    GreenhouseRecord,
    MemoryCard,
    PruningRecord,
    Seed,
    SeedStatus,
    SensitivityLevel,
)
from memory_garden.core.seeds import SeedObserver
from memory_garden.storage.base import GardenRepository
from memory_garden.storage.sqlite import SQLiteGardenRepository


class MemoryGardenCore:
    """最小 Python API：委托 SeedObserver、法庭、生长动作、梦境引擎与仓储。"""

    def __init__(
        self,
        repository: GardenRepository | None = None,
        journal: GardenJournal | None = None,
        observer: SeedObserver | None = None,
        court: MemoryCourtEngine | None = None,
        dream_engine: DreamCycleEngine | None = None,
    ) -> None:
        self._repository = repository or SQLiteGardenRepository(":memory:")
        self._journal = journal or GardenJournal(self._repository)
        self._observer = observer or SeedObserver(self._repository, self._journal)
        self._court = court or MemoryCourtEngine(self._repository, self._journal)
        self._dream = dream_engine or DreamCycleEngine(self._repository, self._journal)

    @property
    def repository(self) -> GardenRepository:
        return self._repository

    def close(self) -> None:
        """关闭底层仓库连接，释放数据库资源。"""
        self._repository.close()

    @property
    def journal(self) -> GardenJournal:
        return self._journal

    def observe(self, text: str, context: dict[str, Any] | None = None) -> list[Seed]:
        """委托 SeedObserver；可选将 context 合并写入已保存种子的 context。"""
        seeds = self._observer.observe(text)
        if not context:
            return seeds
        merged: list[Seed] = []
        for s in seeds:
            ctx = dict(s.context)
            ctx.update(context)
            merged.append(self._repository.update_seed(s.model_copy(update={"context": ctx})))
        return merged

    def open_court(self, seed_ids: list[str] | None = None) -> list[CourtCase]:
        """对候选种子开庭并持久化 CourtCase；不执行判决生长动作。

        seed_ids 为 None 时仅收集「待审」的 pending 种子，避免对已审判的 held/in_court
        等状态重复开庭；显式传入 id 时按给定列表开庭，不额外按状态过滤。
        """
        if seed_ids is None:
            candidates = [s for s in self._repository.list_seeds() if s.status == SeedStatus.pending]
            candidates.sort(key=lambda x: x.id)
        else:
            candidates = [self._repository.get_seed(sid) for sid in seed_ids]
        return [self._court.open_case(s) for s in candidates]

    def apply_verdict(self, case: CourtCase) -> MemoryCard | CompostRecord | GreenhouseRecord | PruningRecord | None:
        """按既有法庭判决委托对应生长动作；不重新裁决。

        多步写操作在事务中执行，保证原子性。
        """
        verdict = case.judge_verdict.verdict
        target_id = case.judge_verdict.target_memory_id
        reason = case.judge_verdict.reason.strip()

        if verdict == CourtVerdictType.hold:
            seed = self._repository.get_seed(case.seed_id)
            held = seed.model_copy(update={"status": SeedStatus.held})
            self._repository.update_seed(held)
            return None

        if verdict == CourtVerdictType.plant:
            with self._repository.transaction():
                seed = self._repository.get_seed(case.seed_id)
                return plant_memory_card(seed, case, self._repository, self._journal)

        if verdict == CourtVerdictType.compost:
            with self._repository.transaction():
                seed = self._repository.get_seed(case.seed_id)
                return self.compost(seed, court_case=case, reason=reason, nutrient=None)

        if verdict == CourtVerdictType.greenhouse:
            if target_id is None or not str(target_id).strip():
                raise ValueError("GREENHOUSE 判决缺少 target_memory_id")
            with self._repository.transaction():
                _, record = greenhouse_memory(
                    str(target_id).strip(),
                    reason,
                    sensitivity_level=SensitivityLevel.medium,
                    access_policy=GreenhouseAccessPolicy.excluded_by_default,
                    repository=self._repository,
                    journal=self._journal,
                )
                return record

        if verdict == CourtVerdictType.prune:
            if target_id is None or not str(target_id).strip():
                raise ValueError("PRUNE 判决缺少 target_memory_id")
            with self._repository.transaction():
                return prune_memory(str(target_id).strip(), reason, self._repository, self._journal)

        if verdict == CourtVerdictType.merge:
            if target_id is None or not str(target_id).strip():
                raise ValueError("MERGE 判决缺少 target_memory_id")
            with self._repository.transaction():
                seed = self._repository.get_seed(case.seed_id)
                return merge_seed_into_memory(
                    seed,
                    str(target_id).strip(),
                    reason,
                    self._repository,
                    self._journal,
                    court_case=case,
                )

        if verdict == CourtVerdictType.forget:
            if target_id is None or not str(target_id).strip():
                raise ValueError("FORGET 判决缺少 target_memory_id")
            # 法庭 forget 语义映射为软遗忘；硬删除须通过 facade.forget(mode=\"hard\") 单独调用
            with self._repository.transaction():
                return forget_memory(
                    str(target_id).strip(),
                    "soft",
                    reason,
                    self._repository,
                    self._journal,
                )

        # 未知判决类型：记录警告并保守返回 None
        import warnings
        warnings.warn(f"apply_verdict: 未识别的判决类型 {verdict.value}，跳过 case {case.id}")
        return None

    def dream(self) -> DreamRecord | None:
        """委托梦境引擎；不做调度或自动开庭。"""
        return self._dream.dream()

    def plant(self, seed: Seed, court_case: CourtCase) -> MemoryCard:
        return plant_memory_card(seed, court_case, self._repository, self._journal)

    def compost(
        self,
        seed: Seed,
        court_case: CourtCase,
        reason: str | None = None,
        nutrient: str | None = None,
    ) -> CompostRecord:
        r = reason.strip() if reason and reason.strip() else "堆肥"
        return compost_seed(seed, court_case, r, nutrient, self._repository, self._journal)

    def greenhouse(
        self,
        memory_id: str,
        reason: str,
        *,
        sensitivity_level: SensitivityLevel = SensitivityLevel.medium,
        access_policy: GreenhouseAccessPolicy = GreenhouseAccessPolicy.excluded_by_default,
    ) -> GreenhouseRecord:
        _, record = greenhouse_memory(
            memory_id,
            reason,
            sensitivity_level=sensitivity_level,
            access_policy=access_policy,
            repository=self._repository,
            journal=self._journal,
        )
        return record

    def prune(self, memory_id: str, reason: str) -> PruningRecord:
        return prune_memory(memory_id, reason, self._repository, self._journal)

    def forget(self, memory_id: str, mode: Literal["soft", "hard"], reason: str) -> PruningRecord:
        if mode not in ("soft", "hard"):
            raise ValueError("mode 必须是 soft 或 hard")
        return forget_memory(memory_id, mode, reason, self._repository, self._journal)

    def merge_seed(
        self,
        seed: Seed,
        target_memory_id: str,
        reason: str,
        court_case: CourtCase | None = None,
    ) -> MemoryCard:
        return merge_seed_into_memory(
            seed,
            target_memory_id,
            reason,
            self._repository,
            self._journal,
            court_case=court_case,
        )

    def merge_memory(self, source_memory_id: str, target_memory_id: str, reason: str) -> MemoryCard:
        return merge_memory_into_memory(
            source_memory_id,
            target_memory_id,
            reason,
            self._repository,
            self._journal,
        )

    def list_memories(
        self,
        include_greenhouse: bool = False,
        lifecycle: MemoryLifecycle | None = None,
        limit: int | None = None,
    ) -> list[MemoryCard]:
        return self._repository.list_memory_cards(
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            limit=limit,
        )

    def recent_events(self, limit: int | None = None) -> list[GardenEvent]:
        lim = 20 if limit is None else limit
        return self._journal.recent_events(limit=lim)
