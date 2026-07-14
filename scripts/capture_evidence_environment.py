"""Capture the minimal runtime and package versions needed to reproduce evidence."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = [
    "coverage",
    "jieba",
    "pydantic",
    "pytest",
    "pytest-cov",
    "sentence-transformers",
    "torch",
    "transformers",
]


def version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main() -> None:
    payload = {
        "schema_version": 1,
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "sqlite": sqlite3.sqlite_version,
        "packages": {name: version(name) for name in PACKAGES},
        "environment_flags": {
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "repository_vcs": "No .git metadata present in the supplied project directory.",
    }
    output = ROOT / "evidence" / "raw" / "environment.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
