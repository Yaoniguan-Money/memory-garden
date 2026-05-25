# Storage and Health

Memory Garden stores data locally.

## Files

A local garden home contains:

- `manifest.json`: garden metadata.
- `garden.db`: SQLite database.

Use `MemoryGarden.local(path)` to initialize the home explicitly. Imports should
not create a garden by themselves.

## SQLite Strategy

The repository stores one domain entity per table:

- `seeds`
- `memory_cards`
- `court_cases`
- `dream_records`
- `compost_records`
- `greenhouse_records`
- `pruning_records`
- `garden_events`

Rows include indexed columns plus a full JSON `payload` round-tripped through
Pydantic models. Do not bypass the repository for normal writes.

The product layer adds workflow tables in the same `garden.db`:

- `memory_proposals`: review inbox, approval/rejection state, conflicts, and
  created memory ids.
- `memory_versions`: immutable snapshots before edits, merges, archives, and
  restores.
- `memory_relations`: duplicate, contradiction, merge, derivation, and support
  links.
- `provider_calls`: audit metadata for caller-owned LLM, embedding, and
  reranker usage.
- `memory_retrieval_events`: query-time hit ids and provider use.
- `memory_strategy_profiles`: layer, scope, maturity, strength, evidence/use
  counters, and strategy metadata for each memory.
- `memory_conflict_arbitrations`: explicit conflict decisions and review
  records.
- `memory_evolution_plans`: reinforcement, promotion, decay, abstraction, and
  archive plans.
- `forget_plans`: dry auditable plan records for destructive forget.
- `forget_proofs`: saved proof checks after hard forget.

Each table stores structured columns for queryability plus a JSON payload
validated by product Pydantic models.

## Search Index

`garden_fts_index` is a SQLite FTS5 index derived from source tables. It is not
the source of truth. Use reindexing or health checks when search looks stale.

## Health Checks

Use:

```python
report = skill.health
```

The health report checks manifest validity and FTS status when a database is
present. Health checks are read-only; they do not repair or mutate data.

Product hard forget executes the Soil cascade delete, then attempts a local
reindex and persists proof checks. The proof verifies that the memory is absent
from the primary table and derived search/index surfaces.

## Backups

The default product does not perform automatic backup or sync. If the user asks
about persistence guarantees, be clear that they are responsible for backing up
the local garden home.
