"""Product 写入工作流内部服务（propose / approve / remember）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard, SensitivityLevel
from memory_garden.product.models import MemoryProposal, MemoryProposalStatus, ProposalWritePolicy, utc_now
from memory_garden.product.policy import MemoryPolicy
from memory_garden.product.services.conflict import ConflictService
from memory_garden.product.storage import ProductMemoryStore
from memory_garden.product.strategy import MemoryStrategyEngine
from memory_garden.storage.base import GardenRepository


@dataclass(frozen=True)
class WriteReceipt:
    """内部写入回执（公开 API 仍返回 MemoryCard / dict）。"""

    proposals: list[MemoryProposal]
    approved_cards: list[MemoryCard]
    pending_proposal_ids: list[str]
    mode: str


class WriteWorkflowService:
    """协调 propose / approve / remember，保持 ProductMemorySystem 门面薄化。"""

    def __init__(
        self,
        *,
        repository: GardenRepository,
        store: ProductMemoryStore,
        strategy: MemoryStrategyEngine,
        policy: MemoryPolicy,
        conflict_service: ConflictService,
        provider_proposals: Callable[..., list[MemoryProposal]],
        local_proposal: Callable[..., MemoryProposal],
        source_seed_ids_for_proposal: Callable[..., list[str]],
        snapshot_version: Callable[..., None],
        record_approval_failure: Callable[[MemoryProposal, str, Exception], None],
        embedding_provider_resolver: Callable[[], Any | None] | None = None,
    ) -> None:
        self._repository = repository
        self._store = store
        self._strategy = strategy
        self._policy = policy
        self._conflict_service = conflict_service
        self._provider_proposals = provider_proposals
        self._local_proposal = local_proposal
        self._source_seed_ids_for_proposal = source_seed_ids_for_proposal
        self._snapshot_version = snapshot_version
        self._record_approval_failure = record_approval_failure
        self._embedding_provider_resolver = embedding_provider_resolver

    def propose(self, text: str, *, metadata: dict[str, Any] | None = None) -> list[MemoryProposal]:
        if not text or not text.strip():
            raise ValueError("proposal text must be non-empty")
        source_seed_ids = self._source_seed_ids_for_proposal(text, metadata)
        proposals = self._provider_proposals(text, metadata=metadata, source_seed_ids=source_seed_ids)
        if not proposals:
            proposals = [self._local_proposal(text, metadata=metadata, source_seed_ids=source_seed_ids)]
        out: list[MemoryProposal] = []
        for proposal in proposals:
            proposal = self._strategy.annotate_proposal_strategy(proposal)
            proposal = self._policy.apply_to_proposal(proposal)
            emb = self._embedding_provider_resolver() if self._embedding_provider_resolver else None
            proposal = self._conflict_service.annotate_proposal(proposal, embedding_provider=emb)
            self._store.save_proposal(proposal)
            out.append(proposal)
        return out

    def approve(self, proposal_id: str, *, auto: bool = False) -> MemoryCard:
        proposal = self._store.get_proposal(proposal_id)
        if proposal.status not in (MemoryProposalStatus.pending, MemoryProposalStatus.edited):
            raise ValueError(f"proposal is not approvable: {proposal.status.value}")
        if proposal.sensitivity == SensitivityLevel.high and not self._policy.allow_sensitive_storage:
            raise PermissionError("policy blocks high-sensitivity memory storage")
        card = MemoryCard(
            title=proposal.title,
            essence=proposal.essence,
            memory_type=proposal.memory_type,
            lifecycle=MemoryLifecycle.sprout,
            tags=proposal.tags,
            fragrance=proposal.evidence or proposal.essence,
            thorns="Use only when relevant and do not over-infer beyond the recorded evidence.",
            confidence=proposal.confidence,
            importance=0.6,
            sensitivity=proposal.sensitivity,
            source_seed_ids=proposal.source_seed_ids,
        )
        pending_proposal = proposal
        profile = self._strategy.profile_for_new_memory(pending_proposal, card.id)
        approved_proposal = pending_proposal.model_copy(
            update={
                "status": MemoryProposalStatus.approved,
                "created_memory_id": card.id,
                "updated_at": utc_now(),
                "metadata": {
                    **pending_proposal.metadata,
                    "decision": "auto_approve" if auto else "approve",
                },
            }
        )
        try:
            with self._repository.transaction() as repo_conn:
                saved = self._repository.save_memory_card(card)
                self._store.save_strategy_profile(profile, conn=repo_conn)
                self._snapshot_version(card, reason="proposal_approved", conn=repo_conn)
                self._store.save_proposal(approved_proposal, conn=repo_conn)
                self._conflict_service.persist_approval_conflicts(
                    approved_proposal, card.id, conn=repo_conn
                )
            return saved
        except Exception as exc:
            self._record_approval_failure(pending_proposal, card.id, exc)
            raise

    def remember(
        self,
        text: str,
        *,
        mode: ProposalWritePolicy | str = ProposalWritePolicy.trusted,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        write_policy = ProposalWritePolicy(mode)
        proposals = self.propose(text, metadata=metadata)
        approved: list[MemoryCard] = []
        approved_proposal_ids: set[str] = set()
        if write_policy == ProposalWritePolicy.auto:
            for proposal in proposals:
                approved.append(self.approve(proposal.id, auto=True))
                approved_proposal_ids.add(proposal.id)
        elif write_policy == ProposalWritePolicy.trusted:
            for proposal in proposals:
                if not proposal.requires_confirmation and proposal.sensitivity in (
                    SensitivityLevel.none,
                    SensitivityLevel.low,
                ):
                    approved.append(self.approve(proposal.id, auto=True))
                    approved_proposal_ids.add(proposal.id)
        receipt = WriteReceipt(
            proposals=proposals,
            approved_cards=approved,
            pending_proposal_ids=[p.id for p in proposals if p.id not in approved_proposal_ids],
            mode=write_policy.value,
        )
        return {
            "proposals": receipt.proposals,
            "approved_memory_ids": [card.id for card in receipt.approved_cards],
            "pending_proposal_ids": receipt.pending_proposal_ids,
            "mode": receipt.mode,
        }
