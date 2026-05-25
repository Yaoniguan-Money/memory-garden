"""Tests for v1.4 features: context manager, HTML report, embedding providers."""

import asyncio
import os

from memory_garden.sdk import MemoryGarden


# ── Context managers ────────────────────────────────────────────────


def test_sync_context_manager(tmp_path):
    with MemoryGarden.local(tmp_path / "garden") as garden:
        r = garden.chat("花花开")
        assert r.session_id is not None


def test_async_context_manager(tmp_path):
    async def _run():
        async with MemoryGarden.local(tmp_path / "garden") as garden:
            r = await garden.async_chat("花花开")
            assert r.session_id is not None

    asyncio.run(_run())


# ── HTML report ─────────────────────────────────────────────────────


def test_html_report_renders(tmp_path):
    from memory_garden.observatory.views import (
        CourtroomView,
        DreamView,
        GardenMapData,
        GardenSummaryView,
        MemoryCardView,
        SeedJourneyView,
    )
    from memory_garden.observatory.renderers.html_report import render_html_report

    card = MemoryCardView(memory_id="m1", title="Dark Mode", lifecycle="bloom",
                          memory_type="preference", tags=["ui"], essence="Prefers dark mode.")
    seed = SeedJourneyView(seed_id="s1", status="planted", signal_type="preference")
    case = CourtroomView(court_case_id="c1", judge_verdict="plant", verdict_reason="Valid")
    dream = DreamView(dream_record_id="d1", observation="Pattern found")
    m = GardenMapData.from_stats(memory_count=1, seed_count=1, court_case_count=1)
    summary = GardenSummaryView(
        map=m, recent_memories=[card], recent_seeds=[seed],
        recent_cases=[case], recent_dreams=[dream],
    )
    html = render_html_report(summary)
    assert "<!DOCTYPE html>" in html
    assert "Dark Mode" in html
    assert "Garden Map" in html
    assert "Memory Cards" in html
    assert "plant" in html
    assert "</html>" in html


def test_html_report_escapes_xss():
    from memory_garden.observatory.views import GardenSummaryView, MemoryCardView
    from memory_garden.observatory.renderers.html_report import render_html_report

    card = MemoryCardView(memory_id="m1", title="<script>alert(1)</script>")
    summary = GardenSummaryView(recent_memories=[card])
    html = render_html_report(summary)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── Embedding providers ─────────────────────────────────────────────


def test_local_embedding_provider():
    from memory_garden.integrations.embedding_providers import LocalEmbeddingProvider

    p = LocalEmbeddingProvider(dimensions=64)
    vec = p.embed("hello world")
    assert len(vec) == 64
    assert p.dimensions == 64
    assert p.config.provider == "memory-garden-local"

    batch = p.embed_batch(["a", "b", "c"])
    assert len(batch) == 3


def test_local_embedding_provider_deterministic():
    from memory_garden.integrations.embedding_providers import LocalEmbeddingProvider

    p = LocalEmbeddingProvider()
    v1 = p.embed("test")
    v2 = p.embed("test")
    assert v1 == v2


def test_sentence_transformers_provider_imports():
    """Provider class imports without forcing a model download."""
    from memory_garden.integrations.embedding_providers import (
        SentenceTransformersProvider,
    )
    p = SentenceTransformersProvider()
    assert p.config.model == "all-MiniLM-L6-v2"
    assert p.dimensions == 384
    if os.environ.get("MEMORY_GARDEN_RUN_REAL_EMBEDDINGS") != "1":
        return
    p.embed("test")


def test_html_report_renders_empty(tmp_path):
    from memory_garden.observatory.views import GardenSummaryView
    from memory_garden.observatory.renderers.html_report import render_html_report

    html = render_html_report(GardenSummaryView.empty())
    assert "<!DOCTYPE html>" in html
    assert "Memory Cards" in html


def test_no_memory_garden_created(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    with MemoryGarden.local(tmp_path / "garden") as garden:
        garden.chat("花花开")

    if not existed_before:
        assert not os.path.exists(cwd_mg)
