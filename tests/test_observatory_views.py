"""Tests for Observatory detailed views."""

from memory_garden.observatory.views import (
    CourtroomView,
    DreamView,
    GardenMapData,
    GardenSummaryView,
    MemoryCardView,
    SeedJourneyView,
)


def test_memory_card_view_from_dict():
    card = type("Card", (), {
        "id": "m1", "title": "Dark Mode", "essence": "User prefers dark mode.",
        "memory_type": "preference", "lifecycle": "bloom",
        "tags": ["ui", "dark"], "fragrance": "Comforting", "thorns": "none",
        "confidence": 0.9, "importance": 0.7, "sensitivity": "low",
        "source_seed_ids": ["s1"], "court_case_ids": ["c1"],
        "dream_record_ids": [], "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    })()
    view = MemoryCardView.from_memory_card(card, event_count=3)
    assert view.memory_id == "m1"
    assert view.title == "Dark Mode"
    assert view.lifecycle == "bloom"
    assert view.related_event_count == 3
    assert "ui" in view.tags
    assert view.sensitivity == "low"


def test_seed_journey_view_from_dict():
    seed = type("Seed", (), {
        "id": "s1", "content": "I like dark mode",
        "source_excerpt": "I like dark mode",
        "created_at": "2025-01-01T00:00:00Z",
        "status": "planted", "signal_type": "preference",
    })()
    view = SeedJourneyView.from_seed(seed, event_count=2)
    assert view.seed_id == "s1"
    assert view.status == "planted"
    assert view.signal_type == "preference"
    assert view.related_event_count == 2


def test_courtroom_view_from_dict():
    verdict = type("Verdict", (), {"verdict": "plant", "reason": "Valid preference", "confidence": 0.85})()
    case = type("Case", (), {
        "id": "c1", "seed_id": "s1",
        "prosecutor_argument": "Short term",
        "defender_argument": "Recurring pattern",
        "privacy_guard_argument": "No sensitive info",
        "judge_verdict": verdict,
        "matched_rules": ["rule_1"], "risk_flags": [],
        "created_at": "2025-01-01T00:00:00Z",
    })()
    view = CourtroomView.from_court_case(case)
    assert view.court_case_id == "c1"
    assert view.judge_verdict == "plant"
    assert "Valid preference" in view.verdict_reason


def test_dream_view_from_dict():
    record = type("Dream", (), {
        "id": "d1",
        "observation": "Patterns detected",
        "reflection": "Consistent preferences",
        "transformation": "Merged similar seeds",
        "morning_garden": "Garden stable",
        "input_seed_ids": ["s1", "s2"],
        "input_memory_ids": ["m1"],
        "created_memory_ids": [],
        "merged_memory_ids": ["m1"],
        "composted_seed_ids": [],
        "pruned_memory_ids": [],
        "created_at": "2025-01-01T00:00:00Z",
    })()
    view = DreamView.from_dream_record(record)
    assert view.dream_record_id == "d1"
    assert "merged" in view.transformation.lower()
    assert len(view.input_seed_ids) == 2


def test_garden_map_from_stats():
    m = GardenMapData.from_stats(
        memory_count=5, seed_count=10, court_case_count=3,
        dream_record_count=1, greenhouse_count=1, compost_count=2,
        pruning_count=0, event_count=20,
        memory_by_lifecycle={"bloom": 3, "rooted": 2},
        memory_by_type={"preference": 5},
        seed_by_status={"planted": 8, "pending": 2},
        top_tags=[("ui", 3), ("dark_mode", 2)],
    )
    assert m.memory_count == 5
    assert m.memory_by_lifecycle["bloom"] == 3
    assert m.generated_at != ""


def test_garden_summary_empty():
    s = GardenSummaryView.empty()
    assert s.map.memory_count == 0
    assert s.recent_memories == []


def test_views_json_roundtrip():
    view = MemoryCardView(
        memory_id="m1", title="Test", lifecycle="bloom",
        tags=["a", "b"], fragrance="nice", thorns="none",
    )
    data = view.model_dump(mode="json")
    v2 = MemoryCardView(**data)
    assert v2.memory_id == "m1"

    map_data = GardenMapData.from_stats(memory_count=1)
    data2 = map_data.model_dump(mode="json")
    m2 = GardenMapData(**data2)
    assert m2.memory_count == 1
