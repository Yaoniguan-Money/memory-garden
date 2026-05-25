"""Observatory queries over the repository abstraction.

Observatory is read-only, but it should not parse SQLite payload columns itself.
This module loads domain objects through ``SQLiteGardenRepository`` and then
maps them into display-oriented view models.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_garden.observatory.views import (
    CourtroomView,
    DreamView,
    GardenMapData,
    GardenSummaryView,
    MemoryCardView,
    SeedJourneyView,
)
from memory_garden.soil.index import DB_FILENAME
from memory_garden.storage.legacy_payloads import load_legacy_payload_summary
from memory_garden.storage.sqlite import SQLiteGardenRepository

_DEFAULT_LIMIT = 50


def _value(obj: Any) -> str:
    return str(getattr(obj, "value", obj) or "")


def _event_counts(events: list[Any]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        object_id = getattr(event, "object_id", "")
        if object_id:
            counts[str(object_id)] += 1
    return dict(counts)


def _memory_view(card: Any, *, event_count: int) -> MemoryCardView:
    return MemoryCardView(
        memory_id=getattr(card, "id", ""),
        title=getattr(card, "title", "") or "",
        essence=getattr(card, "essence", "") or "",
        memory_type=_value(getattr(card, "memory_type", "")),
        lifecycle=_value(getattr(card, "lifecycle", "")),
        tags=list(getattr(card, "tags", []) or []),
        fragrance=getattr(card, "fragrance", "") or "",
        thorns=getattr(card, "thorns", "") or "",
        confidence=float(getattr(card, "confidence", 0) or 0),
        importance=float(getattr(card, "importance", 0) or 0),
        sensitivity=_value(getattr(card, "sensitivity", "low")),
        source_seed_ids=list(getattr(card, "source_seed_ids", []) or []),
        court_case_ids=list(getattr(card, "court_case_ids", []) or []),
        dream_record_ids=list(getattr(card, "dream_record_ids", []) or []),
        created_at=str(getattr(card, "created_at", "")),
        updated_at=str(getattr(card, "updated_at", "")),
        related_event_count=event_count,
    )


def _memory_view_from_payload(data: dict[str, Any], *, event_count: int) -> MemoryCardView:
    return MemoryCardView(
        memory_id=str(data.get("id", "")),
        title=str(data.get("title", "") or ""),
        essence=str(data.get("essence", "") or ""),
        memory_type=str(data.get("memory_type", "") or ""),
        lifecycle=str(data.get("lifecycle", "") or ""),
        tags=list(data.get("tags", []) or []),
        fragrance=str(data.get("fragrance", "") or ""),
        thorns=str(data.get("thorns", "") or ""),
        confidence=float(data.get("confidence", 0) or 0),
        importance=float(data.get("importance", 0) or 0),
        sensitivity=str(data.get("sensitivity", "low") or "low"),
        source_seed_ids=list(data.get("source_seed_ids", []) or []),
        court_case_ids=list(data.get("court_case_ids", []) or []),
        dream_record_ids=list(data.get("dream_record_ids", []) or []),
        created_at=str(data.get("created_at", "") or ""),
        updated_at=str(data.get("updated_at", "") or ""),
        related_event_count=event_count,
    )


def _summary_from_legacy_payloads(db: Path, *, limit: int) -> GardenSummaryView:
    data = load_legacy_payload_summary(db, limit=limit)
    if not data:
        return GardenSummaryView.empty()

    memories_raw = list(data.get("memory_cards", []) or [])
    seeds_raw = list(data.get("seeds", []) or [])
    cases_raw = list(data.get("court_cases", []) or [])
    dreams_raw = list(data.get("dream_records", []) or [])
    events_raw = list(data.get("garden_events", []) or [])

    event_count_by_object = Counter(str(e.get("object_id", "")) for e in events_raw if e.get("object_id"))
    lifecycle_counts = Counter(str(m.get("lifecycle", "")) for m in memories_raw)
    type_counts = Counter(str(m.get("memory_type", "")) for m in memories_raw)
    status_counts = Counter(str(s.get("status", "")) for s in seeds_raw)
    tag_counts: Counter[str] = Counter()
    for memory in memories_raw:
        tag_counts.update(str(tag) for tag in memory.get("tags", []) or [])

    garden_map = GardenMapData.from_stats(
        memory_count=len(memories_raw),
        seed_count=len(seeds_raw),
        court_case_count=len(cases_raw),
        dream_record_count=len(dreams_raw),
        greenhouse_count=len(data.get("greenhouse_records", []) or []),
        compost_count=len(data.get("compost_records", []) or []),
        pruning_count=len(data.get("pruning_records", []) or []),
        event_count=len(events_raw),
        memory_by_lifecycle=dict(lifecycle_counts),
        memory_by_type=dict(type_counts),
        seed_by_status=dict(status_counts),
        top_tags=tag_counts.most_common(12),
    )

    memories = [
        _memory_view_from_payload(m, event_count=event_count_by_object.get(str(m.get("id", "")), 0))
        for m in memories_raw[:limit]
    ]
    seeds = [
        SeedJourneyView(
            seed_id=str(s.get("id", "")),
            source_excerpt=str(s.get("source_excerpt", s.get("content", "")) or ""),
            created_at=str(s.get("created_at", "") or ""),
            status=str(s.get("status", "") or ""),
            signal_type=str(s.get("signal_type", "") or ""),
            related_event_count=event_count_by_object.get(str(s.get("id", "")), 0),
        )
        for s in seeds_raw[:limit]
    ]
    cases = [
        CourtroomView(
            court_case_id=str(c.get("id", "")),
            seed_id=str(c.get("seed_id", "") or ""),
            prosecutor_argument=str(c.get("prosecutor_argument", "") or ""),
            defender_argument=str(c.get("defender_argument", "") or ""),
            privacy_guard_argument=str(c.get("privacy_guard_argument", "") or ""),
            judge_verdict=str((c.get("judge_verdict", {}) or {}).get("verdict", "") or ""),
            verdict_reason=str((c.get("judge_verdict", {}) or {}).get("reason", "") or ""),
            matched_rules=list(c.get("matched_rules", []) or []),
            risk_flags=list(c.get("risk_flags", []) or []),
            confidence=float((c.get("judge_verdict", {}) or {}).get("confidence", 0) or 0),
            created_at=str(c.get("created_at", "") or ""),
        )
        for c in cases_raw[:limit]
    ]
    dreams = [
        DreamView(
            dream_record_id=str(d.get("id", "")),
            observation=str(d.get("observation", "") or ""),
            reflection=str(d.get("reflection", "") or ""),
            transformation=str(d.get("transformation", "") or ""),
            morning_garden=str(d.get("morning_garden", "") or ""),
            input_seed_ids=list(d.get("input_seed_ids", []) or []),
            input_memory_ids=list(d.get("input_memory_ids", []) or []),
            created_memory_ids=list(d.get("created_memory_ids", []) or []),
            merged_memory_ids=list(d.get("merged_memory_ids", []) or []),
            composted_seed_ids=list(d.get("composted_seed_ids", []) or []),
            pruned_memory_ids=list(d.get("pruned_memory_ids", []) or []),
            created_at=str(d.get("created_at", "") or ""),
        )
        for d in dreams_raw[:limit]
    ]

    return GardenSummaryView(
        map=garden_map,
        recent_memories=memories,
        recent_seeds=seeds,
        recent_cases=cases,
        recent_dreams=dreams,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def build_garden_summary(
    garden_home: str | Path,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> GardenSummaryView:
    """Query a real garden database and return a populated ``GardenSummaryView``.

    Returns an empty summary if the database does not exist or cannot be read.
    """
    db = Path(garden_home).resolve() / DB_FILENAME
    if not db.is_file():
        return GardenSummaryView.empty()

    try:
        repo = SQLiteGardenRepository(str(db))
    except Exception:
        return _summary_from_legacy_payloads(db, limit=limit)

    try:
        memories_all = repo.list_memory_cards(include_greenhouse=True)
        memories_recent = repo.list_memory_cards(include_greenhouse=True, limit=limit)
        seeds_all = repo.list_seeds()
        seeds_recent = repo.list_seeds(limit=limit)
        cases_all = repo.list_court_cases()
        cases_recent = repo.list_court_cases(limit=limit)
        dreams_all = repo.list_dream_records()
        dreams_recent = repo.list_dream_records(limit=limit)
        greenhouse_records = repo.list_greenhouse_records()
        compost_records = repo.list_compost_records()
        pruning_records = repo.list_pruning_records()
        events = repo.list_garden_events(limit=None)
    except Exception:
        return _summary_from_legacy_payloads(db, limit=limit)
    finally:
        repo.close()

    lifecycle_counts = Counter(_value(getattr(card, "lifecycle", "")) for card in memories_all)
    type_counts = Counter(_value(getattr(card, "memory_type", "")) for card in memories_all)
    status_counts = Counter(_value(getattr(seed, "status", "")) for seed in seeds_all)
    tag_counts: Counter[str] = Counter()
    for card in memories_all:
        tag_counts.update(str(tag) for tag in getattr(card, "tags", []) or [])

    garden_map = GardenMapData.from_stats(
        memory_count=len(memories_all),
        seed_count=len(seeds_all),
        court_case_count=len(cases_all),
        dream_record_count=len(dreams_all),
        greenhouse_count=len(greenhouse_records),
        compost_count=len(compost_records),
        pruning_count=len(pruning_records),
        event_count=len(events),
        memory_by_lifecycle=dict(lifecycle_counts),
        memory_by_type=dict(type_counts),
        seed_by_status=dict(status_counts),
        top_tags=tag_counts.most_common(12),
    )

    event_count_by_object = _event_counts(events)
    memories = [
        _memory_view(card, event_count=event_count_by_object.get(getattr(card, "id", ""), 0))
        for card in memories_recent
    ]
    seeds = [
        SeedJourneyView.from_seed(seed, event_count=event_count_by_object.get(getattr(seed, "id", ""), 0))
        for seed in seeds_recent
    ]
    cases = [CourtroomView.from_court_case(case) for case in cases_recent]
    dreams = [DreamView.from_dream_record(record) for record in dreams_recent]

    return GardenSummaryView(
        map=garden_map,
        recent_memories=memories,
        recent_seeds=seeds,
        recent_cases=cases,
        recent_dreams=dreams,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
