# How to Run a Policy Audit

The Garden Covenant provides in-memory audit helpers to check policy decisions.

## Audit a Single Decision

```python
from memory_garden.covenant.engine import PolicyEngine
from memory_garden.covenant.defaults import default_covenant

engine = PolicyEngine(covenant=default_covenant())

decision = engine.check_harvest_visibility(
    memory_card=some_card,
    target="external_model",
)

print(f"Allowed: {decision.allowed}")
print(f"Reason: {decision.reason}")
print(f"Severity: {decision.severity}")
```

## Batch Audit

```python
from memory_garden.covenant.audit import audit_decisions

decisions = [
    engine.check_sensitive_content(some_text),
    engine.check_model_call_scope(requested_scope="full_garden"),
    engine.check_export_eligibility(memory_cards),
]

report = audit_decisions(decisions)
print(f"Total: {report.total}")
print(f"Blocked: {report.blocked}")
print(f"Allowed: {report.allowed}")
print(f"Warnings: {report.warnings}")
```

## Stable Covenant Hash

Track policy changes with a stable hash:

```python
from memory_garden.covenant.audit import covenant_hash

h1 = covenant_hash(default_covenant())
# ... change some policy ...
h2 = covenant_hash(modified_covenant)
assert h1 != h2  # Hash changed → policy changed
```

This is useful in CI to detect unexpected policy drift.
