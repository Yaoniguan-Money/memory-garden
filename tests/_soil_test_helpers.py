"""Shared test helpers for Soil FTS index and search tests."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DB_FILENAME = "garden.db"


def setup_garden_db(garden_home: str | Path) -> str:
    """Create the garden SQLite schema at *garden_home* and return the db path."""
    db_path = os.path.join(str(garden_home), DB_FILENAME)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS seeds (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_cards (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            sensitivity TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS court_cases (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            seed_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dream_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compost_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            source_seed_id TEXT,
            source_memory_id TEXT,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS greenhouse_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            sensitivity_level TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pruning_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            old_lifecycle TEXT NOT NULL,
            new_lifecycle TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS garden_events (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()
    return db_path


def insert_test_data(
    garden_home: str | Path,
    *,
    num_memories: int = 0,
    num_seeds: int = 0,
    num_court_cases: int = 0,
    num_dream_records: int = 0,
    start_id_offset: int = 0,
) -> None:
    """Insert synthetic test rows into the garden database."""
    db_path = os.path.join(str(garden_home), DB_FILENAME)
    conn = sqlite3.connect(db_path)

    for i in range(num_memories):
        idx = start_id_offset + i + 1
        mid = f"mem-{idx:04d}"
        payload = json.dumps({
            "id": mid,
            "title": f"Test Memory {idx}: user prefers dark mode",
            "essence": f"The user has expressed a preference for dark mode interfaces across all applications. This is memory card {idx}.",
            "memory_type": "preference",
            "lifecycle": "bloom",
            "tags": ["ui", "dark_mode", "preference"],
            "fragrance": "User feels comfortable with dark interfaces",
            "thorns": "none",
            "roots": [],
            "branches": [],
            "confidence": 0.8,
            "importance": 0.6,
            "sensitivity": "low",
            "source_seed_ids": [],
            "court_case_ids": [],
            "dream_record_ids": [],
            "created_at": f"2025-01-{idx:02d}T00:00:00Z",
            "updated_at": f"2025-01-{idx:02d}T00:00:00Z",
            "last_used_at": f"2025-01-{idx:02d}T00:00:00Z",
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO memory_cards (id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mid, f"2025-01-{idx:02d}T00:00:00Z", "bloom", "preference", "low",
             f"2025-01-{idx:02d}T00:00:00Z", payload),
        )

    for i in range(num_seeds):
        idx = start_id_offset + i + 1
        sid = f"seed-{idx:04d}"
        payload = json.dumps({
            "id": sid,
            "content": f"Test seed {idx}: user mentioned they like working in the morning",
            "tags": ["schedule", "preference"],
            "signal_type": "preference",
            "status": "pending",
            "created_at": f"2025-02-{idx:02d}T00:00:00Z",
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO seeds (id, created_at, status, signal_type, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (sid, f"2025-02-{idx:02d}T00:00:00Z", "pending", "preference", payload),
        )

    for i in range(num_court_cases):
        idx = start_id_offset + i + 1
        cid = f"case-{idx:04d}"
        payload = json.dumps({
            "id": cid,
            "seed_id": f"seed-{idx:04d}",
            "prosecutor_argument": f"Prosecutor argument: This seed {idx} contains a short-term emotional statement.",
            "defender_argument": f"Defender argument: This seed {idx} reflects a recurring pattern.",
            "privacy_guard_argument": "Privacy guard: no sensitive information detected.",
            "judge_verdict": {"verdict": "plant", "reason": f"Seed {idx} is a valid preference."},
            "created_at": f"2025-03-{idx:02d}T00:00:00Z",
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO court_cases (id, created_at, seed_id, verdict, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (cid, f"2025-03-{idx:02d}T00:00:00Z", f"seed-{idx:04d}", "plant", payload),
        )

    for i in range(num_dream_records):
        idx = start_id_offset + i + 1
        did = f"dream-{idx:04d}"
        payload = json.dumps({
            "id": did,
            "observation": f"Dream observation {idx}: noticed patterns of morning productivity.",
            "reflection": f"Dream reflection {idx}: the garden reveals consistent preferences.",
            "transformation": f"Dream transformation {idx}: merged similar seeds about scheduling.",
            "morning_garden": "Garden status unchanged.",
            "created_at": f"2025-04-{idx:02d}T00:00:00Z",
        }, ensure_ascii=False)
        conn.execute(
            "INSERT INTO dream_records (id, created_at, payload) VALUES (?, ?, ?)",
            (did, f"2025-04-{idx:02d}T00:00:00Z", payload),
        )

    conn.commit()
    conn.close()
