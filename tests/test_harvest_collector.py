"""第三层 Stage 3B：LocalCandidateCollector。"""

import inspect
import json

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.harvest.models import (
    CandidateMatchType,
    HarvestQuery,
    MemoryLens,
)
from memory_garden.harvest.collector import LocalCandidateCollector
from memory_garden.runtime_config import HarvestCollectorConfig


def _card(
    *,
    title="t",
    essence="e",
    fragrance="香",
    thorns="刺",
    tags=None,
    roots=None,
    branches=None,
    lifecycle=MemoryLifecycle.sprout,
    card_id="fixed-id-1",
):
    return MemoryCard(
        id=card_id,
        title=title,
        essence=essence,
        fragrance=fragrance,
        thorns=thorns,
        tags=tags or [],
        roots=roots or [],
        branches=branches or [],
        lifecycle=lifecycle,
    )


def test_query_hits_title_generates_candidate() -> None:
    memories = [_card(title="深色模式界面", essence="其它摘要", card_id="m1")]
    q = HarvestQuery(raw_user_text="我需要深色模式界面以便夜间使用")
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert out[0].memory_id == "m1"
    assert out[0].match_type == CandidateMatchType.LEXICAL_STUB


def test_query_hits_essence_generates_candidate() -> None:
    memories = [_card(title="标题", essence="少用感叹号交流", card_id="m2")]
    q = HarvestQuery(raw_user_text="希望以后少用感叹号")
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert out[0].memory_id == "m2"


def test_query_tags_intersect_memory_tags() -> None:
    memories = [_card(title="t", essence="e", tags=["work", "urgent"], card_id="m3")]
    q = HarvestQuery(raw_user_text="无关正文", metadata={"tags": ["work"]})
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert "tags_intersection" in out[0].metadata.get("match_reasons", [])


def test_irrelevant_memory_excluded() -> None:
    memories = [_card(title="猫零食", essence="爱吃鱼", card_id="m4")]
    q = HarvestQuery(raw_user_text="今天股票大盘走势")
    assert LocalCandidateCollector().collect(q, memories) == []


def test_greenhouse_skipped_by_default() -> None:
    memories = [_card(title="温室记忆", essence="温室记忆摘要", lifecycle=MemoryLifecycle.greenhouse, card_id="g1")]
    q = HarvestQuery(raw_user_text="温室记忆")
    assert LocalCandidateCollector().collect(q, memories) == []


def test_greenhouse_allowed_via_query_metadata() -> None:
    memories = [_card(title="温室记忆", essence="温室记忆摘要", lifecycle=MemoryLifecycle.greenhouse, card_id="g2")]
    q = HarvestQuery(
        raw_user_text="温室记忆",
        metadata={"allow_greenhouse": True},
    )
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1


def test_sprout_and_bloom_can_match() -> None:
    m_s = _card(title="发芽", essence="e", lifecycle=MemoryLifecycle.sprout, card_id="s1")
    m_b = _card(title="开花", essence="e", lifecycle=MemoryLifecycle.bloom, card_id="b1")
    q = HarvestQuery(raw_user_text="发芽与开花阶段")
    out = LocalCandidateCollector().collect(q, [m_s, m_b])
    assert len(out) == 2
    ids = {c.memory_id for c in out}
    assert ids == {"s1", "b1"}


def test_candidate_preserves_memory_id_and_lens_metadata() -> None:
    # 透镜名「夜间」在查询正文中出现，归为 lexical 路径真实命中透镜
    lens = MemoryLens(name="夜间")
    q = HarvestQuery(
        raw_user_text="夜间深色阅读偏好",
        lenses=[lens],
    )
    memories = [_card(title="夜间深色阅读", essence="e", card_id="mid-9")]
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert out[0].memory_id == "mid-9"
    assert lens.lens_id in out[0].metadata.get("matched_lenses", [])
    assert out[0].metadata.get("query_lenses") == [lens.lens_id]
    assert out[0].lens_id == lens.lens_id
    assert "lexical_text" in out[0].metadata.get("hit_channels", [])


def test_collect_does_not_invoke_llm_embedding_vector_rerank() -> None:
    import memory_garden.harvest.collector as col

    src = inspect.getsource(col)
    lowered = src.lower()
    for needle in ("openai", "anthropic", "embed", "numpy", "torch", "faiss", "chroma", "llm", "rerank"):
        assert needle not in lowered


def test_collect_does_not_mutate_memory_cards() -> None:
    m = _card(title="稳定标题", essence="稳定摘要", card_id="immut-1")
    before = m.model_dump()
    q = HarvestQuery(raw_user_text="稳定")
    LocalCandidateCollector().collect(q, [m])
    assert m.model_dump() == before


def test_collect_results_json_roundtrip() -> None:
    memories = [_card(title="关键词Alpha", essence="e", card_id="j1")]
    q = HarvestQuery(raw_user_text="请用关键词Alpha说明")
    out = LocalCandidateCollector().collect(q, memories)
    dumped = [c.model_dump(mode="json") for c in out]
    json.dumps(dumped)
    restored = [MemoryCard.model_validate(o["metadata"]["source_memory"]) for o in dumped]
    assert restored[0].id == "j1"


def test_roots_and_branches_keyword_match() -> None:
    memories = [
        _card(
            title="t",
            essence="e",
            roots=["根须A"],
            branches=["枝条B"],
            card_id="rb1",
        )
    ]
    q1 = HarvestQuery(raw_user_text="根须A很长")
    q2 = HarvestQuery(raw_user_text="枝条B脆弱")
    assert len(LocalCandidateCollector().collect(q1, memories)) == 1
    assert len(LocalCandidateCollector().collect(q2, memories)) == 1


def test_fragrance_thorns_fields_match() -> None:
    memories = [_card(title="t", essence="e", fragrance="薄荷香", thorns="谨防过敏", card_id="ft1")]
    q = HarvestQuery(raw_user_text="薄荷香与过敏须知")
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1


def test_tag_hit_matched_lenses_subset_not_all_query_lenses() -> None:
    """仅 tag 命中时：只有与共享标签对齐的透镜进入 matched_lenses。"""
    l_work = MemoryLens(name="A", facet_keys=["work"])
    l_noise = MemoryLens(name="B", facet_keys=["noise_only"])
    memories = [_card(title="x", essence="y", tags=["work"], card_id="tag-lens")]
    q = HarvestQuery(
        raw_user_text="正文与标签无关",
        lenses=[l_work, l_noise],
        metadata={"tags": ["work"]},
    )
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert set(out[0].metadata["query_lenses"]) == {l_work.lens_id, l_noise.lens_id}
    assert out[0].metadata["matched_lenses"] == [l_work.lens_id]
    assert "tag_metadata" in out[0].metadata.get("hit_channels", [])


def test_tag_only_empty_matched_lenses_when_no_lens_aligns_but_json_serializable() -> None:
    l1 = MemoryLens(name="UnrelatedLensOne")
    l2 = MemoryLens(name="UnrelatedLensTwo")
    memories = [_card(title="z", essence="z", tags=["work"], card_id="z1")]
    q = HarvestQuery(
        raw_user_text="zzz",
        lenses=[l1, l2],
        metadata={"tags": ["work"]},
    )
    out = LocalCandidateCollector().collect(q, memories)
    assert len(out) == 1
    assert out[0].metadata["matched_lenses"] == []
    assert len(out[0].metadata["query_lenses"]) == 2
    json.dumps(out[0].model_dump(mode="json"))


def test_collector_uses_injected_snippet_and_term_limits() -> None:
    memories = [
        _card(
            title="alpha beta gamma delta epsilon",
            essence="alpha beta gamma delta epsilon",
            card_id="cfg-1",
        )
    ]
    q = HarvestQuery(raw_user_text="alpha beta gamma delta epsilon")
    collector = LocalCandidateCollector(
        HarvestCollectorConfig(max_snippet_chars=24, max_matched_terms=2)
    )

    out = collector.collect(q, memories)

    assert len(out) == 1
    assert len(out[0].excerpt) <= 24
    assert len(out[0].metadata["matched_terms"]) == 2

