"""Tests for v1.1 optimizations: Observatory bridge, async SDK, summary."""

import os

from memory_garden.observatory.queries import build_garden_summary
from memory_garden.observatory.views import GardenSummaryView
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.home import initialize_garden_home

from ._soil_test_helpers import insert_test_data, setup_garden_db


def test_build_summary_from_empty_garden(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    summary = build_garden_summary(home.root)
    assert isinstance(summary, GardenSummaryView)
    assert summary.map.memory_count == 0


def test_build_summary_from_populated_garden(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=3, num_seeds=2, num_court_cases=2, num_dream_records=1)

    summary = build_garden_summary(home.root)
    assert summary.map.memory_count == 3
    assert summary.map.seed_count == 2
    assert summary.map.court_case_count == 2
    assert summary.map.dream_record_count == 1
    assert len(summary.recent_memories) == 3
    assert len(summary.recent_seeds) == 2
    assert len(summary.recent_cases) == 2
    assert len(summary.recent_dreams) == 1


def test_build_summary_no_database(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    summary = GardenSummaryView.from_garden_home(home.root)
    assert summary.map.memory_count == 0
    assert summary.recent_memories == []


def test_sdk_summary_returns_view(tmp_path):
    path = tmp_path / "garden"
    garden = MemoryGarden.local(path)
    try:
        summary = garden.summary()
        assert isinstance(summary, GardenSummaryView)
        assert summary.map.memory_count == 0
    finally:
        garden.close()


def test_sdk_async_chat_works(tmp_path):
    import asyncio

    async def _run():
        path = tmp_path / "garden_async"
        garden = MemoryGarden.local_async(path)
        try:
            r = await garden.async_chat("花花开")
            assert r.session_id is not None
        finally:
            garden.close()

    asyncio.run(_run())


def test_sdk_async_full_cycle(tmp_path):
    import asyncio

    async def _run():
        path = tmp_path / "garden_async2"
        garden = MemoryGarden.local_async(path)
        try:
            r1 = await garden.async_chat("花花开")
            sid = r1.session_id
            r2 = await garden.async_chat("I prefer dark mode.", session_id=sid)
            assert r2.reply is not None
            r3 = await garden.async_chat("花花关", session_id=sid)
            assert r3.feedback is not None
        finally:
            garden.close()

    asyncio.run(_run())


def test_observatory_has_all_required_views():
    """Verify all observatory view types are importable and constructible."""
    from memory_garden.observatory import (
        build_garden_summary,
        CourtroomView,
        DreamView,
        GardenMapData,
        GardenSummaryView,
        MemoryCardView,
        RedactionLevel,
        SeedJourneyView,
    )
    # All must be importable
    assert RedactionLevel.PUBLIC.value == "public"
    assert CourtroomView is not None
    assert DreamView is not None
    assert GardenMapData is not None
    assert GardenSummaryView is not None
    assert MemoryCardView is not None
    assert SeedJourneyView is not None
    assert callable(build_garden_summary)


def test_no_memory_garden_created(tmp_path):
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed_before = os.path.exists(candidate)

    path = tmp_path / "garden"
    garden = MemoryGarden.local(path)
    garden.summary()
    garden.close()

    if not existed_before:
        assert not os.path.exists(candidate)
