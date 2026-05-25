# How to Add a Lab Case

Lab cases are snapshot-based regression checks. This guide shows how to add one.

## 1. Understand the Structure

A LabCase needs:
- `case_id` — unique identifier
- `name` — human-readable name
- `description` — what behavior this case checks
- `assertions` — list of `LabAssertion` objects
- `metadata` — optional, can include `lab_fixture_example_actual` snapshot

## 2. Write the Case

```python
from memory_garden.lab.models import (
    LabCase,
    LabAssertion,
    LabAssertionType,
    LabTarget,
)

my_case = LabCase(
    case_id="my_custom_check_001",
    name="Custom: user preference creates pending seed",
    description="Verify that a preference-like user message creates a seed with pending status",
    assertions=[
        LabAssertion(
            assertion_type=LabAssertionType.equals,
            target=LabTarget.seed,
            field_path="status",
            expected_value="pending",
        ),
        LabAssertion(
            assertion_type=LabAssertionType.equals,
            target=LabTarget.seed,
            field_path="signal_type",
            expected_value="preference",
        ),
    ],
    metadata={
        "lab_fixture_example_actual": {
            "seed": {
                "status": "pending",
                "signal_type": "preference",
                "tags": ["ui", "dark_mode"],
            }
        }
    },
)
```

## 3. Register in a Suite

```python
from memory_garden.lab.models import LabSuite

my_suite = LabSuite(
    suite_id="my_custom_suite",
    name="My Custom Checks",
    cases=[my_case],
)
```

## 4. Run It

```python
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.report import format_lab_run_report

runner = SnapshotLabRunner()
run = runner.run_suite(my_suite, actual_data_by_case_id={})
print(format_lab_run_report(run))
```

## Available Assertion Types

| Type | What it checks |
|---|---|
| `equals` | field value equals expected |
| `not_equals` | field value does not equal expected |
| `contains` | field value contains substring |
| `not_contains` | field value does not contain substring |
| `is_true` | field value is truthy |
| `is_false` | field value is falsy |
| `count_equals` | list field length equals expected |
| `count_at_most` | list field length does not exceed expected |
| `field_present` | field exists in the snapshot |
| `field_absent` | field does not exist in the snapshot |

## Available Targets

The `target` field selects which sub-domain the assertion applies to: `seed`, `court`, `growth`, `dream`, `harvest`, `runtime`, `observatory`.
