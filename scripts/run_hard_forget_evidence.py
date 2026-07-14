"""Exercise hard-forget proof, retrieval, cache, and source-trace surfaces."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory_garden.product import ProductMemorySystem
from memory_garden.providers import FakeEmbeddingProvider, ProviderPolicy, ProviderRegistry
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.search import search_garden
from memory_garden.storage.base import NotFoundError


CONFIG_PATH = ROOT / "evidence" / "config" / "hard_forget_experiment.json"


def _event_mentions(store_path: str, memory_id: str) -> bool:
    conn = sqlite3.connect(store_path)
    try:
        rows = conn.execute("SELECT payload FROM memory_retrieval_events").fetchall()
        return any(memory_id in json.loads(row[0]).get("memory_ids", []) for row in rows)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "evidence" / "raw" / "hard_forget_runs.json"))
    parser.add_argument("--failures", default=str(ROOT / "evidence" / "failures" / "hard_forget_failures.jsonl"))
    args = parser.parse_args()
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    rows = []

    with tempfile.TemporaryDirectory(prefix="memory-garden-forget-") as temp_root:
        for seed in config["seeds"]:
            garden = MemoryGarden.local(Path(temp_root) / str(seed))
            product = ProductMemorySystem(
                garden_home=garden.home.root,
                repository=garden.core.repository,
                providers=ProviderRegistry(
                    policy=ProviderPolicy(allow_raw_user_text=True),
                    embedding=FakeEmbeddingProvider(),
                ),
            )
            try:
                cases = []
                for index in range(config["cases_per_seed"]):
                    marker = f"hard-forget-{seed}-{index:02d}-quartz"
                    result = product.remember(f"remember: unique private marker {marker}", mode="trusted")
                    memory_id = result["approved_memory_ids"][0]
                    card = garden.core.repository.get_memory_card(memory_id)
                    inspection = product.inspect_memory(memory_id)
                    cases.append((marker, memory_id, card, inspection))

                product.warm_embedding_cache()
                for marker, memory_id, card, inspection in cases:
                    before_hits = product.retrieve(marker, limit=5, mutate=True)
                    cache_before = product.store.get_memory_embedding(
                        memory_id=memory_id,
                        model="fake-local-embedding",
                    )
                    event_before = _event_mentions(str(product.store.path), memory_id)
                    plan = product.plan_forget(memory_id=memory_id)
                    executed, proof = product.execute_forget(plan.id)

                    db_absent = False
                    try:
                        garden.core.repository.get_memory_card(memory_id)
                    except NotFoundError:
                        db_absent = True
                    fts_absent = memory_id not in {
                        hit.target_id for hit in search_garden(garden.home.root, marker, limit=20)
                    }
                    product_absent = memory_id not in {
                        hit.memory.id for hit in product.retrieve(marker, limit=20, mutate=False).hits
                    }
                    cache_absent = product.store.get_memory_embedding(
                        memory_id=memory_id,
                        model="fake-local-embedding",
                    ) is None
                    event_absent = not _event_mentions(str(product.store.path), memory_id)
                    source_trace_before = bool(card.source_seed_ids) and bool(inspection.proposals)
                    checks = {
                        "source_trace_before": source_trace_before,
                        "retrievable_before": memory_id in {hit.memory.id for hit in before_hits.hits},
                        "cache_before": cache_before is not None,
                        "event_before": event_before,
                        "plan_affected": bool(plan.affected),
                        "executed": executed.status == "executed",
                        "proof_proven": proof.proven,
                        "content_level": proof.proof_level == "content",
                        "content_probe_fingerprint": bool(proof.content_probe_fingerprint),
                        "db_absent": db_absent,
                        "fts_absent": fts_absent,
                        "product_absent": product_absent,
                        "cache_absent": cache_absent,
                        "event_absent": event_absent,
                    }
                    rows.append(
                        {
                            "seed": seed,
                            "case_index": len(rows) % config["cases_per_seed"],
                            "memory_id": memory_id,
                            "marker_sha256": __import__("hashlib").sha256(marker.encode()).hexdigest(),
                            "source_seed_count": len(card.source_seed_ids),
                            "proof_checks": proof.checks,
                            "checks": checks,
                            "passed": all(checks.values()),
                        }
                    )
            finally:
                garden.close()

    payload = {
        "schema_version": 1,
        "config": config,
        "summary": {
            "total_cases": len(rows),
            "passed_cases": sum(row["passed"] for row in rows),
            "failed_cases": sum(not row["passed"] for row in rows),
            "pass_rate": sum(row["passed"] for row in rows) / len(rows) if rows else 0.0,
        },
        "cases": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = [row for row in rows if not row["passed"]]
    failure_path = Path(args.failures)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    failure_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in failures),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
