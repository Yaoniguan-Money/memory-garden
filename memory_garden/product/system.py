"""Product-grade Memory Garden system facade."""

from __future__ import annotations

import logging
import sqlite3
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import numpy as _np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    _np = None  # type: ignore[assignment]


def _batch_score_features(
    raw: list[tuple[RetrievalFeatureVector, MemoryCard, list[str]]],
) -> tuple[list[tuple[float, MemoryCard, list[str]]], dict[str, RetrievalFeatureVector]]:
    """NumPy 批量评分，不可用时回退到逐条 score_feature_vector。"""
    if not raw:
        return [], {}

    weights = default_garden_runtime_config().retrieval_fusion
    if _HAS_NUMPY:
        w = _np.array([weights.fts, weights.lexical, weights.applicability, weights.recency_policy, weights.embedding])
        matrix = _np.array([
            [f.fts_score, f.lexical_score, f.applicability_score, f.recency_policy_score, f.embedding_score]
            for f, _c, _r in raw
        ])
        scores = matrix.dot(w)
        bonuses = _np.array([weights.vector_recall_bonus if f.vector_recall else 0.0 for f, _c, _r in raw])
        totals_list = (scores + bonuses).tolist()
    else:
        totals_list = [score_feature_vector(f, weights=weights)[0] for f, _c, _r in raw]

    scored: list[tuple[float, MemoryCard, list[str]]] = []
    feature_by_id: dict[str, RetrievalFeatureVector] = {}
    for idx, total in enumerate(totals_list):
        features, card, notes = raw[idx]
        feature_by_id[card.id] = features
        scored.append((total, card, [*notes, f"feature:score={total:.4f}"]))
    return scored, feature_by_id

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import (
    MemoryCard,
    MemoryType,
    Seed,
    SeedSignalType,
    SeedStatus,
    SensitivityLevel,
)
from memory_garden.cognition.models import CognitiveHarvestMode
from memory_garden.harvest.coarse_scoring import compute_coarse_lexical_score
from memory_garden.product.harvest_adapter import (
    RETRIEVAL_DIAGNOSTICS_KEY,
    RETRIEVAL_LATENCY_MS_KEY,
    HarvestQuery,
    attach_retrieval_diagnostics,
    build_retrieval_diagnostics,
    cosine_similarity,
    embed_local,
    get_coarse_top_m,
    get_product_scan_limit,
    get_retrieval_strategy,
    get_vector_top_n,
    get_score_top_n,
    resolve_total_available_after_scan,
    scan_memory_cards,
    select_product_candidate_source,
)
from memory_garden.runtime_config import default_garden_runtime_config
from memory_garden.product.models import (
    ApplicabilityContext,
    ApplicabilityDecision,
    EvolutionAction,
    ForgetPlanRecord,
    ForgetProofRecord,
    MemoryEvolutionPlan,
    MemoryInspection,
    MemoryListFilter,
    MemoryPatch,
    MemoryProposal,
    MemoryProposalStatus,
    MemoryRelation,
    MemoryRelationType,
    MemoryRetrievalResult,
    MemoryStrategyProfile,
    MemoryVersionRecord,
    MemoryView,
    ProposalWritePolicy,
    RetrievalHit,
    utc_now,
    new_id,
)
from memory_garden.product.policy import MemoryPolicy
from memory_garden.product.retrieval_features import (
    RetrievalFeatureVector,
    build_feature_vector,
    is_hard_block,
    score_feature_vector,
)
from memory_garden.product.services import ConflictService, ForgetService, WriteWorkflowService
from memory_garden.product.storage import ProductMemoryStore
from memory_garden.product.strategy import MemoryStrategyEngine, _card_text, _tokens
from memory_garden.providers import ProviderCallContext, ProviderRegistry, RerankCandidate
from memory_garden.runtime.session import GardenBrief
from memory_garden.storage.base import GardenRepository, NotFoundError


class ProductMemorySystem:
    """Full product memory workflow over a local Memory Garden instance."""

    def __init__(
        self,
        *,
        garden_home: str | Path,
        repository: GardenRepository,
        providers: ProviderRegistry | None = None,
        policy: MemoryPolicy | None = None,
        cognition_providers: dict[str, Any] | None = None,
    ) -> None:
        self.garden_home = Path(garden_home).resolve()
        self.repository = repository
        self.providers = providers or ProviderRegistry()
        self.policy = policy or MemoryPolicy(provider_policy=self.providers.policy)
        self.store = ProductMemoryStore(self.garden_home)
        self.strategy = MemoryStrategyEngine()
        self.cognition_providers = dict(cognition_providers or {})
        self._forget_service = ForgetService(
            garden_home=self.garden_home,
            store=self.store,
            resolve_memory_id=self.resolve_memory_id,
            logger=logger,
        )
        self._conflict_service = ConflictService(
            repository=self.repository,
            store=self.store,
            strategy=self.strategy,
        )
        self._write_service = WriteWorkflowService(
            repository=self.repository,
            store=self.store,
            strategy=self.strategy,
            policy=self.policy,
            conflict_service=self._conflict_service,
            provider_proposals=self._provider_proposals,
            local_proposal=self._local_proposal,
            source_seed_ids_for_proposal=self._source_seed_ids_for_proposal,
            snapshot_version=lambda card, reason, conn=None: self._snapshot_version(
                card, reason=reason, conn=conn
            ),
            record_approval_failure=self._record_approval_failure,
            embedding_provider_resolver=lambda: self.providers.optional_embedding(),
        )

    def close(self) -> None:
        close = getattr(self.repository, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> ProductMemorySystem:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # Proposals

    def propose(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[MemoryProposal]:
        """Create memory proposals without writing MemoryCards."""
        return self._write_service.propose(text, metadata=metadata)

    def inbox(self, *, status: MemoryProposalStatus | str | None = MemoryProposalStatus.pending, limit: int = 100) -> list[MemoryProposal]:
        status_value = status.value if isinstance(status, MemoryProposalStatus) else status
        return self.store.list_proposals(status=status_value, limit=limit)

    def approve(self, proposal_id: str, *, auto: bool = False) -> MemoryCard:
        card = self._write_service.approve(proposal_id, auto=auto)
        self._cache_card_embedding_if_available(card)
        try:
            self._index_card_for_retrieval(card)
        except Exception:
            pass
        return card

    def reject(self, proposal_id: str, *, reason: str = "") -> MemoryProposal:
        proposal = self.store.get_proposal(proposal_id)
        proposal = proposal.model_copy(
            update={
                "status": MemoryProposalStatus.rejected,
                "updated_at": utc_now(),
                "metadata": {**proposal.metadata, "reject_reason": reason},
            }
        )
        return self.store.save_proposal(proposal)

    def edit_proposal(self, proposal_id: str, patch: MemoryPatch) -> MemoryProposal:
        proposal = self.store.get_proposal(proposal_id)
        updates = patch.as_update()
        proposal = proposal.model_copy(
            update={
                **updates,
                "status": MemoryProposalStatus.edited,
                "updated_at": utc_now(),
                "metadata": {**proposal.metadata, **patch.metadata},
            }
        )
        proposal = self.policy.apply_to_proposal(proposal)
        proposal = self._conflict_service.annotate_proposal(
            proposal,
            embedding_provider=self.providers.optional_embedding(),
        )
        return self.store.save_proposal(proposal)

    def remember(
        self,
        text: str,
        *,
        mode: ProposalWritePolicy | str = ProposalWritePolicy.trusted,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._write_service.remember(text, mode=mode, metadata=metadata)

    # Memory management

    def list_memories(self, filters: MemoryListFilter | None = None) -> list[MemoryView]:
        filters = filters or MemoryListFilter()
        cards = self.repository.list_memory_cards(
            lifecycle=None,
            include_greenhouse=filters.include_greenhouse,
            limit=filters.limit,
        )
        views = []
        for card in cards:
            profile = self._ensure_strategy_profile(card)
            if filters.memory_type is not None and card.memory_type != filters.memory_type:
                continue
            if filters.sensitivity is not None and card.sensitivity != filters.sensitivity:
                continue
            if filters.tag is not None and filters.tag not in card.tags:
                continue
            if filters.layer is not None and profile.layer != filters.layer:
                continue
            if filters.scope is not None and profile.scope != filters.scope:
                continue
            if filters.scope_id is not None and profile.scope_id != filters.scope_id:
                continue
            if filters.maturity is not None and profile.maturity != filters.maturity:
                continue
            if not filters.include_archived and card.lifecycle in (MemoryLifecycle.pruned, MemoryLifecycle.composted):
                continue
            views.append(self._view_from_card(card, profile))
        return views

    def inspect_memory(self, memory_id: str, *, applicability_queries: list[str] | None = None) -> MemoryInspection:
        card = self.repository.get_memory_card(memory_id)
        profile = self._ensure_strategy_profile(card)
        applicability = [
            self.strategy.decide_applicability(query=query, card=card, profile=profile)
            for query in (applicability_queries or [])
        ]
        events = [
            _event_to_dict(event)
            for event in self.repository.list_garden_events(object_id=memory_id, limit=100)
        ]
        return MemoryInspection(
            memory=self._view_from_card(card, profile),
            versions=self.store.list_versions(memory_id),
            relations=self.store.list_relations(memory_id),
            proposals=self.store.proposals_for_memory(memory_id),
            events=events,
            lineage={
                "source_seed_ids": list(card.source_seed_ids),
                "court_case_ids": list(card.court_case_ids),
                "dream_record_ids": list(card.dream_record_ids),
            },
            strategy=profile,
            applicability=applicability,
            conflict_arbitrations=self.store.list_conflict_arbitrations(memory_id),
            evolution_plans=self.store.list_evolution_plans(memory_id),
        )

    def edit_memory(self, memory_id: str, patch: MemoryPatch, *, reason: str = "memory_edit") -> MemoryCard:
        card = self.repository.get_memory_card(memory_id)
        self._snapshot_version(card, reason=reason)
        updates = patch.as_update()
        if updates:
            updates["updated_at"] = utc_now()
        updated = card.model_copy(update=updates)
        saved = self.repository.update_memory_card(updated)
        profile = self._ensure_strategy_profile(saved)
        if patch.tags is not None or patch.memory_type is not None or patch.essence is not None:
            new_layer = self.strategy.classify_layer(saved.memory_type, saved.tags, _card_text(saved))
            self.store.save_strategy_profile(
                profile.model_copy(
                    update={
                        "layer": new_layer,
                        "applies_to_tags": list(dict.fromkeys([*saved.tags, new_layer.value])),
                        "updated_at": utc_now(),
                    }
                )
            )
        if any(
            value is not None
            for value in (patch.title, patch.essence, patch.fragrance, patch.thorns, patch.tags)
        ):
            self.store.delete_memory_embedding(saved.id)
            self._cache_card_embedding_if_available(saved)
        return saved

    def retag_memory(self, memory_id: str, tags: list[str]) -> MemoryCard:
        return self.edit_memory(memory_id, MemoryPatch(tags=list(dict.fromkeys(tags))), reason="retag_memory")

    def set_sensitivity(self, memory_id: str, level: SensitivityLevel | str) -> MemoryCard:
        return self.edit_memory(memory_id, MemoryPatch(sensitivity=SensitivityLevel(level)), reason="set_sensitivity")

    def archive_memory(self, memory_id: str, *, reason: str = "archive") -> MemoryCard:
        return self.prune_memory(memory_id, reason=reason)

    def prune_memory(self, memory_id: str, *, reason: str = "archive") -> MemoryCard:
        card = self.repository.get_memory_card(memory_id)
        self._snapshot_version(card, reason=reason)
        updated = card.model_copy(update={"lifecycle": MemoryLifecycle.pruned, "updated_at": utc_now()})
        return self.repository.update_memory_card(updated)

    def restore_memory(self, memory_id: str, *, reason: str = "restore") -> MemoryCard:
        card = self.repository.get_memory_card(memory_id)
        self._snapshot_version(card, reason=reason)
        updated = card.model_copy(update={"lifecycle": MemoryLifecycle.sprout, "updated_at": utc_now()})
        return self.repository.update_memory_card(updated)

    def merge_memories(self, source_ids: list[str], target_id: str | None = None) -> MemoryCard:
        if not source_ids:
            raise ValueError("source_ids must be non-empty")
        cards = [self.repository.get_memory_card(mid) for mid in source_ids]
        target = self.repository.get_memory_card(target_id) if target_id else cards[0]
        sources = [card for card in cards if card.id != target.id]
        self._snapshot_version(target, reason="merge_target")
        merged_tags = list(dict.fromkeys([*target.tags, *(tag for source in sources for tag in source.tags)]))
        merged_essence = target.essence
        for source in sources:
            if source.essence not in merged_essence:
                merged_essence += f"\n{source.essence}"
        updated = target.model_copy(
            update={
                "essence": merged_essence,
                "tags": merged_tags,
                "importance": max([target.importance, *(s.importance for s in sources)] or [target.importance]),
                "updated_at": utc_now(),
            }
        )
        saved = self.repository.update_memory_card(updated)
        for source in sources:
            self.store.save_relation(
                MemoryRelation(
                    relation_type=MemoryRelationType.merged_into,
                    source_memory_id=source.id,
                    target_memory_id=saved.id,
                    reason="User or product workflow merged memories",
                    confidence=1.0,
                )
            )
            self.prune_memory(source.id, reason=f"merged_into:{saved.id}")
        return saved

    # Retrieval

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        explain: bool = True,
        context: ApplicabilityContext | dict[str, Any] | None = None,
        mutate: bool = True,
    ) -> MemoryRetrievalResult:
        if not query or not query.strip():
            raise ValueError("query must be non-empty")
        self._profile_cache: dict[str, MemoryStrategyProfile] = {}
        started = time.perf_counter()
        app_context = self._coerce_applicability_context(query, context)
        coarse = self._coarse_recall(query)
        cards = list(coarse.cards)
        source_metadata = dict(coarse.metadata_by_id or {})
        cards, source_metadata = self._augment_with_vector_candidates(
            query,
            cards,
            source_metadata,
            limit=max(get_coarse_top_m(), limit * 20),
        )
        total_available = coarse.total_available
        scanned_count = coarse.scanned_count
        scored, decisions_by_id, feature_by_id = self._score_coarse_candidates(
            query,
            cards,
            app_context,
            source_metadata,
        )
        candidate_count = len(scored)
        scored = self._apply_embedding_rescore(query, scored, feature_by_id, record_calls=mutate)
        scored = [item for item in scored if item[0] > 0.0]
        scored.sort(key=lambda item: (item[0], item[1].importance, item[1].updated_at), reverse=True)
        scored, provider_used = self._apply_provider_rerank(query, scored, limit)

        hits = [
            RetrievalHit(
                memory=self._view_from_card(card, self._ensure_strategy_profile(card)),
                score=round(score, 4),
                why_used=why if explain else [],
                policy_status="allowed" if decisions_by_id[card.id].allowed else "blocked",
                risk_flags=decisions_by_id[card.id].risk_flags,
                source="hybrid",
                applicability_score=round(decisions_by_id[card.id].score, 4),
                applicability_reasons=decisions_by_id[card.id].reasons if explain else [],
            )
            for score, card, why in scored[: max(1, limit)]
        ]
        if mutate:
            for hit in hits:
                profile = self.store.get_strategy_profile(hit.memory.id)
                if profile is None:
                    continue
                updated, plan = self.strategy.reinforce_profile(profile, reason="retrieval_used")
                self.store.save_strategy_profile(updated)
                if plan is not None:
                    self.store.save_evolution_plan(plan)
        event = {
            "id": new_id("retrieval"),
            "query": query,
            "created_at": utc_now().isoformat(),
            "memory_ids": [hit.memory.id for hit in hits],
            "provider_used": provider_used,
            "blocked_memory_ids": [mid for mid, decision in decisions_by_id.items() if not decision.allowed],
        }
        if mutate:
            self.store.record_retrieval_event(event)
        diagnostics = build_retrieval_diagnostics(
            total_available=total_available,
            scanned_count=scanned_count,
            candidate_count=candidate_count,
            source="product_retrieval",
            fallback_reason=coarse.fallback_reason,
            candidate_source=coarse.candidate_source,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._profile_cache = {}
        metadata = attach_retrieval_diagnostics(
            {
                "event_id": event["id"] if mutate else "",
                "mutated": mutate,
                "feature_vectors": {mid: feature.as_dict() for mid, feature in feature_by_id.items()},
                RETRIEVAL_LATENCY_MS_KEY: latency_ms,
            },
            diagnostics,
        )
        return MemoryRetrievalResult(query=query, hits=hits, provider_used=provider_used, metadata=metadata)

    def _coarse_recall(self, query: str):
        return self._get_candidate_source().recall(query, top_m=get_coarse_top_m())

    def warm_embedding_cache(self, *, limit: int | None = None) -> dict[str, Any]:
        """Precompute persistent memory embeddings for the configured provider."""
        embedding = self.providers.optional_embedding()
        if embedding is None:
            return {"provider": "", "model": "", "encoded": 0, "cached": 0}
        model_key = self._embedding_model_key(embedding)
        cards = self.repository.list_memory_cards(
            include_greenhouse=False,
            limit=limit or get_product_scan_limit(),
        )
        pending: list[tuple[MemoryCard, str, str]] = []
        cached = 0
        for card in cards:
            text = _card_text(card)
            content_hash = self._content_hash(text)
            if self.store.get_memory_embedding(
                memory_id=card.id,
                model=model_key,
                content_hash=content_hash,
            ) is not None:
                cached += 1
                continue
            pending.append((card, text, content_hash))

        if not pending:
            return {"provider": embedding.name, "model": model_key, "encoded": 0, "cached": cached}

        context = ProviderCallContext(
            purpose="memory_embedding_cache_build",
            provider_kind="embedding",
            garden_home=str(self.garden_home),
            allow_remote=embedding.is_remote,
        )
        encoded = 0
        batch_size = int(getattr(getattr(embedding, "_config", None), "batch_size", 32) or 32)
        for index in range(0, len(pending), batch_size):
            chunk = pending[index : index + batch_size]
            texts = [item[1] for item in chunk]
            self.policy.assert_provider_call_allowed(context, "\n".join(texts))
            vectors = self._embedding_vectors(embedding.embed_texts(texts, context=context))
            for (card, _text, content_hash), vector in zip(chunk, vectors):
                self.store.save_memory_embedding(
                    memory_id=card.id,
                    model=model_key,
                    vector=vector,
                    content_hash=content_hash,
                    updated_at=utc_now().isoformat(),
                )
                encoded += 1
        if encoded:
            self.store.record_provider_call(
                {
                    "id": new_id("provider_call"),
                    "provider_name": embedding.name,
                    "provider_kind": "embedding",
                    "purpose": "memory_embedding_cache_build",
                    "created_at": utc_now().isoformat(),
                    "candidate_count": encoded,
                }
            )
        return {"provider": embedding.name, "model": model_key, "encoded": encoded, "cached": cached}

    def _cache_card_embedding_if_available(self, card: MemoryCard) -> None:
        embedding = self.providers.optional_embedding()
        if embedding is None:
            return
        text = _card_text(card)
        if not text.strip():
            return
        model_key = self._embedding_model_key(embedding)
        content_hash = self._content_hash(text)
        if self.store.get_memory_embedding(
            memory_id=card.id,
            model=model_key,
            content_hash=content_hash,
        ) is not None:
            return
        context = ProviderCallContext(
            purpose="memory_embedding_cache_write",
            provider_kind="embedding",
            garden_home=str(self.garden_home),
            allow_remote=embedding.is_remote,
        )
        self.policy.assert_provider_call_allowed(context, text)
        vectors = self._embedding_vectors(embedding.embed_texts([text], context=context))
        if not vectors:
            return
        self.store.save_memory_embedding(
            memory_id=card.id,
            model=model_key,
            vector=vectors[0],
            content_hash=content_hash,
            updated_at=utc_now().isoformat(),
        )

    def _augment_with_vector_candidates(
        self,
        query: str,
        cards: list[MemoryCard],
        source_metadata: dict[str, dict[str, object]],
        *,
        limit: int,
    ) -> tuple[list[MemoryCard], dict[str, dict[str, object]]]:
        strategy = get_retrieval_strategy()
        if strategy == "fts_only":
            return cards, source_metadata

        embedding = self.providers.optional_embedding()
        if embedding is None:
            return cards, source_metadata
        model_key = self._embedding_model_key(embedding)

        if strategy == "fts_with_vector_rescore":
            candidate_ids = {card.id for card in cards}
            vectors = self.store.list_memory_embeddings_for_ids(
                model=model_key,
                memory_ids=candidate_ids,
            )
        else:
            vector_limit = max(limit, get_vector_top_n())
            vectors = self.store.list_memory_embeddings(
                model=model_key,
                limit=vector_limit,
            )

        if not vectors:
            return cards, source_metadata

        context = ProviderCallContext(
            purpose="memory_embedding_query",
            provider_kind="embedding",
            garden_home=str(self.garden_home),
            allow_remote=embedding.is_remote,
        )
        self.policy.assert_provider_call_allowed(context, query)
        query_vectors = self._embedding_vectors(embedding.embed_texts([query], context=context))
        if not query_vectors:
            return cards, source_metadata
        query_vector = query_vectors[0]

        by_id = {card.id: card for card in cards}
        scored_vectors: list[tuple[str, float]] = []
        for memory_id, vector in vectors.items():
            sim = cosine_similarity(query_vector, vector)
            if sim > 0.0:
                scored_vectors.append((memory_id, sim))
        scored_vectors.sort(key=lambda item: item[1], reverse=True)

        merged = list(cards)
        for position, (memory_id, sim) in enumerate(scored_vectors[:limit]):
            meta = dict(source_metadata.get(memory_id, {}))
            meta["vector_similarity"] = sim
            meta["vector_position"] = position
            meta["vector_recall"] = True
            if "candidate_source" not in meta:
                meta["candidate_source"] = "vector"
            source_metadata[memory_id] = meta
            if memory_id in by_id:
                continue
            if strategy != "full_hybrid":
                continue
            try:
                card = self.repository.get_memory_card(memory_id)
            except NotFoundError:
                continue
            if card.lifecycle == MemoryLifecycle.greenhouse:
                continue
            by_id[memory_id] = card
            merged.append(card)
        return merged, source_metadata

    def _embedding_model_key(self, embedding: Any) -> str:
        cfg = getattr(embedding, "_config", None)
        model_name = str(getattr(cfg, "model_name", "") or "")
        return f"{embedding.name}:{model_name}" if model_name else str(embedding.name)

    def _embedding_vectors(self, result: Any) -> list[list[float]]:
        vectors = getattr(result, "vectors", result)
        if not isinstance(vectors, list):
            return []
        return [[float(v) for v in row] for row in vectors if isinstance(row, list)]

    def _content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _score_coarse_candidates(
        self,
        query: str,
        cards: list[MemoryCard],
        app_context: ApplicabilityContext,
        source_metadata: dict[str, dict[str, object]] | None = None,
    ) -> tuple[
        list[tuple[float, MemoryCard, list[str]]],
        dict[str, ApplicabilityDecision],
        dict[str, RetrievalFeatureVector],
    ]:
        score_top_n = get_score_top_n()
        cards = cards[:score_top_n]
        if not cards:
            return [], {}, {}

        # Bulk-load pre-computed index rows from write-time indexing
        index_rows = self.store.bulk_get_retrieval_index({card.id for card in cards})

        query_lower = query.casefold()
        query_tokens = set(_tokens(query))
        query_embedding = embed_local(query)

        raw_features: list[tuple[RetrievalFeatureVector, MemoryCard, list[str]]] = []
        decisions_by_id: dict[str, ApplicabilityDecision] = {}
        source_metadata = source_metadata or {}
        now = datetime.now(timezone.utc)

        for card in cards:
            idx = index_rows.get(card.id)
            if idx is not None:
                card_tokens_set = idx["card_tokens"]
                card_emb = idx["card_embedding"]
            else:
                text = _card_text(card)
                card_tokens_set = set(_tokens(text))
                card_emb = embed_local(text)

            profile = self._ensure_strategy_profile(card)
            if app_context.include_scopes and profile.scope.value not in app_context.include_scopes:
                continue

            decision = self.strategy.decide_applicability(
                query=query,
                card=card,
                profile=profile,
                context=app_context,
                allow_sensitive_model_use=self.policy.allow_model_visibility_for_sensitive,
            )

            if not decision.allowed and is_hard_block(decision):
                decisions_by_id[card.id] = decision
                continue
            if not decision.allowed:
                decision = decision.model_copy(
                    update={
                        "allowed": True,
                        "risk_flags": [risk for risk in decision.risk_flags if not risk.startswith("below_applicability_threshold")],
                        "reasons": [*decision.reasons, "soft_applicability_threshold:retained_by_retrieval_signal"],
                    }
                )
            decisions_by_id[card.id] = decision
            lexical, why = self._score_card_fast(
                query, card, query_lower, query_tokens, query_embedding,
                card_tokens_set, card_emb,
            )
            meta = dict(source_metadata.get(card.id, {}))
            embedding_score = float(meta.get("vector_similarity", 0.0) or 0.0)

            features = build_feature_vector(
                card=card, profile=profile, decision=decision,
                lexical_score=lexical, source_metadata=meta,
                embedding_score=embedding_score, now=now,
            )
            raw_features.append((features, card, [*why, *decision.reasons]))

        scored, feature_by_id = _batch_score_features(raw_features)
        return scored, decisions_by_id, feature_by_id

    def _apply_embedding_rescore(
        self,
        query: str,
        scored: list[tuple[float, MemoryCard, list[str]]],
        feature_by_id: dict[str, RetrievalFeatureVector] | None = None,
        *,
        record_calls: bool = True,
    ) -> list[tuple[float, MemoryCard, list[str]]]:
        embedding = self.providers.optional_embedding()
        if embedding is None or not scored:
            return scored
        context = ProviderCallContext(
            purpose="memory_embedding_retrieval",
            provider_kind="embedding",
            garden_home=str(self.garden_home),
            allow_remote=embedding.is_remote,
        )
        self.policy.assert_provider_call_allowed(context, query)
        cached_vectors: dict[str, list[float]] = {}
        model_key = self._embedding_model_key(embedding)
        for _base, card, _why in scored:
            text = _card_text(card)
            cached = self.store.get_memory_embedding(
                memory_id=card.id,
                model=model_key,
                content_hash=self._content_hash(text),
            )
            if cached is not None:
                cached_vectors[card.id] = cached
        if cached_vectors:
            query_vectors = self._embedding_vectors(embedding.embed_texts([query], context=context))
            if not query_vectors:
                return scored
            query_vector = query_vectors[0]
            rescored_cached: list[tuple[float, MemoryCard, list[str]]] = []
            for base, card, why in scored:
                vector = cached_vectors.get(card.id)
                if vector is None:
                    rescored_cached.append((base, card, why))
                    continue
                ext_sim = cosine_similarity(query_vector, vector)
                previous = feature_by_id.get(card.id) if feature_by_id else None
                if previous is not None:
                    updated = RetrievalFeatureVector(
                        memory_id=previous.memory_id,
                        fts_score=previous.fts_score,
                        lexical_score=previous.lexical_score,
                        applicability_score=previous.applicability_score,
                        recency_policy_score=previous.recency_policy_score,
                        embedding_score=max(previous.embedding_score, ext_sim),
                        vector_recall=previous.vector_recall,
                    )
                    feature_by_id[card.id] = updated
                    base, feature_notes = score_feature_vector(updated)
                    why = [*why, "cached_embedding_similarity", *feature_notes]
                rescored_cached.append((base, card, why))
            return rescored_cached

        texts = [query, *[_card_text(card) for _score, card, _why in scored]]
        vectors = self._embedding_vectors(embedding.embed_texts(texts, context=context))
        if len(vectors) != len(scored) + 1:
            return scored
        query_vector = vectors[0]
        rescored: list[tuple[float, MemoryCard, list[str]]] = []
        for base, card, why in scored:
            ext_sim = cosine_similarity(query_vector, vectors[len(rescored) + 1])
            if ext_sim > 0.0:
                previous = feature_by_id.get(card.id) if feature_by_id else None
                if previous is not None:
                    updated = RetrievalFeatureVector(
                        memory_id=previous.memory_id,
                        fts_score=previous.fts_score,
                        lexical_score=previous.lexical_score,
                        applicability_score=previous.applicability_score,
                        recency_policy_score=previous.recency_policy_score,
                        embedding_score=max(previous.embedding_score, ext_sim),
                        vector_recall=previous.vector_recall,
                    )
                    feature_by_id[card.id] = updated
                    base, feature_notes = score_feature_vector(updated)
                    why = [*why, "external_embedding_similarity", *feature_notes]
                else:
                    base += ext_sim * 0.25
                    why = [*why, "external_embedding_similarity"]
            rescored.append((base, card, why))
        if record_calls:
            self.store.record_provider_call(
                {
                    "id": new_id("provider_call"),
                    "provider_name": embedding.name,
                    "provider_kind": "embedding",
                    "purpose": "memory_embedding_retrieval",
                    "created_at": utc_now().isoformat(),
                    "candidate_count": len(rescored),
                }
            )
        return rescored

    def _apply_provider_rerank(
        self,
        query: str,
        scored: list[tuple[float, MemoryCard, list[str]]],
        limit: int,
    ) -> tuple[list[tuple[float, MemoryCard, list[str]]], str]:
        reranker = self.providers.optional_reranker()
        if reranker is None or not scored:
            return scored, ""
        candidates = [
            RerankCandidate(id=card.id, text=_card_text(card), metadata={"base_score": score})
            for score, card, _why in scored[: self.providers.policy.max_candidates_per_call]
        ]
        context = ProviderCallContext(
            purpose="memory_rerank",
            provider_kind="reranker",
            garden_home=str(self.garden_home),
            allow_remote=reranker.is_remote,
        )
        self.policy.assert_provider_call_allowed(
            context,
            "\n".join([query, *[candidate.text for candidate in candidates]]),
        )
        result = reranker.rerank(
            query=query,
            candidates=candidates,
            top_k=limit,
            context=context,
        )
        self.store.record_provider_call(
            {
                "id": new_id("provider_call"),
                "provider_name": reranker.name,
                "provider_kind": "reranker",
                "purpose": "memory_rerank",
                "created_at": utc_now().isoformat(),
                "candidate_count": len(candidates),
            }
        )
        id_to_item = {card.id: (score, card, why) for score, card, why in scored}
        reranked: list[tuple[float, MemoryCard, list[str]]] = []
        for mid in result.ranked_ids:
            if mid in id_to_item:
                score, card, why = id_to_item[mid]
                reranked.append((result.scores.get(mid, score), card, [*why, *result.explanations.get(mid, [])]))
        if reranked:
            return reranked, reranker.name
        return scored, ""

    def build_brief(
        self,
        query: str,
        *,
        limit: int = 5,
        context: ApplicabilityContext | dict[str, Any] | None = None,
    ) -> GardenBrief:
        result = self.retrieve(query, limit=limit, context=context)
        ids = [hit.memory.id for hit in result.hits]
        if ids:
            use = "; ".join(f"{hit.memory.title}: {hit.memory.essence}" for hit in result.hits)
        else:
            use = "No relevant local memory matched this query."
        return GardenBrief(
            intent=f"Memory Garden product brief for: {query[:120]}",
            use=use,
            avoid="Do not invent memories or infer beyond the listed source ids.",
            style="Use the memories only when directly relevant.",
            safety="Respect sensitivity and visibility policy.",
            nudge="Ignore any memory whose scope, maturity, or applicability does not fit the current task.",
            source_memory_ids=ids,
        )

    def harvest_cognitive(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: CognitiveHarvestMode | None = None,
    ) -> tuple[Any, Any]:
        from memory_garden.harvest.harvester import GardenHarvester

        if not query or not query.strip():
            raise ValueError("query must be non-empty")
        harvester = GardenHarvester(
            emb_provider=self.cognition_providers.get("emb_provider"),
            rank_provider=self.cognition_providers.get("rank_provider"),
            cog_writer=self.cognition_providers.get("cog_writer"),
        )
        scan = scan_memory_cards(
            self.repository,
            include_greenhouse=False,
            max_cards=max(1, limit) * 20,
            source="product_harvest_cognitive",
        )
        hq = HarvestQuery(
            raw_user_text=query,
            metadata={
                RETRIEVAL_DIAGNOSTICS_KEY: scan.diagnostics,
                "total_available": scan.total_available,
                "truncated": scan.truncated,
                "retrieval_source": "product_harvest_cognitive",
            },
        )
        brief, trace = harvester.harvest_cognitive(hq, scan.cards, mode=mode)
        if scan.truncated:
            trace.warnings.append(
                f"memory_scan_truncated: scanned={scan.scanned_count} total={scan.total_available}"
            )
            breakdown = dict(trace.score_breakdown or {})
            breakdown[RETRIEVAL_DIAGNOSTICS_KEY] = scan.diagnostics
            trace.score_breakdown = breakdown
        return brief, trace

    # Strategy

    def get_strategy_profile(self, memory_id: str) -> MemoryStrategyProfile:
        return self._ensure_strategy_profile(self.repository.get_memory_card(memory_id))

    def assess_applicability(
        self,
        memory_id: str,
        query: str,
        *,
        context: ApplicabilityContext | dict[str, Any] | None = None,
    ) -> ApplicabilityDecision:
        card = self.repository.get_memory_card(memory_id)
        profile = self._ensure_strategy_profile(card)
        return self.strategy.decide_applicability(
            query=query,
            card=card,
            profile=profile,
            context=self._coerce_applicability_context(query, context),
            allow_sensitive_model_use=self.policy.allow_model_visibility_for_sensitive,
        )

    def reinforce_memory(
        self,
        memory_id: str,
        *,
        reason: str = "manual_reinforce",
        amount: float = 0.08,
    ) -> MemoryStrategyProfile:
        profile = self.get_strategy_profile(memory_id)
        updated, plan = self.strategy.reinforce_profile(profile, reason=reason, amount=amount)
        self.store.save_strategy_profile(updated)
        if plan is not None:
            self.store.save_evolution_plan(plan)
        return updated

    def decay_memories(self, *, limit: int = 500) -> list[MemoryEvolutionPlan]:
        plans: list[MemoryEvolutionPlan] = []
        for profile in self.store.list_strategy_profiles(limit=limit):
            updated, plan = self.strategy.decay_profile(profile)
            self.store.save_strategy_profile(updated)
            if plan is None:
                continue
            self.store.save_evolution_plan(plan)
            plans.append(plan)
            if plan.action == EvolutionAction.archive:
                try:
                    self.archive_memory(profile.memory_id, reason=plan.reason)
                except Exception as exc:
                    logger.debug("archive_memory failed for %s: %s", profile.memory_id, exc)
        return plans

    def plan_abstractions(self, *, limit: int = 500) -> list[MemoryEvolutionPlan]:
        cards = self.repository.list_memory_cards(include_greenhouse=False, limit=limit)
        profiles = [self._ensure_strategy_profile(card) for card in cards]
        plan = self.strategy.abstraction_plan(cards, profiles)
        if plan is None:
            return []
        return [self.store.save_evolution_plan(plan)]

    # Forget

    def plan_forget(self, target: str = "", *, memory_id: str | None = None, cascade: bool = True) -> ForgetPlanRecord:
        return self._forget_service.plan_forget(target, memory_id=memory_id, cascade=cascade)

    def execute_forget(self, plan_id: str) -> tuple[ForgetPlanRecord, ForgetProofRecord]:
        return self._forget_service.execute_forget(plan_id)

    def prove_forget(
        self,
        memory_id: str,
        *,
        plan_id: str = "",
        content_probes=None,
        cascade: bool | None = None,
    ) -> ForgetProofRecord:
        return self._forget_service.prove_forget(
            memory_id,
            plan_id=plan_id,
            content_probes=content_probes,
            cascade=cascade,
        )

    def resolve_memory_id(self, target: str) -> str | None:
        needle = (target or "").strip().casefold()
        if not needle:
            return None

        def _matches(card: MemoryCard) -> bool:
            if card.id == target:
                return True
            return needle in _card_text(card).casefold()

        scan = scan_memory_cards(
            self.repository,
            include_greenhouse=True,
            match_fn=_matches,
            source="product_resolve_memory_id",
        )
        for card in scan.cards:
            if _matches(card):
                return card.id
        return None

    # Internals

    def _get_candidate_source(self):
        source = getattr(self, "_candidate_source", None)
        if source is None:
            source = select_product_candidate_source(self.garden_home, self.repository)
            self._candidate_source = source
        return source

    def _provider_proposals(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None,
        source_seed_ids: list[str],
    ) -> list[MemoryProposal]:
        llm = self.providers.optional_llm()
        if llm is None:
            return []
        context = ProviderCallContext(
            purpose="memory_extraction",
            provider_kind="llm",
            garden_home=str(self.garden_home),
            allow_remote=llm.is_remote,
        )
        self.policy.assert_provider_call_allowed(context, text)
        schema = {
            "type": "object",
            "properties": {
                "proposals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "essence": {"type": "string"},
                            "evidence": {"type": "string"},
                            "memory_type": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "sensitivity": {"type": "string"},
                            "confidence": {"type": "number"},
                            "requires_confirmation": {"type": "boolean"},
                        },
                        "required": ["title", "essence"],
                    },
                }
            },
            "required": ["proposals"],
        }
        result = llm.complete_json(system="Extract memory proposals.", user=text, schema=schema, context=context)
        proposals = []
        for item in result.data.get("proposals", []):
            try:
                mt = MemoryType(item.get("memory_type", "unknown"))
            except ValueError:
                mt = MemoryType.unknown
            try:
                sl = SensitivityLevel(item.get("sensitivity", "none"))
            except ValueError:
                sl = SensitivityLevel.none
            proposals.append(
                MemoryProposal(
                    title=item.get("title") or text[:80],
                    essence=item.get("essence") or text,
                    evidence=item.get("evidence") or text[:500],
                    memory_type=mt,
                    tags=list(item.get("tags") or []),
                    sensitivity=sl,
                    confidence=float(item.get("confidence", 0.6)),
                    requires_confirmation=bool(item.get("requires_confirmation", True)),
                    source=llm.name,
                    source_seed_ids=list(source_seed_ids),
                    metadata={**dict(metadata or {}), "source_seed_ids": list(source_seed_ids)},
                )
            )
        self.store.record_provider_call(
            {
                "id": new_id("provider_call"),
                "provider_name": llm.name,
                "provider_kind": "llm",
                "purpose": "memory_extraction",
                "created_at": utc_now().isoformat(),
                "proposal_count": len(proposals),
            }
        )
        return proposals

    def _local_proposal(
        self,
        text: str,
        *,
        metadata: dict[str, Any] | None,
        source_seed_ids: list[str],
    ) -> MemoryProposal:
        clean = text.strip()
        title = _title_from_text(clean)
        tags = _tags_from_text(clean)
        memory_type = _type_from_tags(tags)
        return MemoryProposal(
            title=title,
            essence=clean,
            evidence=clean[:500],
            memory_type=memory_type,
            tags=tags,
            sensitivity=SensitivityLevel.none,
            confidence=0.72 if "explicit_remember" in tags else 0.58,
            requires_confirmation="explicit_remember" not in tags,
            source="local_rules",
            source_seed_ids=list(source_seed_ids),
            metadata={**dict(metadata or {}), "source_seed_ids": list(source_seed_ids)},
        )

    def _source_seed_ids_for_proposal(self, text: str, metadata: dict[str, Any] | None) -> list[str]:
        meta = dict(metadata or {})
        provided = meta.get("source_seed_ids")
        if provided is None:
            provided = meta.get("source_seed_id")
        if isinstance(provided, str):
            ids = [provided]
        elif isinstance(provided, list):
            ids = [item for item in provided if isinstance(item, str)]
        else:
            ids = []
        ids = [item.strip() for item in ids if item.strip()]
        if ids:
            return list(dict.fromkeys(ids))

        clean = text.strip()
        context = dict(meta)
        context.setdefault("product_source", True)
        context.setdefault("source_role", str(context.get("role") or "user"))
        seed = Seed(
            content=clean,
            source_excerpt=clean[:500],
            context=context,
            tags=["product_proposal_source"],
            signal_type=SeedSignalType.unknown,
            confidence=0.6,
            status=SeedStatus.held,
        )
        return [self.repository.save_seed(seed).id]

    def _ensure_strategy_profile(self, card: MemoryCard) -> MemoryStrategyProfile:
        cache = getattr(self, "_profile_cache", None)
        if cache is not None and card.id in cache:
            return cache[card.id]
        profile = self.store.get_strategy_profile(card.id)
        if profile is not None:
            if cache is not None:
                cache[card.id] = profile
            return profile
        proposal = MemoryProposal(
            title=card.title,
            essence=card.essence,
            evidence=card.fragrance,
            memory_type=card.memory_type,
            tags=list(card.tags),
            sensitivity=card.sensitivity,
            confidence=card.confidence,
            requires_confirmation=False,
            source="backfilled_card",
            source_seed_ids=list(card.source_seed_ids),
        )
        result = self.store.save_strategy_profile(self.strategy.profile_for_new_memory(proposal, card.id))
        try:
            self._index_card_for_retrieval(card, profile=result)
        except Exception:
            pass  # index is a performance optimization, never block on failure
        return result

    def _index_card_for_retrieval(self, card: MemoryCard, profile: MemoryStrategyProfile | None = None) -> None:
        """写时索引：预计算并持久化检索所需的静态特征。"""
        profile = profile or self._ensure_strategy_profile(card)
        text = _card_text(card)
        card_tokens = sorted(set(_tokens(text)))
        card_embedding = embed_local(text)
        updated = card.updated_at
        if hasattr(updated, "isoformat"):
            updated_str = updated.isoformat()
        else:
            updated_str = str(updated)
        self.store.save_retrieval_index(
            memory_id=card.id,
            card_tokens=card_tokens,
            card_embedding=card_embedding,
            card_importance=float(card.importance or 0.5),
            card_confidence=float(card.confidence or 0.5),
            card_lifecycle=card.lifecycle.value if hasattr(card.lifecycle, "value") else str(card.lifecycle),
            card_sensitivity=card.sensitivity.value if hasattr(card.sensitivity, "value") else str(card.sensitivity),
            card_tags=list(card.tags),
            card_updated_at=updated_str,
            strategy_layer=profile.layer.value if hasattr(profile.layer, "value") else str(profile.layer),
            strategy_scope=profile.scope.value if hasattr(profile.scope, "value") else str(profile.scope),
            strategy_scope_id=profile.scope_id,
            strategy_maturity=profile.maturity.value if hasattr(profile.maturity, "value") else str(profile.maturity),
            strategy_strength=float(profile.strength),
            updated_at=utc_now().isoformat(),
        )

    def reindex_retrieval_scores(self, *, limit: int | None = None) -> dict[str, int]:
        """重建所有记忆的检索索引。策略规则更新后调用。"""
        cards = self.repository.list_memory_cards(include_greenhouse=False, limit=limit or get_product_scan_limit())
        indexed = 0
        skipped_errors = 0
        for card in cards:
            try:
                self._index_card_for_retrieval(card)
                indexed += 1
            except Exception:
                skipped_errors += 1
        return {"indexed": indexed, "skipped_errors": skipped_errors}

    def _view_from_card(self, card: MemoryCard, profile: MemoryStrategyProfile | None = None) -> MemoryView:
        profile = profile or self._ensure_strategy_profile(card)
        return MemoryView.from_card(card).model_copy(
            update={
                "layer": profile.layer.value,
                "scope": profile.scope.value,
                "scope_id": profile.scope_id,
                "maturity": profile.maturity.value,
                "strength": profile.strength,
                "evidence_count": profile.evidence_count,
            }
        )

    def _coerce_applicability_context(
        self,
        query: str,
        context: ApplicabilityContext | dict[str, Any] | None,
    ) -> ApplicabilityContext:
        if context is None:
            return ApplicabilityContext(query=query)
        if isinstance(context, ApplicabilityContext):
            if context.query:
                return context
            return context.model_copy(update={"query": query})
        return ApplicabilityContext(query=query, **context)

    def _snapshot_version(
        self,
        card: MemoryCard,
        *,
        reason: str,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.store.save_version(
            MemoryVersionRecord(
                memory_id=card.id,
                version=self.store.next_version_number(card.id, conn=conn),
                reason=reason,
                snapshot=card.model_dump(mode="json"),
            ),
            conn=conn,
        )

    def _record_approval_failure(self, proposal: MemoryProposal, failed_memory_id: str, exc: Exception) -> None:
        """事务已回滚后记录错误态 proposal（路径 B 下 memory/product 写入同一连接）。"""
        cleanup_status: list[str] = []
        if failed_memory_id:
            try:
                cleanup_status.extend(self.store.delete_memory_products(failed_memory_id))
            except Exception as cleanup_exc:
                cleanup_status.append(f"cleanup_failed:{type(cleanup_exc).__name__}:{cleanup_exc}")
        failed = proposal.model_copy(
            update={
                "status": MemoryProposalStatus.error,
                "created_memory_id": None,
                "updated_at": utc_now(),
                "metadata": {
                    **proposal.metadata,
                    "approve_error": f"{type(exc).__name__}: {exc}",
                    "failed_memory_id": failed_memory_id,
                    "cleanup_status": cleanup_status,
                },
            }
        )
        try:
            self.store.save_proposal(failed)
        except Exception as save_exc:
            logger.debug("failed to persist approval error state for %s: %s", proposal.id, save_exc)

    def _score_card(self, query: str, card: MemoryCard) -> tuple[float, MemoryCard, list[str]]:
        query_lower = query.casefold()
        query_tokens = set(_tokens(query))
        query_emb = embed_local(query)
        text = _card_text(card)
        card_tokens = set(_tokens(text))
        card_emb = embed_local(text)
        score, why = self._score_card_fast(
            query, card, query_lower, query_tokens, query_emb, card_tokens, card_emb,
        )
        return score, card, why

    def _score_card_fast(
        self,
        query: str,
        card: MemoryCard,
        query_lower: str,
        query_tokens: set[str],
        query_embedding: list[float],
        card_tokens: set[str],
        card_embedding: list[float],
    ) -> tuple[float, list[str]]:
        coarse = default_garden_runtime_config().harvest.coarse
        why: list[str] = []
        score = compute_coarse_lexical_score(query, card, weights=coarse)
        for token in sorted(query_tokens & card_tokens):
            why.append(f"keyword_match:{token}")
        if any(tag.casefold() in query_lower for tag in card.tags):
            why.append("tag_match")
        local_sim = cosine_similarity(query_embedding, card_embedding)
        if local_sim > coarse.local_embedding_threshold:
            score += local_sim * coarse.local_embedding_weight
            why.append("local_embedding_similarity")
        return score, why


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type.value,
        "object_type": event.object_type.value,
        "object_id": event.object_id,
        "summary": event.summary,
        "created_at": event.created_at.isoformat(),
        "metadata": dict(event.metadata),
    }


def _title_from_text(text: str) -> str:
    clean = text.strip().replace("\n", " ")
    if clean.startswith("请记住："):
        clean = clean[len("请记住：") :]
    if clean.lower().startswith("remember:"):
        clean = clean[len("remember:") :]
    return clean[:80] or "Untitled memory"


def _tags_from_text(text: str) -> list[str]:
    lower = text.casefold()
    tags = []
    if any(marker in lower for marker in ("remember", "记住", "请记住")):
        tags.append("explicit_remember")
    if any(marker in lower for marker in ("prefer", "preference", "喜欢", "偏好")):
        tags.append("preference")
    if any(marker in lower for marker in ("must", "never", "不要", "必须")):
        tags.append("constraint")
    if any(marker in lower for marker in ("project", "项目")):
        tags.append("project")
    return tags or ["memory"]


def _type_from_tags(tags: list[str]) -> MemoryType:
    if "preference" in tags:
        return MemoryType.preference
    if "constraint" in tags:
        return MemoryType.boundary
    if "project" in tags:
        return MemoryType.project
    return MemoryType.unknown
