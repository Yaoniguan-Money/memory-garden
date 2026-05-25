"""Rules-only GardenBouquet placement."""

from __future__ import annotations

from typing import Any

from memory_garden.harvest.models import (
    BouquetSlot,
    GardenBouquet,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.ranking import HarvestRankOutcome
from memory_garden.runtime_config import BouquetPlacementConfig


def _score_map(scores: list[HarvestScore]) -> dict[str, HarvestScore]:
    mapped: dict[str, HarvestScore] = {}
    for score in scores:
        if score.candidate_id not in mapped:
            mapped[score.candidate_id] = score
    return mapped


def _lifecycle(source_memory: dict[str, Any]) -> str:
    value = source_memory.get("lifecycle")
    return value.strip().lower() if isinstance(value, str) else ""


def _coerce_source(candidate_metadata: dict[str, Any]) -> dict[str, Any]:
    source_memory = candidate_metadata.get("source_memory")
    return source_memory if isinstance(source_memory, dict) else {}


def _is_caution(
    score: HarvestScore | None,
    *,
    lifecycle: str,
    thorns_preview_len: int,
    config: BouquetPlacementConfig,
) -> tuple[bool, str]:
    if lifecycle in config.caution_lifecycles:
        return True, f"caution_lifecycle:{lifecycle}"
    if score is None:
        return True, "caution_missing_score"
    notes = "\n".join(score.notes).lower()
    if "risk:" in notes or "greenhouse_candidate" in notes:
        return True, "caution_risk_notes"
    relevance = float(score.relevance)
    if relevance < config.caution_max_relevance:
        return True, "caution_low_relevance"
    if thorns_preview_len >= config.thorns_caution_min_chars:
        return True, f"caution_thorns_len(thorns_chars>={config.thorns_caution_min_chars})"
    return False, ""


def _token_estimate(excerpt_len: int, config: BouquetPlacementConfig) -> int:
    estimate = excerpt_len // config.token_estimate_chars_per_token + config.token_estimate_overhead
    return max(config.min_token_estimate, estimate)


class GardenBouquetBuilder:
    """Place ranked candidates into bouquet slots with configurable thresholds."""

    def __init__(self, config: BouquetPlacementConfig | None = None) -> None:
        self._config = config or BouquetPlacementConfig()

    def build(
        self,
        query: HarvestQuery,
        rank_outcome: HarvestRankOutcome,
        scores: list[HarvestScore],
        policy: HarvestBudgetPolicy | None = None,
    ) -> GardenBouquet:
        _ = query
        by_id = _score_map(scores)
        reject = set(rank_outcome.policy_decision.reject_candidate_ids)
        ranked = list(rank_outcome.ranked_candidates)

        max_total = int(policy.max_candidates) if policy is not None else len(ranked)
        if max_total < 0:
            max_total = 0
        soft_budget: int | None = None
        if policy is not None and policy.token_budget_soft is not None:
            soft_budget = int(policy.token_budget_soft)

        eligible_list = [
            (idx, cand)
            for idx, cand in enumerate(ranked)
            if cand.candidate_id not in reject
        ]

        core_ids, core_reason = self._select_core_candidates(eligible_list, by_id)
        slots = self._empty_slots()
        placements: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []

        token_so_far = 0
        placed = 0
        for _idx, cand in eligible_list:
            candidate_id = cand.candidate_id
            memory_id = cand.memory_id
            score = by_id.get(candidate_id)
            source = _coerce_source(cand.metadata)
            thorns_len = _thorns_len(source)

            is_caution, caution_reason = _is_caution(
                score,
                lifecycle=_lifecycle(source),
                thorns_preview_len=thorns_len,
                config=self._config,
            )

            estimate = _token_estimate(len(cand.excerpt or ""), self._config)
            if placed >= max_total:
                excluded.append(
                    {"candidate_id": candidate_id, "memory_id": memory_id, "reason": "excluded_by_budget_count"}
                )
                continue
            if soft_budget is not None and token_so_far + estimate > soft_budget:
                excluded.append(
                    {
                        "candidate_id": candidate_id,
                        "memory_id": memory_id,
                        "reason": "excluded_by_budget_token_soft",
                    }
                )
                continue

            slot, reason = self._slot_for_candidate(
                candidate_id,
                score,
                source,
                is_caution=is_caution,
                caution_reason=caution_reason,
                core_ids=core_ids,
                core_reason=core_reason,
            )
            slots[slot].append(candidate_id)
            placements.append(
                {
                    "candidate_id": candidate_id,
                    "memory_id": memory_id,
                    "slot": slot.value,
                    "reason": reason,
                }
            )
            token_so_far += estimate
            placed += 1

        return GardenBouquet(slots=slots, metadata=self._metadata(slots, placements, excluded))

    def _select_core_candidates(
        self,
        eligible_list: list[tuple[int, MemoryCandidate]],
        by_id: dict[str, HarvestScore],
    ) -> tuple[list[str], dict[str, str]]:
        scored_rows: list[tuple[int, str, float]] = []
        for idx, candidate in eligible_list:
            score = by_id.get(candidate.candidate_id)
            source = _coerce_source(candidate.metadata)
            is_caution, _reason = _is_caution(
                score,
                lifecycle=_lifecycle(source),
                thorns_preview_len=_thorns_len(source),
                config=self._config,
            )
            if is_caution or score is None:
                continue
            relevance = float(score.relevance)
            if relevance < self._config.core_pool_min_relevance:
                continue
            scored_rows.append((idx, candidate.candidate_id, relevance))

        scored_rows.sort(key=lambda row: (-row[2], row[0]))
        core_ids: list[str] = []
        core_reason: dict[str, str] = {}
        for _idx, candidate_id, _relevance in scored_rows:
            if len(core_ids) >= self._config.core_quota:
                break
            core_ids.append(candidate_id)
            core_reason[candidate_id] = "slot:primary:core_high_relevance"
        return core_ids, core_reason

    @staticmethod
    def _empty_slots() -> dict[BouquetSlot, list[str]]:
        return {
            BouquetSlot.PRIMARY: [],
            BouquetSlot.CORROBORATION: [],
            BouquetSlot.GUARDRAIL: [],
            BouquetSlot.CONTRAST: [],
            BouquetSlot.RESERVED: [],
        }

    def _slot_for_candidate(
        self,
        candidate_id: str,
        score: HarvestScore | None,
        source: dict[str, Any],
        *,
        is_caution: bool,
        caution_reason: str,
        core_ids: list[str],
        core_reason: dict[str, str],
    ) -> tuple[BouquetSlot, str]:
        if is_caution or score is None:
            reason = caution_reason or "caution"
            lifecycle = _lifecycle(source)
            if lifecycle:
                reason = f"{reason}|lifecycle={lifecycle}"
            return BouquetSlot.GUARDRAIL, reason
        if candidate_id in core_ids:
            return BouquetSlot.PRIMARY, core_reason.get(candidate_id, "slot:primary:core_high_relevance")
        return BouquetSlot.CORROBORATION, "slot:corroboration:support_relevant"

    @staticmethod
    def _metadata(
        slots: dict[BouquetSlot, list[str]],
        placements: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "placements": placements,
            "excluded": excluded,
            "candidate_ids_ordered": [
                candidate_id
                for slot in (
                    BouquetSlot.PRIMARY,
                    BouquetSlot.CORROBORATION,
                    BouquetSlot.GUARDRAIL,
                )
                for candidate_id in slots.get(slot, [])
            ],
            "memory_ids_ordered": [
                placement["memory_id"]
                for placement in placements
                if isinstance(placement.get("memory_id"), str)
            ],
        }


def _thorns_len(source: dict[str, Any]) -> int:
    thorns = source.get("thorns", "")
    return len(thorns) if isinstance(thorns, str) else 0
