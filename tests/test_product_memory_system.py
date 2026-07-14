import json
import sqlite3
from types import SimpleNamespace

import pytest

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard, SeedStatus, SensitivityLevel
from memory_garden.product import MemoryListFilter, MemoryPatch, MemoryProposalStatus, ProductMemorySystem
from memory_garden.product.services.forget import _redact_proof_metadata
from memory_garden.providers import FakeEmbeddingProvider, ProviderPolicy, ProviderRegistry
from memory_garden.sdk import MemoryGarden
from memory_garden.storage.base import NotFoundError


def _product(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    return garden, ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)


def _retrieval_event_ids(product: ProductMemorySystem) -> list[str]:
    conn = sqlite3.connect(product.store.path)
    try:
        rows = conn.execute("SELECT payload FROM memory_retrieval_events ORDER BY id").fetchall()
        return [json.loads(row[0])["id"] for row in rows]
    finally:
        conn.close()


def test_product_proposal_approval_inspection_and_retrieval(tmp_path):
    garden, product = _product(tmp_path)
    try:
        proposals = product.propose("remember: prefer dark mode for production dashboards")
        assert len(proposals) == 1
        assert proposals[0].status.value == "pending"
        assert proposals[0].source_seed_ids

        card = product.approve(proposals[0].id)
        assert card.id
        assert product.store.get_proposal(proposals[0].id).status == MemoryProposalStatus.approved
        assert card.sensitivity == SensitivityLevel.none
        assert card.source_seed_ids == proposals[0].source_seed_ids
        assert garden.core.repository.get_seed(card.source_seed_ids[0]).status == SeedStatus.held

        inspection = product.inspect_memory(card.id)
        assert inspection.memory.id == card.id
        assert inspection.proposals[0].id == proposals[0].id
        assert inspection.versions[0].reason == "proposal_approved"

        result = product.retrieve("dark dashboard", limit=3)
        assert result.hits
        assert result.hits[0].memory.id == card.id
        assert result.hits[0].why_used
    finally:
        garden.close()


def test_product_retrieve_mutate_false_is_read_only(tmp_path):
    garden, product = _product(tmp_path)
    try:
        card = product.approve(product.propose("remember: prefer read only retrieval checks")[0].id)
        before_profile = product.get_strategy_profile(card.id)
        assert _retrieval_event_ids(product) == []

        result = product.retrieve("read only retrieval", limit=3, mutate=False)

        after_profile = product.get_strategy_profile(card.id)
        assert result.hits
        assert result.metadata["mutated"] is False
        assert after_profile.use_count == before_profile.use_count
        assert _retrieval_event_ids(product) == []
    finally:
        garden.close()


def test_product_embedding_cache_warms_and_surfaces_features(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    product = ProductMemorySystem(
        garden_home=garden.home.root,
        repository=garden.core.repository,
        providers=ProviderRegistry(
            policy=ProviderPolicy(allow_raw_user_text=True),
            embedding=FakeEmbeddingProvider(),
        ),
    )
    try:
        card = product.approve(product.propose("remember: prefer release checklist detail")[0].id)
        summary = product.warm_embedding_cache()

        result = product.retrieve("release checklist detail", limit=3, mutate=False)
        features = result.metadata["feature_vectors"][card.id]

        assert summary["cached"] + summary["encoded"] >= 1
        assert product.store.get_memory_embedding(
            memory_id=card.id,
            model="fake-local-embedding",
        )
        assert features["embedding_score"] > 0.0
    finally:
        garden.close()


def test_approve_rolls_back_memory_card_when_strategy_profile_save_fails(tmp_path, monkeypatch):
    garden, product = _product(tmp_path)
    try:
        proposal = product.propose("remember: approval rollback marker")[0]

        def fail_save_strategy_profile(_profile, **kwargs):
            raise RuntimeError("profile write failed")

        monkeypatch.setattr(product.store, "save_strategy_profile", fail_save_strategy_profile)

        try:
            product.approve(proposal.id)
        except RuntimeError as exc:
            assert "profile write failed" in str(exc)
        else:
            raise AssertionError("approve should fail")

        failed = product.store.get_proposal(proposal.id)
        failed_memory_id = failed.metadata["failed_memory_id"]
        assert failed.status == MemoryProposalStatus.error
        assert "profile write failed" in failed.metadata["approve_error"]
        assert garden.core.repository.get_seed(proposal.source_seed_ids[0]).status == SeedStatus.held
        with pytest.raises(NotFoundError):
            garden.core.repository.get_memory_card(failed_memory_id)
    finally:
        garden.close()


def test_approve_marks_proposal_error_when_product_write_fails(tmp_path, monkeypatch):
    garden, product = _product(tmp_path)
    try:
        proposal = product.propose("remember: approval error marker")[0]

        def fail_snapshot(_card, *, reason, **kwargs):
            raise RuntimeError("version write failed")

        monkeypatch.setattr(product._write_service, "_snapshot_version", fail_snapshot)

        try:
            product.approve(proposal.id)
        except RuntimeError:
            pass
        else:
            raise AssertionError("approve should fail")

        failed = product.store.get_proposal(proposal.id)
        assert failed.status == MemoryProposalStatus.error
        assert failed.created_memory_id is None
        assert "version write failed" in failed.metadata["approve_error"]
    finally:
        garden.close()


def test_approve_cleans_product_rows_after_late_failure(tmp_path, monkeypatch):
    garden, product = _product(tmp_path)
    try:
        existing = product.approve(product.propose("remember: duplicate base marker")[0].id)
        proposal = product.propose("remember: duplicate base marker")[0]
        assert existing.id in proposal.duplicate_memory_ids

        def fail_save_relation(_relation, **kwargs):
            raise RuntimeError("relation write failed")

        monkeypatch.setattr(product.store, "save_relation", fail_save_relation)

        try:
            product.approve(proposal.id)
        except RuntimeError:
            pass
        else:
            raise AssertionError("approve should fail")

        failed = product.store.get_proposal(proposal.id)
        failed_memory_id = failed.metadata["failed_memory_id"]
        assert failed.status == MemoryProposalStatus.error
        assert failed_memory_id
        assert product.store.get_strategy_profile(failed_memory_id) is None
        assert product.store.list_versions(failed_memory_id) == []
        with pytest.raises(NotFoundError):
            garden.core.repository.get_memory_card(failed_memory_id)
    finally:
        garden.close()


def test_product_edit_retag_archive_restore_and_filters(tmp_path):
    garden, product = _product(tmp_path)
    try:
        card = product.approve(product.propose("remember: prefer compact table layouts")[0].id)

        edited = product.edit_memory(
            card.id,
            MemoryPatch(title="Compact tables", tags=["ui", "tables"], importance=0.9),
            reason="test_edit",
        )
        assert edited.title == "Compact tables"
        assert edited.importance == 0.9
        assert len(product.inspect_memory(card.id).versions) == 2

        retagged = product.retag_memory(card.id, ["ui", "ui", "product"])
        assert retagged.tags == ["ui", "product"]

        hidden = product.archive_memory(card.id, reason="test_archive")
        assert hidden.lifecycle == MemoryLifecycle.pruned
        assert product.list_memories(MemoryListFilter(tag="ui")) == []
        assert product.list_memories(MemoryListFilter(tag="ui", include_archived=True))[0].id == card.id

        restored = product.restore_memory(card.id)
        assert restored.lifecycle == MemoryLifecycle.sprout
    finally:
        garden.close()


def test_product_duplicate_relation_merge_and_forget_proof(tmp_path):
    garden, product = _product(tmp_path)
    try:
        first = product.approve(product.propose("remember: prefer concise status updates")[0].id)
        second_prop = product.propose("remember: prefer concise status updates")
        assert first.id in second_prop[0].duplicate_memory_ids
        second = product.approve(second_prop[0].id)

        merged = product.merge_memories([first.id, second.id], target_id=first.id)
        assert merged.id == first.id
        second_after = garden.core.repository.get_memory_card(second.id)
        assert second_after.lifecycle == MemoryLifecycle.pruned
        assert any(rel.relation_type.value == "merged_into" for rel in product.inspect_memory(first.id).relations)

        plan = product.plan_forget(memory_id=first.id)
        assert plan.affected
        executed, proof = product.execute_forget(plan.id)
        assert executed.status == "executed"
        assert proof.proven is True
        assert proof.proof_level == "content"
        assert proof.content_probe_fingerprint
    finally:
        garden.close()


def test_product_forget_proof_metadata_removes_plaintext_probe_queries(tmp_path):
    garden, product = _product(tmp_path)
    try:
        marker = "proof-redaction-unique-quartz-marker"
        card = product.approve(product.propose(f"remember: {marker}")[0].id)
        plan = product.plan_forget(memory_id=card.id)
        _, proof = product.execute_forget(plan.id)

        def contains_queries_key(value):
            if isinstance(value, dict):
                return "queries" in value or any(contains_queries_key(item) for item in value.values())
            if isinstance(value, list):
                return any(contains_queries_key(item) for item in value)
            return False

        assert proof.proven is True
        assert contains_queries_key(proof.metadata) is False
        assert marker not in json.dumps(proof.metadata, ensure_ascii=False)
    finally:
        garden.close()


def test_redact_proof_metadata_strips_queries_from_check_evidence():
    proof = SimpleNamespace(
        model_dump=lambda **_: {
            "checks": [
                {
                    "surface": "search_content_probe",
                    "evidence": {"queries": ["private plaintext probe"], "matches": 0},
                }
            ]
        }
    )

    payload = _redact_proof_metadata(proof, content_probes=None)

    assert payload["checks"][0]["evidence"] == {"matches": 0}


def test_product_forget_facade_behavior_unchanged_after_service_extract(tmp_path):
    garden, product = _product(tmp_path)
    try:
        card = product.approve(product.propose("remember: forget facade unique marker")[0].id)

        plan = product.plan_forget("forget facade unique marker")
        executed, proof = product.execute_forget(plan.id)

        assert plan.memory_id == card.id
        assert executed.status == "executed"
        assert proof.proven is True
        with pytest.raises(NotFoundError):
            garden.core.repository.get_memory_card(card.id)
    finally:
        garden.close()


def test_product_forget_service_does_not_change_proof_ordering(tmp_path, monkeypatch):
    garden, product = _product(tmp_path)
    try:
        card = product.approve(product.propose("remember: forget ordering unique marker")[0].id)
        plan = product.plan_forget(memory_id=card.id)
        events = []
        original_save_plan = product.store.save_forget_plan
        original_save_proof = product.store.save_forget_proof

        def record_save_plan(record):
            events.append(("plan", record.status, bool(record.result)))
            return original_save_plan(record)

        def record_save_proof(record):
            events.append(("proof", record.plan_id, record.proven))
            return original_save_proof(record)

        monkeypatch.setattr(product.store, "save_forget_plan", record_save_plan)
        monkeypatch.setattr(product.store, "save_forget_proof", record_save_proof)

        executed, proof = product.execute_forget(plan.id)

        assert proof.plan_id == plan.id
        assert executed.status == "executed"
        assert events == [
            ("proof", plan.id, True),
            ("plan", "executed", True),
        ]
    finally:
        garden.close()


def test_product_remember_modes(tmp_path):
    garden, product = _product(tmp_path)
    try:
        manual = product.remember("remember: manual proposal only", mode="manual")
        assert manual["approved_memory_ids"] == []
        assert manual["pending_proposal_ids"]

        trusted = product.remember("remember: trusted safe preference", mode="trusted")
        assert trusted["approved_memory_ids"]
        assert trusted["pending_proposal_ids"] == []
    finally:
        garden.close()


def test_purge_retrieval_events_exact_memory_id_does_not_delete_prefix_neighbor(tmp_path):
    garden, product = _product(tmp_path)
    try:
        product.store.record_retrieval_event(
            {
                "id": "retrieval-mem-1",
                "query": "q",
                "created_at": "2026-01-01T00:00:00Z",
                "memory_ids": ["mem-1"],
                "blocked_memory_ids": [],
            }
        )
        product.store.record_retrieval_event(
            {
                "id": "retrieval-mem-10",
                "query": "q",
                "created_at": "2026-01-01T00:00:01Z",
                "memory_ids": ["mem-10"],
                "blocked_memory_ids": [],
            }
        )

        assert product.store.purge_retrieval_events_for_memory("mem-1") == 1

        assert _retrieval_event_ids(product) == ["retrieval-mem-10"]
    finally:
        garden.close()


def test_purge_retrieval_events_removes_blocked_memory_id_references(tmp_path):
    garden, product = _product(tmp_path)
    try:
        product.store.record_retrieval_event(
            {
                "id": "retrieval-blocked",
                "query": "q",
                "created_at": "2026-01-01T00:00:00Z",
                "memory_ids": [],
                "blocked_memory_ids": ["mem-1"],
            }
        )

        assert product.store.purge_retrieval_events_for_memory("mem-1") == 1

        assert _retrieval_event_ids(product) == []
    finally:
        garden.close()


def test_execute_forget_purges_target_retrieval_event_but_preserves_unrelated_event(tmp_path):
    garden, product = _product(tmp_path)
    try:
        target = garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-1",
                title="target memory",
                essence="target memory unique proof text",
                fragrance="target memory unique proof text",
                thorns="none",
            )
        )
        garden.core.repository.save_memory_card(
            MemoryCard(
                id="mem-10",
                title="neighbor memory",
                essence="neighbor memory unique proof text",
                fragrance="neighbor memory unique proof text",
                thorns="none",
            )
        )
        product.store.record_retrieval_event(
            {
                "id": "retrieval-target",
                "query": "target",
                "created_at": "2026-01-01T00:00:00Z",
                "memory_ids": [target.id],
                "blocked_memory_ids": [],
            }
        )
        product.store.record_retrieval_event(
            {
                "id": "retrieval-neighbor",
                "query": "neighbor",
                "created_at": "2026-01-01T00:00:01Z",
                "memory_ids": ["mem-10"],
                "blocked_memory_ids": [],
            }
        )

        plan = product.plan_forget(memory_id=target.id)
        executed, proof = product.execute_forget(plan.id)

        assert executed.status == "executed"
        assert proof.proven is True
        assert _retrieval_event_ids(product) == ["retrieval-neighbor"]
    finally:
        garden.close()
