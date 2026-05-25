"""Smoke test a Memory Garden product workflow with optional real providers.

Offline run:
    python scripts/real_provider_smoke.py --provider fake --embedding-provider fake

OpenAI-compatible run:
    set OPENAI_API_KEY=...
    set MEMORY_GARDEN_LLM_MODEL=...
    set MEMORY_GARDEN_EMBEDDING_MODEL=...
    python scripts/real_provider_smoke.py --provider openai --embedding-provider openai

DeepSeek LLM run:
    set DEEPSEEK_API_KEY=...
    python scripts/real_provider_smoke.py --provider deepseek --embedding-provider fake

For one-off local debugging you may also pass ``--api-key`` or
``--embedding-api-key``, but prefer environment variables so secrets do not end
up in shell history.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_garden.providers import (
    DeepSeekLLMProvider,
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeRerankerProvider,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleRerankerProvider,
    ProviderPolicy,
    ProviderRegistry,
)
from memory_garden.sdk import MemoryGarden


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = Path(args.path)
    if args.fresh and path.exists():
        shutil.rmtree(path)

    registry = _registry_from_args(args)
    garden = MemoryGarden.local(path)
    try:
        skill = garden.as_skill()
        skill.configure_providers(registry)

        report: dict[str, Any] = {
            "provider": args.provider,
            "embedding_provider": args.embedding_provider,
            "rerank": args.rerank,
            "path": str(path),
            "steps": [],
        }

        text = args.text or "remember: I prefer concise release checklists with explicit rollback steps."
        proposals = skill.propose_memory(text, metadata={"smoke": True})
        report["steps"].append({"name": "propose", "count": len(proposals), "sources": [p.source for p in proposals]})
        if not proposals:
            report["ok"] = False
            report["error"] = "no proposals returned"
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return 1

        approved = skill.approve_memory_proposal(proposals[0].id)
        report["steps"].append({"name": "approve", "memory_id": approved.id, "title": approved.title})

        query = args.query or "How should release checklists be written?"
        retrieval = skill.retrieve_memories(query, limit=args.limit)
        hit_ids = [hit.memory.id for hit in retrieval.hits]
        report["steps"].append(
            {
                "name": "retrieve",
                "hit_ids": hit_ids,
                "provider_used": retrieval.provider_used,
            }
        )

        brief = skill.build_memory_brief(query, limit=args.limit)
        report["steps"].append(
            {
                "name": "brief",
                "source_memory_ids": brief.source_memory_ids,
                "use": brief.use[:500],
            }
        )

        report["ok"] = bool(hit_ids and approved.id in brief.source_memory_ids)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report["ok"] else 1
    finally:
        garden.close()


def _registry_from_args(args: argparse.Namespace) -> ProviderRegistry:
    llm = _llm_provider(args)
    embedding = _embedding_provider(args)
    reranker = OpenAICompatibleRerankerProvider(llm=llm) if args.rerank and args.provider != "fake" else None
    if args.rerank and args.provider == "fake":
        reranker = FakeRerankerProvider()

    return ProviderRegistry(
        policy=ProviderPolicy(
            allow_remote_llm=args.provider != "fake",
            allow_remote_embeddings=args.embedding_provider == "openai",
            allow_remote_rerank=bool(args.rerank and args.provider != "fake"),
            allow_raw_user_text=True,
            allow_sensitive_text=args.allow_sensitive_text,
            max_candidates_per_call=args.max_candidates,
        ),
        llm=llm,
        embedding=embedding,
        reranker=reranker,
    )


def _llm_provider(args: argparse.Namespace):
    if args.provider == "fake":
        return FakeLLMProvider()
    if args.provider == "deepseek":
        api_key = args.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise SystemExit("DEEPSEEK_API_KEY or --api-key is required for --provider deepseek")
        return DeepSeekLLMProvider(api_key=api_key, model=args.llm_model or "deepseek-chat")
    if args.provider == "openai":
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        model = args.llm_model or os.environ.get("MEMORY_GARDEN_LLM_MODEL")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY or --api-key is required for --provider openai")
        if not model:
            raise SystemExit("MEMORY_GARDEN_LLM_MODEL or --llm-model is required for --provider openai")
        return OpenAICompatibleLLMProvider(
            api_key=api_key,
            model=model,
            base_url=args.base_url,
            name="openai-llm",
        )
    raise SystemExit(f"unsupported provider: {args.provider}")


def _embedding_provider(args: argparse.Namespace):
    if args.embedding_provider == "none":
        return None
    if args.embedding_provider == "fake":
        return FakeEmbeddingProvider()
    if args.embedding_provider == "openai":
        api_key = args.embedding_api_key or args.api_key or os.environ.get("OPENAI_API_KEY")
        model = args.embedding_model or os.environ.get("MEMORY_GARDEN_EMBEDDING_MODEL")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY, --api-key, or --embedding-api-key is required for OpenAI embeddings")
        if not model:
            raise SystemExit("MEMORY_GARDEN_EMBEDDING_MODEL or --embedding-model is required for OpenAI embeddings")
        return OpenAICompatibleEmbeddingProvider(
            api_key=api_key,
            model=model,
            base_url=args.embedding_base_url or args.base_url,
            name="openai-embedding",
        )
    raise SystemExit(f"unsupported embedding provider: {args.embedding_provider}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a real-provider Memory Garden smoke workflow")
    parser.add_argument("--path", default="./.memory_garden_real_smoke")
    parser.add_argument("--fresh", action="store_true", help="Delete the smoke garden before running")
    parser.add_argument("--provider", choices=["fake", "openai", "deepseek"], default="fake")
    parser.add_argument("--embedding-provider", choices=["none", "fake", "openai"], default="fake")
    parser.add_argument("--rerank", action="store_true")
    parser.add_argument("--api-key", help="Provider API key. Prefer environment variables to avoid shell history leaks.")
    parser.add_argument("--base-url")
    parser.add_argument("--llm-model")
    parser.add_argument(
        "--embedding-api-key",
        help="Embedding API key. Prefer environment variables to avoid shell history leaks.",
    )
    parser.add_argument("--embedding-base-url")
    parser.add_argument("--embedding-model")
    parser.add_argument("--allow-sensitive-text", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=32)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--text")
    parser.add_argument("--query")
    return parser


if __name__ == "__main__":
    sys.exit(main())
