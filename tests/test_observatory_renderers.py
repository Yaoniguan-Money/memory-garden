"""Tests for Observatory renderers (Markdown, JSON)."""

import json

from memory_garden.observatory.views import (
    CourtroomView,
    DreamView,
    GardenMapData,
    GardenSummaryView,
    MemoryCardView,
    SeedJourneyView,
)
from memory_garden.observatory.renderers.markdown import (
    render_garden_map_markdown,
    render_garden_summary_markdown,
    render_memory_card_markdown,
    render_seed_journey_markdown,
)
from memory_garden.observatory.renderers.json_export import (
    build_export_payload,
    export_garden_summary_json,
    export_map_json,
    export_memory_card_json,
)


def _sample_summary() -> GardenSummaryView:
    card = MemoryCardView(
        memory_id="m1", title="Dark Mode", essence="Prefers dark mode.",
        memory_type="preference", lifecycle="bloom",
        tags=["ui"], fragrance="Comforting", thorns="none",
        sensitivity="low", confidence=0.9, created_at="2025-01-01T00:00:00Z",
    )
    seed = SeedJourneyView(
        seed_id="s1", source_excerpt="I like dark mode", status="planted",
        signal_type="preference", court_case_ids=["c1"],
    )
    case = CourtroomView(
        court_case_id="c1", seed_id="s1", judge_verdict="plant",
        verdict_reason="Valid preference", created_at="2025-01-01T00:00:00Z",
    )
    dream = DreamView(
        dream_record_id="d1", observation="Patterns found",
        reflection="Consistent", transformation="Merged",
        created_at="2025-01-01T00:00:00Z",
    )
    m = GardenMapData.from_stats(memory_count=1, seed_count=1, court_case_count=1)
    return GardenSummaryView(
        map=m, recent_memories=[card], recent_seeds=[seed],
        recent_cases=[case], recent_dreams=[dream],
        generated_at="2025-01-01T00:00:00Z",
    )


def test_markdown_report_renders():
    summary = _sample_summary()
    md = render_garden_summary_markdown(summary)
    assert "Garden Observatory Report" in md
    assert "Garden Map" in md
    assert "Dark Mode" in md
    assert "Recent Memories" in md
    assert "Recent Seeds" in md
    assert "Recent Court Cases" in md
    assert "Recent Dreams" in md
    assert "Memory Cards | 1" in md


def test_markdown_map_renders():
    m = GardenMapData.from_stats(memory_count=3, seed_count=5)
    md = render_garden_map_markdown(m)
    assert "Memory Cards | 3" in md
    assert "Seeds | 5" in md


def test_markdown_memory_card_renders():
    card = MemoryCardView(memory_id="m1", title="Dark Mode", lifecycle="bloom", tags=["ui"])
    md = render_memory_card_markdown(card)
    assert "Dark Mode" in md
    assert "m1" in md
    assert "bloom" in md


def test_markdown_seed_journey_renders():
    seed = SeedJourneyView(seed_id="s1", status="planted", signal_type="preference",
                           source_excerpt="I like dark mode")
    md = render_seed_journey_markdown(seed)
    assert "s1" in md
    assert "planted" in md


def test_json_export_memory_card():
    card = MemoryCardView(memory_id="m1", title="Test")
    raw = export_memory_card_json(card)
    data = json.loads(raw)
    assert data["memory_id"] == "m1"


def test_json_export_map():
    m = GardenMapData.from_stats(memory_count=5)
    raw = export_map_json(m)
    data = json.loads(raw)
    assert data["memory_count"] == 5


def test_json_export_summary():
    summary = _sample_summary()
    raw = export_garden_summary_json(summary)
    data = json.loads(raw)
    assert "map" in data
    assert "recent_memories" in data


def test_build_export_payload():
    summary = _sample_summary()
    payload = build_export_payload(summary)
    assert payload["export_format"] == "memory-garden-observatory/v1"
    assert "exported_at" in payload
    assert len(payload["recent_memories"]) == 1
    assert len(payload["recent_seeds"]) == 1


def test_renderer_no_side_effects():
    """Calling render functions should not create files or .memory_garden."""
    import os
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    summary = _sample_summary()
    render_garden_summary_markdown(summary)
    export_garden_summary_json(summary)

    if not existed_before:
        assert not os.path.exists(cwd_mg)
