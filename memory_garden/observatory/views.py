"""Observatory detailed views: structured DTOs for garden entities.

These are read-only Pydantic models that present domain objects in a
display-friendly format.  Each view answers a specific question about
the garden's state.

Design source: planning Layer 6 (Garden Observatory).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MemoryCardView(BaseModel):
    """Plant profile: a MemoryCard presented for display."""

    memory_id: str = Field(description="MemoryCard ID")
    title: str = Field(default="")
    essence: str = Field(default="")
    memory_type: str = Field(default="")
    lifecycle: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    fragrance: str = Field(default="")
    thorns: str = Field(default="")
    confidence: float = Field(default=0.0)
    importance: float = Field(default=0.0)
    sensitivity: str = Field(default="low")
    source_seed_ids: list[str] = Field(default_factory=list)
    court_case_ids: list[str] = Field(default_factory=list)
    dream_record_ids: list[str] = Field(default_factory=list)
    pruning_record_ids: list[str] = Field(default_factory=list)
    compost_record_ids: list[str] = Field(default_factory=list)
    harvest_count: int = Field(default=0)
    last_harvested_at: str = Field(default="")
    created_at: str = Field(default="")
    updated_at: str = Field(default="")
    related_event_count: int = Field(default=0)

    @classmethod
    def from_memory_card(cls, card: Any, *, event_count: int = 0) -> "MemoryCardView":
        return cls(
            memory_id=getattr(card, "id", ""),
            title=getattr(card, "title", ""),
            essence=getattr(card, "essence", ""),
            memory_type=str(getattr(card, "memory_type", "")),
            lifecycle=str(getattr(card, "lifecycle", "")),
            tags=list(getattr(card, "tags", []) or []),
            fragrance=getattr(card, "fragrance", ""),
            thorns=getattr(card, "thorns", ""),
            confidence=float(getattr(card, "confidence", 0) or 0),
            importance=float(getattr(card, "importance", 0) or 0),
            sensitivity=str(getattr(card, "sensitivity", "low")),
            source_seed_ids=list(getattr(card, "source_seed_ids", []) or []),
            court_case_ids=list(getattr(card, "court_case_ids", []) or []),
            dream_record_ids=list(getattr(card, "dream_record_ids", []) or []),
            pruning_record_ids=[],
            compost_record_ids=[],
            harvest_count=0,
            last_harvested_at="",
            created_at=str(getattr(card, "created_at", "")),
            updated_at=str(getattr(card, "updated_at", "")),
            related_event_count=event_count,
        )


class SeedJourneyView(BaseModel):
    """Seed journey: where a seed came from and what happened to it."""

    seed_id: str = Field(description="Seed ID")
    source_excerpt: str = Field(default="")
    created_at: str = Field(default="")
    status: str = Field(default="")
    signal_type: str = Field(default="")
    court_case_ids: list[str] = Field(default_factory=list)
    verdict: str = Field(default="")
    resulting_memory_ids: list[str] = Field(default_factory=list)
    compost_record_ids: list[str] = Field(default_factory=list)
    greenhouse_record_ids: list[str] = Field(default_factory=list)
    pruning_record_ids: list[str] = Field(default_factory=list)
    related_event_count: int = Field(default=0)

    @classmethod
    def from_seed(cls, seed: Any, *, event_count: int = 0) -> "SeedJourneyView":
        return cls(
            seed_id=getattr(seed, "id", ""),
            source_excerpt=getattr(seed, "source_excerpt", getattr(seed, "content", "")),
            created_at=str(getattr(seed, "created_at", "")),
            status=str(getattr(seed, "status", "")),
            signal_type=str(getattr(seed, "signal_type", "")),
            related_event_count=event_count,
        )


class CourtroomView(BaseModel):
    """Courtroom view: the trial that decided a seed's fate."""

    court_case_id: str = Field(description="CourtCase ID")
    seed_id: str = Field(default="")
    seed_excerpt: str = Field(default="")
    prosecutor_argument: str = Field(default="")
    defender_argument: str = Field(default="")
    privacy_guard_argument: str = Field(default="")
    judge_verdict: str = Field(default="")
    verdict_reason: str = Field(default="")
    matched_rules: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0)
    created_at: str = Field(default="")

    @classmethod
    def from_court_case(cls, case: Any) -> "CourtroomView":
        return cls(
            court_case_id=getattr(case, "id", ""),
            seed_id=getattr(case, "seed_id", ""),
            prosecutor_argument=getattr(case, "prosecutor_argument", ""),
            defender_argument=getattr(case, "defender_argument", ""),
            privacy_guard_argument=getattr(case, "privacy_guard_argument", ""),
            judge_verdict=str(getattr(getattr(case, "judge_verdict", None), "verdict", "")),
            verdict_reason=str(getattr(getattr(case, "judge_verdict", None), "reason", "")),
            matched_rules=list(getattr(case, "matched_rules", []) or []),
            risk_flags=list(getattr(case, "risk_flags", []) or []),
            confidence=float(getattr(getattr(case, "judge_verdict", None), "confidence", 0) or 0),
            created_at=str(getattr(case, "created_at", "")),
        )


class DreamView(BaseModel):
    """Dream view: what the dream cycle observed and transformed."""

    dream_record_id: str = Field(description="DreamRecord ID")
    observation: str = Field(default="")
    reflection: str = Field(default="")
    transformation: str = Field(default="")
    morning_garden: str = Field(default="")
    input_seed_ids: list[str] = Field(default_factory=list)
    input_memory_ids: list[str] = Field(default_factory=list)
    created_memory_ids: list[str] = Field(default_factory=list)
    merged_memory_ids: list[str] = Field(default_factory=list)
    composted_seed_ids: list[str] = Field(default_factory=list)
    pruned_memory_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default="")

    @classmethod
    def from_dream_record(cls, record: Any) -> "DreamView":
        return cls(
            dream_record_id=getattr(record, "id", ""),
            observation=getattr(record, "observation", ""),
            reflection=getattr(record, "reflection", ""),
            transformation=getattr(record, "transformation", ""),
            morning_garden=getattr(record, "morning_garden", ""),
            input_seed_ids=list(getattr(record, "input_seed_ids", []) or []),
            input_memory_ids=list(getattr(record, "input_memory_ids", []) or []),
            created_memory_ids=list(getattr(record, "created_memory_ids", []) or []),
            merged_memory_ids=list(getattr(record, "merged_memory_ids", []) or []),
            composted_seed_ids=list(getattr(record, "composted_seed_ids", []) or []),
            pruned_memory_ids=list(getattr(record, "pruned_memory_ids", []) or []),
            created_at=str(getattr(record, "created_at", "")),
        )


class GardenMapData(BaseModel):
    """Garden map: a high-level summary of the entire garden structure."""

    memory_count: int = Field(default=0)
    memory_by_lifecycle: dict[str, int] = Field(default_factory=dict)
    memory_by_type: dict[str, int] = Field(default_factory=dict)
    seed_count: int = Field(default=0)
    seed_by_status: dict[str, int] = Field(default_factory=dict)
    court_case_count: int = Field(default=0)
    dream_record_count: int = Field(default=0)
    greenhouse_count: int = Field(default=0)
    compost_count: int = Field(default=0)
    pruning_count: int = Field(default=0)
    event_count: int = Field(default=0)
    top_tags: list[tuple[str, int]] = Field(default_factory=list)
    generated_at: str = Field(default="")

    @classmethod
    def from_stats(cls, **kwargs: Any) -> "GardenMapData":
        from datetime import timezone
        return cls(
            generated_at=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )


class GardenSummaryView(BaseModel):
    """Aggregated garden overview: the complete observable surface."""

    map: GardenMapData = Field(default_factory=GardenMapData)
    recent_memories: list[MemoryCardView] = Field(default_factory=list)
    recent_seeds: list[SeedJourneyView] = Field(default_factory=list)
    recent_cases: list[CourtroomView] = Field(default_factory=list)
    recent_dreams: list[DreamView] = Field(default_factory=list)
    generated_at: str = Field(default="")

    @classmethod
    def empty(cls) -> "GardenSummaryView":
        from datetime import timezone
        return cls(generated_at=datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_garden_home(cls, garden_home: str | "Path", *, limit: int = 50) -> "GardenSummaryView":
        """Query a real garden database and return a populated summary.

        Delegates to ``memory_garden.observatory.queries.build_garden_summary``.
        Returns an empty summary if the database does not exist.
        """
        from memory_garden.observatory.queries import build_garden_summary
        return build_garden_summary(garden_home, limit=limit)
