# How to Control Brief Injection

The Garden Brief contains harvested memories relevant to the current turn. How it reaches your agent is controlled by `BriefInjectionMode`.

## Modes

| Mode | Behavior |
|---|---|
| `none` | Brief is computed but not passed to the agent. Useful for logging-only setups. |
| `context_argument` | Brief text is passed as the `extra_context` string argument. |
| `system_prefix` | Brief is prefixed with a system-role marker and passed via `extra_context`. |
| `developer_message` | Similar to `system_prefix` but marked as a developer-level message. |
| `metadata` | Only brief metadata (length, source IDs) is passed; no full text. |

## Choosing a Mode

```python
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig

# Default: brief goes into extra_context
config = GardenAdapterConfig(
    brief_injection_mode=BriefInjectionMode.context_argument,
)

# Brief is computed but your agent never sees it
config = GardenAdapterConfig(
    brief_injection_mode=BriefInjectionMode.none,
)

# Only pass metadata (safer for untrusted model contexts)
config = GardenAdapterConfig(
    brief_injection_mode=BriefInjectionMode.metadata,
)
```

## In Your Agent

```python
class MyAgent:
    def generate_assistant_reply(self, *, user_message, session_id, extra_context=None):
        if extra_context:
            # extra_context contains the Garden Brief text (or metadata JSON)
            system_prompt = f"Relevant context from memory:\n{extra_context}"
        else:
            system_prompt = "No relevant memories found."
        # ... use system_prompt in your model call
```

## Security Note

When integrating with an external LLM, prefer `metadata` or carefully review what the brief contains. The brief may include memory excerpts that the Covenant's visibility rules would restrict in certain contexts.
