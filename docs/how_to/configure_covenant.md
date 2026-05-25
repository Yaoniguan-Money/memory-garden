# How to Configure the Covenant

The Garden Covenant is the memory policy layer. You can customize it through a YAML file, a Python dict, or environment variables.

## Default Covenant

If you don't configure anything, Memory Garden uses a local-first default covenant. This default is safe for development and single-user use.

## From a YAML File

Create `garden_covenant.yaml`:

```yaml
covenant_version: "1.0"
consent:
  require_explicit_consent: true
  default_consent_scope: "session"
admission:
  allow_negative_self_descriptions_as_identity: false
  allow_third_party_claims_without_corroboration: false
emotional_safety:
  reject_harm_self_content: true
  reject_hate_speech: true
sensitive_memory:
  auto_greenhouse_sensitive: true
  sensitive_categories:
    - health
    - financial
    - credentials
model_calls:
  allow_full_garden_export: false
  max_memories_per_model_call: 20
harvest:
  never_harvest_greenhouse_for_external_model: true
  never_harvest_pruned: true
visibility:
  default_redaction_level: "SAFE"
portability:
  allow_export: false
  export_requires_audit_log: true
```

Load it:

```python
from memory_garden.covenant.loader import load_covenant

covenant = load_covenant(source="garden_covenant.yaml")
```

## From a Dict

```python
from memory_garden.covenant.loader import load_covenant

covenant = load_covenant(source={
    "covenant_version": "1.0",
    "consent": {"require_explicit_consent": True},
    "sensitive_memory": {"auto_greenhouse_sensitive": True},
})
```

## From Environment Variables

```python
import os
from memory_garden.covenant.loader import load_covenant

os.environ["GARDEN_COVENANT_PATH"] = "garden_covenant.yaml"
covenant = load_covenant(source="env")
```

## Validate

The loader validates your covenant automatically. Hard baselines cannot be disabled:

```python
# This would raise CovenantValidationError:
bad_covenant = load_covenant(source={
    "covenant_version": "1.0",
    "hard_baselines": {"hard_forgotten_text_never_visible": False},
})
```

## Use with the Policy Engine

```python
from memory_garden.covenant.engine import PolicyEngine

engine = PolicyEngine(covenant=covenant)
decision = engine.check_harvest_visibility(
    memory_card=some_card,
    target="external_model",
)
print(decision.allowed, decision.reason)
```
