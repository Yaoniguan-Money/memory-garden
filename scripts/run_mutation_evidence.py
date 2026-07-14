"""Run a small, explicit mutation audit over the Hard Forget critical path."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    relative_path: str
    original: str
    replacement: str
    risk: str


MUTATIONS = [
    Mutation(
        "forget-proof-boolean-or",
        "memory_garden/soil/forget_proof.py",
        "proven=(failed == 0 and passed > 0)",
        "proven=(failed == 0 or passed > 0)",
        "A proof with a failed surface could be marked proven.",
    ),
    Mutation(
        "product-cleanup-inverted-status",
        "memory_garden/product/services/forget.py",
        'if result.status == "ok":',
        'if result.status != "ok":',
        "Product cache and relation cleanup would be skipped after a successful hard delete.",
    ),
    Mutation(
        "retrieval-event-purge-disabled",
        "memory_garden/product/services/forget.py",
        "purged = self.store.purge_retrieval_events_for_memory(plan.memory_id)",
        "purged = 0",
        "Retrieval events would retain the forgotten memory id.",
    ),
    Mutation(
        "proof-query-redaction-disabled",
        "memory_garden/product/services/forget.py",
        'evidence.pop("queries", None)',
        'evidence.get("queries", None)',
        "Plaintext content probes could remain in persisted proof metadata.",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "evidence" / "raw" / "mutation_runs.json"))
    args = parser.parse_args()
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_forget_proof.py",
        "tests/test_forget_content_proof.py",
        "tests/test_product_memory_system.py",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    results = []

    for mutation in MUTATIONS:
        path = ROOT / mutation.relative_path
        original_bytes = path.read_bytes()
        before_hash = hashlib.sha256(original_bytes).hexdigest()
        text = original_bytes.decode("utf-8")
        count = text.count(mutation.original)
        if count != 1:
            raise RuntimeError(f"{mutation.mutation_id}: expected one target, found {count}")
        path.write_text(text.replace(mutation.original, mutation.replacement, 1), encoding="utf-8")
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            results.append(
                {
                    "mutation_id": mutation.mutation_id,
                    "file": mutation.relative_path,
                    "risk": mutation.risk,
                    "killed": completed.returncode != 0,
                    "pytest_returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
        finally:
            path.write_bytes(original_bytes)
        if _sha256(path) != before_hash:
            raise RuntimeError(f"{mutation.mutation_id}: source restoration hash mismatch")

    killed = sum(row["killed"] for row in results)
    payload = {
        "schema_version": 1,
        "scope": ["Hard Forget verdict", "product cleanup", "retrieval-event purge", "proof redaction"],
        "test_command": command,
        "summary": {
            "total_mutants": len(results),
            "killed_mutants": killed,
            "survived_mutants": len(results) - killed,
            "mutation_score": killed / len(results),
        },
        "mutants": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
