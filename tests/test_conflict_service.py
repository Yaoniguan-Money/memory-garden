"""ConflictService 单元测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.retrieval_diagnostics import RETRIEVAL_DIAGNOSTICS_KEY
from memory_garden.product import ProductMemorySystem
from memory_garden.product.models import MemoryProposal
from memory_garden.product.services.conflict import ConflictService, contradiction_score
from memory_garden.providers import FakeEmbeddingProvider
from memory_garden.sdk import MemoryGarden

_SCALE_MARKER = "zzconflict501"


def _product(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    product = ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)
    return garden, product


def _seed_library(repo, *, total: int) -> None:
    now = datetime.now(timezone.utc)
    for i in range(total):
        repo.save_memory_card(
            MemoryCard(
                id=f"conflict-filler-{i}",
                title=f"conflict filler {i}",
                essence=f"conflict filler content {i}",
                fragrance="neutral",
                thorns="none",
                created_at=now - timedelta(seconds=i),
            )
        )


def test_conflict_service_scans_full_library_without_silent_truncation(tmp_path):
    garden, product = _product(tmp_path)
    try:
        _seed_library(garden.core.repository, total=501)
        proposals = product.propose(f"remember: {_SCALE_MARKER} detailed updates instead of concise")
        assert proposals
        diag = proposals[0].metadata.get(RETRIEVAL_DIAGNOSTICS_KEY)
        assert diag is not None
        assert diag["total_available"] == 501
        assert diag["scanned_count"] == 501
        assert diag["truncated"] is False
    finally:
        garden.close()


def test_conflict_service_detects_correction_with_arbitration(tmp_path):
    garden, product = _product(tmp_path)
    try:
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        existing_id = garden.core.repository.save_memory_card(
            MemoryCard(
                id="conflict-correction-target",
                title="release notes stay concise and short",
                essence="release notes stay concise and short for weekly updates",
                fragrance="neutral",
                thorns="none",
            )
        ).id
        proposal = MemoryProposal(
            title="correction update",
            essence="actually prefer detailed and long release notes instead",
            tags=["correction"],
        )
        annotated = service.annotate_proposal(proposal)
        assert annotated.conflict_memory_ids == [existing_id]
        assert annotated.duplicate_memory_ids == []

        saved = product.store.save_proposal(annotated)
        new_card = product.approve(saved.id)

        arbitrations = product.store.list_conflict_arbitrations(existing_id)
        assert len(arbitrations) == 1
        assert arbitrations[0].winner_memory_id == new_card.id
        assert arbitrations[0].resolution == "new_user_correction_supersedes_existing"
    finally:
        garden.close()


def test_conflict_service_detects_duplicate_by_title(tmp_path):
    garden, product = _product(tmp_path)
    try:
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        existing_id = garden.core.repository.save_memory_card(
            MemoryCard(
                id="conflict-duplicate-target",
                title="shared release checklist title",
                essence="verify changelog and smoke tests before release",
                fragrance="neutral",
                thorns="none",
            )
        ).id
        proposal = MemoryProposal(
            title="shared release checklist title",
            essence="add rollback plan to the release checklist",
            tags=["release"],
        )
        annotated = service.annotate_proposal(proposal)
        assert existing_id in annotated.duplicate_memory_ids
        assert annotated.conflict_memory_ids == []

        saved = product.store.save_proposal(annotated)
        new_card = product.approve(saved.id)
        relations = product.store.list_relations(new_card.id)
        assert any(
            rel.relation_type.value == "duplicates" and rel.target_memory_id == existing_id
            for rel in relations
        )
    finally:
        garden.close()


def test_conflict_service_finds_oldest_contradiction_across_pages(tmp_path):
    garden, product = _product(tmp_path)
    try:
        now = datetime.now(timezone.utc)
        _seed_library(garden.core.repository, total=500)
        oldest = garden.core.repository.save_memory_card(
            MemoryCard(
                id="conflict-oldest-target",
                title=f"{_SCALE_MARKER} concise preference",
                essence=f"prefer concise and short updates for {_SCALE_MARKER} reports",
                fragrance="neutral",
                thorns="none",
                created_at=now - timedelta(days=400),
            )
        )
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        proposal = MemoryProposal(
            title="correction for oldest page",
            essence=f"actually prefer detailed and long updates instead for {_SCALE_MARKER} reports",
            tags=["correction"],
        )
        annotated = service.annotate_proposal(proposal)
        diag = annotated.metadata[RETRIEVAL_DIAGNOSTICS_KEY]
        assert diag["total_available"] == 501
        assert diag["scanned_count"] == 501
        assert diag["truncated"] is False
        assert oldest.id in annotated.conflict_memory_ids
    finally:
        garden.close()


@pytest.mark.parametrize(
    ("existing_essence", "proposal_essence"),
    [
        ("团队偏好快速简洁上线", "我们决定采用慢速详细发布"),
        ("用户喜欢深色简短界面", "用户讨厌浅色详细界面"),
        ("文档保持简洁短摘要", "改为详细长篇幅说明"),
        ("预算总是充足且多", "预算从不充足且少"),
        ("推荐本地手动部署", "反对云端自动部署"),
        ("流程需要手动同步审批", "流程改为自动异步审批"),
        ("前端同步迭代主导", "后端异步迭代主导"),
        ("会议氛围严肃正式", "会议氛围轻松随意"),
        ("同意立即快速执行", "反对稍后慢速执行"),
        ("同步静态接口设计", "异步动态接口设计"),
    ],
)
def test_conflict_service_chinese_contradiction_pairs(tmp_path, existing_essence, proposal_essence):
    garden, product = _product(tmp_path)
    try:
        assert contradiction_score(existing_essence, proposal_essence) > 0.5
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        card_id = garden.core.repository.save_memory_card(
            MemoryCard(
                id=f"cn-conflict-{hash(existing_essence) % 10000}",
                title="cn conflict target",
                essence=existing_essence,
                fragrance="neutral",
                thorns="none",
            )
        ).id
        proposal = MemoryProposal(
            title="cn correction",
            essence=proposal_essence,
            tags=["correction"],
        )
        annotated = service.annotate_proposal(proposal)
        assert card_id in annotated.conflict_memory_ids
    finally:
        garden.close()


def test_conflict_service_embedding_provider_boosts_detection(tmp_path):
    garden, product = _product(tmp_path)
    try:
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        card_id = garden.core.repository.save_memory_card(
            MemoryCard(
                id="embed-conflict-target",
                title="release cadence preference",
                essence="prefer concise and short release notes for weekly cadence",
                fragrance="neutral",
                thorns="none",
            )
        ).id
        proposal = MemoryProposal(
            title="update",
            essence="prefer detailed and long release notes for weekly cadence",
            tags=["correction"],
        )
        without_emb = service.annotate_proposal(proposal)
        with_emb = service.annotate_proposal(proposal, embedding_provider=FakeEmbeddingProvider(dimensions=64))
        assert card_id in without_emb.conflict_memory_ids
        assert card_id in with_emb.conflict_memory_ids
    finally:
        garden.close()


def test_conflict_service_unit_annotate_records_diagnostics(tmp_path):
    garden, product = _product(tmp_path)
    try:
        service = ConflictService(
            repository=garden.core.repository,
            store=product.store,
            strategy=product.strategy,
        )
        garden.core.repository.save_memory_card(
            MemoryCard(
                id="conflict-target",
                title="prefer concise updates",
                essence="prefer concise and short updates for status",
                fragrance="neutral",
                thorns="none",
            )
        )
        proposal = MemoryProposal(
            title="correction update",
            essence="actually prefer detailed and long updates instead",
            tags=["correction"],
        )
        annotated = service.annotate_proposal(proposal)
        assert "conflict-target" in annotated.conflict_memory_ids
        assert RETRIEVAL_DIAGNOSTICS_KEY in annotated.metadata
        assert annotated.metadata[RETRIEVAL_DIAGNOSTICS_KEY]["source"] == "product_conflict_scan"
    finally:
        garden.close()
