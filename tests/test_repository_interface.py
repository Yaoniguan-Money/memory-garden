"""仓储抽象接口与 Fake 内存实现测试（Stage 1B）。"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    DreamRecord,
    GardenEvent,
    GardenEventType,
    GardenObjectType,
    GreenhouseRecord,
    MemoryCard,
    MemoryType,
    PruningRecord,
    Seed,
    SeedStatus,
)
from memory_garden.storage.base import (
    DuplicateIdError,
    GardenRepository,
    NotFoundError,
    RepositoryError,
)


def test_repository_exceptions_hierarchy() -> None:
    assert issubclass(NotFoundError, RepositoryError)
    assert issubclass(DuplicateIdError, RepositoryError)
    err = RepositoryError("x")
    assert str(err) == "x"


def test_garden_repository_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        GardenRepository()


def test_garden_repository_all_methods_abstract() -> None:
    abstract = getattr(GardenRepository, "__abstractmethods__", None)
    assert abstract is not None
    assert len(abstract) > 0
    for name in abstract:
        method = getattr(GardenRepository, name)
        assert getattr(method, "__isabstractmethod__", False)


EXPECTED_ABSTRACT_METHODS = frozenset(
    {
        "save_seed",
        "get_seed",
        "list_seeds",
        "update_seed",
        "save_memory_card",
        "get_memory_card",
        "list_memory_cards",
        "count_memory_cards",
        "update_memory_card",
        "delete_memory_card",
        "save_court_case",
        "get_court_case",
        "list_court_cases",
        "delete_court_case",
        "save_dream_record",
        "get_dream_record",
        "list_dream_records",
        "save_compost_record",
        "get_compost_record",
        "list_compost_records",
        "save_greenhouse_record",
        "get_greenhouse_record",
        "list_greenhouse_records",
        "save_pruning_record",
        "get_pruning_record",
        "list_pruning_records",
        "save_garden_event",
        "get_garden_event",
        "list_garden_events",
    }
)


def test_garden_repository_expected_abstract_method_names() -> None:
    assert GardenRepository.__abstractmethods__ == EXPECTED_ABSTRACT_METHODS


def test_list_memory_cards_signature_matches_spec() -> None:
    sig = inspect.signature(GardenRepository.list_memory_cards)
    params = list(sig.parameters.keys())
    assert params == ["self", "lifecycle", "include_greenhouse", "limit"]
    assert sig.parameters["include_greenhouse"].default is False


def test_count_memory_cards_signature_matches_spec() -> None:
    sig = inspect.signature(GardenRepository.count_memory_cards)
    params = list(sig.parameters.keys())
    assert params == ["self", "lifecycle", "include_greenhouse"]
    assert sig.parameters["include_greenhouse"].default is False


def test_append_only_records_have_no_update_delete_on_abc() -> None:
    """追加型记录在仓储接口上不暴露 update/delete（由规格隐含）。"""
    forbidden = (
        "update_dream_record",
        "delete_dream_record",
        "update_compost_record",
        "delete_compost_record",
        "update_greenhouse_record",
        "delete_greenhouse_record",
        "update_pruning_record",
        "delete_pruning_record",
        "update_garden_event",
        "delete_garden_event",
        "update_court_case",
    )
    for name in forbidden:
        assert not hasattr(GardenRepository, name)


class FakeGardenRepository(GardenRepository):
    """测试用内存仓储：dict 存储，不放入 production 包。"""

    def __init__(self) -> None:
        self._seeds: dict[str, Seed] = {}
        self._memory_cards: dict[str, MemoryCard] = {}
        self._court_cases: dict[str, CourtCase] = {}
        self._dream_records: dict[str, DreamRecord] = {}
        self._compost_records: dict[str, CompostRecord] = {}
        self._greenhouse_records: dict[str, GreenhouseRecord] = {}
        self._pruning_records: dict[str, PruningRecord] = {}
        self._garden_events: dict[str, GardenEvent] = {}
        # 简易温室占用：用于 list_memory_cards(include_greenhouse=False) 过滤，不做完整业务规则
        self._memory_ids_in_greenhouse: set[str] = set()

    @staticmethod
    def _filter_memory_rows(
        cards: dict[str, MemoryCard],
        *,
        lifecycle: MemoryLifecycle | None,
        include_greenhouse: bool,
        greenhouse_ids: set[str],
    ) -> list[MemoryCard]:
        rows = list(cards.values())
        if lifecycle is not None:
            rows = [m for m in rows if m.lifecycle == lifecycle]
        if not include_greenhouse:
            rows = [m for m in rows if m.id not in greenhouse_ids]
        rows.sort(key=lambda m: m.created_at, reverse=True)
        return rows

    @staticmethod
    def _take_limit(items: list[Any], limit: int | None) -> list[Any]:
        if limit is None:
            return items
        return items[:limit]

    def save_seed(self, seed: Seed) -> Seed:
        if seed.id in self._seeds:
            raise DuplicateIdError(seed.id)
        self._seeds[seed.id] = seed
        return seed

    def get_seed(self, seed_id: str) -> Seed:
        if seed_id not in self._seeds:
            raise NotFoundError(seed_id)
        return self._seeds[seed_id]

    def list_seeds(
        self,
        status: SeedStatus | None = None,
        limit: int | None = None,
    ) -> list[Seed]:
        rows = [s for s in self._seeds.values() if status is None or s.status == status]
        return self._take_limit(rows, limit)

    def update_seed(self, seed: Seed) -> Seed:
        if seed.id not in self._seeds:
            raise NotFoundError(seed.id)
        self._seeds[seed.id] = seed
        return seed

    def save_memory_card(self, memory: MemoryCard) -> MemoryCard:
        if memory.id in self._memory_cards:
            raise DuplicateIdError(memory.id)
        self._memory_cards[memory.id] = memory
        return memory

    def get_memory_card(self, memory_id: str) -> MemoryCard:
        if memory_id not in self._memory_cards:
            raise NotFoundError(memory_id)
        return self._memory_cards[memory_id]

    def list_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int | None = None,
    ) -> list[MemoryCard]:
        rows = self._filter_memory_rows(
            self._memory_cards,
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            greenhouse_ids=self._memory_ids_in_greenhouse,
        )
        return self._take_limit(rows, limit)

    def list_memory_cards_paged(
        self,
        *,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int,
        offset: int = 0,
    ) -> list[MemoryCard]:
        rows = self._filter_memory_rows(
            self._memory_cards,
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            greenhouse_ids=self._memory_ids_in_greenhouse,
        )
        start = max(0, offset)
        return rows[start : start + limit]

    def count_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
    ) -> int:
        return len(
            self._filter_memory_rows(
                self._memory_cards,
                lifecycle=lifecycle,
                include_greenhouse=include_greenhouse,
                greenhouse_ids=self._memory_ids_in_greenhouse,
            )
        )

    def update_memory_card(self, memory: MemoryCard) -> MemoryCard:
        if memory.id not in self._memory_cards:
            raise NotFoundError(memory.id)
        self._memory_cards[memory.id] = memory
        return memory

    def delete_memory_card(self, memory_id: str) -> None:
        if memory_id not in self._memory_cards:
            raise NotFoundError(memory_id)
        del self._memory_cards[memory_id]

    def save_court_case(self, case: CourtCase) -> CourtCase:
        if case.id in self._court_cases:
            raise DuplicateIdError(case.id)
        self._court_cases[case.id] = case
        return case

    def get_court_case(self, case_id: str) -> CourtCase:
        if case_id not in self._court_cases:
            raise NotFoundError(case_id)
        return self._court_cases[case_id]

    def delete_court_case(self, case_id: str) -> None:
        if case_id not in self._court_cases:
            raise NotFoundError(case_id)
        del self._court_cases[case_id]

    def list_court_cases(
        self,
        seed_id: str | None = None,
        limit: int | None = None,
    ) -> list[CourtCase]:
        rows = [c for c in self._court_cases.values() if seed_id is None or c.seed_id == seed_id]
        return self._take_limit(rows, limit)

    def save_dream_record(self, record: DreamRecord) -> DreamRecord:
        if record.id in self._dream_records:
            raise DuplicateIdError(record.id)
        self._dream_records[record.id] = record
        return record

    def get_dream_record(self, record_id: str) -> DreamRecord:
        if record_id not in self._dream_records:
            raise NotFoundError(record_id)
        return self._dream_records[record_id]

    def list_dream_records(self, limit: int | None = None) -> list[DreamRecord]:
        return self._take_limit(list(self._dream_records.values()), limit)

    def save_compost_record(self, record: CompostRecord) -> CompostRecord:
        if record.id in self._compost_records:
            raise DuplicateIdError(record.id)
        self._compost_records[record.id] = record
        return record

    def get_compost_record(self, record_id: str) -> CompostRecord:
        if record_id not in self._compost_records:
            raise NotFoundError(record_id)
        return self._compost_records[record_id]

    def list_compost_records(
        self,
        source_seed_id: str | None = None,
        source_memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[CompostRecord]:
        rows = list(self._compost_records.values())
        if source_seed_id is not None:
            rows = [r for r in rows if r.source_seed_id == source_seed_id]
        if source_memory_id is not None:
            rows = [r for r in rows if r.source_memory_id == source_memory_id]
        return self._take_limit(rows, limit)

    def save_greenhouse_record(self, record: GreenhouseRecord) -> GreenhouseRecord:
        if record.id in self._greenhouse_records:
            raise DuplicateIdError(record.id)
        self._greenhouse_records[record.id] = record
        self._memory_ids_in_greenhouse.add(record.memory_id)
        return record

    def get_greenhouse_record(self, record_id: str) -> GreenhouseRecord:
        if record_id not in self._greenhouse_records:
            raise NotFoundError(record_id)
        return self._greenhouse_records[record_id]

    def list_greenhouse_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[GreenhouseRecord]:
        rows = [
            r for r in self._greenhouse_records.values() if memory_id is None or r.memory_id == memory_id
        ]
        return self._take_limit(rows, limit)

    def save_pruning_record(self, record: PruningRecord) -> PruningRecord:
        if record.id in self._pruning_records:
            raise DuplicateIdError(record.id)
        self._pruning_records[record.id] = record
        return record

    def get_pruning_record(self, record_id: str) -> PruningRecord:
        if record_id not in self._pruning_records:
            raise NotFoundError(record_id)
        return self._pruning_records[record_id]

    def list_pruning_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[PruningRecord]:
        rows = [r for r in self._pruning_records.values() if memory_id is None or r.memory_id == memory_id]
        return self._take_limit(rows, limit)

    def save_garden_event(self, event: GardenEvent) -> GardenEvent:
        if event.id in self._garden_events:
            raise DuplicateIdError(event.id)
        self._garden_events[event.id] = event
        return event

    def get_garden_event(self, event_id: str) -> GardenEvent:
        if event_id not in self._garden_events:
            raise NotFoundError(event_id)
        return self._garden_events[event_id]

    def list_garden_events(
        self,
        event_type: GardenEventType | None = None,
        object_type: GardenObjectType | None = None,
        object_id: str | None = None,
        limit: int | None = None,
    ) -> list[GardenEvent]:
        rows = list(self._garden_events.values())
        if event_type is not None:
            rows = [e for e in rows if e.event_type == event_type]
        if object_type is not None:
            rows = [e for e in rows if e.object_type == object_type]
        if object_id is not None:
            rows = [e for e in rows if e.object_id == object_id]
        return self._take_limit(rows, limit)


def _sample_verdict() -> CourtVerdict:
    return CourtVerdict(verdict=CourtVerdictType.plant, reason="测试判决")


def test_fake_seed_save_get_list_update() -> None:
    repo = FakeGardenRepository()
    s = Seed(content="c1", source_excerpt="e1", status=SeedStatus.pending)
    assert repo.save_seed(s) is s
    assert repo.get_seed(s.id) == s
    assert repo.list_seeds() == [s]
    assert repo.list_seeds(status=SeedStatus.pending) == [s]
    assert repo.list_seeds(status=SeedStatus.planted) == []

    s2 = s.model_copy(update={"status": SeedStatus.in_court})
    assert repo.update_seed(s2).status == SeedStatus.in_court
    assert repo.get_seed(s.id).status == SeedStatus.in_court


def test_fake_memory_card_save_get_list_update_delete() -> None:
    repo = FakeGardenRepository()
    m = MemoryCard(title="t", essence="e", fragrance="f", thorns="th", memory_type=MemoryType.project)
    repo.save_memory_card(m)
    assert repo.get_memory_card(m.id) == m
    assert repo.list_memory_cards() == [m]

    m2 = m.model_copy(update={"essence": "新摘要"})
    repo.update_memory_card(m2)
    assert repo.get_memory_card(m.id).essence == "新摘要"

    repo.delete_memory_card(m.id)
    with pytest.raises(NotFoundError):
        repo.get_memory_card(m.id)


def test_fake_court_case_dream_append_only_save_get_list() -> None:
    repo = FakeGardenRepository()
    verdict = _sample_verdict()
    case = CourtCase(
        seed_id="sid",
        prosecutor_argument="p",
        defender_argument="d",
        privacy_guard_argument="pg",
        judge_verdict=verdict,
    )
    repo.save_court_case(case)
    assert repo.get_court_case(case.id) == case
    assert repo.list_court_cases(seed_id="sid") == [case]

    dr = DreamRecord(
        observation="o",
        reflection="r",
        transformation="t",
        morning_garden="m",
    )
    repo.save_dream_record(dr)
    assert repo.get_dream_record(dr.id) == dr
    assert repo.list_dream_records() == [dr]


def test_fake_compost_greenhouse_pruning_garden_event_save_get_list() -> None:
    repo = FakeGardenRepository()
    cp = CompostRecord(
        source_seed_id="s1",
        discarded_surface="x",
        reason="r",
    )
    repo.save_compost_record(cp)
    assert repo.get_compost_record(cp.id) == cp
    assert repo.list_compost_records(source_seed_id="s1") == [cp]

    gh = GreenhouseRecord(memory_id="mem1", reason="敏感")
    repo.save_greenhouse_record(gh)
    assert repo.get_greenhouse_record(gh.id) == gh
    assert repo.list_greenhouse_records(memory_id="mem1") == [gh]

    pr = PruningRecord(
        memory_id="mem1",
        reason="修剪",
        old_lifecycle=MemoryLifecycle.bloom,
        new_lifecycle=MemoryLifecycle.pruned,
    )
    repo.save_pruning_record(pr)
    assert repo.get_pruning_record(pr.id) == pr
    assert repo.list_pruning_records(memory_id="mem1") == [pr]

    ev = GardenEvent(
        event_type=GardenEventType.seed_created,
        object_type=GardenObjectType.seed,
        object_id="oid",
        summary="摘要",
    )
    repo.save_garden_event(ev)
    assert repo.get_garden_event(ev.id) == ev


def test_get_not_found_raises() -> None:
    repo = FakeGardenRepository()
    with pytest.raises(NotFoundError):
        repo.get_seed("nope")
    with pytest.raises(NotFoundError):
        repo.get_memory_card("nope")
    with pytest.raises(NotFoundError):
        repo.get_court_case("nope")
    with pytest.raises(NotFoundError):
        repo.get_dream_record("nope")
    with pytest.raises(NotFoundError):
        repo.get_compost_record("nope")
    with pytest.raises(NotFoundError):
        repo.get_greenhouse_record("nope")
    with pytest.raises(NotFoundError):
        repo.get_pruning_record("nope")
    with pytest.raises(NotFoundError):
        repo.get_garden_event("nope")


def test_duplicate_save_raises_duplicate_id_error() -> None:
    repo = FakeGardenRepository()
    s = Seed(content="a", source_excerpt="b")
    repo.save_seed(s)
    with pytest.raises(DuplicateIdError):
        repo.save_seed(s)

    m = MemoryCard(title="t", essence="e", fragrance="f", thorns="x")
    repo.save_memory_card(m)
    with pytest.raises(DuplicateIdError):
        repo.save_memory_card(m)


def test_list_memory_cards_include_greenhouse_parameter_works() -> None:
    """验证 include_greenhouse 参数存在且 False 时可排除已登记温室记忆（Fake 简化规则）。"""
    repo = FakeGardenRepository()
    m = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
    repo.save_memory_card(m)
    assert repo.list_memory_cards(include_greenhouse=False) == [m]
    gh = GreenhouseRecord(memory_id=m.id, reason="进温室")
    repo.save_greenhouse_record(gh)
    assert repo.list_memory_cards(include_greenhouse=False) == []
    assert repo.list_memory_cards(include_greenhouse=True) == [m]


def test_list_garden_events_filters() -> None:
    repo = FakeGardenRepository()
    e1 = GardenEvent(
        event_type=GardenEventType.verdict_made,
        object_type=GardenObjectType.court_case,
        object_id="c1",
        summary="s1",
    )
    e2 = GardenEvent(
        event_type=GardenEventType.seed_created,
        object_type=GardenObjectType.seed,
        object_id="s1",
        summary="s2",
    )
    repo.save_garden_event(e1)
    repo.save_garden_event(e2)

    assert repo.list_garden_events(event_type=GardenEventType.verdict_made) == [e1]
    assert repo.list_garden_events(object_type=GardenObjectType.seed) == [e2]
    assert repo.list_garden_events(object_id="c1") == [e1]
    assert repo.list_garden_events(
        event_type=GardenEventType.seed_created,
        object_id="s1",
    ) == [e2]


def test_fake_repo_is_garden_repository_instance() -> None:
    repo = FakeGardenRepository()
    assert isinstance(repo, GardenRepository)


def test_list_compost_records_and_filters() -> None:
    repo = FakeGardenRepository()
    c1 = CompostRecord(
        source_seed_id="sa",
        discarded_surface="d1",
        reason="r1",
    )
    c2 = CompostRecord(
        source_memory_id="mb",
        discarded_surface="d2",
        reason="r2",
    )
    repo.save_compost_record(c1)
    repo.save_compost_record(c2)
    all_rows = repo.list_compost_records()
    assert len(all_rows) == 2
    assert {r.id for r in all_rows} == {c1.id, c2.id}
    assert repo.list_compost_records(source_seed_id="sa") == [c1]
    assert repo.list_compost_records(source_memory_id="mb") == [c2]
