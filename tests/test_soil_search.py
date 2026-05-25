"""Tests for Garden Soil FTS5 search."""

import json
import sqlite3

from memory_garden.soil.index import reindex_garden
from memory_garden.soil.home import initialize_garden_home
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.search import search_garden, search_garden_scoped

from ._soil_test_helpers import insert_test_data, setup_garden_db


def _setup_index(garden_home, num_memories=5):
    setup_garden_db(garden_home)
    insert_test_data(garden_home, num_memories=num_memories)
    reindex_garden(garden_home, dry_run=False)


def test_search_finds_memory_card(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)

    hits = search_garden(home.root, "preference")
    assert len(hits) >= 1
    assert any("preference" in h.snippet.lower() for h in hits)
    assert all(h.target_type == "memory_card" for h in hits)


def test_search_limit_respected(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=10)

    hits = search_garden(home.root, "memory", limit=3)
    assert len(hits) <= 3


def test_search_limit_clamped_to_max(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=5)

    hits = search_garden(home.root, "memory", limit=9999)
    assert len(hits) <= 200


def test_search_target_types_filter(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)

    insert_test_data(home.root, num_seeds=2)
    reindex_garden(home.root, dry_run=False)

    all_hits = search_garden(home.root, "test")
    has_memory = any(h.target_type == "memory_card" for h in all_hits)
    has_seed = any(h.target_type == "seed" for h in all_hits)

    if has_memory and has_seed:
        filtered = search_garden(home.root, "test", target_types=["memory_card"])
        assert all(h.target_type == "memory_card" for h in filtered)
    else:
        # At least the filter shouldn't crash
        filtered = search_garden(home.root, "test", target_types=["memory_card"])
        assert all(h.target_type == "memory_card" for h in filtered)


def test_search_empty_query_returns_empty(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)

    assert search_garden(home.root, "") == []
    assert search_garden(home.root, "   ") == []


def test_search_no_index_returns_empty(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=3)
    # No reindex called

    hits = search_garden(home.root, "preference")
    assert hits == []


def test_search_no_database_returns_empty(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    hits = search_garden(home.root, "anything")
    assert hits == []


def test_search_hit_has_required_fields(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)

    hits = search_garden(home.root, "preference")
    assert len(hits) >= 1
    hit = hits[0]
    assert hit.target_type
    assert hit.target_id
    assert hasattr(hit, "title")
    assert hasattr(hit, "snippet")
    assert hasattr(hit, "rank")
    assert isinstance(hit.metadata, dict)


def test_search_models_json_roundtrip():
    from memory_garden.soil.models import GardenSearchHit

    hit = GardenSearchHit(
        target_type="memory_card",
        target_id="m1",
        title="Test Memory",
        snippet="this is a test",
        rank=1.5,
        metadata={"key": "value"},
    )
    data = hit.model_dump(mode="json")
    h2 = GardenSearchHit(**data)
    assert h2.target_type == "memory_card"
    assert h2.target_id == "m1"
    assert h2.rank == 1.5


def test_scoped_search_filters_project_strategy_profiles(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        product = ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)
        atlas = product.remember(
            "remember: project release notes should include rollback steps",
            mode="trusted",
            metadata={"project_id": "atlas"},
        )["approved_memory_ids"][0]
        zephyr = product.remember(
            "remember: project release notes should include customer impact",
            mode="trusted",
            metadata={"project_id": "zephyr"},
        )["approved_memory_ids"][0]
        reindex_garden(garden.home.root, dry_run=False)

        unscoped_ids = {hit.target_id for hit in search_garden(garden.home.root, "release notes")}
        scoped_ids = {
            hit.target_id
            for hit in search_garden_scoped(
                garden.home.root,
                "release notes",
                project_id="atlas",
            )
        }

        assert atlas in unscoped_ids
        assert zephyr in unscoped_ids
        assert atlas in scoped_ids
        assert zephyr not in scoped_ids
    finally:
        garden.close()


def test_scoped_search_does_not_create_product_tables(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)

    hits = search_garden_scoped(home.root, "preference", project_id="atlas")
    conn = sqlite3.connect(str(home.root / "garden.db"))
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_strategy_profiles'"
        ).fetchone()
    finally:
        conn.close()

    assert hits == []
    assert table is None


def test_cjk_ngram_search_finds_continuous_chinese(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    conn = sqlite3.connect(str(home.root / "garden.db"))
    try:
        payload = {
            "id": "mem-cjk-1",
            "title": "深色模式偏好",
            "essence": "用户偏好深色模式界面护眼",
            "fragrance": "neutral",
            "thorns": "none",
            "tags": ["preference"],
            "memory_type": "preference",
            "lifecycle": "bloom",
            "sensitivity": "none",
            "confidence": 0.8,
            "importance": 0.6,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        conn.execute(
            """
            INSERT INTO memory_cards (id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mem-cjk-1",
                "2026-01-01T00:00:00+00:00",
                "bloom",
                "preference",
                "none",
                "2026-01-01T00:00:00+00:00",
                json.dumps(payload),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    reindex_garden(home.root, dry_run=False)

    hits = search_garden(home.root, "深色模式")
    assert hits
    assert any(h.target_id == "mem-cjk-1" for h in hits)


def test_english_fts_unchanged_after_ngram_column(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_index(home.root, num_memories=3)
    hits = search_garden(home.root, "preference")
    assert len(hits) >= 1
    assert any("preference" in h.snippet.lower() for h in hits)
