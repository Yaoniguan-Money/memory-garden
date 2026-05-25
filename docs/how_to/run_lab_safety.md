# How to Run Lab Safety Tests

Safety tests verify the Memory Garden safety contracts: greenhouse isolation, hard forget, content rejection, and redaction.

## In Python

```python
from memory_garden.lab.suite_packs import safety_pack
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.report import format_lab_run_report

suites = safety_pack(default_lab_suites())
run = SnapshotLabRunner().run_suites(suites, {})
print(format_lab_run_report(run))
```

## What Safety Covers

- Court: negative self-descriptions are not promoted to identity
- Court: sensitive content is greenhouse-routed
- Harvest: brief does not embed full memory card bodies
- Observatory: PUBLIC views do not expose full user/assistant text

## In CI

Run safety checks on every PR:

```bash
python -c "
from memory_garden.lab.suite_packs import safety_pack
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.report import format_lab_run_report
import sys

suites = safety_pack(default_lab_suites())
run = SnapshotLabRunner().run_suites(suites, {})
print(format_lab_run_report(run))
sys.exit(0 if run.status.value == 'passed' else 1)
"
```

## Adding New Safety Cases

See [Add a Lab Case](add_lab_case.md).
