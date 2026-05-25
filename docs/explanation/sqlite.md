# Why SQLite?

Memory Garden uses SQLite as its only storage backend. No PostgreSQL, no MySQL, no cloud database.

## Rationale

### Zero Setup

SQLite is bundled with Python's standard library. There is nothing to install, configure, or start. The test suite runs without any external processes.

### Single-File Storage

The entire garden lives in one file. Backup is `cp garden.db garden.db.bak`. Inspection is `sqlite3 garden.db`. No connection strings, no port numbers, no authentication.

### Adequate for Single-User Workloads

A single user's memory garden typically holds hundreds to low thousands of memory cards. SQLite handles this comfortably. Write contention is not a concern because there is one writer (the agent's process).

### JSON-in-Relational

Each entity (Seed, MemoryCard, CourtCase) is stored as a row with a JSON payload column. This gives:

- **Schema flexibility**: Add fields to Pydantic models without migrations.
- **Query simplicity**: `SELECT payload FROM memory_cards WHERE json_extract(payload, '$.lifecycle') = 'active'`
- **Round-trip integrity**: Pydantic validates on save and load.

## When to Replace SQLite

If you need:

- **Multi-process concurrent writes**: SQLite's single-writer model becomes a bottleneck.
- **Horizontal scaling**: SQLite does not shard.
- **Multi-region replication**: Not built in.

In these cases, the `GardenRepository` abstract interface allows swapping in a different backend without changing the domain logic.
