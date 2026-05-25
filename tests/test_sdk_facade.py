"""Tests for MemoryGarden SDK Facade."""

import os

from memory_garden.cognition.fake_providers import FakeBriefWriterProvider, FakeHarvestRerankerProvider
from memory_garden.product import ProductMemorySystem
from memory_garden.providers import FakeEmbeddingProvider
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.models import GardenHome


def test_local_creates_garden_home(tmp_path):
    path = tmp_path / "my_garden"
    garden = MemoryGarden.local(path)
    try:
        assert isinstance(garden.home, GardenHome)
        assert garden.home.root == path.resolve()
        assert (path / "manifest.json").is_file()
    finally:
        garden.close()


def test_local_creates_database(tmp_path):
    path = tmp_path / "garden2"
    garden = MemoryGarden.local(path)
    try:
        assert (path / "garden.db").is_file()
    finally:
        garden.close()


def test_garden_health_is_not_unhealthy(tmp_path):
    path = tmp_path / "garden3"
    garden = MemoryGarden.local(path)
    try:
        report = garden.health()
        # No FTS index yet, so degraded is expected — not unhealthy
        assert report.status in ("healthy", "degraded")
    finally:
        garden.close()


def test_garden_chat_flower_open(tmp_path):
    path = tmp_path / "garden4"
    garden = MemoryGarden.local(path)
    try:
        result = garden.chat("花花开")
        assert result.session_id is not None
        assert "花花开" not in result.reply  # command short-circuit
    finally:
        garden.close()


def test_garden_chat_full_cycle(tmp_path):
    path = tmp_path / "garden5"
    garden = MemoryGarden.local(path)
    try:
        r1 = garden.chat("花花开")
        sid = r1.session_id
        r2 = garden.chat("I prefer dark mode.", session_id=sid)
        assert r2.reply is not None
        r3 = garden.chat("花花关", session_id=sid)
        assert r3.feedback is not None
    finally:
        garden.close()


def test_garden_properties(tmp_path):
    path = tmp_path / "garden6"
    garden = MemoryGarden.local(path)
    try:
        assert garden.core is not None
        assert garden.runtime is not None
        assert garden.observer is not None
        assert garden.home is not None
    finally:
        garden.close()


def test_local_does_not_create_memory_garden_in_cwd(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    path = tmp_path / "garden7"
    garden = MemoryGarden.local(path)
    garden.close()

    if not existed_before:
        assert not os.path.exists(cwd_mg), "MemoryGarden.local must not create .memory_garden in CWD"


def test_sdk_retrieve_and_build_brief_use_strategy_context(tmp_path):
    garden = MemoryGarden.local(
        tmp_path / "garden8",
        strategy_context={"scope": "project", "project_id": "atlas"},
    )
    try:
        product = ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)
        atlas = product.remember(
            "remember: release brief should include rollback checklist",
            mode="trusted",
            metadata={"project_id": "atlas"},
        )["approved_memory_ids"][0]
        zephyr = product.remember(
            "remember: release brief should include customer checklist",
            mode="trusted",
            metadata={"project_id": "zephyr"},
        )["approved_memory_ids"][0]

        retrieved = garden.retrieve("release brief checklist")
        brief = garden.build_brief("release brief checklist")
        hit_ids = [hit.memory.id for hit in retrieved.hits]

        assert atlas in hit_ids
        assert zephyr not in hit_ids
        assert atlas in brief.source_memory_ids
        assert zephyr not in brief.source_memory_ids
    finally:
        garden.close()


def test_local_cognition_providers_feed_runtime_harvest(tmp_path):
    garden = MemoryGarden.local(
        tmp_path / "garden9",
        cognition={
            "emb_provider": FakeEmbeddingProvider(dimensions=64),
            "rank_provider": FakeHarvestRerankerProvider(),
            "cog_writer": FakeBriefWriterProvider(),
        },
    )
    try:
        product = ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)
        memory_id = product.remember(
            "remember: sdk runtime recall should surface cobalt marker",
            mode="trusted",
        )["approved_memory_ids"][0]

        session = garden.runtime.open_session()
        result = garden.chat("cobalt marker runtime recall", session_id=session.session_id)

        assert result.garden_brief is not None
        assert memory_id in result.garden_brief.source_memory_ids
    finally:
        garden.close()
