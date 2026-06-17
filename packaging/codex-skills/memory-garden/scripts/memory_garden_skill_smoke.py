"""Smoke-test the Memory Garden Codex skill against the stable Python API."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

INSTALL_HINT = (
    "memory_garden is not importable. Install the package before running this "
    "external skill smoke check, for example: "
    "python -m pip install -e <path-to-memory-garden-repo> --no-deps"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--garden-home",
        type=Path,
        default=None,
        help="Garden home to use. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temporary garden home after the run.",
    )
    return parser.parse_args()


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _load_runtime() -> tuple[type[Any], Any]:
    try:
        from memory_garden.sdk import MemoryGarden
        from memory_garden.soil import reindex_garden
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("memory_garden"):
            raise RuntimeError(INSTALL_HINT) from exc
        raise
    return MemoryGarden, reindex_garden


def _run(garden_home: Path) -> dict[str, Any]:
    MemoryGarden, reindex_garden = _load_runtime()

    session_id = ""
    memory_id = ""
    garden = MemoryGarden.local(garden_home)
    try:
        skill = garden.as_skill()

        opened = skill.open_session()
        _assert(opened.ok and bool(opened.session_id), "open_session failed")
        session_id = opened.session_id or ""

        remembered = skill.remember_memory(
            "remember: prefer dark mode for interface examples",
            mode="trusted",
            metadata={"smoke": True},
        )
        memory_ids = remembered.get("approved_memory_ids") or []
        _assert(memory_ids, "remember_memory produced no approved memory id")
        memory_id = memory_ids[0]

        retrieval = skill.retrieve_memories("dark mode interface examples", limit=5)
        hit_ids = [hit.memory.id for hit in retrieval.hits]
        _assert(memory_id in hit_ids, "retrieve_memories did not return saved memory")

        brief = skill.build_memory_brief("dark mode interface examples", limit=5)
        _assert(memory_id in brief.source_memory_ids, "build_memory_brief lost source memory id")

        audit = skill.audit(limit=10)
        _assert(audit.memory_count >= 1, "audit did not see saved memory")
        _assert("provider_mode" in audit.config, "audit config missing provider_mode")

        plan = skill.plan_memory_forget(memory_id=memory_id)
        _assert(plan.memory_id == memory_id, "forget plan lost memory id")

        executed, proof = skill.execute_memory_forget(plan.id)
        _assert(executed.status == "executed", f"forget execution status is {executed.status}")
        _assert(proof.proven, "forget proof was not proven")

        retrieval_after = skill.retrieve_memories("dark mode interface examples", limit=5)
        after_ids = [hit.memory.id for hit in retrieval_after.hits]
        _assert(memory_id not in after_ids, "forgotten memory still retrievable")

        closed = skill.close_session()
        _assert(closed.ok, "close_session failed")
    finally:
        garden.close()

    reindex = reindex_garden(garden_home, dry_run=False)
    _assert(reindex.status == "ok", f"reindex failed: {reindex.status}")
    _assert(not reindex.issues, f"reindex reported issues: {reindex.issues}")

    health_garden = MemoryGarden.local(garden_home)
    try:
        health = health_garden.as_skill().health
    finally:
        health_garden.close()

    health_status = getattr(health.status, "value", str(health.status))
    _assert(health_status == "healthy", f"health status is {health_status}: {health.issues}")

    return {
        "ok": True,
        "garden_home": str(garden_home),
        "session_id": session_id,
        "memory_id": memory_id,
        "health_status": health_status,
        "indexed_count": reindex.indexed_count,
    }


def main() -> int:
    args = _parse_args()
    temp_dir: Path | None = None
    if args.garden_home is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="memory-garden-skill-"))
        garden_home = temp_dir / "garden"
    else:
        garden_home = args.garden_home

    try:
        result = _run(garden_home)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if temp_dir is not None and not args.keep:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
