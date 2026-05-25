"""Memory Garden 命令行入口。

常用命令示例::

    python -m memory_garden demo --path ./.memory_garden
    python -m memory_garden health --path ./.memory_garden
    python -m memory_garden search "dark mode" --path ./.memory_garden
    python -m memory_garden --provider deepseek retrieve "dark mode"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from typing import Any


def _cmd_demo(args: argparse.Namespace) -> int:
    """运行完整 Garden 流程：打开会话、对话、观察、关闭。"""
    from memory_garden.sdk import MemoryGarden

    print("=" * 62)
    print("  Memory Garden 演示 - 默认本地运行，可选接入大模型")
    print("=" * 62)
    print(f"  Garden 路径: {args.path}")
    print()

    garden = MemoryGarden.local(args.path)
    try:
        r = garden.chat("花花开")
        sid = r.session_id
        print(f"  [花花开] 会话已打开 ({sid[:16]}...)")
        print()

        msg1 = "I prefer dark mode for all interfaces."
        print(f"  [user] {msg1}")
        r = garden.chat(msg1, session_id=sid)
        brief_note = "有" if r.garden_brief else "无"
        print(f"  [garden] 简报: {brief_note}, 回复: {r.reply[:80]}...")
        print()

        msg2 = "I work best in the morning, please remember that."
        print(f"  [user] {msg2}")
        r = garden.chat(msg2, session_id=sid)
        brief_note = "有" if r.garden_brief else "无"
        print(f"  [garden] 简报: {brief_note}, 回复: {r.reply[:80]}...")
        print()

        r = garden.chat("花花关", session_id=sid)
        print("  [花花关] 会话已关闭")
        if r.feedback:
            fb = r.feedback
            print(f"  [feedback] {fb.summary}")
            for bullet in fb.bullets:
                print(f"    - {bullet}")
        print()

        health = garden.health()
        print(f"  健康状态: {health.status.value}")
        print()

        from memory_garden.soil import check_garden_index, reindex_garden, search_garden

        idx = check_garden_index(args.path)
        if not idx.exists:
            print("  [index] 正在构建 FTS5 索引...")
            reindex_garden(args.path, dry_run=False)

        for query in ["dark mode", "morning", "preference"]:
            hits = search_garden(args.path, query, limit=3)
            if hits:
                print(f"  [search] '{query}' -> {len(hits)} result(s)")
                for hit in hits[:2]:
                    print(f"    - {hit.title or hit.target_id}")

        brief = garden.build_brief("dark mode", limit=3)
        print(f"  [strategy] 简报引用记忆数: {len(brief.source_memory_ids)}")
        print()
        print("  Demo complete. 演示完成，Garden 已写入可审计记忆。")
        print("=" * 62)
    finally:
        garden.close()
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    from memory_garden.soil import initialize_garden_home

    home = initialize_garden_home(args.path, create=True)
    print(f"Garden initialized at {home.root}")
    print(f"  manifest:  {home.manifest_path}")
    print(f"  schema:    v{home.manifest.schema_version}")
    return 0


def _cmd_health(args: argparse.Namespace) -> int:
    from memory_garden.soil import check_garden_health

    report = check_garden_health(args.path)
    print(f"Garden: {report.garden_home}")
    print(f"Status: {report.status.value}")
    if report.issues:
        for issue in report.issues:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}")
    else:
        print("  No issues detected.")
    return 0 if report.status.value != "unhealthy" else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Run release-oriented local checks without creating a garden."""

    from pathlib import Path

    from memory_garden.soil import check_garden_health

    root = Path(args.path).expanduser().resolve()
    repo_root = Path.cwd().resolve()
    ignore_file = repo_root / ".gitignore"
    required_ignore_patterns = [
        ".memory_garden/",
        "*.db",
        "*.db-wal",
        "*.db-shm",
        "*_state.json",
        "provider_config.json",
    ]

    report = check_garden_health(root)
    missing_ignore_patterns: list[str] = []
    if ignore_file.is_file():
        ignored = ignore_file.read_text(encoding="utf-8")
        missing_ignore_patterns = [
            pattern for pattern in required_ignore_patterns
            if pattern not in ignored
        ]
    else:
        missing_ignore_patterns = list(required_ignore_patterns)

    provider_config = root / "provider_config.json"
    has_deepseek_env = bool(os.environ.get("DEEPSEEK_API_KEY"))
    has_dashscope_env = bool(os.environ.get("DASHSCOPE_API_KEY"))

    print("Memory Garden doctor")
    print(f"  garden: {root}")
    print(f"  health: {report.status.value}")
    for issue in report.issues:
        print(f"    [{issue.severity.value}] {issue.code}: {issue.message}")
    print(f"  .gitignore: {'ok' if not missing_ignore_patterns else 'missing patterns'}")
    for pattern in missing_ignore_patterns:
        print(f"    missing: {pattern}")
    print(f"  provider env: deepseek={'set' if has_deepseek_env else 'unset'}, dashscope={'set' if has_dashscope_env else 'unset'}")
    print(f"  provider_config.json: {'present' if provider_config.is_file() else 'absent'}")

    if report.status.value == "unhealthy" or missing_ignore_patterns:
        return 1
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from memory_garden.soil import check_garden_index, search_garden, search_garden_scoped

    status = check_garden_index(args.path)
    if not status.exists:
        print(f"No FTS index found. Run: python -m memory_garden demo --path {args.path}")
        return 1
    if args.project or args.workspace or args.scope:
        hits = search_garden_scoped(
            args.path,
            args.query,
            limit=args.limit,
            scope=args.scope,
            project_id=args.project,
            workspace_id=args.workspace,
        )
    else:
        hits = search_garden(args.path, args.query, limit=args.limit)
    if not hits:
        print(f"No results for: {args.query}")
        return 0
    for index, hit in enumerate(hits, 1):
        print(f"[{index}] [{hit.target_type}] {hit.title or hit.target_id}")
        if hit.snippet:
            print(f"    {hit.snippet}")
    return 0


def _cmd_observe(args: argparse.Namespace) -> int:
    from memory_garden.observatory.views import GardenSummaryView

    summary = GardenSummaryView.from_garden_home(args.path, limit=args.limit)
    if summary.map.memory_count == 0 and summary.map.seed_count == 0:
        print(f"No data found in garden at {args.path}")
        print("Run 'memory-garden demo' first to populate the garden.")
        return 0

    if args.html:
        from memory_garden.observatory.renderers.html_report import render_html_report

        html = render_html_report(summary, title=f"Memory Garden Observatory - {args.path}")
        out_path = args.output or (args.path.rstrip("/\\") + "/observatory_report.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML report written to: {out_path}")
        if args.open:
            import webbrowser

            webbrowser.open("file://" + os.path.abspath(out_path))
        return 0

    if args.terminal:
        _print_terminal_observe(summary)
        return 0

    from memory_garden.observatory.renderers.markdown import render_garden_summary_markdown

    print(render_garden_summary_markdown(summary))
    return 0


def _print_terminal_observe(summary: Any) -> None:
    """在终端打印简洁的 Garden 观测摘要。"""
    m = summary.map
    print("Memory Garden Observatory")
    print(f"记忆: {m.memory_count}  种子: {m.seed_count}  法庭: {m.court_case_count}")
    print(f"梦境: {m.dream_record_count}  堆肥: {m.compost_count}  修剪: {m.pruning_count}")
    print(f"温室: {m.greenhouse_count}  事件: {m.event_count}")

    if summary.recent_memories:
        print("最近记忆:")
        for card in summary.recent_memories[:5]:
            print(f"  - {card.title or card.memory_id[:16]} [{card.lifecycle}]")

    if summary.recent_seeds:
        print("最近种子:")
        for seed in summary.recent_seeds[:3]:
            print(f"  - {seed.seed_id}")

    if summary.recent_cases:
        print("最近法庭案件:")
        for case in summary.recent_cases[:3]:
            print(f"  - {case.court_case_id} -> {case.judge_verdict}")


def _providers_from_args(args: argparse.Namespace):
    provider = getattr(args, "provider", None)
    if provider in (None, ""):
        return None

    from memory_garden.providers import (
        DeepSeekLLMProvider,
        FakeEmbeddingProvider,
        FakeLLMProvider,
        FakeRerankerProvider,
        OpenAICompatibleEmbeddingProvider,
        OpenAICompatibleLLMProvider,
        ProviderPolicy,
        ProviderRegistry,
    )

    remote_policy = ProviderPolicy(
        allow_remote_llm=True,
        allow_remote_embeddings=True,
        allow_remote_rerank=True,
        allow_raw_user_text=True,
    )
    local_fake_policy = ProviderPolicy(allow_raw_user_text=True)

    if provider == "fake":
        return ProviderRegistry(
            policy=local_fake_policy,
            llm=FakeLLMProvider(),
            embedding=FakeEmbeddingProvider(),
            reranker=FakeRerankerProvider(),
        )

    if provider == "deepseek":
        key = getattr(args, "api_key", None) or os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise SystemExit("缺少 DeepSeek API Key：请传入 --api-key 或设置 DEEPSEEK_API_KEY")
        return ProviderRegistry(
            policy=remote_policy,
            llm=DeepSeekLLMProvider(
                api_key=key,
                model=getattr(args, "model", None) or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                base_url=getattr(args, "base_url", None)
                or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            ),
        )

    if provider == "openai":
        key = getattr(args, "api_key", None) or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("缺少 OpenAI API Key：请传入 --api-key 或设置 OPENAI_API_KEY")
        base_url = getattr(args, "base_url", None) or os.environ.get("OPENAI_BASE_URL")
        llm = OpenAICompatibleLLMProvider(
            api_key=key,
            model=getattr(args, "model", None) or os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            base_url=base_url,
            name="openai-llm",
        )
        embedding = OpenAICompatibleEmbeddingProvider(
            api_key=key,
            model=os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            base_url=base_url,
            name="openai-embedding",
        )
        return ProviderRegistry(policy=remote_policy, llm=llm, embedding=embedding)

    raise SystemExit("不支持的 provider：" + str(provider))


def _product_system(args_or_path: argparse.Namespace | str):
    from memory_garden.product import ProductMemorySystem
    from memory_garden.sdk import MemoryGarden

    path = args_or_path.path if isinstance(args_or_path, argparse.Namespace) else args_or_path
    garden = MemoryGarden.local(path)
    providers = _providers_from_args(args_or_path) if isinstance(args_or_path, argparse.Namespace) else None
    return garden, ProductMemorySystem(
        garden_home=garden.home.root,
        repository=garden.core.repository,
        providers=providers,
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default))


def _parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def _patch_from_args(args: argparse.Namespace):
    from memory_garden.core.models import MemoryType, SensitivityLevel
    from memory_garden.product import MemoryPatch

    updates: dict[str, Any] = {}
    for key in ("title", "essence", "fragrance", "thorns"):
        value = getattr(args, key, None)
        if value is not None:
            updates[key] = value
    if getattr(args, "tags", None) is not None:
        updates["tags"] = _parse_csv(args.tags) or []
    if getattr(args, "memory_type", None) is not None:
        updates["memory_type"] = MemoryType(args.memory_type)
    if getattr(args, "sensitivity", None) is not None:
        updates["sensitivity"] = SensitivityLevel(args.sensitivity)
    if getattr(args, "confidence", None) is not None:
        updates["confidence"] = args.confidence
    if getattr(args, "importance", None) is not None:
        updates["importance"] = args.importance
    return MemoryPatch(**updates)


def _context_from_args(args: argparse.Namespace):
    from memory_garden.product import ApplicabilityContext

    return ApplicabilityContext(
        query=getattr(args, "query", "") or "",
        project_id=getattr(args, "project_id", "") or "",
        workspace_id=getattr(args, "workspace_id", "") or "",
        user_id=getattr(args, "user_id", "") or "",
        session_id=getattr(args, "session_id", "") or "",
        task_type=getattr(args, "task_type", "") or "",
        tags=_parse_csv(getattr(args, "context_tags", None)) or [],
        allow_sensitive=bool(getattr(args, "allow_sensitive", False)),
    )


def _cmd_product_remember(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.remember(args.text, mode=args.mode, metadata={"cli": True}))
        return 0
    finally:
        garden.close()


def _cmd_product_propose(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.propose(args.text, metadata={"cli": True}))
        return 0
    finally:
        garden.close()


def _cmd_product_inbox(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        status = None if args.status == "all" else args.status
        _print_json(product.inbox(status=status, limit=args.limit))
        return 0
    finally:
        garden.close()


def _cmd_product_approve(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.approve(args.proposal_id))
        return 0
    finally:
        garden.close()


def _cmd_product_reject(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.reject(args.proposal_id, reason=args.reason))
        return 0
    finally:
        garden.close()


def _cmd_product_edit_proposal(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.edit_proposal(args.proposal_id, _patch_from_args(args)))
        return 0
    finally:
        garden.close()


def _cmd_product_memories(args: argparse.Namespace) -> int:
    from memory_garden.core.models import MemoryType, SensitivityLevel
    from memory_garden.product import MemoryLayer, MemoryListFilter, MemoryMaturityStage, MemoryScope

    garden, product = _product_system(args)
    try:
        filters = MemoryListFilter(
            memory_type=MemoryType(args.memory_type) if args.memory_type else None,
            sensitivity=SensitivityLevel(args.sensitivity) if args.sensitivity else None,
            tag=args.tag,
            layer=MemoryLayer(args.layer) if args.layer else None,
            scope=MemoryScope(args.scope) if args.scope else None,
            scope_id=args.scope_id,
            maturity=MemoryMaturityStage(args.maturity) if args.maturity else None,
            include_greenhouse=args.include_greenhouse,
            include_archived=args.include_archived,
            limit=args.limit,
        )
        _print_json(product.list_memories(filters))
        return 0
    finally:
        garden.close()


def _cmd_product_inspect(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.inspect_memory(args.memory_id, applicability_queries=args.applicability_query or []))
        return 0
    finally:
        garden.close()


def _cmd_product_update(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.edit_memory(args.memory_id, _patch_from_args(args), reason=args.reason))
        return 0
    finally:
        garden.close()


def _cmd_product_archive(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.archive_memory(args.memory_id, reason=args.reason))
        return 0
    finally:
        garden.close()


def _cmd_product_restore(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.restore_memory(args.memory_id, reason=args.reason))
        return 0
    finally:
        garden.close()


def _cmd_product_merge(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.merge_memories(args.memory_ids, target_id=args.target))
        return 0
    finally:
        garden.close()


def _cmd_product_retrieve(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.retrieve(args.query, limit=args.limit, explain=not args.no_explain, context=_context_from_args(args)))
        return 0
    finally:
        garden.close()


def _cmd_product_brief(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.build_brief(args.query, limit=args.limit, context=_context_from_args(args)))
        return 0
    finally:
        garden.close()


def _cmd_product_strategy(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.get_strategy_profile(args.memory_id))
        return 0
    finally:
        garden.close()


def _cmd_product_applicability(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.assess_applicability(args.memory_id, args.query, context=_context_from_args(args)))
        return 0
    finally:
        garden.close()


def _cmd_product_reinforce(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.reinforce_memory(args.memory_id, reason=args.reason, amount=args.amount))
        return 0
    finally:
        garden.close()


def _cmd_product_decay(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.decay_memories(limit=args.limit))
        return 0
    finally:
        garden.close()


def _cmd_product_abstractions(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.plan_abstractions(limit=args.limit))
        return 0
    finally:
        garden.close()


def _cmd_product_forget_plan(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        _print_json(product.plan_forget(args.target, memory_id=args.memory_id, cascade=not args.no_cascade))
        return 0
    finally:
        garden.close()


def _cmd_product_forget_exec(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        plan, proof = product.execute_forget(args.plan_id)
        _print_json({"plan": plan, "proof": proof})
        return 0 if proof.proven else 1
    finally:
        garden.close()


def _cmd_product_forget_proof(args: argparse.Namespace) -> int:
    garden, product = _product_system(args)
    try:
        proof = product.prove_forget(args.memory_id, plan_id=args.plan_id)
        _print_json(proof)
        return 0 if proof.proven else 1
    finally:
        garden.close()


def _cmd_product_providers(args: argparse.Namespace) -> int:
    from memory_garden.providers import ProviderPolicy

    policy = ProviderPolicy()
    _print_json(
        {
            "provider_interfaces": ["LLMProvider", "EmbeddingProvider", "RerankerProvider", "SecretProvider"],
            "default_policy": {
                "remote_llm": "allowed" if policy.allow_remote_llm else "blocked",
                "remote_embedding": "allowed" if policy.allow_remote_embeddings else "blocked",
                "remote_reranker": "allowed" if policy.allow_remote_rerank else "blocked",
                "raw_text_to_provider": "allowed" if policy.allow_raw_user_text else "blocked",
                "sensitive_text_to_provider": "allowed" if policy.allow_sensitive_text else "blocked",
            },
            "note": "CLI 可通过 --provider openai/deepseek/fake 配置 provider；未显式配置时仍只使用本地规则。",
        }
    )
    return 0


def _add_patch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title")
    parser.add_argument("--essence")
    parser.add_argument("--memory-type")
    parser.add_argument("--tags", help="逗号分隔的标签")
    parser.add_argument("--fragrance")
    parser.add_argument("--thorns")
    parser.add_argument("--confidence", type=float)
    parser.add_argument("--importance", type=float)
    parser.add_argument("--sensitivity")


def _add_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", default="")
    parser.add_argument("--workspace-id", default="")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--task-type", default="")
    parser.add_argument("--context-tags", help="逗号分隔的上下文标签")
    parser.add_argument("--allow-sensitive", action="store_true")


def _add_provider_args(parser: argparse.ArgumentParser, *, suppress_default: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_default else None
    parser.add_argument(
        "--provider",
        choices=["openai", "deepseek", "fake"],
        default=default,
        help="选择模型 provider：openai / deepseek / fake",
    )
    parser.add_argument(
        "--api-key",
        default=default,
        help="Provider API Key；优先使用环境变量，避免把密钥写进 shell history",
    )
    parser.add_argument("--model", default=default, help="模型名称；未传时读取环境变量或使用 provider 默认值")
    parser.add_argument("--base-url", default=default, help="自定义 OpenAI 兼容 endpoint")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memory-garden",
        description="Memory Garden - 默认本地运行、可选接入大模型的可审计记忆层",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            示例:
              memory-garden demo                         运行完整 Garden 演示
              memory-garden init --path ./my_garden      创建新的本地 Garden
              memory-garden health                       检查 Garden 健康状态
              memory-garden search "深色模式"            搜索本地记忆
              memory-garden observe --path ./my_garden   查看观测报告
              memory-garden remember "请记住：我偏好深色模式" --mode trusted
              memory-garden --provider deepseek retrieve "深色模式"
              export OPENAI_API_KEY="..."
              memory-garden --provider openai brief "深色模式"
        """),
    )
    _add_provider_args(parser)
    sub = parser.add_subparsers(dest="command")

    p_demo = sub.add_parser("demo", help="运行完整 Garden 演示")
    p_demo.add_argument("--path", default="./.memory_garden")
    p_demo.set_defaults(func=_cmd_demo)

    p_init = sub.add_parser("init", help="初始化 Garden 本地目录")
    p_init.add_argument("--path", default="./.memory_garden")
    p_init.set_defaults(func=_cmd_init)

    p_health = sub.add_parser("health", help="检查 Garden 健康状态")
    p_health.add_argument("--path", default="./.memory_garden")
    p_health.set_defaults(func=_cmd_health)

    p_doctor = sub.add_parser("doctor", help="Run local release and safety checks")
    p_doctor.add_argument("--path", default="./.memory_garden")
    p_doctor.set_defaults(func=_cmd_doctor)

    p_search = sub.add_parser("search", help="使用 FTS5 搜索本地记忆")
    p_search.add_argument("query", help="搜索文本")
    p_search.add_argument("--path", default="./.memory_garden")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--project", help="只返回指定项目 scope id 的记忆卡片")
    p_search.add_argument("--workspace", help="只返回指定工作区 scope id 的记忆卡片")
    p_search.add_argument("--scope", choices=["global_user", "project", "workspace", "session", "identity"])
    p_search.set_defaults(func=_cmd_search)

    p_observe = sub.add_parser("observe", help="显示观测台摘要报告")
    p_observe.add_argument("--path", default="./.memory_garden")
    p_observe.add_argument("--limit", type=int, default=50)
    p_observe.add_argument("--html", action="store_true", help="输出自包含 HTML 报告")
    p_observe.add_argument("--open", action="store_true", help="在浏览器中打开 HTML 报告（需要 --html）")
    p_observe.add_argument("--output", default=None, help="HTML 报告输出路径")
    p_observe.add_argument("--terminal", action="store_true", help="输出彩色终端视图")
    p_observe.set_defaults(func=_cmd_observe)

    p_remember = sub.add_parser("remember", help="运行产品级记忆提案流程")
    p_remember.add_argument("text")
    p_remember.add_argument("--path", default="./.memory_garden")
    p_remember.add_argument("--mode", choices=["manual", "trusted", "auto"], default="trusted")
    p_remember.set_defaults(func=_cmd_product_remember)

    p_propose = sub.add_parser("propose", help="创建记忆提案但不写入长期记忆")
    p_propose.add_argument("text")
    p_propose.add_argument("--path", default="./.memory_garden")
    p_propose.set_defaults(func=_cmd_product_propose)

    p_inbox = sub.add_parser("inbox", help="列出记忆提案")
    p_inbox.add_argument("--path", default="./.memory_garden")
    p_inbox.add_argument("--status", choices=["all", "pending", "approved", "rejected", "edited", "superseded"], default="pending")
    p_inbox.add_argument("--limit", type=int, default=100)
    p_inbox.set_defaults(func=_cmd_product_inbox)

    p_approve = sub.add_parser("approve", help="批准一个记忆提案")
    p_approve.add_argument("proposal_id")
    p_approve.add_argument("--path", default="./.memory_garden")
    p_approve.set_defaults(func=_cmd_product_approve)

    p_reject = sub.add_parser("reject", help="拒绝一个记忆提案")
    p_reject.add_argument("proposal_id")
    p_reject.add_argument("--path", default="./.memory_garden")
    p_reject.add_argument("--reason", default="")
    p_reject.set_defaults(func=_cmd_product_reject)

    p_edit_prop = sub.add_parser("edit-proposal", help="编辑一个记忆提案")
    p_edit_prop.add_argument("proposal_id")
    p_edit_prop.add_argument("--path", default="./.memory_garden")
    _add_patch_args(p_edit_prop)
    p_edit_prop.set_defaults(func=_cmd_product_edit_proposal)

    p_memories = sub.add_parser("memories", help="列出产品级记忆视图")
    p_memories.add_argument("--path", default="./.memory_garden")
    p_memories.add_argument("--tag")
    p_memories.add_argument("--memory-type")
    p_memories.add_argument("--sensitivity")
    p_memories.add_argument("--layer")
    p_memories.add_argument("--scope")
    p_memories.add_argument("--scope-id")
    p_memories.add_argument("--maturity")
    p_memories.add_argument("--include-greenhouse", action="store_true")
    p_memories.add_argument("--include-archived", action="store_true")
    p_memories.add_argument("--limit", type=int, default=50)
    p_memories.set_defaults(func=_cmd_product_memories)

    p_inspect = sub.add_parser("inspect", help="检查单条记忆及其版本和关系")
    p_inspect.add_argument("memory_id")
    p_inspect.add_argument("--path", default="./.memory_garden")
    p_inspect.add_argument("--applicability-query", action="append")
    p_inspect.set_defaults(func=_cmd_product_inspect)

    p_update = sub.add_parser("update-memory", help="修补一条记忆并保留旧版本")
    p_update.add_argument("memory_id")
    p_update.add_argument("--path", default="./.memory_garden")
    p_update.add_argument("--reason", default="cli_update")
    _add_patch_args(p_update)
    p_update.set_defaults(func=_cmd_product_update)

    p_archive = sub.add_parser("archive-memory", help="归档一条记忆，使其退出主动检索")
    p_archive.add_argument("memory_id")
    p_archive.add_argument("--path", default="./.memory_garden")
    p_archive.add_argument("--reason", default="cli_archive")
    p_archive.set_defaults(func=_cmd_product_archive)

    p_restore = sub.add_parser("restore-memory", help="恢复一条已归档记忆")
    p_restore.add_argument("memory_id")
    p_restore.add_argument("--path", default="./.memory_garden")
    p_restore.add_argument("--reason", default="cli_restore")
    p_restore.set_defaults(func=_cmd_product_restore)

    p_merge = sub.add_parser("merge-memories", help="把多条记忆合并到目标记忆")
    p_merge.add_argument("memory_ids", nargs="+")
    p_merge.add_argument("--path", default="./.memory_garden")
    p_merge.add_argument("--target")
    p_merge.set_defaults(func=_cmd_product_merge)

    p_retrieve = sub.add_parser("retrieve", help="带解释的产品级记忆检索")
    p_retrieve.add_argument("query")
    p_retrieve.add_argument("--path", default="./.memory_garden")
    p_retrieve.add_argument("--limit", type=int, default=5)
    p_retrieve.add_argument("--no-explain", action="store_true")
    _add_context_args(p_retrieve)
    p_retrieve.set_defaults(func=_cmd_product_retrieve)

    p_brief = sub.add_parser("brief", help="生成产品级 GardenBrief")
    p_brief.add_argument("query")
    p_brief.add_argument("--path", default="./.memory_garden")
    p_brief.add_argument("--limit", type=int, default=5)
    _add_context_args(p_brief)
    p_brief.set_defaults(func=_cmd_product_brief)

    p_strategy = sub.add_parser("strategy", help="显示记忆策略画像")
    p_strategy.add_argument("memory_id")
    p_strategy.add_argument("--path", default="./.memory_garden")
    p_strategy.set_defaults(func=_cmd_product_strategy)

    p_applicability = sub.add_parser("applicability", help="解释一条记忆是否适用于当前查询或任务")
    p_applicability.add_argument("memory_id")
    p_applicability.add_argument("query")
    p_applicability.add_argument("--path", default="./.memory_garden")
    _add_context_args(p_applicability)
    p_applicability.set_defaults(func=_cmd_product_applicability)

    p_reinforce = sub.add_parser("reinforce-memory", help="强化一条记忆的策略画像")
    p_reinforce.add_argument("memory_id")
    p_reinforce.add_argument("--path", default="./.memory_garden")
    p_reinforce.add_argument("--reason", default="cli_reinforce")
    p_reinforce.add_argument("--amount", type=float, default=0.08)
    p_reinforce.set_defaults(func=_cmd_product_reinforce)

    p_decay = sub.add_parser("decay-memories", help="执行确定性的记忆衰减")
    p_decay.add_argument("--path", default="./.memory_garden")
    p_decay.add_argument("--limit", type=int, default=500)
    p_decay.set_defaults(func=_cmd_product_decay)

    p_abstractions = sub.add_parser("plan-abstractions", help="规划更高层级的记忆抽象")
    p_abstractions.add_argument("--path", default="./.memory_garden")
    p_abstractions.add_argument("--limit", type=int, default=500)
    p_abstractions.set_defaults(func=_cmd_product_abstractions)

    p_forget_plan = sub.add_parser("forget-plan", help="创建硬删除遗忘计划")
    p_forget_plan.add_argument("target", nargs="?", default="")
    p_forget_plan.add_argument("--path", default="./.memory_garden")
    p_forget_plan.add_argument("--memory-id")
    p_forget_plan.add_argument("--no-cascade", action="store_true")
    p_forget_plan.set_defaults(func=_cmd_product_forget_plan)

    p_forget_exec = sub.add_parser("forget-exec", help="执行硬删除遗忘计划并保存证明")
    p_forget_exec.add_argument("plan_id")
    p_forget_exec.add_argument("--path", default="./.memory_garden")
    p_forget_exec.set_defaults(func=_cmd_product_forget_exec)

    p_forget_proof = sub.add_parser("forget-proof", help="证明指定记忆 id 已被遗忘")
    p_forget_proof.add_argument("memory_id")
    p_forget_proof.add_argument("--path", default="./.memory_garden")
    p_forget_proof.add_argument("--plan-id", default="")
    p_forget_proof.set_defaults(func=_cmd_product_forget_proof)

    p_providers = sub.add_parser("providers", help="显示外部 provider 接口策略")
    p_providers.set_defaults(func=_cmd_product_providers)

    for subparser in (
        p_demo,
        p_init,
        p_health,
        p_doctor,
        p_search,
        p_observe,
        p_remember,
        p_propose,
        p_inbox,
        p_approve,
        p_reject,
        p_edit_prop,
        p_memories,
        p_inspect,
        p_update,
        p_archive,
        p_restore,
        p_merge,
        p_retrieve,
        p_brief,
        p_strategy,
        p_applicability,
        p_reinforce,
        p_decay,
        p_abstractions,
        p_forget_plan,
        p_forget_exec,
        p_forget_proof,
        p_providers,
    ):
        _add_provider_args(subparser, suppress_default=True)

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
