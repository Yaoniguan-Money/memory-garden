# How Tests Are Organized

## Directory Layout

```
tests/
├── __init__.py
├── test_models.py                    # Core Pydantic models
├── test_core_flow.py                 # MemoryGardenCore facade
├── test_seed_lifecycle.py            # Seed observation and lifecycle
├── test_court_case.py                # Court engine and verdicts
├── test_dream_cycle.py               # Dream cycle engine
├── test_compost.py                   # Compost growth action
├── test_greenhouse.py                # Greenhouse isolation
├── test_pruning.py                   # Pruning growth action
├── test_journal.py                   # Garden journal
├── test_repository_interface.py      # Abstract repository contract
├── test_sqlite_repository.py         # SQLite implementation
├── test_runtime_*.py                 # Runtime layer (8 files)
├── test_before_reply.py              # before_reply hooks
├── test_after_reply.py               # after_reply hooks
├── test_command_not_memorized.py     # Command short-circuit
├── test_garden_tick.py               # Tick triggers
├── test_harvest_*.py                 # Harvest layer (7 files)
├── test_observatory_*.py             # Observatory layer (4 files)
├── test_garden_observer.py           # Observer facade
├── test_integration_*.py             # Integration layer (4 files)
├── test_lab_*.py                     # Lab layer (9 files)
├── test_covenant_*.py               # Covenant layer (5 files)
├── test_policy_engine.py             # Policy engine
└── test_manual_nursery_structure.py  # Layer 9 structural checks
```

## Naming Convention

- `test_<module>.py` — tests for `memory_garden/<package>/<module>.py`
- `test_<layer>_<component>.py` — tests for a specific component within a layer

## Test Style

- Tests use plain `assert` statements, not unittest.TestCase.
- Fixtures are defined per-file, not in conftest.py.
- Tests do not call real LLMs, network services, or external APIs.
- Tests that need a database use `:memory:` SQLite by default.
- Temporary file tests use `tmp_path` from pytest.
