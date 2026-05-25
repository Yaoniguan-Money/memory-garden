# How to Run Lab Smoke Tests

Smoke tests are a fast subset of Lab cases that verify basic integrity before a commit.

## In Python

```python
from memory_garden.lab.suite_packs import smoke_pack
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.report import format_lab_run_report

suites = smoke_pack(default_lab_suites())
runner = SnapshotLabRunner()
run = runner.run_suites(suites, actual_data_by_case_id={})
print(format_lab_run_report(run))
assert run.status.value == "passed"
```

## In CI

Add to your CI script:

```bash
python -c "
from memory_garden.lab.suite_packs import smoke_pack
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.report import format_lab_run_report
import sys

suites = smoke_pack(default_lab_suites())
run = SnapshotLabRunner().run_suites(suites, {})
print(format_lab_run_report(run))
sys.exit(0 if run.status.value == 'passed' else 1)
"
```

## What Smoke Covers

The smoke pack selects a small subset of cases covering:
- Runtime command short-circuit
- Harvest brief constraints
- Observatory redaction

It runs in under 100ms and is suitable for pre-commit hooks.
