"""Agent Brief 注入对比演示 — 无 Memory Garden vs 有 Garden Brief。

展示同一 user query 下：
1. 无 brief 的 deterministic fake agent 只能泛化回答；
2. 经 ``GardenSkill.before()`` 生成 Garden Brief 并注入后，agent 能引用预置记忆。

运行（仓库根目录）::

    python examples/agent_brief_injection_demo.py
    python examples/agent_brief_injection_demo.py --path /tmp/my_garden

零云依赖、无 API key、默认使用临时目录（不落盘到仓库）。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_garden.sdk import MemoryGarden

# ── 固定演示场景 ──────────────────────────────────────────────────

DEMO_MARKER = "MG_STAGE15_DEMO"

USER_QUERY = (
    "When helping me with Memory Garden, what stack, constraints, and demo rules should you follow?"
)

SEED_MEMORIES: tuple[str, ...] = (
    (
        f"remember: {DEMO_MARKER} For Memory Garden project use Python and TypeScript; "
        "keep local-first with no cloud dependency; never invent benchmark numbers in demos."
    ),
)

# stdout 分区标题（测试 grep 用）
SECTION_USER_QUERY = "========== USER QUERY =========="
SECTION_NO_MEMORY = "========== NO-MEMORY RESPONSE =========="
SECTION_GARDEN_BRIEF = "========== GARDEN BRIEF =========="
SECTION_MESSAGE_INJECTION = "========== MESSAGE INJECTION =========="
SECTION_WITH_MEMORY = "========== WITH-MEMORY RESPONSE =========="

# agent 从 brief 中识别的 cue（casefold 匹配）
_BRIEF_CUES: tuple[tuple[str, str], ...] = (
    ("python", "Python"),
    ("typescript", "TypeScript"),
    ("local-first", "local-first"),
    ("local", "local-first"),
    ("memory garden", "Memory Garden"),
    ("benchmark", "no invented benchmark numbers"),
    ("cloud", "no cloud dependency"),
)


class SilentHarvestAgent:
    """供 ``garden.set_host_agent()`` 使用：``skill.before()`` 内部 chat 不干扰演示输出。"""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str:
        self.calls.append((user_message, session_id))
        return "[internal-harvest-only]"


class DeterministicFakeAgent:
    """规则 fake agent：无 brief 时泛化；有 brief 时从 brief + 记忆摘要提取 cue。"""

    def reply(self, *, query: str, brief_text: str, memory_context: str = "") -> str:
        if not brief_text or not brief_text.strip():
            return (
                "[no-memory agent] I have no prior context about your project. "
                "I'd suggest any popular stack, cloud tools when convenient, "
                "and citing performance metrics when they help the explanation."
            )
        blob = f"{brief_text}\n{memory_context}".casefold()
        matched: list[str] = []
        seen: set[str] = set()
        for needle, label in _BRIEF_CUES:
            if needle in blob and label not in seen:
                seen.add(label)
                matched.append(label)
        if not matched:
            use_lines = [
                line.split("]", 1)[-1].strip()
                for line in brief_text.splitlines()
                if line.strip().lower().startswith("[use]")
            ]
            excerpt = use_lines[0][:120] if use_lines else brief_text[:120]
            return (
                f"[with-memory agent] Garden Brief supplied context: {excerpt}"
            )
        cues = ", ".join(matched)
        return (
            f"[with-memory agent] Following your Memory Garden brief — "
            f"stack/constraints/rules: {cues}."
        )


class DemoRunResult:
    """演示运行结果。"""

    __slots__ = (
        "ok",
        "stdout",
        "user_query",
        "no_memory_response",
        "garden_brief",
        "with_memory_response",
        "memory_ids",
        "error",
    )

    def __init__(
        self,
        *,
        ok: bool,
        stdout: str = "",
        user_query: str = USER_QUERY,
        no_memory_response: str = "",
        garden_brief: str = "",
        with_memory_response: str = "",
        memory_ids: list[str] | None = None,
        error: str = "",
    ) -> None:
        self.ok = ok
        self.stdout = stdout
        self.user_query = user_query
        self.no_memory_response = no_memory_response
        self.garden_brief = garden_brief
        self.with_memory_response = with_memory_response
        self.memory_ids = memory_ids or []
        self.error = error


def format_message_diff(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    """展示 ``inject_into_messages`` 前后差异。"""
    lines = ["--- before injection ---", json.dumps(before, ensure_ascii=False, indent=2)]
    lines.append("--- after injection ---")
    lines.append(json.dumps(after, ensure_ascii=False, indent=2))
    injected = after[len(before) :] if len(after) > len(before) else []
    for msg in after:
        if msg.get("role") == "system" and "[Memory Garden Brief]" in str(msg.get("content", "")):
            lines.append("--- injected system message ---")
            lines.append(str(msg.get("content", "")))
            break
    if not injected and len(after) == len(before):
        for b, a in zip(before, after, strict=False):
            if b != a:
                lines.append("--- modified system content ---")
                lines.append(str(a.get("content", "")))
                break
    return "\n".join(lines)


def _memory_excerpts(garden: MemoryGarden, source_ids: list[str]) -> str:
    """Demo 层：按 brief 中的 source_memory_ids 解析记忆摘要（模拟真实集成方补全上下文）。"""
    lines: list[str] = []
    for mid in source_ids:
        card = garden.core.repository.get_memory_card(mid)
        if card is None:
            continue
        lines.append(f"{card.title}: {card.essence}")
    return "\n".join(lines)


def _seed_memories(skill) -> list[str]:
    memory_ids: list[str] = []
    for text in SEED_MEMORIES:
        result = skill.remember(text)
        if not result.ok:
            err = result.error.message if result.error else str(result.skipped_reasons)
            raise RuntimeError(f"remember failed: {err}")
        memory_ids.extend(result.memory_ids)
    if not memory_ids:
        raise RuntimeError("no memories planted during seed phase")
    return list(dict.fromkeys(memory_ids))


def run_demo(*, garden_home: Path | None = None, quiet: bool = False) -> DemoRunResult:
    """执行完整演示；``garden_home`` 为 None 时由调用方管理临时目录。"""
    lines: list[str] = []
    garden_path = Path(garden_home) if garden_home is not None else None
    own_temp = garden_path is None
    temp_ctx = tempfile.TemporaryDirectory(prefix="mg_brief_demo_") if own_temp else None

    try:
        if garden_path is None:
            assert temp_ctx is not None
            garden_path = Path(temp_ctx.name)

        garden = MemoryGarden.local(garden_path)
        try:
            garden.set_host_agent(SilentHarvestAgent())
            skill = garden.as_skill()
            agent = DeterministicFakeAgent()

            memory_ids = _seed_memories(skill)

            no_memory_response = agent.reply(query=USER_QUERY, brief_text="")

            skill.open()
            messages_before = [{"role": "user", "content": USER_QUERY}]
            ctx = skill.before(USER_QUERY, messages=list(messages_before))
            if not ctx.brief_text.strip():
                raise RuntimeError("Garden Brief is empty after harvest; cannot demonstrate injection")

            messages_after = ctx.inject_into_messages(list(messages_before))
            source_ids = list(ctx.brief_dict.get("source_memory_ids") or [])
            memory_context = _memory_excerpts(garden, source_ids)
            with_memory_response = agent.reply(
                query=USER_QUERY,
                brief_text=ctx.brief_text,
                memory_context=memory_context,
            )
            skill.after(USER_QUERY, with_memory_response)
            skill.close()

            lines.append(SECTION_USER_QUERY)
            lines.append(USER_QUERY)
            lines.append("")
            lines.append(SECTION_NO_MEMORY)
            lines.append(no_memory_response)
            lines.append("")
            lines.append(SECTION_GARDEN_BRIEF)
            lines.append(ctx.brief_text)
            if source_ids:
                lines.append("")
                lines.append(f"(source_memory_ids: {', '.join(source_ids)})")
            if memory_context.strip():
                lines.append("")
                lines.append("--- resolved memory excerpts (demo helper) ---")
                lines.append(memory_context)
            lines.append("")
            lines.append(SECTION_MESSAGE_INJECTION)
            lines.append(format_message_diff(messages_before, messages_after))
            lines.append("")
            lines.append(SECTION_WITH_MEMORY)
            lines.append(with_memory_response)
            lines.append("")
            lines.append(f"(seeded {len(memory_ids)} memory card(s) in {garden_path})")

            stdout = "\n".join(lines)
            if not quiet:
                print(stdout, end="" if stdout.endswith("\n") else "\n")

            return DemoRunResult(
                ok=True,
                stdout=stdout,
                no_memory_response=no_memory_response,
                garden_brief=ctx.brief_text,
                with_memory_response=with_memory_response,
                memory_ids=memory_ids,
            )
        finally:
            garden.close()
    except Exception as exc:
        msg = str(exc)
        if not quiet:
            print(f"demo failed: {msg}", file=sys.stderr)
        return DemoRunResult(ok=False, error=msg, stdout="\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Memory Garden Agent Brief injection demo")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Garden home directory (default: temporary directory, auto-deleted)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout (for tests)")
    args = parser.parse_args(argv)

    if args.path is not None:
        result = run_demo(garden_home=args.path, quiet=args.quiet)
    else:
        with tempfile.TemporaryDirectory(prefix="mg_brief_demo_") as tmp:
            result = run_demo(garden_home=Path(tmp), quiet=args.quiet)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
