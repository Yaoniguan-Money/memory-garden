"""中文 FTS 检索质量样本测试。"""

from __future__ import annotations

from memory_garden.core.models import MemoryCard
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.index import reindex_garden
from memory_garden.soil.search import search_garden


def _seed_cjk_library(repo, cases: list[tuple[str, str, str]]) -> None:
    for memory_id, title, essence in cases:
        repo.save_memory_card(
            MemoryCard(
                id=memory_id,
                title=title,
                essence=essence,
                fragrance="neutral",
                thorns="none",
            )
        )


def test_cjk_search_recall_at_20_on_curated_queries(tmp_path):
    """20 条中文查询在 curated 库上的 Recall@20。"""
    garden = MemoryGarden.local(tmp_path / "cjk-search")
    try:
        cases = [
            ("cjk-gold-01", "用户偏好深色界面", "用户唯一标识 ALPHA 偏好深色界面主题"),
            ("cjk-gold-02", "团队喜欢快速发布", "团队喜欢快速发布节奏与短迭代"),
            ("cjk-gold-03", "预算总是充足", "财务记录显示预算总是充足无需担心"),
            ("cjk-gold-04", "推荐本地部署", "架构组推荐本地部署方案"),
            ("cjk-gold-05", "同步接口设计", "服务采用同步接口设计满足需求"),
            ("cjk-gold-06", "前端主导迭代", "产品由前端主导迭代与交付"),
            ("cjk-gold-07", "会议氛围严肃", "周会氛围严肃正式"),
            ("cjk-gold-08", "文档简洁摘要", "对外文档保持简洁摘要风格"),
            ("cjk-gold-09", "手动审批流程", "变更需要手动审批流程"),
            ("cjk-gold-10", "同意立即执行", "项目组同意该方案立即执行"),
            ("cjk-noise-01", "噪声主题一", "Atlas Zephyr 通用噪声不含独特标识"),
            ("cjk-noise-02", "噪声主题二", "Beta Orion 通用噪声不含独特标识"),
            ("cjk-noise-03", "噪声主题三", "Gamma Nova 通用噪声不含独特标识"),
            ("cjk-noise-04", "噪声主题四", "Delta Luna 通用噪声不含独特标识"),
            ("cjk-noise-05", "噪声主题五", "Epsilon Sol 通用噪声不含独特标识"),
        ]
        _seed_cjk_library(garden.core.repository, cases)
        reindex_garden(garden.home.root, dry_run=False)

        queries = [
            ("深色 界面", "cjk-gold-01"),
            ("快速 发布", "cjk-gold-02"),
            ("预算 充足", "cjk-gold-03"),
            ("本地 部署", "cjk-gold-04"),
            ("同步 接口", "cjk-gold-05"),
            ("前端 迭代", "cjk-gold-06"),
            ("严肃 会议", "cjk-gold-07"),
            ("简洁 摘要", "cjk-gold-08"),
            ("手动 审批", "cjk-gold-09"),
            ("立即 执行", "cjk-gold-10"),
            ("用户 ALPHA 深色", "cjk-gold-01"),
            ("团队 快速", "cjk-gold-02"),
            ("财务 预算", "cjk-gold-03"),
            ("架构 本地", "cjk-gold-04"),
            ("服务 同步", "cjk-gold-05"),
            ("产品 前端", "cjk-gold-06"),
            ("周会 严肃", "cjk-gold-07"),
            ("对外 文档", "cjk-gold-08"),
            ("变更 手动", "cjk-gold-09"),
            ("项目 同意", "cjk-gold-10"),
        ]

        hits = 0
        for query, expected_id in queries:
            ranked = [h.target_id for h in search_garden(garden.home.root, query, limit=20, target_types=["memory_card"])]
            if expected_id in ranked:
                hits += 1

        recall_at_20 = hits / len(queries)
        assert recall_at_20 >= 0.8, f"recall@20={recall_at_20:.2f}"

        hits_at_5 = 0
        for query, expected_id in queries[:10]:
            ranked = [h.target_id for h in search_garden(garden.home.root, query, limit=5, target_types=["memory_card"])]
            if expected_id in ranked:
                hits_at_5 += 1
        recall_at_5 = hits_at_5 / 10
        assert recall_at_5 >= 0.3, f"recall@5={recall_at_5:.2f}"

        english_ranked = [
            h.target_id
            for h in search_garden(
                garden.home.root,
                "Atlas Zephyr release",
                limit=5,
                target_types=["memory_card"],
            )
        ]
        assert isinstance(english_ranked, list)
    finally:
        garden.close()
