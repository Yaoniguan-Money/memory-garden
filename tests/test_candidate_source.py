"""Stage 17c：CandidateSource 粗召回测试。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.candidate_source import (
    FtsCandidateSource,
    InMemoryCandidateSource,
    select_product_candidate_source,
)
from memory_garden.harvest.retrieval_diagnostics import PRODUCT_SCAN_LIMIT, RETRIEVAL_DIAGNOSTICS_KEY
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.index import reindex_garden


def _product(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    return garden, ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)


def test_missing_fts_index_uses_in_memory_without_error(tmp_path):
    garden, product = _product(tmp_path)
    try:
        card = garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-inmem-1",
                title="in memory recall marker",
                essence="in memory recall marker essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        result = product.retrieve("in memory recall marker", limit=3)
        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["candidate_source"] == "in_memory"
        assert diag["scanned_count"] <= PRODUCT_SCAN_LIMIT
        assert result.hits
        assert result.hits[0].memory.id == card.id
    finally:
        garden.close()


def test_fts_backed_retrieval_returns_expected_memory_id(tmp_path):
    garden, product = _product(tmp_path)
    try:
        card = garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-fts-1",
                title="fts unique alpha marker",
                essence="fts unique alpha marker essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        reindex_garden(garden.home.root, dry_run=False)
        result = product.retrieve("fts unique alpha marker", limit=3)
        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["candidate_source"] == "fts"
        assert diag["scanned_count"] < 200
        assert result.hits
        assert result.hits[0].memory.id == card.id

        source = select_product_candidate_source(garden.home.root, garden.core.repository)
        coarse = source.recall("fts unique alpha marker", top_m=10)
        assert coarse.candidate_source == "fts"
        assert card.id in coarse.memory_ids
    finally:
        garden.close()


def test_fts_primary_does_not_run_full_in_memory_scan(tmp_path):
    garden, product = _product(tmp_path)
    try:
        for i in range(120):
            garden.core.repository.save_memory_card(
                MemoryCard(
                    id=f"fts-no-union-{i}",
                    title=f"filler token {i}",
                    essence=f"filler content {i}",
                    fragrance="neutral",
                    thorns="none",
                )
            )
        target = garden.core.repository.save_memory_card(
            MemoryCard(
                id="fts-no-union-target",
                title="fts union guard marker",
                essence="fts union guard marker essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        reindex_garden(garden.home.root, dry_run=False)
        result = product.retrieve("fts union guard marker", limit=3)
        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["candidate_source"] == "fts"
        assert diag["scanned_count"] < 121
        assert result.hits[0].memory.id == target.id
    finally:
        garden.close()


def test_fts_source_directly(tmp_path):
    garden, product_sys = _product(tmp_path)
    try:
        card = garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-fts-direct",
                title="direct fts beta marker",
                essence="direct fts beta marker essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        reindex_garden(garden.home.root, dry_run=False)
        fts = FtsCandidateSource(garden.home.root, garden.core.repository)
        coarse = fts.recall("direct fts beta marker", top_m=5)
        assert coarse.candidate_source == "fts"
        assert coarse.scanned_count <= 5
        assert coarse.total_available == 1
        assert card.id in coarse.memory_ids
    finally:
        garden.close()


def test_in_memory_source_preserves_lexical_recall_within_bound(tmp_path):
    garden, product_sys = _product(tmp_path)
    try:
        card = garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-lex-1",
                title="lexical gamma marker",
                essence="lexical gamma marker essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        source = InMemoryCandidateSource(garden.core.repository)
        coarse = source.recall("lexical gamma marker", top_m=20)
        assert coarse.candidate_source == "in_memory"
        assert coarse.scanned_count <= PRODUCT_SCAN_LIMIT
        assert card.id in coarse.memory_ids
    finally:
        garden.close()


def test_product_retrieval_1000_memories_bounded_without_fts(tmp_path):
    garden, product = _product(tmp_path)
    try:
        marker = "zzbench1000nofts"
        now = datetime.now(timezone.utc)
        for i in range(999):
            garden.core.repository.save_memory_card(
                MemoryCard(
                    id=f"bench-nofts-{i}",
                    title=f"bench filler {i}",
                    essence=f"bench filler content {i}",
                    fragrance="neutral",
                    thorns="none",
                    created_at=now - timedelta(seconds=i),
                )
            )
        target = garden.core.repository.save_memory_card(
            MemoryCard(
                id="bench-nofts-target",
                title=f"{marker} target",
                essence=f"unique {marker} essence",
                fragrance="neutral",
                thorns="none",
                created_at=now - timedelta(days=400),
            )
        )

        start = time.perf_counter()
        result = product.retrieve(marker, limit=5)
        latency_ms = (time.perf_counter() - start) * 1000.0

        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["candidate_source"] == "in_memory"
        assert diag["total_available"] == 1000
        assert diag["scanned_count"] == PRODUCT_SCAN_LIMIT
        assert diag["scanned_count"] < 1000
        assert diag["truncated"] is True
        assert latency_ms < 30_000
        assert target.id not in {hit.memory.id for hit in result.hits}
    finally:
        garden.close()


def test_product_retrieval_1000_memories_fts_primary(tmp_path):
    garden, product = _product(tmp_path)
    try:
        marker = "zzbench1000fts"
        for i in range(999):
            garden.core.repository.save_memory_card(
                MemoryCard(
                    id=f"bench-fts-{i}",
                    title=f"bench fts filler {i}",
                    essence=f"bench fts filler content {i}",
                    fragrance="neutral",
                    thorns="none",
                )
            )
        target = garden.core.repository.save_memory_card(
            MemoryCard(
                id="bench-fts-target",
                title=f"{marker} target",
                essence=f"unique {marker} essence",
                fragrance="neutral",
                thorns="none",
            )
        )
        reindex_garden(garden.home.root, dry_run=False)

        start = time.perf_counter()
        result = product.retrieve(marker, limit=5)
        latency_ms = (time.perf_counter() - start) * 1000.0

        diag = result.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["candidate_source"] == "fts"
        assert diag["total_available"] == 1000
        assert diag["scanned_count"] < 1000
        assert diag["truncated"] is True
        assert result.hits
        assert result.hits[0].memory.id == target.id
        assert latency_ms < 30_000
    finally:
        garden.close()


def test_product_retrieval_micro_benchmark_reports_latency(tmp_path, capsys):
    """1000 条库：对比无 FTS / 有 FTS 的 scanned_count 与 latency。"""
    garden, product = _product(tmp_path)
    try:
        marker = "zzmicrobench1000"
        for i in range(1000):
            garden.core.repository.save_memory_card(
                MemoryCard(
                    id=f"micro-{i}",
                    title=f"micro filler {i}",
                    essence=f"micro filler content {i}",
                    fragrance="neutral",
                    thorns="none",
                )
            )
        garden.core.repository.save_memory_card(
            MemoryCard(
                id="micro-target",
                title=f"{marker} target",
                essence=f"unique {marker} essence",
                fragrance="neutral",
                thorns="none",
            )
        )

        start = time.perf_counter()
        no_fts = product.retrieve(marker, limit=5)
        no_fts_ms = (time.perf_counter() - start) * 1000.0
        no_fts_diag = no_fts.metadata[RETRIEVAL_DIAGNOSTICS_KEY]

        reindex_garden(garden.home.root, dry_run=False)
        product._candidate_source = None

        start = time.perf_counter()
        with_fts = product.retrieve(marker, limit=5)
        with_fts_ms = (time.perf_counter() - start) * 1000.0
        with_fts_diag = with_fts.metadata[RETRIEVAL_DIAGNOSTICS_KEY]

        print(
            f"micro-benchmark no_fts: latency_ms={no_fts_ms:.2f} "
            f"scanned_count={no_fts_diag['scanned_count']} "
            f"candidate_source={no_fts_diag['candidate_source']}"
        )
        print(
            f"micro-benchmark with_fts: latency_ms={with_fts_ms:.2f} "
            f"scanned_count={with_fts_diag['scanned_count']} "
            f"candidate_source={with_fts_diag['candidate_source']}"
        )

        assert no_fts_diag["scanned_count"] == PRODUCT_SCAN_LIMIT
        assert no_fts_diag["candidate_source"] == "in_memory"
        assert with_fts_diag["scanned_count"] < 1000
        assert with_fts_diag["candidate_source"] == "fts"
        assert with_fts.hits[0].memory.id == "micro-target"
    finally:
        garden.close()
