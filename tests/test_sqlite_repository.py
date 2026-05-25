"""SQLiteGardenRepository 集成测试（:memory: 与临时文件）。"""

from __future__ import annotations

import os
import tempfile
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
    PruningRecord,
    Seed,
    SeedStatus,
)
from memory_garden.storage.base import DuplicateIdError, NotFoundError
from memory_garden.storage.sqlite import SQLiteGardenRepository


def test_memory_repository_initializes() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        assert repo is not None
    finally:
        repo.close()


def test_tempfile_roundtrip_reopen() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        seed_id: str | None = None
        r1 = SQLiteGardenRepository(path)
        try:
            s = Seed(content="持久化", source_excerpt="摘")
            seed_id = s.id
            r1.save_seed(s)
        finally:
            r1.close()

        r2 = SQLiteGardenRepository(path)
        try:
            assert seed_id is not None
            got = r2.get_seed(seed_id)
            assert isinstance(got, Seed)
            assert got.content == "持久化"
        finally:
            r2.close()
    finally:
        os.unlink(path)


def test_seed_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        s = Seed(content="c", source_excerpt="e", status=SeedStatus.pending)
        repo.save_seed(s)
        g = repo.get_seed(s.id)
        assert isinstance(g, Seed)
        assert g.model_dump() == s.model_dump()

        s2 = s.model_copy(update={"status": SeedStatus.in_court})
        repo.update_seed(s2)
        assert repo.get_seed(s.id).status == SeedStatus.in_court

        listed = repo.list_seeds(status=SeedStatus.in_court)
        assert len(listed) == 1 and isinstance(listed[0], Seed)
    finally:
        repo.close()


def test_memory_card_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        m = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
        repo.save_memory_card(m)
        g = repo.get_memory_card(m.id)
        assert isinstance(g, MemoryCard)
        m2 = m.model_copy(update={"essence": "新"})
        repo.update_memory_card(m2)
        assert repo.get_memory_card(m.id).essence == "新"
        repo.delete_memory_card(m.id)
        with pytest.raises(NotFoundError):
            repo.get_memory_card(m.id)
    finally:
        repo.close()


def test_court_case_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        case = CourtCase(
            seed_id="sid",
            prosecutor_argument="p",
            defender_argument="d",
            privacy_guard_argument="pg",
            judge_verdict=CourtVerdict(verdict=CourtVerdictType.plant, reason="判"),
        )
        repo.save_court_case(case)
        got = repo.get_court_case(case.id)
        assert isinstance(got, CourtCase)
        assert got.judge_verdict.verdict == CourtVerdictType.plant
        assert repo.list_court_cases(seed_id="sid")[0].id == case.id
    finally:
        repo.close()


def test_dream_record_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        dr = DreamRecord(
            observation="o",
            reflection="r",
            transformation="t",
            morning_garden="m",
        )
        repo.save_dream_record(dr)
        got = repo.get_dream_record(dr.id)
        assert isinstance(got, DreamRecord)
        assert repo.list_dream_records()[0].id == dr.id
    finally:
        repo.close()


def test_compost_record_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        c = CompostRecord(
            source_seed_id="ss",
            discarded_surface="d",
            reason="r",
        )
        repo.save_compost_record(c)
        got = repo.get_compost_record(c.id)
        assert isinstance(got, CompostRecord)
        rows = repo.list_compost_records(source_seed_id="ss")
        assert len(rows) == 1 and rows[0].id == c.id
    finally:
        repo.close()


def test_greenhouse_record_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        g = GreenhouseRecord(memory_id="mid", reason="原因")
        repo.save_greenhouse_record(g)
        got = repo.get_greenhouse_record(g.id)
        assert isinstance(got, GreenhouseRecord)
        assert repo.list_greenhouse_records(memory_id="mid")[0].id == g.id
    finally:
        repo.close()


def test_pruning_record_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        p = PruningRecord(
            memory_id="m",
            reason="r",
            old_lifecycle=MemoryLifecycle.bloom,
            new_lifecycle=MemoryLifecycle.pruned,
        )
        repo.save_pruning_record(p)
        got = repo.get_pruning_record(p.id)
        assert isinstance(got, PruningRecord)
        assert repo.list_pruning_records(memory_id="m")[0].id == p.id
    finally:
        repo.close()


def test_garden_event_metadata_nested_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        meta: dict[str, Any] = {"层级": {"列表": [1, 2, {"k": "v"}]}}
        ev = GardenEvent(
            event_type=GardenEventType.verdict_made,
            object_type=GardenObjectType.court_case,
            object_id="oid",
            summary="摘要",
            metadata=meta,
        )
        repo.save_garden_event(ev)
        got = repo.get_garden_event(ev.id)
        assert isinstance(got, GardenEvent)
        assert got.metadata == meta
        assert repo.list_garden_events()[0].metadata == meta
    finally:
        repo.close()


def test_duplicate_save_raises() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        s = Seed(content="a", source_excerpt="b")
        repo.save_seed(s)
        with pytest.raises(DuplicateIdError):
            repo.save_seed(s)
    finally:
        repo.close()


def test_get_missing_raises() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        with pytest.raises(NotFoundError):
            repo.get_seed("不存在-id")
    finally:
        repo.close()


def test_list_seeds_filter_status() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        a = Seed(content="a", source_excerpt="x", status=SeedStatus.pending)
        b = Seed(content="b", source_excerpt="y", status=SeedStatus.planted)
        repo.save_seed(a)
        repo.save_seed(b)
        pending = repo.list_seeds(status=SeedStatus.pending)
        assert len(pending) == 1 and pending[0].id == a.id
    finally:
        repo.close()


def test_list_memory_cards_filter_lifecycle() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        m1 = MemoryCard(
            title="a",
            essence="e",
            fragrance="f",
            thorns="t",
            lifecycle=MemoryLifecycle.sprout,
        )
        m2 = MemoryCard(
            title="b",
            essence="e2",
            fragrance="f",
            thorns="t",
            lifecycle=MemoryLifecycle.bloom,
        )
        repo.save_memory_card(m1)
        repo.save_memory_card(m2)
        blooms = repo.list_memory_cards(lifecycle=MemoryLifecycle.bloom)
        assert len(blooms) == 1 and blooms[0].id == m2.id
    finally:
        repo.close()


def test_list_memory_cards_exclude_greenhouse_lifecycle_by_default() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        normal = MemoryCard(
            title="n",
            essence="e",
            fragrance="f",
            thorns="t",
            lifecycle=MemoryLifecycle.sprout,
        )
        gh_card = MemoryCard(
            title="g",
            essence="e",
            fragrance="f",
            thorns="t",
            lifecycle=MemoryLifecycle.greenhouse,
        )
        repo.save_memory_card(normal)
        repo.save_memory_card(gh_card)
        default_list = repo.list_memory_cards()
        ids = {m.id for m in default_list}
        assert normal.id in ids and gh_card.id not in ids
        all_inc = repo.list_memory_cards(include_greenhouse=True)
        assert {m.id for m in all_inc} == {normal.id, gh_card.id}
    finally:
        repo.close()


def test_list_garden_events_filters() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        e1 = GardenEvent(
            event_type=GardenEventType.seed_created,
            object_type=GardenObjectType.seed,
            object_id="s1",
            summary="一",
        )
        e2 = GardenEvent(
            event_type=GardenEventType.verdict_made,
            object_type=GardenObjectType.court_case,
            object_id="c1",
            summary="二",
        )
        repo.save_garden_event(e1)
        repo.save_garden_event(e2)
        assert len(repo.list_garden_events(event_type=GardenEventType.seed_created)) == 1
        assert (
            repo.list_garden_events(object_type=GardenObjectType.court_case)[0].id == e2.id
        )
        assert repo.list_garden_events(object_id="s1")[0].id == e1.id
    finally:
        repo.close()


def test_record_types_no_extra_mutators_on_class() -> None:
    """追加型仓储记录仅在 ABC / SQLite 上暴露 save/get/list，无 update/delete。"""
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
        assert not hasattr(SQLiteGardenRepository, name)


def test_all_get_list_return_pydantic_instances() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        seed = Seed(content="x", source_excerpt="y")
        repo.save_seed(seed)
        assert type(repo.get_seed(seed.id)) is Seed
        assert all(type(x) is Seed for x in repo.list_seeds())

        mc = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
        repo.save_memory_card(mc)
        assert type(repo.get_memory_card(mc.id)) is MemoryCard
        assert all(type(x) is MemoryCard for x in repo.list_memory_cards(include_greenhouse=True))

        cc = CourtCase(
            seed_id="s",
            prosecutor_argument="p",
            defender_argument="d",
            privacy_guard_argument="pg",
            judge_verdict=CourtVerdict(verdict=CourtVerdictType.hold, reason="r"),
        )
        repo.save_court_case(cc)
        assert type(repo.get_court_case(cc.id)) is CourtCase

        dr = DreamRecord(
            observation="o",
            reflection="r",
            transformation="t",
            morning_garden="m",
        )
        repo.save_dream_record(dr)
        assert type(repo.get_dream_record(dr.id)) is DreamRecord

        cp = CompostRecord(source_memory_id="m", discarded_surface="d", reason="r")
        repo.save_compost_record(cp)
        assert type(repo.get_compost_record(cp.id)) is CompostRecord

        gh = GreenhouseRecord(memory_id="mid", reason="r")
        repo.save_greenhouse_record(gh)
        assert type(repo.get_greenhouse_record(gh.id)) is GreenhouseRecord

        pr = PruningRecord(
            memory_id="mid",
            reason="r",
            old_lifecycle=MemoryLifecycle.sprout,
            new_lifecycle=MemoryLifecycle.pruned,
        )
        repo.save_pruning_record(pr)
        assert type(repo.get_pruning_record(pr.id)) is PruningRecord

        ge = GardenEvent(
            event_type=GardenEventType.memory_pruned,
            object_type=GardenObjectType.memory_card,
            object_id="id",
            summary="s",
        )
        repo.save_garden_event(ge)
        assert type(repo.get_garden_event(ge.id)) is GardenEvent
        assert all(type(x) is GardenEvent for x in repo.list_garden_events())
    finally:
        repo.close()
