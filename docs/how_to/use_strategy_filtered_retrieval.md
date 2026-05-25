# Use Strategy-Filtered Retrieval

Memory Garden has two retrieval surfaces:

- `memory-garden search`: FTS5 keyword search over the local index.
- `MemoryGarden.retrieve()` / `MemoryGarden.build_brief()`: product retrieval through strategy profiles.

Both are local-first.  They do not call LLMs, embedding providers, or network
services unless the host application explicitly configures providers elsewhere.

## CLI Search With Scope

Unscoped search keeps the original FTS5 behavior:

```bash
memory-garden search "release notes" --path ./my_garden
```

Scoped search first recalls with FTS5, then filters memory-card hits through
saved product strategy profiles:

```bash
memory-garden search "release notes" --path ./my_garden --project atlas
memory-garden search "release notes" --path ./my_garden --workspace zephyr
memory-garden search "release notes" --path ./my_garden --scope project --project atlas
```

`--project` includes global-user memories and project memories whose
`scope_id` matches the project.  `--workspace` does the same for workspace
scope.  Passing `--scope` narrows results to that exact scope.

The base `search_garden()` API is unchanged.  Python callers that need scoped
FTS search can call:

```python
from memory_garden.soil import search_garden_scoped

hits = search_garden_scoped(
    "./my_garden",
    "release notes",
    project_id="atlas",
    limit=5,
)
```

## SDK Strategy Retrieval

`MemoryGarden.chat()` still uses the existing synchronous chat adapter path.
For strategy-aware retrieval, use the new high-level APIs:

```python
from memory_garden.sdk import MemoryGarden

garden = MemoryGarden.local(
    "./my_garden",
    strategy_context={"scope": "project", "project_id": "atlas"},
)

result = garden.retrieve("release notes", limit=5)
brief = garden.build_brief("release notes", limit=5)
```

`retrieve()` returns product retrieval hits with applicability reasons.
`build_brief()` returns a source-id-preserving `GardenBrief` that can be
injected into a host LLM call.

## Calibrate Strategy Weights

The calibration script is standalone and does not import Memory Garden:

```bash
python scripts/calibrate_weights.py
```

Replace the script's `GROUND_TRUTH` and `MEMORIES` constants with labeled
examples from your application.  The script prints the best grid-search weights
and the resulting `NDCG@3`.  It does not modify `strategy.py`.
