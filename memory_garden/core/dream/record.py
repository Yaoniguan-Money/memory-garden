"""DreamRecord 规则版文本拼装：可解释、含实体 id，非全文摘要。"""

from __future__ import annotations

from memory_garden.core.models import Seed


def build_observation(
    seed_ids: list[str],
    memory_ids: list[str],
) -> str:
    return (
        f"夜巡：审阅 {len(seed_ids)} 颗待整理种子与 {len(memory_ids)} 张非温室记忆卡；"
        f"种子 id 序列为 {seed_ids}，记忆卡 id 序列为 {memory_ids}。"
    )


def build_reflection(
    composted: list[str],
    cluster_count: int,
    merge_count: int,
) -> str:
    return (
        f"规则理解：将短期负面自评与情绪碎片优先交给堆肥，避免身份化；"
        f"对同信号、同标签或文本相近的长期种子做夜间收敛；"
        f"将落单种子在朴素相似度下并入已有记忆枝。本次识别堆肥 {len(composted)} 条、"
        f"可聚类组 {cluster_count} 组、种子并卡 {merge_count} 次。"
    )


def build_transformation(
    record_id: str,
    created_memory_ids: list[str],
    merged_memory_ids: list[str],
    composted_seed_ids: list[str],
    pruned_memory_ids: list[str],
) -> str:
    return (
        f"梦境操作（记录 {record_id}）："
        f"新建记忆卡 {created_memory_ids}；"
        f"更新合并目标 {merged_memory_ids}；"
        f"堆肥种子 {composted_seed_ids}；"
        f"修剪记忆 {pruned_memory_ids}。"
        f"各步骤均保留可追踪 id，而非仅输出叙述性摘要。"
    )


def build_morning_garden(
    created_memory_ids: list[str],
    merged_memory_ids: list[str],
    composted_seed_ids: list[str],
) -> str:
    return (
        f"朝露：花园新增长期驻点 {len(created_memory_ids)} 处（{created_memory_ids}），"
        f"已有植株延展 {len(merged_memory_ids)} 处（{merged_memory_ids}），"
        f"情绪沉渣经堆肥归土 {len(composted_seed_ids)} 批（{composted_seed_ids}），"
        f"可继续被清晨的观察与书写唤醒。"
    )


def cluster_essence_from_seeds(seeds: list[Seed]) -> str:
    """多颗种子聚为一条记忆时的规则版高层表达（非逐字拼接）。"""
    seeds = sorted(seeds, key=lambda s: s.id)
    n = len(seeds)
    st = seeds[0].signal_type.value
    common_tags: set[str] = set(seeds[0].tags) if seeds[0].tags else set()
    for s in seeds[1:]:
        if s.tags:
            if not common_tags:
                common_tags = set(s.tags)
            else:
                common_tags &= set(s.tags)
    if common_tags:
        tag_label = sorted(common_tags)[0]
        tag_desc = f"在共享标签「{tag_label}」所界定的主题下"
    else:
        tag_desc = "在若干独立表述之间"
    return (
        f"夜间收敛：{tag_desc}，将 {n} 条同信号（{st}）线索收束为一条稳定取向；"
        f"本质以共同意图为轴，而非把各条原文简单串联。"
    )


def cluster_roots_branches(seeds: list[Seed]) -> tuple[list[str], list[str]]:
    """在根与枝中保留各颗种子的简短来源，便于追溯。"""
    seeds = sorted(seeds, key=lambda s: s.id)
    roots: list[str] = []
    branches: list[str] = []
    for s in seeds:
        line = f"[梦源种子 {s.id}] {s.content.strip()[:200]}"
        roots.append(line)
    return roots, branches
