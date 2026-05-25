"""Smoke-test the Memory Garden Codex skill against the stable Python API."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if (REPO_ROOT / "memory_garden").is_dir():
    sys.path.insert(0, str(REPO_ROOT))


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


def _run(garden_home: Path) -> dict[str, Any]:
    from memory_garden.sdk import MemoryGarden

    garden = MemoryGarden.local(garden_home)
    try:
        skill = garden.as_skill()

        opened = skill.open_session()
        _assert(opened.ok and bool(opened.session_id), "open_session failed")

        remembered = skill.remember("请记住：我喜欢深色模式，以后界面相关回答请优先考虑这一点。")
        _assert(remembered.ok, "remember failed")
        _assert(remembered.verdicts, "remember produced no court verdicts")
        _assert(remembered.memory_ids, "remember produced no memory id")
        memory_id = remembered.memory_ids[0]

        harvested = skill.harvest("深色模式", limit=5)
        _assert(harvested.ok, "harvest failed")
        _assert(memory_id in harvested.source_memory_ids, "harvest did not return saved memory")

        dry_run = skill.forget("深色模式", memory_id=memory_id, reason="smoke test", dry_run=True)
        _assert(dry_run.preview, "forget dry_run did not report preview")
        _assert(memory_id in dry_run.memory_ids, "forget dry_run lost memory id")

        audit = skill.audit(limit=10)
        _assert(audit.memory_count >= 1, "audit did not see saved memory")
        _assert("provider_mode" in audit.config, "audit config missing provider_mode")

        deleted = skill.forget("深色模式", memory_id=memory_id, reason="smoke test", cascade=True)
        _assert(deleted.ok, "forget delete failed")

        harvested_after = skill.harvest("深色模式", limit=5)
        _assert(memory_id not in harvested_after.source_memory_ids, "forgotten memory still harvestable")

        health = skill.health
        _assert(hasattr(health, "status"), "health report missing status")

        closed = skill.close_session()
        _assert(closed.ok, "close_session failed")

        return {
            "ok": True,
            "garden_home": str(garden_home),
            "session_id": opened.session_id,
            "memory_id": memory_id,
            "health_status": getattr(health.status, "value", str(health.status)),
        }
    finally:
        garden.close()


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
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if temp_dir is not None and not args.keep:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
