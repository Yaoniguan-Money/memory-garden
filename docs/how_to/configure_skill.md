# Configure Memory Garden Skill

`SkillConfig` controls the Skill layer without changing Core rules.

```python
from memory_garden.skill import SkillConfig

skill = garden.as_skill(SkillConfig(
    enable_harvest_brief=True,
    enable_dream=False,
    enable_court_shadow=False,
    enable_cognitive_harvest=False,
    provider_mode="disabled",
    default_write_mode="court",
    redaction_level="basic",
))
```

## Defaults

| Field | Default | Meaning |
|---|---:|---|
| `provider_mode` | `disabled` | No network provider is loaded |
| `default_write_mode` | `court` | Writes go through RuleCourt |
| `enable_cognitive_harvest` | `false` | No semantic provider path by default |
| `enable_court_shadow` | `false` | No advisor provider by default |
| `enable_dream` | `false` | No Skill-level automatic Dream by default |
| `allow_hard_forget` | `true` | Skill forget can call Soil hard forget |

## Provider Modes

- `disabled`: product default, no external calls.
- `fake`: deterministic local test providers only.
- `custom`: caller-injected providers only.

The Skill layer does not read API keys from the environment and does not import
vendor SDKs by default.

## Write Modes

- `court`: observe text, open RuleCourt, then apply safe rule verdicts.
- `preview`: observe text and open RuleCourt, but skip Growth mutation.

Use preview mode for dry-run UX, tests, and review tools.
