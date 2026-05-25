#!/usr/bin/env python3
"""增强 Harvest LLM Rerank 演示 — 规则排序 vs LLM 重排序对比。

使用 DeepSeek API 对规则收获结果进行语义重排，展示规则引擎
在关键词重叠场景下的局限性以及 LLM 重排的价值。

用法：
    $env:DEEPSEEK_API_KEY="<DEEPSEEK_API_KEY>"; python examples/harvest_rerank_demo.py

仅建议在一次性本地调试时使用 ``--api-key``，避免把密钥写进 shell history。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from typing import Any

# ── 12 条测试记忆（4 个主题 × 3 条，故意关键词重叠）───────────────

TEST_MEMORIES: list[dict[str, Any]] = [
    # 主题 A — Python 偏好（含 "system" 关键词，与主题 B 冲突）
    {
        "id": "mem_101",
        "title": "Python 类型系统偏好",
        "essence": "用户强烈偏好 Python 的类型系统，认为类型注解是大型项目的必需品",
        "tags": ["python", "type_system", "preference"],
    },
    {
        "id": "mem_102",
        "title": "Pydantic 数据校验",
        "essence": "用户喜欢用 Pydantic 做数据校验，觉得 dataclass 不够严谨",
        "tags": ["python", "pydantic", "validation"],
    },
    {
        "id": "mem_103",
        "title": "Python async/await 并发",
        "essence": "用户依赖 Python 的 async/await 做并发，不喜欢 threading",
        "tags": ["python", "async", "concurrency"],
    },
    # 主题 B — 系统管理（含 "system" "python" 关键词，与主题 A 冲突）
    {
        "id": "mem_201",
        "title": "systemd 服务管理",
        "essence": "用户通过 systemd 管理 Linux 服务，写 Python 脚本做自动化部署",
        "tags": ["systemd", "linux", "python", "devops"],
    },
    {
        "id": "mem_202",
        "title": "WSL2 开发环境",
        "essence": "用户的开发环境是 WSL2 + Ubuntu，主要用 systemctl 管理服务",
        "tags": ["wsl2", "ubuntu", "systemctl", "environment"],
    },
    {
        "id": "mem_203",
        "title": "日志轮转脚本",
        "essence": "用户习惯用 Python 写定时任务脚本管理系统日志轮转",
        "tags": ["python", "logging", "cron", "devops"],
    },
    # 主题 C — 开发工具（含 "tool" "environment" 关键词）
    {
        "id": "mem_301",
        "title": "VSCode 切换到 Neovim",
        "essence": "用户从 VSCode 切换到了 Neovim，看重轻量和可配置性",
        "tags": ["editor", "neovim", "tools"],
    },
    {
        "id": "mem_302",
        "title": "tmux + zsh 终端环境",
        "essence": "用户用 tmux + zsh 做终端环境，有 3 年以上的配置积累",
        "tags": ["tmux", "zsh", "terminal", "environment"],
    },
    {
        "id": "mem_303",
        "title": "dotfiles 管理工具",
        "essence": "用户写了一个 dotfiles 管理工具来自动化环境搭建",
        "tags": ["dotfiles", "automation", "tools"],
    },
    # 主题 D — 架构观点（独立主题，不与任何主题关键词冲突）
    {
        "id": "mem_401",
        "title": "数据质量 > 模型能力",
        "essence": "用户认为 AI 系统的核心瓶颈不是模型能力而是数据质量",
        "tags": ["ai", "data_quality", "architecture"],
    },
    {
        "id": "mem_402",
        "title": "混合架构偏好",
        "essence": "用户坚持「规则兜底 + LLM 增强」的混合架构优于纯规则或纯 LLM",
        "tags": ["ai", "architecture", "hybrid"],
    },
    {
        "id": "mem_403",
        "title": "审计追溯 > 向量检索",
        "essence": "用户认为 AI memory 系统最缺的不是向量检索而是审计追溯",
        "tags": ["ai", "memory", "audit", "architecture"],
    },
]

# 6 个测试查询（充分覆盖混淆场景）
TEST_QUERIES: list[str] = [
    "用户用什么编程语言开发？",
    "用户对类型系统的看法是什么？",
    "用户的系统管理方式是怎样的？",
    "用户用什么开发工具和编辑器？",
    "用户对 AI 架构有什么见解？",
    "用户用什么做并发编程？",  # 应该只命中 mem_103
]


# ── DeepSeek Reranker ────────────────────────────────────────────────


class DeepSeekReranker:
    """使用 DeepSeek API 对候选记忆做语义重排。"""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.deepseek.com/v1"

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """调用 DeepSeek API 重排序，返回按语义相关性排序后的列表。"""
        if not candidates:
            return []

        lines = "\n".join(
            f"[{c['id']}] {c['title']}: {c['essence']}"
            for c in candidates
        )

        prompt = (
            "你是一个 AI 记忆检索系统的重排器。请根据用户查询，对以下候选记忆"
            "按语义相关性从高到低排序。只输出 JSON 数组的 memory_id，"
            "不要输出其他任何文字。\n\n"
            f"用户查询：{query}\n\n"
            f"候选记忆：\n{lines}\n\n"
            "输出 JSON 数组格式示例：[\"mem_101\", \"mem_102\", ...]"
        )

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system",
                     "content": "你是一个精确的记忆排序助手。只输出 JSON 数组。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 500,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=60)
            body = json.loads(resp.read().decode())
            raw = body["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print(f"  [WARN] API 调用失败: {exc}，回退到输入顺序")
            return list(candidates)

        ranked_ids = _parse_json_array(raw)
        if not ranked_ids:
            print(f"  [WARN] LLM 未返回有效 JSON 数组，回退到输入顺序。原始输出: {raw[:120]}")
            return list(candidates)

        # 按 LLM 排序重建结果
        id_map = {c["id"]: c for c in candidates}
        result: list[dict] = []
        seen: set[str] = set()
        for mid in ranked_ids:
            if mid in id_map and mid not in seen:
                result.append(id_map[mid])
                seen.add(mid)
        for c in candidates:
            if c["id"] not in seen:
                result.append(c)
        return result


def _parse_json_array(raw: str) -> list[str]:
    """从 LLM 输出中提取 JSON 字符串数组。"""
    raw = raw.strip()
    # 直接解析
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
            return parsed
    except json.JSONDecodeError:
        pass
    # 正则提取 JSON 数组
    m = re.search(r'\["[^"]*"(?:\s*,\s*"[^"]*")*\]', raw)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


# ── 简易规则检索 ────────────────────────────────────────────────────


def keyword_rank(query: str, memories: list[dict], top_k: int = 5) -> list[dict]:
    """基于关键词重叠 + 标签匹配的简易规则排序。"""
    q_words = set(query)
    scored: list[tuple[float, dict]] = []
    for m in memories:
        text = m["title"] + " " + m["essence"] + " " + " ".join(m.get("tags", []))
        kw_overlap = len(q_words & set(text))
        tag_hits = sum(1 for t in m.get("tags", []) if t in query.lower())
        score = float(kw_overlap + tag_hits * 3)
        if score > 0:
            scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:top_k]]


# ── 主流程 ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest LLM Rerank 演示")
    parser.add_argument(
        "--api-key",
        default=None,
        help="DeepSeek API key。优先使用环境变量，避免把密钥写进 shell history。",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：需要 DeepSeek API key。")
        print("  方式 1: 设置环境变量 DEEPSEEK_API_KEY")
        print("  方式 2: 仅在一次性本地调试时使用 --api-key")
        sys.exit(1)

    reranker = DeepSeekReranker(api_key=api_key)

    print("=" * 80)
    print("  Memory Garden — Harvest LLM Rerank 演示")
    print("  12 条记忆 | 4 个主题 | 关键词故意重叠 | 6 个混淆查询")
    print("=" * 80)
    print()

    all_results: list[dict] = []

    for i, query in enumerate(TEST_QUERIES, 1):
        print(f"查询 {i}: {query}")
        print("-" * 56)

        rule_top5 = keyword_rank(query, TEST_MEMORIES, top_k=5)
        rule_ids = [m["id"] for m in rule_top5[:3]]

        llm_sorted = reranker.rerank(query, rule_top5)
        llm_ids = [m["id"] for m in llm_sorted[:3]]

        overlap = len(set(rule_ids) & set(llm_ids))

        print(f"  规则 Top-3: {', '.join(rule_ids)}")
        print(f"  LLM  Top-3: {', '.join(llm_ids)}")
        print(f"  重叠率: {overlap}/3")
        print()

        all_results.append({
            "query": query,
            "overlap": overlap,
            "rule_top3": rule_ids,
            "llm_top3": llm_ids,
        })

    # ── 汇总表 ─────────────────────────────────────────────────────
    changed = sum(1 for r in all_results if r["rule_top3"] != r["llm_top3"])

    print("=" * 80)
    print("  汇总")
    print("=" * 80)

    def _fmt(ids: list[str]) -> str:
        return ", ".join(ids)

    header = (
        f"  {'查询':<32s}  {'重叠':>4s}  "
        f"{'规则 Top-3':<42s}  {'LLM Top-3':<42s}"
    )
    sep = (
        f"  {'─' * 32}  {'─' * 4}  "
        f"{'─' * 42}  {'─' * 42}"
    )
    print(header)
    print(sep)

    for r in all_results:
        q_short = r["query"][:30]
        rule_s = _fmt(r["rule_top3"])[:40]
        llm_s = _fmt(r["llm_top3"])[:40]
        print(f"  {q_short:<32s}  {r['overlap']:>2d}/3  {rule_s:<42s}  {llm_s:<42s}")

    print()
    print(f"  总结：{len(TEST_QUERIES)} 次查询中，{changed} 次 LLM 排序与规则排序 Top-3 不一致。")

    # 找最严重误判
    worst = None
    worst_gap = 0
    for r in all_results:
        if r["rule_top3"] != r["llm_top3"] and r["llm_top3"]:
            best_llm = r["llm_top3"][0]
            if best_llm in r["rule_top3"]:
                pos = r["rule_top3"].index(best_llm) + 1
                if pos > 1 and pos > worst_gap:
                    worst_gap = pos
                    worst = (r["query"], best_llm, pos)
    if worst:
        print(f"  最严重的误判：规则引擎将 {worst[1]} 排第 {worst[2]}，"
              f"但语义上它应该是第 1。")

    print()


if __name__ == "__main__":
    main()
