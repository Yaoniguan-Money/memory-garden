# How to Run the Test Suite

## Full Suite

```bash
python -m pytest tests -q
```

As of v1.1.1, this runs 1071 tests.

## By Layer

```bash
# Layer 1: Core
python -m pytest tests/test_models.py tests/test_core_flow.py tests/test_seed_lifecycle.py tests/test_court_case.py tests/test_dream_cycle.py tests/test_compost.py tests/test_greenhouse.py tests/test_pruning.py tests/test_journal.py tests/test_repository_interface.py tests/test_sqlite_repository.py -q

# Layer 2: Runtime
python -m pytest tests/test_runtime_*.py tests/test_before_reply.py tests/test_after_reply.py tests/test_command_not_memorized.py tests/test_garden_tick.py -q

# Layer 3: Harvest
python -m pytest tests/test_harvest_*.py -q

# Layer 4: Observatory
python -m pytest tests/test_observatory_*.py tests/test_garden_observer.py -q

# Layer 5: Integration
python -m pytest tests/test_integration_*.py -q

# Layer 6-7: Lab
python -m pytest tests/test_lab_*.py -q

# Layer 8: Covenant
python -m pytest tests/test_covenant_*.py tests/test_policy_engine.py -q

# Layer 9: Manual & Nursery
python -m pytest tests/test_manual_nursery_structure.py -q
```

## With Verbose Output

```bash
python -m pytest tests -v
```

## Single Test File

```bash
python -m pytest tests/test_lab_runner.py -q
```

## Requirements

Tests require `pytest>=7.0` (installed via `pip install -e ".[dev]"`). No other test dependencies are needed.
