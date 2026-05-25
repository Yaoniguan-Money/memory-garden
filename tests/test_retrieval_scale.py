"""Stage 17a：检索规模与截断 diagnostics 测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.models import HarvestQuery
from memory_garden.harvest.retrieval_diagnostics import RETRIEVAL_DIAGNOSTICS_KEY
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden

_SCALE_MARKER = "zzscale501marker"
_FILLER_PREFIX = "scale filler"


def _product(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    return garden, ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)


def _assert_truncation_invariant(diag: dict) -> None:
    assert diag["truncated"] == (diag["scanned_count"] < diag["total_available"])


def _seed_scale_library(repo, *, total: int, marker: str) -> MemoryCard:
    """写入 total 条记忆：最新 total-1 条为 filler，最旧 1 条含唯一 marker。"""
    now = datetime.now(timezone.utc)
    for i in range(total - 1):
        repo.save_memory_card(
            MemoryCard(
                id=f"scale-filler-{i}",
                title=f"{_FILLER_PREFIX} {i}",
                essence=f"{_FILLER_PREFIX} content {i}",
                fragrance="neutral",
                thorns="none",
                created_at=now - timedelta(seconds=i),
            )
        )
    return repo.save_memory_card(
        MemoryCard(
            id="scale-target-oldest",
            title=f"{marker} target",
            essence=f"unique {marker} essence",
            fragrance=f"unique {marker} fragrance",
            thorns="none",
            created_at=now - timedelta(days=365),
        )
    )


def test_product_retrieval_fts_finds_oldest_target(tmp_path):
    from memory_garden.soil.index import reindex_garden

    garden, product = _product(tmp_path)
    try:
        target = _seed_scale_library(garden.core.repository, total=501, marker=_SCALE_MARKER)
        reindex_garden(garden.home.root, dry_run=False)

        result = product.retrieve(_SCALE_MARKER, limit=5)
        diag = result.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
        assert diag is not None
        assert diag["source"] == "product_retrieval"
        assert diag["total_available"] == 501
        assert diag["scanned_count"] < 501
        assert diag["candidate_source"] == "fts"
        assert diag["truncated"] is True
        _assert_truncation_invariant(diag)
        assert result.hits
        assert result.hits[0].memory.id == target.id
    finally:
        garden.close()


def test_product_retrieval_in_memory_bounded_scan(tmp_path):
    garden, product = _product(tmp_path)
    try:
        _seed_scale_library(garden.core.repository, total=501, marker=_SCALE_MARKER)

        result = product.retrieve(_SCALE_MARKER, limit=5)
        diag = result.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
        assert diag is not None
        assert diag["source"] == "product_retrieval"
        assert diag["total_available"] == 501
        assert diag["scanned_count"] == 500
        assert diag["candidate_source"] == "in_memory"
        assert diag["truncated"] is True
        _assert_truncation_invariant(diag)
    finally:
        garden.close()


def test_product_retrieval_diagnostics_when_library_within_scan_limit(tmp_path):
    garden, product = _product(tmp_path)
    try:
        target = _seed_scale_library(garden.core.repository, total=50, marker=_SCALE_MARKER)

        result = product.retrieve(_SCALE_MARKER, limit=3)
        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["total_available"] == 50
        assert diag["scanned_count"] == 50
        assert diag["truncated"] is False
        _assert_truncation_invariant(diag)
        assert result.hits
        assert result.hits[0].memory.id == target.id
    finally:
        garden.close()


def test_harvest_trace_includes_retrieval_diagnostics(tmp_path):
    now = datetime.now(timezone.utc)
    memories = [
        MemoryCard(
            id="harvest-diag-1",
            title="harvest diag alpha",
            essence="harvest diag alpha essence",
            fragrance="neutral",
            thorns="none",
            created_at=now,
        ),
        MemoryCard(
            id="harvest-diag-2",
            title="harvest diag beta",
            essence="harvest diag beta essence",
            fragrance="neutral",
            thorns="none",
            created_at=now - timedelta(seconds=1),
        ),
    ]
    harvester = GardenHarvester()
    query = HarvestQuery(raw_user_text="harvest diag alpha")
    trace = harvester.harvest(query, memories)

    diag = trace.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
    assert diag is not None
    assert diag["source"] == "harvest_rules"
    assert diag["total_available"] == 2
    assert diag["scanned_count"] == 2
    assert diag["candidate_count"] >= 1
    assert diag["truncated"] is False
    _assert_truncation_invariant(diag)


def test_harvest_trace_honors_total_available_metadata_for_truncation():
    now = datetime.now(timezone.utc)
    memories = [
        MemoryCard(
            id="harvest-partial-1",
            title="partial scan memory",
            essence="partial scan memory essence",
            fragrance="neutral",
            thorns="none",
            created_at=now,
        )
    ]
    harvester = GardenHarvester()
    query = HarvestQuery(
        raw_user_text="partial scan memory",
        metadata={"total_available": 501, "retrieval_source": "harvest_test_subset"},
    )
    trace = harvester.harvest(query, memories)

    diag = trace.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
    assert diag["source"] == "harvest_test_subset"
    assert diag["total_available"] == 501
    assert diag["scanned_count"] == 1
    assert diag["truncated"] is True
    _assert_truncation_invariant(diag)


def test_resolve_memory_id_finds_oldest_memory_across_pages(tmp_path):
    garden, product = _product(tmp_path)
    try:
        target = _seed_scale_library(garden.core.repository, total=501, marker=_SCALE_MARKER)
        resolved = product.resolve_memory_id(_SCALE_MARKER)
        assert resolved == target.id
    finally:
        garden.close()


def test_conflict_scan_detects_oldest_duplicate_and_reports_diagnostics(tmp_path):
    garden, product = _product(tmp_path)
    try:
        target = _seed_scale_library(garden.core.repository, total=501, marker=_SCALE_MARKER)
        proposals = product.propose(f"remember: unique {_SCALE_MARKER} preference update")
        assert proposals
        proposal = proposals[0]
        diag = proposal.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
        assert diag is not None
        assert diag["total_available"] == 501
        assert diag["scanned_count"] == 501
        assert diag["truncated"] is False
        _assert_truncation_invariant(diag)
    finally:
        garden.close()


def test_runtime_harvest_reports_truncation_metadata(tmp_path):
    from memory_garden.harvest import GardenHarvester, RuntimeGardenHarvesterAdapter
    from memory_garden.harvest.bounded_scan import create_bounded_runtime_memory_provider
    from memory_garden.runtime.session import TurnContext

    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        repo = garden.core.repository
        now = datetime.now(timezone.utc)
        for i in range(501):
            repo.save_memory_card(
                MemoryCard(
                    id=f"runtime-scale-{i}",
                    title=f"runtime filler {i}",
                    essence=f"runtime filler content {i}",
                    fragrance="neutral",
                    thorns="none",
                    created_at=now - timedelta(seconds=i),
                )
            )
        adapter = RuntimeGardenHarvesterAdapter(
            GardenHarvester(),
            memory_provider=create_bounded_runtime_memory_provider(repo),
        )
        adapter.harvest(
            TurnContext(session_id="runtime-scale", turn_index=0, user_message="runtime filler 0")
        )
        trace = adapter.last_trace
        assert trace is not None
        diag = trace.metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
        assert diag is not None
        assert diag["total_available"] == 501
        assert diag["scanned_count"] == 500
        assert diag["truncated"] is True
        _assert_truncation_invariant(diag)
    finally:
        garden.close()
