"""Schema management for the SQLite repository."""

from __future__ import annotations

import sqlite3


def initialize_schema(conn: sqlite3.Connection) -> None:
    """Create repository tables and indexes if they do not already exist."""

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
        CREATE INDEX IF NOT EXISTS idx_seeds_status ON seeds(status);

        CREATE TABLE IF NOT EXISTS memory_cards (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            sensitivity TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memory_cards_lifecycle ON memory_cards(lifecycle);

        CREATE TABLE IF NOT EXISTS court_cases (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            seed_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_court_cases_seed ON court_cases(seed_id);

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
        CREATE INDEX IF NOT EXISTS idx_compost_seed ON compost_records(source_seed_id);
        CREATE INDEX IF NOT EXISTS idx_compost_memory ON compost_records(source_memory_id);

        CREATE TABLE IF NOT EXISTS greenhouse_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            sensitivity_level TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_greenhouse_memory ON greenhouse_records(memory_id);

        CREATE TABLE IF NOT EXISTS pruning_records (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            memory_id TEXT NOT NULL,
            old_lifecycle TEXT NOT NULL,
            new_lifecycle TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pruning_memory ON pruning_records(memory_id);

        CREATE TABLE IF NOT EXISTS garden_events (
            id TEXT PRIMARY KEY NOT NULL,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_garden_events_type ON garden_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_garden_events_obj ON garden_events(object_type, object_id);
        """
    )
    conn.commit()
