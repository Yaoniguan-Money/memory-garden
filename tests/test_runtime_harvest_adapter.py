"""第三层 Stage 3H：RuntimeGardenHarvesterAdapter 与 RuntimeHooks.before_reply 边界。"""

import inspect
import json

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.cognition.fake_providers import FakeBriefWriterProvider, FakeHarvestRerankerProvider
from memory_garden.cognition.models import CognitiveHarvestMode
from memory_garden.harvest import GardenHarvester, RuntimeGardenHarvesterAdapter, turn_context_to_harvest_query
from memory_garden.providers import FakeEmbeddingProvider
from memory_garden.runtime import GardenSessionManager, RuntimeHooks, RuntimeState
from memory_garden.runtime.harvest import TemplateBriefWriter
from memory_garden.runtime.interfaces import HarvesterProtocol
from memory_garden.runtime.session import GardenBrief, TurnContext


def _card(
    *,
    title="t",
    essence="e",
    fragrance="香",
    thorns="刺",
    tags=None,
    lifecycle=MemoryLifecycle.sprout,
    card_id="cid-1",
):
    return MemoryCard(
        id=card_id,
        title=title,
        essence=essence,
        fragrance=fragrance,
        thorns=thorns,
        tags=list(tags or []),
        lifecycle=lifecycle,
    )


@pytest.fixture
def core() -> MemoryGardenCore:
    return MemoryGardenCore()


@pytest.fixture
def manager() -> GardenSessionManager:
    return GardenSessionManager()


@pytest.fixture
def gh_stack() -> GardenHarvester:
    return GardenHarvester()


def test_adapter_satisfies_harvester_protocol(gh_stack: GardenHarvester) -> None:
    ad = RuntimeGardenHarvesterAdapter(gh_stack)
    assert isinstance(ad, HarvesterProtocol)
    tb = TurnContext(session_id="s", turn_index=0, user_message="ping")
    b = ad.harvest(tb)
    assert isinstance(b, GardenBrief)


def test_turn_context_to_harvest_query_mapping() -> None:
    tc = TurnContext(
        session_id="sess-99",
        turn_index=2,
        user_message="用户正文",
        metadata={"k": "v"},
    )
    hq = turn_context_to_harvest_query(tc)
    assert hq.session_id == tc.session_id
    assert hq.turn_index == tc.turn_index
    assert hq.raw_user_text == tc.user_message
    assert hq.metadata.get("namespace") == "sess-99"
    assert hq.metadata.get("k") == "v"


def test_open_before_reply_uses_adapter_brief_via_hooks(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    gh_stack: GardenHarvester,
) -> None:
    mgr = manager
    calls: list[int] = []
    memories = [_card(title="深色模式护眼", essence="其它", tags=["prefs"], card_id="mem-runtime-1")]

    def mp(_tc: TurnContext) -> list[MemoryCard]:
        calls.append(1)
        return list(memories)

    mgr.open_session()
    sid = mgr.current_session().session_id
    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=mp)
    hooks = RuntimeHooks(mgr, adapter, TemplateBriefWriter(), core)
    br = hooks.before_reply(sid, "开启深色模式方便夜间护眼", metadata={"tags": ["prefs"]})
    assert calls == [1]
    assert br.brief is not None
    assert br.brief.source_memory_ids == ["mem-runtime-1"]
    assert adapter.last_trace is not None


def test_closed_before_reply_skips_memory_provider_and_no_brief(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    gh_stack: GardenHarvester,
) -> None:
    calls: list[int] = []

    def mp(_tc: TurnContext) -> list[MemoryCard]:
        calls.append(1)
        return [_card()]

    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=mp)
    hooks = RuntimeHooks(manager, adapter, TemplateBriefWriter(), core)
    sid = manager.current_session().session_id
    r = hooks.before_reply(sid, "你好")
    assert calls == []
    assert r.brief is None


def test_closing_before_reply_skips_memory_provider(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    gh_stack: GardenHarvester,
) -> None:
    calls: list[int] = []

    def mp(_tc: TurnContext) -> list[MemoryCard]:
        calls.append(1)
        return [_card(title="noop", essence="noop", tags=["x"], card_id="c99")]

    manager.open_session()
    manager.enter_closing()
    assert manager.current_session().state == RuntimeState.CLOSING
    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=mp)
    hooks = RuntimeHooks(manager, adapter, TemplateBriefWriter(), core)
    sid = manager.current_session().session_id
    r = hooks.before_reply(sid, "收尾一句")
    assert calls == []
    assert r.brief is None


def test_empty_memories_safe_brief_via_adapter_direct(gh_stack: GardenHarvester) -> None:
    ad = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [])
    tb = TurnContext(session_id="s1", turn_index=0, user_message=" lone ")
    rb = ad.harvest(tb)
    assert rb.source_memory_ids == []


def test_relevant_memory_in_source_memory_ids(
    gh_stack: GardenHarvester,
) -> None:
    m = _card(title="关键词命中", essence="附录", card_id="hit-7")
    ad = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m])
    tb = TurnContext(session_id="s2", turn_index=0, user_message="关键词命中说明")
    rb = ad.harvest(tb)
    assert "hit-7" in rb.source_memory_ids


def test_adapter_can_use_cognitive_harvest_when_configured() -> None:
    harvester = GardenHarvester(
        emb_provider=FakeEmbeddingProvider(dimensions=64),
        rank_provider=FakeHarvestRerankerProvider(),
        cog_writer=FakeBriefWriterProvider(),
    )
    m = _card(
        title="cognitive runtime topic",
        essence="runtime hook should recall cognitive runtime topic",
        tags=["runtime"],
        card_id="cog-runtime-1",
    )
    ad = RuntimeGardenHarvesterAdapter(
        harvester,
        memory_provider=lambda _c: [m],
        cognitive_mode=CognitiveHarvestMode.HYBRID,
    )
    tb = TurnContext(session_id="s-cog", turn_index=0, user_message="cognitive runtime topic")

    rb = ad.harvest(tb)

    assert "cog-runtime-1" in rb.source_memory_ids
    assert ad.last_trace is None
    assert ad.last_cognitive_trace is not None
    assert ad.last_cognitive_trace.mode == CognitiveHarvestMode.HYBRID


def test_greenhouse_not_in_positive_source_memory_ids_hooks(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    gh_stack: GardenHarvester,
) -> None:
    gh_mid = "gh-open-allowed"
    mem = _card(
        title="温室话题唯一",
        essence="温室正文",
        lifecycle=MemoryLifecycle.greenhouse,
        card_id=gh_mid,
    )

    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [mem])
    hooks = RuntimeHooks(manager, adapter, TemplateBriefWriter(), core)
    manager.open_session()
    sid = manager.current_session().session_id
    r = hooks.before_reply(
        sid,
        "温室话题唯一上下文",
        metadata={"allow_greenhouse": True},
    )
    assert r.brief is not None
    assert gh_mid not in r.brief.source_memory_ids


def test_pruned_not_positive_source_but_listed_under_avoid(
    gh_stack: GardenHarvester,
) -> None:
    mid = "pr-11"
    m = _card(
        title="剪枝告警词",
        essence="修剪态摘要",
        lifecycle=MemoryLifecycle.pruned,
        tags=["risk"],
        card_id=mid,
    )
    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m])
    tb = TurnContext(
        session_id="s-risk",
        turn_index=0,
        user_message="剪枝告警词说明",
        metadata={"tags": ["risk"]},
    )
    rb = adapter.harvest(tb)
    assert mid not in rb.source_memory_ids
    assert mid in rb.avoid


@pytest.mark.parametrize("lifecycle", [MemoryLifecycle.composted, MemoryLifecycle.pruned])
def test_restricted_card_long_essence_not_in_runtime_garden_brief(
    lifecycle: MemoryLifecycle,
    gh_stack: GardenHarvester,
) -> None:
    secret = "COMPOST_BODY_SECRET_UNIQUE_88441"
    m = _card(
        title="标签耦合",
        essence=secret + "后缀说明",
        lifecycle=lifecycle,
        tags=["obs"],
        card_id=f"risk-{lifecycle.value}",
    )
    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m])
    tb = TurnContext(
        session_id="s-obs",
        turn_index=0,
        user_message="无关字面",
        metadata={"tags": ["obs"]},
    )
    rb = adapter.harvest(tb)
    dumped = json.dumps(rb.model_dump(mode="json"))
    assert secret not in dumped


def test_last_trace_and_trace_sink(gh_stack: GardenHarvester) -> None:
    sink_ids: list[str] = []

    def sink(tr) -> None:  # type: ignore[no-untyped-def]
        sink_ids.append(tr.trace_id)

    m = _card(title="追踪", essence="追踪摘要", tags=["tg"], card_id="tr-01")
    ad = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m], trace_sink=sink)
    tb = TurnContext(session_id="s-tr", turn_index=0, user_message="追踪", metadata={"tags": ["tg"]})
    ad.harvest(tb)
    assert ad.last_trace is not None and ad.last_trace.trace_id == sink_ids[0]


def test_runtime_garden_brief_dump_has_no_trace_object(
    gh_stack: GardenHarvester,
) -> None:
    m = _card(title="短", essence="短", tags=["tg2"], card_id="tr02")
    ad = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m])
    tb = TurnContext(session_id="s-plain", turn_index=1, user_message="短", metadata={"tags": ["tg2"]})
    rb = ad.harvest(tb)
    dumped = rb.model_dump(mode="json")
    assert set(dumped.keys()) == {
        "intent",
        "use",
        "avoid",
        "style",
        "safety",
        "nudge",
        "source_memory_ids",
    }
    blob = json.dumps(dumped)
    assert "HarvestTrace" not in blob


def test_memory_cards_not_mutated_through_adapter_harvest_path(
    gh_stack: GardenHarvester,
) -> None:
    m = _card(card_id="immut-a", tags=["immutable"])
    snap = m.model_dump()
    adapter = RuntimeGardenHarvesterAdapter(gh_stack, memory_provider=lambda _c: [m])
    adapter.harvest(
        TurnContext(
            session_id="imu",
            turn_index=0,
            user_message="任意正文",
            metadata={"tags": ["immutable"]},
        )
    )
    assert m.model_dump() == snap


def test_runtime_adapter_surface_has_no_ml_or_storage() -> None:
    import memory_garden.harvest.runtime_adapter as ra

    src = inspect.getsource(ra).lower()
    for bad in ("openai", "anthropic", "embedding", "rerank", "sqlite", "repository", "vector", "faiss"):
        assert bad not in src

