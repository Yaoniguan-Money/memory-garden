"""Memory strategy engine: layering, scope, applicability, conflict, evolution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard, MemoryType, SensitivityLevel
from memory_garden.core.text_utils import card_text as _card_text, tokenize_text as _tokens
from memory_garden.product.models import (
    ApplicabilityContext,
    ApplicabilityDecision,
    ConflictArbitrationRecord,
    ConflictResolutionStatus,
    EvolutionAction,
    MemoryEvolutionPlan,
    MemoryLayer,
    MemoryMaturityStage,
    MemoryProposal,
    MemoryRelation,
    MemoryRelationType,
    MemoryScope,
    MemoryStrategyProfile,
    utc_now,
)

# ── 适用性评分权重（可通过 MemoryPolicy 扩展配置）──
_SCOPE_MATCH_BONUS = 0.18
_KEYWORD_OVERLAP_MAX = 0.35
_KEYWORD_OVERLAP_PER = 0.06
_TAG_HIT_MAX = 0.18
_TAG_HIT_PER = 0.06
_LAYER_MATCH_BONUS = 0.12
_LAYER_WEAK_PENALTY = 0.08
_MATURITY_BONUS: dict[MemoryMaturityStage, float] = {
    MemoryMaturityStage.candidate: -0.12,
    MemoryMaturityStage.observed: 0.0,
    MemoryMaturityStage.stable: 0.12,
    MemoryMaturityStage.canonical: 0.20,
    MemoryMaturityStage.deprecated: -0.35,
}
_STRENGTH_MULTIPLIER = 0.35
_STRENGTH_OFFSET = 0.5
_STALE_DAYS_THRESHOLD = 90
_STALE_PENALTY = 0.18
_CONTRADICTION_MAX_PENALTY = 0.25
_CONTRADICTION_PER = 0.08


class MemoryStrategyEngine:
    """Deterministic strategy engine for product-grade memory behavior."""

    def profile_for_new_memory(self, proposal: MemoryProposal, memory_id: str) -> MemoryStrategyProfile:
        layer = proposal.suggested_layer or self.classify_layer(
            proposal.memory_type,
            proposal.tags,
            f"{proposal.title}\n{proposal.essence}\n{proposal.evidence}",
        )
        if proposal.suggested_scope is not None:
            scope = proposal.suggested_scope
            scope_id = proposal.suggested_scope_id
        else:
            scope, scope_id = self.infer_scope(proposal.metadata, proposal.tags)
        maturity = self.initial_maturity(proposal)
        strength = self.initial_strength(proposal, layer)
        return MemoryStrategyProfile(
            memory_id=memory_id,
            layer=layer,
            scope=scope,
            scope_id=scope_id,
            maturity=maturity,
            strength=strength,
            evidence_count=max(1, len(proposal.source_seed_ids) or 1),
            mention_count=1,
            applies_to_tags=list(dict.fromkeys([*proposal.tags, layer.value])),
            last_reinforced_at=utc_now(),
            metadata={
                "proposal_id": proposal.id,
                "proposal_source": proposal.source,
                "requires_confirmation": proposal.requires_confirmation,
            },
        )

    def classify_layer(self, memory_type: MemoryType, tags: list[str], text: str) -> MemoryLayer:
        tagset = {tag.casefold() for tag in tags}
        lower = text.casefold()
        if memory_type == MemoryType.identity or "identity" in tagset:
            return MemoryLayer.identity
        if memory_type == MemoryType.boundary or "constraint" in tagset or "must" in lower or "never" in lower:
            return MemoryLayer.safety_boundary
        if memory_type == MemoryType.preference or "preference" in tagset or "prefer" in lower:
            return MemoryLayer.preference
        if memory_type == MemoryType.procedural or "workflow" in tagset or "procedure" in tagset:
            return MemoryLayer.procedural
        if memory_type == MemoryType.project or "project" in tagset:
            return MemoryLayer.project_state
        if any(marker in tagset for marker in ("fact", "semantic", "knowledge")):
            return MemoryLayer.semantic
        return MemoryLayer.episodic

    def infer_scope(
        self,
        metadata: dict[str, Any],
        tags: list[str],
        suggested_scope: MemoryScope | None = None,
    ) -> tuple[MemoryScope, str]:
        if suggested_scope is not None:
            return suggested_scope, str(metadata.get("scope_id") or metadata.get("strategy_scope_id") or "")
        if metadata.get("project_id"):
            return MemoryScope.project, str(metadata["project_id"])
        if metadata.get("workspace_id"):
            return MemoryScope.workspace, str(metadata["workspace_id"])
        if metadata.get("session_id"):
            return MemoryScope.session, str(metadata["session_id"])
        if metadata.get("identity_id") or "identity" in {tag.casefold() for tag in tags}:
            return MemoryScope.identity, str(metadata.get("identity_id") or metadata.get("user_id") or "")
        return MemoryScope.global_user, str(metadata.get("user_id") or "")

    def initial_maturity(self, proposal: MemoryProposal) -> MemoryMaturityStage:
        if proposal.requires_confirmation:
            return MemoryMaturityStage.observed
        if proposal.confidence >= 0.8:
            return MemoryMaturityStage.stable
        return MemoryMaturityStage.observed

    def initial_strength(self, proposal: MemoryProposal, layer: MemoryLayer) -> float:
        base = max(0.25, min(0.9, proposal.confidence))
        if layer in (MemoryLayer.safety_boundary, MemoryLayer.identity):
            base += 0.05
        if proposal.requires_confirmation:
            base -= 0.05
        return max(0.1, min(1.0, base))

    def annotate_proposal_strategy(self, proposal: MemoryProposal) -> MemoryProposal:
        layer = self.classify_layer(
            proposal.memory_type,
            proposal.tags,
            f"{proposal.title}\n{proposal.essence}\n{proposal.evidence}",
        )
        scope, scope_id = self.infer_scope(proposal.metadata, proposal.tags, proposal.suggested_scope)
        tags = list(dict.fromkeys([*proposal.tags, f"layer:{layer.value}", f"scope:{scope.value}"]))
        metadata = {**proposal.metadata, "strategy_layer": layer.value, "strategy_scope": scope.value}
        if scope_id:
            metadata["strategy_scope_id"] = scope_id
        return proposal.model_copy(
            update={
                "tags": tags,
                "suggested_layer": layer,
                "suggested_scope": scope,
                "suggested_scope_id": scope_id,
                "metadata": metadata,
            }
        )

    def decide_applicability(
        self,
        *,
        query: str,
        card: MemoryCard,
        profile: MemoryStrategyProfile,
        context: ApplicabilityContext | None = None,
        allow_sensitive_model_use: bool = False,
    ) -> ApplicabilityDecision:
        context = context or ApplicabilityContext(query=query)
        reasons: list[str] = []
        risks: list[str] = []
        score = 0.0
        allowed = True

        if card.lifecycle in (MemoryLifecycle.pruned, MemoryLifecycle.composted):
            return ApplicabilityDecision(
                memory_id=card.id,
                allowed=False,
                score=0.0,
                reasons=["memory_is_archived"],
                maturity=profile.maturity,
            )

        scope_match, scope_reason = self._scope_matches(profile, context)
        if scope_match:
            score += _SCOPE_MATCH_BONUS
            reasons.append(scope_reason)
        else:
            allowed = False
            risks.append(scope_reason)

        if card.sensitivity in (SensitivityLevel.medium, SensitivityLevel.high) and not (
            context.allow_sensitive or allow_sensitive_model_use
        ):
            allowed = False
            risks.append("sensitive_memory_blocked_for_context")

        query_tokens = set(_tokens(query or context.query))
        memory_tokens = set(_tokens(_card_text(card)))
        overlap = sorted(query_tokens & memory_tokens)
        if overlap:
            score += min(_KEYWORD_OVERLAP_MAX, _KEYWORD_OVERLAP_PER * len(overlap))
            reasons.extend(f"keyword:{token}" for token in overlap[:6])
        tag_hits = sorted(tag for tag in card.tags if tag.casefold() in (query or context.query).casefold())
        if tag_hits:
            score += min(_TAG_HIT_MAX, _TAG_HIT_PER * len(tag_hits))
            reasons.extend(f"tag:{tag}" for tag in tag_hits[:4])

        if profile.layer in self._preferred_layers_for_task(context.task_type):
            score += _LAYER_MATCH_BONUS
            reasons.append(f"layer_matches_task:{profile.layer.value}")
        elif context.task_type:
            score -= _LAYER_WEAK_PENALTY
            reasons.append(f"layer_weak_for_task:{profile.layer.value}")

        maturity_bonus = _MATURITY_BONUS[profile.maturity]
        score += maturity_bonus
        reasons.append(f"maturity:{profile.maturity.value}")

        score += (profile.strength - _STRENGTH_OFFSET) * _STRENGTH_MULTIPLIER
        days_old = _days_since(profile.last_reinforced_at or profile.updated_at)
        if days_old > _STALE_DAYS_THRESHOLD and profile.maturity not in (MemoryMaturityStage.canonical, MemoryMaturityStage.stable):
            score -= _STALE_PENALTY
            risks.append("stale_memory")
        if profile.contradiction_count:
            score -= min(_CONTRADICTION_MAX_PENALTY, profile.contradiction_count * _CONTRADICTION_PER)
            risks.append("has_unresolved_contradictions")

        score = max(0.0, min(1.0, score))
        threshold = self._threshold_for_layer(profile.layer)
        if score < threshold:
            allowed = False
            risks.append(f"below_applicability_threshold:{threshold:.2f}")

        return ApplicabilityDecision(
            memory_id=card.id,
            allowed=allowed,
            score=score,
            reasons=reasons,
            risk_flags=risks,
            scope_match=scope_match,
            layer_match=not any(r.startswith("layer_weak_for_task") for r in reasons),
            maturity=profile.maturity,
        )

    def reinforce_profile(
        self,
        profile: MemoryStrategyProfile,
        *,
        reason: str,
        amount: float = 0.05,
    ) -> tuple[MemoryStrategyProfile, MemoryEvolutionPlan | None]:
        before = profile.model_dump(mode="json")
        strength = min(1.0, profile.strength + amount)
        use_count = profile.use_count + 1
        maturity = self._promoted_stage(profile.maturity, profile.evidence_count, profile.mention_count, use_count, strength)
        updated = profile.model_copy(
            update={
                "strength": strength,
                "use_count": use_count,
                "maturity": maturity,
                "last_reinforced_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        plan = None
        if maturity != profile.maturity:
            plan = MemoryEvolutionPlan(
                memory_id=profile.memory_id,
                action=EvolutionAction.promote,
                status="executed",
                reason=reason,
                before=before,
                after=updated.model_dump(mode="json"),
                executed_at=utc_now(),
            )
        return updated, plan

    def decay_profile(self, profile: MemoryStrategyProfile, *, now: datetime | None = None) -> tuple[MemoryStrategyProfile, MemoryEvolutionPlan | None]:
        now = now or utc_now()
        anchor = profile.last_reinforced_at or profile.updated_at
        days = max(0, (now - anchor).days)
        if days < 30 or profile.maturity == MemoryMaturityStage.canonical:
            return profile, None
        before = profile.model_dump(mode="json")
        decay = min(0.3, days / 365.0 * 0.25)
        strength = max(0.0, profile.strength - decay)
        maturity = profile.maturity
        action = EvolutionAction.decay
        status = "executed"
        reason = f"memory not reinforced for {days} days"
        if strength < 0.2:
            maturity = MemoryMaturityStage.deprecated
            action = EvolutionAction.archive
        updated = profile.model_copy(
            update={
                "strength": strength,
                "maturity": maturity,
                "last_decayed_at": now,
                "updated_at": now,
            }
        )
        plan = MemoryEvolutionPlan(
            memory_id=profile.memory_id,
            action=action,
            status=status,
            reason=reason,
            before=before,
            after=updated.model_dump(mode="json"),
            executed_at=now,
        )
        return updated, plan

    def arbitrate_conflict(
        self,
        *,
        proposal: MemoryProposal,
        existing: MemoryCard,
        existing_profile: MemoryStrategyProfile | None,
        new_memory_id: str = "",
    ) -> ConflictArbitrationRecord:
        reasons: list[str] = []
        status = ConflictResolutionStatus.needs_user_review
        winner = ""
        loser = ""
        resolution = "manual_review_required"
        confidence = 0.55

        new_is_correction = _looks_like_correction(proposal.essence, proposal.tags)
        if new_is_correction:
            winner = new_memory_id
            loser = existing.id
            status = ConflictResolutionStatus.superseded if new_memory_id else ConflictResolutionStatus.needs_user_review
            resolution = "new_user_correction_supersedes_existing"
            reasons.append("proposal_looks_like_explicit_correction")
            confidence = 0.82
        elif existing_profile and existing_profile.maturity in (MemoryMaturityStage.stable, MemoryMaturityStage.canonical):
            winner = existing.id
            loser = new_memory_id
            resolution = "existing_stable_memory_retained"
            reasons.append(f"existing_maturity:{existing_profile.maturity.value}")
            confidence = 0.72
        elif proposal.confidence > existing.confidence + 0.2:
            winner = new_memory_id
            loser = existing.id
            resolution = "higher_confidence_new_memory"
            reasons.append("proposal_confidence_significantly_higher")
            confidence = 0.68
        else:
            reasons.append("insufficient_conflict_evidence")

        return ConflictArbitrationRecord(
            proposal_id=proposal.id,
            new_memory_id=new_memory_id,
            existing_memory_id=existing.id,
            status=status,
            winner_memory_id=winner or "",
            loser_memory_id=loser or "",
            resolution=resolution,
            reasons=reasons,
            confidence=confidence,
            resolved_at=utc_now() if status in (ConflictResolutionStatus.resolved, ConflictResolutionStatus.superseded) else None,
        )

    def abstraction_plan(self, cards: list[MemoryCard], profiles: list[MemoryStrategyProfile]) -> MemoryEvolutionPlan | None:
        if len(cards) < 3:
            return None
        profile_by_id = {profile.memory_id: profile for profile in profiles}
        stable_cards = [
            card
            for card in cards
            if (profile_by_id.get(card.id) and profile_by_id[card.id].maturity in (MemoryMaturityStage.stable, MemoryMaturityStage.canonical))
        ]
        if len(stable_cards) < 3:
            return None
        common_tags = set(stable_cards[0].tags)
        for card in stable_cards[1:]:
            common_tags &= set(card.tags)
        if not common_tags:
            return None
        return MemoryEvolutionPlan(
            memory_id=stable_cards[0].id,
            action=EvolutionAction.abstract,
            reason=f"stable memories share tags: {', '.join(sorted(common_tags)[:5])}",
            related_memory_ids=[card.id for card in stable_cards],
            after={"common_tags": sorted(common_tags), "candidate_count": len(stable_cards)},
        )

    def relation_for_arbitration(self, arbitration: ConflictArbitrationRecord) -> MemoryRelation:
        if arbitration.winner_memory_id and arbitration.loser_memory_id:
            source = arbitration.loser_memory_id
            target = arbitration.winner_memory_id
            relation_type = MemoryRelationType.supersedes
        else:
            source = arbitration.new_memory_id or arbitration.existing_memory_id
            target = arbitration.existing_memory_id
            relation_type = MemoryRelationType.contradicts
        return MemoryRelation(
            relation_type=relation_type,
            source_memory_id=source,
            target_memory_id=target,
            reason=arbitration.resolution,
            confidence=arbitration.confidence,
            metadata={"arbitration_id": arbitration.id, "status": arbitration.status.value},
        )

    def _scope_matches(self, profile: MemoryStrategyProfile, context: ApplicabilityContext) -> tuple[bool, str]:
        if profile.scope == MemoryScope.global_user:
            return True, "scope:global_user"
        if profile.scope == MemoryScope.project:
            return profile.scope_id == context.project_id, "scope:project_match" if profile.scope_id == context.project_id else "scope_project_mismatch"
        if profile.scope == MemoryScope.workspace:
            return profile.scope_id == context.workspace_id, "scope:workspace_match" if profile.scope_id == context.workspace_id else "scope_workspace_mismatch"
        if profile.scope == MemoryScope.session:
            return profile.scope_id == context.session_id, "scope:session_match" if profile.scope_id == context.session_id else "scope_session_mismatch"
        if profile.scope == MemoryScope.identity:
            if profile.scope_id and profile.scope_id == context.user_id:
                return True, "scope:identity_match"
            if not profile.scope_id:
                return False, "scope_identity_missing_id"
            return False, "scope_identity_mismatch"
        return False, "scope_unknown"

    def _preferred_layers_for_task(self, task_type: str) -> set[MemoryLayer]:
        task = task_type.casefold()
        if task in ("code", "coding", "implementation", "debug"):
            return {MemoryLayer.preference, MemoryLayer.procedural, MemoryLayer.project_state, MemoryLayer.safety_boundary}
        if task in ("chat", "conversation", "writing"):
            return {MemoryLayer.preference, MemoryLayer.identity, MemoryLayer.safety_boundary}
        if task in ("planning", "project"):
            return {MemoryLayer.project_state, MemoryLayer.procedural, MemoryLayer.preference}
        return set(MemoryLayer)

    def _threshold_for_layer(self, layer: MemoryLayer) -> float:
        if layer in (MemoryLayer.identity, MemoryLayer.safety_boundary):
            return 0.18
        if layer == MemoryLayer.episodic:
            return 0.34
        return 0.25

    def _promoted_stage(
        self,
        current: MemoryMaturityStage,
        evidence_count: int,
        mention_count: int,
        use_count: int,
        strength: float,
    ) -> MemoryMaturityStage:
        if current == MemoryMaturityStage.deprecated:
            return current
        if strength >= 0.9 and evidence_count >= 3 and (mention_count + use_count) >= 5:
            return MemoryMaturityStage.canonical
        if strength >= 0.72 and (evidence_count >= 2 or (mention_count + use_count) >= 3):
            return MemoryMaturityStage.stable
        if current == MemoryMaturityStage.candidate:
            return MemoryMaturityStage.observed
        return current


def _days_since(value: datetime | None) -> int:
    if value is None:
        return 0
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, (now - value).days)


def _looks_like_correction(text: str, tags: list[str]) -> bool:
    lower = text.casefold()
    tagset = {tag.casefold() for tag in tags}
    return bool(
        {"correction", "correct", "override", "supersede"} & tagset
        or any(marker in lower for marker in ("actually", "correction", "instead", "not anymore", "更正", "不是", "改成"))
    )
