"""End-to-end tests for the complete Memory Garden SDK cycle."""

import os

from memory_garden.covenant.enforcer import CovenantEnforcer
from memory_garden.covenant.defaults import default_garden_covenant
from memory_garden.integrations.mock_providers import (
    MockEmbeddingProvider,
    MockLLMProvider,
    MockRelevanceProvider,
)
from memory_garden.sdk import MemoryGarden


def test_e2e_full_cycle_with_covenant(tmp_path):
    """Full garden cycle with Covenant enforcement enabled."""
    garden = MemoryGarden.local(
        tmp_path / "garden",
        covenant=default_garden_covenant(),
    )
    try:
        # Enforcer is attached
        assert garden.enforcer is not None
        assert isinstance(garden.enforcer, CovenantEnforcer)

        # Before harvesting, enforcer should allow bloom memories
        result = garden.enforcer.before_harvest(
            type("Mem", (), {"id": "m1", "lifecycle": "bloom", "sensitivity": "low", "tags": []})(),
            purpose="brief",
        )
        assert result.allowed is True

        # Full chat cycle
        r1 = garden.chat("花花开")
        sid = r1.session_id
        r2 = garden.chat("I prefer dark mode for all interfaces.", session_id=sid)
        assert r2.reply is not None
        r3 = garden.chat("花花关", session_id=sid)
        assert r3.feedback is not None
    finally:
        garden.close()


def test_e2e_health_and_summary(tmp_path):
    """Health check and observatory summary from the same garden."""
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        garden.chat("花花开")
        health = garden.health()
        assert health.status.value in ("healthy", "degraded")

        summary = garden.summary()
        assert summary.map is not None
        assert hasattr(summary, "recent_memories")
    finally:
        garden.close()


def test_e2e_no_covenant_no_error(tmp_path):
    """Without covenant, enforcer is None — no crash."""
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        assert garden.enforcer is None
        r = garden.chat("花花开")
        assert r.session_id is not None
    finally:
        garden.close()


def test_e2e_mock_providers_satisfy_contracts():
    """All mock providers satisfy their respective ABC contracts."""
    llm = MockLLMProvider()
    result = llm.structured_generate("hello", dict)
    assert isinstance(result, dict)
    assert llm.config.provider == "mock"

    emb = MockEmbeddingProvider(dimensions=32)
    vec = emb.embed("test")
    assert len(vec) == 32
    assert emb.dimensions == 32
    batch = emb.embed_batch(["a", "b", "c"])
    assert len(batch) == 3

    rel = MockRelevanceProvider()
    scores = rel.score("dark mode", ["I prefer dark mode", "banana smoothie", "dark themes"])
    assert len(scores) == 3
    assert scores[0] > scores[1]  # "dark mode" should match better than "banana"
    assert scores[2] > scores[1]


def test_e2e_provider_registry_composition():
    """ProviderRegistry can hold mock providers."""
    import warnings
    warnings.filterwarnings('ignore', message='integrations.providers.ProviderRegistry')
    from memory_garden.integrations.providers import ProviderRegistry

    reg = ProviderRegistry(
        llm=MockLLMProvider(),
        embedding=MockEmbeddingProvider(),
        relevance=MockRelevanceProvider(),
    )
    assert reg.has_llm
    assert reg.has_embedding
    assert reg.has_relevance


def test_e2e_observe_cli(tmp_path):
    """CLI observe command works on a populated garden."""
    from memory_garden.__main__ import main
    import sys
    from io import StringIO

    path = tmp_path / "garden"
    garden = MemoryGarden.local(path)
    garden.chat("花花开")
    garden.close()

    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(["observe", "--path", str(path)])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    assert rc == 0
    assert "Garden" in output or "No data" in output


def test_e2e_no_memory_garden_created(tmp_path):
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed_before = os.path.exists(candidate)

    garden = MemoryGarden.local(tmp_path / "garden")
    garden.chat("花花开")
    garden.health()
    garden.summary()
    garden.close()

    if not existed_before:
        assert not os.path.exists(candidate)
