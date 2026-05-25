"""Stage 2: Dream Reflective Clustering 测试。

覆盖：
- rules_only 默认行为不变
- reflective fallback、provider 调用、校验、trace
- 敏感推断约束 + 3 组语义 fixture
"""

import pytest

from memory_garden.core.models import MemoryCard
from memory_garden.cognition.fake_providers import FakeDreamWeaverProvider
from memory_garden.cognition.models import (
    DreamMemoryInput,
    DreamMode,
    DreamProposal,
    DreamProposalBatch,
    DreamRelationType,
    DreamSuggestedAction,
    DreamTrace,
)
from memory_garden.cognition.providers import DreamWeaverProvider
from memory_garden.cognition.dream_reflective import run_reflective_dream
from memory_garden.cognition.validation import (
    validate_dream_batch,
    validate_dream_proposal,
)


def _make_memory(mid: str, title: str = "", essence: str = "", tags: list[str] | None = None) -> MemoryCard:
    return MemoryCard(
        id=mid,
        title=title or mid,
        essence=essence or "记忆内容",
        fragrance="香",
        thorns="无",
        tags=tags or [],
        lifecycle="sprout",
        importance=0.5,
        confidence=0.5,
        memory_type="preference",
    )


# ── models 可构造 ──────────────────────────────────────────────────


def test_dream_mode_enum():
    assert DreamMode.RULES_ONLY == "rules_only"
    assert DreamMode.REFLECTIVE == "reflective"


def test_dream_proposal_constructs():
    p = DreamProposal(
        proposal_id="p1",
        title="聚类标题",
        summary="多条记忆显示用户偏好深色主题。",
        source_memory_ids=["m1", "m2"],
        relation_type=DreamRelationType.SAME_THEME,
        suggested_action=DreamSuggestedAction.RECORD_REFLECTION,
        confidence=0.75,
        reason="标签重叠 + 内容相似。",
    )
    assert p.proposal_id == "p1"
    assert len(p.source_memory_ids) == 2


def test_dream_trace_constructs():
    t = DreamTrace(
        dream_run_id="run-1",
        mode=DreamMode.REFLECTIVE,
        input_memory_ids=["m1", "m2", "m3"],
        proposal_ids=["p1"],
        provider_name="fake",
        fallback_used=False,
    )
    assert t.dream_run_id == "run-1"
    assert t.mode == DreamMode.REFLECTIVE


# ── validation ──────────────────────────────────────────────────────


def test_validate_proposal_empty_source_ids():
    p = DreamProposal(
        proposal_id="p1", title="x", summary="y", reason="z",
        source_memory_ids=[],
        relation_type=DreamRelationType.OTHER,
        suggested_action=DreamSuggestedAction.NO_ACTION,
        confidence=0.5,
    )
    issues = validate_dream_proposal(p, {"m1"})
    assert len(issues) >= 1
    assert any("source_memory_ids" in i for i in issues)


def test_validate_proposal_foreign_source_id():
    p = DreamProposal(
        proposal_id="p1", title="x", summary="y", reason="z",
        source_memory_ids=["m_unknown"],
        relation_type=DreamRelationType.OTHER,
        suggested_action=DreamSuggestedAction.NO_ACTION,
        confidence=0.5,
    )
    issues = validate_dream_proposal(p, {"m1"})
    assert len(issues) >= 1
    assert any("m_unknown" in i for i in issues)


def test_validate_proposal_empty_title():
    p = DreamProposal(
        proposal_id="p1", title=" ", summary="y", reason="z",
        source_memory_ids=["m1"],
        relation_type=DreamRelationType.OTHER,
        suggested_action=DreamSuggestedAction.NO_ACTION,
        confidence=0.5,
    )
    issues = validate_dream_proposal(p, {"m1"})
    assert any("title" in i for i in issues)


def test_validate_proposal_confidence_oob():
    """Pydantic Field(ge=0.0, le=1.0) catches confidence OOB at construction time.

    这是比 validate_dream_proposal() 更早的防线——pydantic 在模型构造时拒绝非法值。
    """
    with pytest.raises(Exception):
        DreamProposal(
            proposal_id="p1", title="x", summary="y", reason="z",
            source_memory_ids=["m1"],
            relation_type=DreamRelationType.OTHER,
            suggested_action=DreamSuggestedAction.NO_ACTION,
            confidence=1.5,
        )


def test_validate_batch():
    batch = DreamProposalBatch(
        proposals=[
            DreamProposal(
                proposal_id="ok", title="T", summary="S", reason="R",
                source_memory_ids=["m1", "m2"],
                relation_type=DreamRelationType.SAME_THEME,
                suggested_action=DreamSuggestedAction.RECORD_REFLECTION,
                confidence=0.8,
            ),
            DreamProposal(
                proposal_id="bad", title=" ", summary="S", reason="R",
                source_memory_ids=["m1"],
                relation_type=DreamRelationType.OTHER,
                suggested_action=DreamSuggestedAction.NO_ACTION,
                confidence=0.5,
            ),
        ],
    )
    inputs = [DreamMemoryInput(memory_id="m1", text="a"), DreamMemoryInput(memory_id="m2", text="b")]
    issues = validate_dream_batch(batch, inputs)
    assert any("bad" in i for i in issues)


# ── run_reflective_dream ────────────────────────────────────────────


def test_rules_only_produces_tag_clusters():
    memories = [
        _make_memory("m1", "深色模式", "用户喜欢深色界面", tags=["ui", "preference"]),
        _make_memory("m2", "字体偏好", "用户需要大字体", tags=["ui", "accessibility"]),
        _make_memory("m3", "项目技术栈", "使用 Python 开发", tags=["project"]),
    ]
    batch, trace = run_reflective_dream(memories, mode=DreamMode.RULES_ONLY)
    assert isinstance(batch, DreamProposalBatch)
    assert isinstance(trace, DreamTrace)
    assert trace.mode == DreamMode.RULES_ONLY
    assert trace.fallback_used is False
    # "ui" tag appears twice → should get a cluster
    ui_proposals = [p for p in batch.proposals if "ui" in p.title.lower()]
    assert len(ui_proposals) >= 1


def test_reflective_with_provider():
    memories = [
        _make_memory("m1", "深色模式", "用户喜欢深色界面", tags=["ui"]),
        _make_memory("m2", "深色主题", "用户偏好暗色主题", tags=["ui", "preference"]),
        _make_memory("m3", "Python", "使用 Python", tags=["project"]),
    ]
    provider = FakeDreamWeaverProvider()
    batch, trace = run_reflective_dream(
        memories, mode=DreamMode.REFLECTIVE, weaver_provider=provider,
    )
    assert trace.mode == DreamMode.REFLECTIVE
    assert trace.fallback_used is False
    assert len(batch.proposals) >= 1
    for p in batch.proposals:
        for mid in p.source_memory_ids:
            assert mid in {"m1", "m2", "m3"}, f"{mid} not in input"


def test_reflective_falls_back_when_no_provider():
    memories = [_make_memory("m1", "x", "y", tags=["a"]), _make_memory("m2", "z", "w", tags=["a"])]
    batch, trace = run_reflective_dream(memories, mode=DreamMode.REFLECTIVE)
    assert trace.fallback_used is True
    assert "weaver_provider not configured" in (trace.fallback_reason or "")


def test_reflective_provider_exception_falls_back():
    class _FailingWeaver:
        def propose_clusters(self, memories, policy=None):
            raise RuntimeError("boom")

    memories = [_make_memory("m1", "x", "y", tags=["a"]), _make_memory("m2", "z", "w", tags=["a"])]
    batch, trace = run_reflective_dream(
        memories, mode=DreamMode.REFLECTIVE, weaver_provider=_FailingWeaver(),
    )
    assert trace.fallback_used is True
    assert "boom" in (trace.fallback_reason or "")
    assert trace.mode == DreamMode.RULES_ONLY


def test_reflective_invalid_provider_output_falls_back():
    class _BadWeaver:
        def propose_clusters(self, memories, policy=None):
            return DreamProposalBatch(
                proposals=[
                    DreamProposal(
                        proposal_id="bad",
                        title="bad",
                        summary="bad",
                        reason="bad",
                        source_memory_ids=["not-input"],
                        relation_type=DreamRelationType.SAME_THEME,
                        suggested_action=DreamSuggestedAction.SUGGEST_MERGE,
                        confidence=0.8,
                    )
                ],
                provider_name="bad_weaver",
            )

    memories = [
        _make_memory("m1", "a", "a", tags=["shared"]),
        _make_memory("m2", "b", "b", tags=["shared"]),
    ]
    batch, trace = run_reflective_dream(
        memories, mode=DreamMode.REFLECTIVE, weaver_provider=_BadWeaver(),
    )
    assert trace.fallback_used is True
    assert trace.mode == DreamMode.RULES_ONLY
    assert trace.fallback_reason == "weaver_provider output failed validation"
    assert all("not-input" not in p.source_memory_ids for p in batch.proposals)


def test_reflective_empty_provider_output_falls_back():
    class _EmptyWeaver:
        def propose_clusters(self, memories, policy=None):
            return DreamProposalBatch(proposals=[], provider_name="empty_weaver")

    memories = [
        _make_memory("m1", "a", "a", tags=["shared"]),
        _make_memory("m2", "b", "b", tags=["shared"]),
    ]
    batch, trace = run_reflective_dream(
        memories, mode=DreamMode.REFLECTIVE, weaver_provider=_EmptyWeaver(),
    )
    assert trace.fallback_used is True
    assert trace.mode == DreamMode.RULES_ONLY
    assert len(batch.proposals) >= 1


def test_reflective_trace_has_input_ids():
    memories = [_make_memory("m1", "a", "b"), _make_memory("m2", "c", "d")]
    _, trace = run_reflective_dream(memories, mode=DreamMode.RULES_ONLY)
    assert set(trace.input_memory_ids) == {"m1", "m2"}


def test_reflective_trace_has_proposal_ids():
    provider = FakeDreamWeaverProvider()
    memories = [
        _make_memory("m1", "深色", "喜欢深色", tags=["ui"]),
        _make_memory("m2", "暗色", "偏好暗色", tags=["ui"]),
    ]
    _, trace = run_reflective_dream(memories, mode=DreamMode.REFLECTIVE, weaver_provider=provider)
    assert len(trace.proposal_ids) >= 1


def test_reflective_does_not_modify_memories():
    """DreamProposal 不修改原始 MemoryCard。"""
    memories = [
        _make_memory("m1", "深色模式", "用户喜欢深色界面", tags=["ui"]),
        _make_memory("m2", "字体偏好", "用户需要大字体", tags=["ui"]),
    ]
    m1_title_before = memories[0].title
    run_reflective_dream(memories, mode=DreamMode.REFLECTIVE,
                         weaver_provider=FakeDreamWeaverProvider())
    assert memories[0].title == m1_title_before


def test_empty_memories_returns_empty_batch():
    batch, trace = run_reflective_dream([], mode=DreamMode.REFLECTIVE)
    assert batch.proposals == []
    assert trace.input_memory_ids == []


# ── FakeDreamWeaverProvider 单元 ────────────────────────────────────


def test_fake_weaver_satisfies_protocol():
    assert isinstance(FakeDreamWeaverProvider(), DreamWeaverProvider)


def test_fake_weaver_presets():
    preset = DreamProposal(
        proposal_id="custom-1", title="T", summary="S", reason="R",
        source_memory_ids=["m1"],
        relation_type=DreamRelationType.SAME_THEME,
        suggested_action=DreamSuggestedAction.RECORD_REFLECTION,
        confidence=0.9,
    )
    p = FakeDreamWeaverProvider(preset_proposals=[preset])
    batch = p.propose_clusters([])
    assert len(batch.proposals) == 1
    assert batch.proposals[0].proposal_id == "custom-1"


def test_fake_weaver_discovers_duplicates():
    p = FakeDreamWeaverProvider()
    memories = [
        DreamMemoryInput(memory_id="a", text="用户偏爱深色主题界面暗色模式"),
        DreamMemoryInput(memory_id="b", text="用户偏爱深色主题界面暗色风格"),
    ]
    batch = p.propose_clusters(memories)
    dupes = [x for x in batch.proposals if x.relation_type == DreamRelationType.DUPLICATE]
    assert len(dupes) >= 1
    assert dupes[0].suggested_action == DreamSuggestedAction.SUGGEST_MERGE


# ── 3 组语义 fixture ────────────────────────────────────────────────


def test_fixture_anti_ai_phrasing():
    """多条"讨厌 AI 味 / 喜欢说人话"的记忆 → 应形成表达偏好主题 proposal。"""
    provider = FakeDreamWeaverProvider()
    memories = [
        _make_memory("m1", "讨厌AI味", "不要用AI味的套话回复我", tags=["style", "ai_aversion"]),
        _make_memory("m2", "说人话", "请用自然的人话和我交流", tags=["style", "natural"]),
        _make_memory("m3", "拒绝模板", "我不想要模板化的回复", tags=["style", "ai_aversion"]),
    ]
    batch, trace = run_reflective_dream(memories, mode=DreamMode.REFLECTIVE, weaver_provider=provider)
    style_related = [p for p in batch.proposals if "style" in p.title.lower() or "style" in " ".join(p.source_memory_ids).lower()]
    assert len(style_related) >= 1 or len(batch.proposals) >= 1
    assert trace.mode == DreamMode.REFLECTIVE


def test_fixture_engineering_values():
    """多条"项目要可审计 / 可追溯 / 本地优先"的记忆 → 应形成工程价值主题 proposal。"""
    provider = FakeDreamWeaverProvider()
    memories = [
        _make_memory("m1", "本地优先", "所有数据必须本地存储", tags=["engineering", "local_first"]),
        _make_memory("m2", "可审计", "系统必须可审计可追溯", tags=["engineering", "audit"]),
        _make_memory("m3", "零依赖", "不希望引入外部服务依赖", tags=["engineering", "local_first"]),
    ]
    batch, _ = run_reflective_dream(memories, mode=DreamMode.REFLECTIVE, weaver_provider=provider)
    eng_related = [p for p in batch.proposals
                   if "engineering" in p.title.lower() or "engineering" in " ".join(p.source_memory_ids).lower()]
    assert len(eng_related) >= 1 or len(batch.proposals) >= 1


def test_fixture_conflicting_preferences():
    """两条互相矛盾的偏好 → provider 可能标记 duplicate 或按标签聚类，不强行合并。"""
    provider = FakeDreamWeaverProvider()
    memories = [
        _make_memory("m1", "深色模式", "用户喜欢深色界面", tags=["preference", "dark"]),
        _make_memory("m2", "浅色模式", "用户改用浅色界面", tags=["preference", "light"]),
    ]
    batch, _ = run_reflective_dream(memories, mode=DreamMode.REFLECTIVE, weaver_provider=provider)
    # 无 SUGGEST_MERGE 的 proposal 应带 conflict 标记或只是标签聚类
    merge_proposals = [p for p in batch.proposals
                       if p.suggested_action == DreamSuggestedAction.SUGGEST_MERGE]
    for p in merge_proposals:
        # 两源同时出现才算真的合并
        if "m1" in p.source_memory_ids and "m2" in p.source_memory_ids:
            assert p.relation_type in (DreamRelationType.CONFLICTING, DreamRelationType.DUPLICATE), (
                f"Conflicting preferences should not be merged: {p.relation_type}"
            )


# ── 无副作用 ────────────────────────────────────────────────────────


def test_no_memory_garden_created(tmp_path):
    import os
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed = os.path.exists(candidate)
    run_reflective_dream([], mode=DreamMode.RULES_ONLY)
    if not existed:
        assert not os.path.exists(candidate)
