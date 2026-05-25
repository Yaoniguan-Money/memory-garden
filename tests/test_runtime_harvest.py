"""第二层 Stage 2D：Harvester / BriefWriter 协议与占位实现。"""

import inspect
import json

import pytest
from pydantic import ValidationError

from memory_garden.runtime.harvest import NullHarvester, TemplateBriefWriter
from memory_garden.runtime.interfaces import BriefWriterProtocol, HarvesterProtocol
from memory_garden.runtime.session import GardenBrief, TurnContext


def _minimal_turn() -> TurnContext:
    return TurnContext(session_id="s", turn_index=0, user_message="hi")


def test_null_harvester_satisfies_protocol() -> None:
    h = NullHarvester()
    assert isinstance(h, HarvesterProtocol)


def test_template_writer_satisfies_protocol() -> None:
    w = TemplateBriefWriter()
    assert isinstance(w, BriefWriterProtocol)


def test_null_harvester_returns_garden_brief() -> None:
    b = NullHarvester().harvest(_minimal_turn())
    assert isinstance(b, GardenBrief)


def test_null_harvester_empty_source_memory_ids() -> None:
    b = NullHarvester().harvest(_minimal_turn())
    assert b.source_memory_ids == []


def test_template_writer_returns_garden_brief() -> None:
    b = TemplateBriefWriter().write(["m1", "m2", 123], _minimal_turn())
    assert isinstance(b, GardenBrief)
    assert "m1" in b.source_memory_ids


def test_template_writer_source_has_no_llm_stack_keywords() -> None:
    import memory_garden.runtime.harvest as hv

    src = inspect.getsource(hv)
    lower = src.lower()
    for bad in ("llm", "embedding", "vector", "search", "openai", "rerank"):
        assert bad not in lower


def test_harvest_module_has_no_core_imports() -> None:
    import memory_garden.runtime.harvest as hv

    src = inspect.getsource(hv)
    for needle in ("MemoryGardenCore", "SQLiteGardenRepository", "SeedObserver", "memory_garden.core"):
        assert needle not in src


def test_garden_brief_json_roundtrip_from_harvest() -> None:
    b = NullHarvester().harvest(_minimal_turn())
    raw = b.model_dump(mode="json")
    json.dumps(raw)
    b2 = GardenBrief.model_validate(raw)
    assert b2.intent == b.intent


def test_garden_brief_field_length_guard() -> None:
    long_text = "x" * 600
    with pytest.raises(ValidationError):
        GardenBrief(
            intent=long_text,
            use="u",
            avoid="a",
            style="s",
            safety="sf",
            nudge="n",
        )
