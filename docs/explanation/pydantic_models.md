# Why Pydantic Models?

All Memory Garden domain objects are Pydantic models. This is the project's only hard runtime dependency.

## Rationale

### Validation at Construction

Pydantic validates field types, constraints, and defaults when an object is created. A `Seed` with a missing required field fails immediately, not three layers later when something tries to read it.

### JSON Serialization Built In

Every object can be round-tripped through JSON. This is critical for:

- **SQLite storage**: Objects are serialized to JSON for the payload column.
- **Testing**: Expected values in assertions are JSON-compatible dicts.
- **Observatory**: Traces and views are JSON-serializable by construction.

### Schema as Code

The model definitions serve as documentation. Reading `memory_garden/core/models.py` shows you every field, type, and default in the Seed and MemoryCard schemas. No separate schema file to keep in sync.

### No ORM Required

With JSON columns in SQLite, there is no object-relational mapping to maintain. Pydantic handles object ↔ dict; the repository handles dict ↔ SQLite row. This keeps the dependency tree small and the mapping layer explicit.

## Cost

- **Larger on-disk footprint**: JSON columns are less compact than normalized tables.
- **No relational queries on fields**: `json_extract` works but is not as efficient as indexed columns.
- **Pydantic v2 migration**: The `>=2.0,<3` constraint means staying current with a rapidly evolving library.

For the scale Memory Garden targets (hundreds to low thousands of records), these costs are acceptable.
