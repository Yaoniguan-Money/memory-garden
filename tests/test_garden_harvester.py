"""第三层 Stage 3G：GardenHarvester 内存流水线。"""

import inspect
import json

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.harvest.bouquet import GardenBouquetBuilder
from memory_garden.harvest.brief import HarvestGardenBriefWriter
from memory_garden.harvest.collector import LocalCandidateCollector
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.models import HarvestGardenBrief, HarvestQuery, HarvestTrace, MemoryLens
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.ranking import RuleBasedHarvestRanker
from memory_garden.harvest.scoring import RuleBasedHarvestScorer
from memory_garden.runtime.session import GardenBrief as RuntimeGardenBrief


def _card(
    *,
    title="t",
    essence="e",
    fragrance="香",
    thorns="刺",
    tags=None,
    lifecycle=MemoryLifecycle.sprout,
    card_id="m1",
):
    return MemoryCard(
        id=card_id,
        title=title,
        essence=essence,
        fragrance=fragrance,
        thorns=thorns,
        tags=tags or [],
        lifecycle=lifecycle,
    )


def test_harvest_runs_full_pipeline_and_returns_trace() -> None:
    memories = [_card(title="深色模式", essence="其它", card_id="mem-a")]
    q = HarvestQuery(raw_user_text="我要开启深色模式方便夜间使用")
    tr = GardenHarvester().harvest(q, memories)
    assert isinstance(tr, HarvestTrace)
    assert tr.query is q
    assert len(tr.candidates) >= 1
    assert len(tr.scores) == len(tr.candidates)
    assert tr.bouquet is not None
    assert isinstance(tr.brief, HarvestGardenBrief)
    assert tr.brief.source_memory_ids
    rt = tr.brief.to_runtime_brief()
    assert isinstance(rt, RuntimeGardenBrief)


def test_empty_memories_no_error() -> None:
    q = HarvestQuery(raw_user_text="anything")
    tr = GardenHarvester().harvest(q, [])
    assert tr.candidates == []
    assert tr.scores == []
    assert tr.bouquet is not None
    assert tr.brief is not None
    assert tr.brief.source_memory_ids == []
    assert tr.model_calls == []


def test_no_matching_candidates_no_error() -> None:
    memories = [_card(title="猫零食", essence="鱼干", card_id="x")]
    q = HarvestQuery(raw_user_text="量子纠缠实验步骤")
    tr = GardenHarvester().harvest(q, memories)
    assert tr.candidates == []
    assert tr.policy_decisions[0].allow_candidate_ids == []


def test_model_calls_always_empty_stub() -> None:
    memories = [_card(title="阿尔法", essence="贝塔", tags=["grp"], card_id="g1")]
    q = HarvestQuery(raw_user_text="无关", metadata={"tags": ["grp"]})
    tr = GardenHarvester().harvest(q, memories)
    assert tr.model_calls == []


def test_max_candidates_caps_rank_allow_list() -> None:
    memories = [
        _card(title=f"n{i}", essence=f"共享标签批处理{i}", tags=["capbatch"], card_id=f"id-{i}") for i in range(8)
    ]
    q = HarvestQuery(raw_user_text="zzz", metadata={"tags": ["capbatch"]})
    pol = HarvestBudgetPolicy(max_candidates=3)
    tr = GardenHarvester().harvest(q, memories, pol)
    assert len(tr.candidates) == 8
    pd0 = tr.policy_decisions[0]
    assert len(pd0.allow_candidate_ids) == 3
    reasons = "\n".join(pd0.reasons)
    assert "ranking_cap_applied" in reasons


def test_greenhouse_memory_not_in_positive_source_ids_when_allowed_in_pipeline() -> None:
    """允许采集温室卡时，花束与简报仍不得将其当作积极 source_memory_ids。"""
    gh_id = "gh-mid-1"
    memories = [_card(title="温室专用词", essence="温室专用词详情", lifecycle=MemoryLifecycle.greenhouse, card_id=gh_id)]
    q = HarvestQuery(raw_user_text="温室专用词", metadata={"allow_greenhouse": True})
    tr = GardenHarvester().harvest(q, memories)
    assert len(tr.candidates) == 1
    assert gh_id not in tr.brief.source_memory_ids


def test_input_memory_cards_not_mutated() -> None:
    m = _card(title="稳定标题", essence="稳定摘要含关键词不变", card_id="stable-1")
    before = m.model_dump()
    mid = id(m)
    q = HarvestQuery(raw_user_text="关键词不变")
    GardenHarvester().harvest(q, [m])
    assert id(m) == mid
    assert m.model_dump() == before


def test_trace_json_dumpable_without_harvester_constructing_story_blob() -> None:
    memories = [_card(title="短", essence="短", card_id="j1")]
    q = HarvestQuery(raw_user_text="短")
    tr = GardenHarvester().harvest(q, memories)
    raw = json.dumps(tr.model_dump(mode="json"))
    assert "自动生成一万字" not in raw
    assert len(raw) < 500_000


def test_source_memory_ids_come_from_brief_only_logical_path() -> None:
    """简报中的 source_memory_ids 与 trace.brief 一致；harvester 不另写冗余 id 字段。"""
    memories = [_card(title="链路", essence="链路同步", card_id="chain-9")]
    q = HarvestQuery(raw_user_text="链路同步测试")
    tr = GardenHarvester().harvest(q, memories)
    assert tr.brief is not None
    dumped = tr.model_dump(mode="json")
    assert dumped["brief"]["source_memory_ids"] == list(tr.brief.source_memory_ids)


def test_harvester_module_skips_ml_and_repository_surface() -> None:
    import memory_garden.harvest.harvester as hv

    src = inspect.getsource(hv).lower()
    for bad in ("openai", "anthropic", "embedding", "llm.invoke", "vector", "faiss", "rerank"):
        assert bad not in src
    assert "sqlite" not in src
    assert "repository" not in src


def test_harvester_does_not_import_runtime_module_directly() -> None:
    import memory_garden.harvest.harvester as hv

    src = inspect.getsource(hv)
    assert "memory_garden.runtime" not in src


def test_policy_default_lenses_in_effective_query_and_trace() -> None:
    """policy.default_lenses 进入 effective_query.lenses，并出现在 trace 中。"""
    q_lens = MemoryLens(name="查询透镜", facet_keys=["qfacet"])
    pol_lens = MemoryLens(name="策略默认透镜", facet_keys=["pfacet"])
    q = HarvestQuery(raw_user_text="无关节", metadata={"tags": ["eff"]}, lenses=[q_lens])
    pol = HarvestBudgetPolicy(default_lenses=[pol_lens])
    memories = [_card(title="x", essence="y", tags=["eff"], card_id="eff-1")]
    tr = GardenHarvester().harvest(q, memories, pol)

    ids_tr = [lz.lens_id for lz in tr.query.lenses]
    assert q_lens.lens_id in ids_tr
    assert pol_lens.lens_id in ids_tr
    assert tr.lenses == list(tr.query.lenses)
    mid = tr.metadata.get("original_query_id")
    assert mid == q.query_id
    assert tr.metadata.get("original_lens_ids") == [q_lens.lens_id]
    assert tr.query.query_id == q.query_id
    assert tr.query is not q  # ``model_copy`` 快照；不篡改入参引用


def test_collector_and_trace_lenses_match_effective_pipeline() -> None:
    observed: list[list[str]] = []

    pol_lens = MemoryLens(name="管线透镜", facet_keys=[])
    q = HarvestQuery(raw_user_text="标签命中", metadata={"tags": ["pipe"]}, lenses=[])
    pol = HarvestBudgetPolicy(default_lenses=[pol_lens])
    memories = [_card(title="p", essence="p", tags=["pipe"], card_id="pipe-m")]

    col = LocalCandidateCollector()
    _collect_impl = LocalCandidateCollector.collect.__get__(col, LocalCandidateCollector)

    def spy_collect(hq, m):
        observed.append([lz.lens_id for lz in hq.lenses])
        return _collect_impl(hq, m)

    col.collect = spy_collect  # type: ignore[method-assign]

    tr = GardenHarvester(collector=col).harvest(q, memories, pol)
    assert observed == [[pol_lens.lens_id]]
    assert [lz.lens_id for lz in tr.lenses] == [pol_lens.lens_id]


def test_original_harvest_query_not_mutated_when_policy_adds_lenses() -> None:
    q_lens = MemoryLens(name="原位", facet_keys=[])
    pol_lens = MemoryLens(name="附加", facet_keys=[])
    q = HarvestQuery(raw_user_text="t", lenses=[q_lens])
    snap = q.model_dump()
    pol = HarvestBudgetPolicy(default_lenses=[pol_lens])
    GardenHarvester().harvest(q, [], pol)
    assert q.model_dump() == snap
    assert len(q.lenses) == 1


def test_policy_none_preserves_original_query_lens_and_identity() -> None:
    lz = MemoryLens(name="仅存于查询", facet_keys=["k"])
    q = HarvestQuery(raw_user_text="k", lenses=[lz])
    tr = GardenHarvester().harvest(q, [])
    assert tr.query is q
    assert [x.lens_id for x in tr.lenses] == [lz.lens_id]


def test_dependency_injection_invocation_order() -> None:
    order: list[str] = []

    col = LocalCandidateCollector()
    _collect_impl = LocalCandidateCollector.collect.__get__(col, LocalCandidateCollector)

    def w_col(q, m):
        order.append("collect")
        return _collect_impl(q, m)

    col.collect = w_col  # type: ignore[method-assign]

    sc = RuleBasedHarvestScorer()
    _score_impl = RuleBasedHarvestScorer.score.__get__(sc, RuleBasedHarvestScorer)

    def w_sc(q, cands):
        order.append("score")
        return _score_impl(q, cands)

    sc.score = w_sc  # type: ignore[method-assign]

    rk = RuleBasedHarvestRanker()
    _rank_impl = RuleBasedHarvestRanker.rank.__get__(rk, RuleBasedHarvestRanker)

    def w_rk(q, cands, scs, pol=None):
        order.append("rank")
        return _rank_impl(q, cands, scs, pol)

    rk.rank = w_rk  # type: ignore[method-assign]

    bb = GardenBouquetBuilder()
    _build_impl = GardenBouquetBuilder.build.__get__(bb, GardenBouquetBuilder)

    def w_bb(q, outcome, scs, pol=None):
        order.append("build")
        return _build_impl(q, outcome, scs, pol)

    bb.build = w_bb  # type: ignore[method-assign]

    bw = HarvestGardenBriefWriter()
    _write_impl = HarvestGardenBriefWriter.write.__get__(bw, HarvestGardenBriefWriter)

    def w_bw(q, bq, cands, scs, pol=None):
        order.append("write")
        return _write_impl(q, bq, cands, scs, pol)

    bw.write = w_bw  # type: ignore[method-assign]

    gh = GardenHarvester(
        collector=col,
        scorer=sc,
        ranker=rk,
        bouquet_builder=bb,
        brief_writer=bw,
    )
    memories = [_card(title="\u5e8f", essence="\u6b65\u9aa4", tags=["inj"], card_id="inj-1")]
    q = HarvestQuery(raw_user_text="x", metadata={"tags": ["inj"]})
    gh.harvest(q, memories)
    assert order == ["collect", "score", "rank", "build", "write"]
