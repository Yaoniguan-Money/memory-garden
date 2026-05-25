# Examples (Nursery)

This directory contains runnable examples that demonstrate Memory Garden integration patterns. Each example is self-contained and uses only local resources.

## Running Examples

All examples are run from the repository root:

```bash
python examples/<example_name>.py
```

## Available Examples

### sync_chat_agent.py

Minimal synchronous chat adapter demonstration. Uses `RuleBasedDemoAgent` (no external LLM) to show the full garden cycle: open session, chat with observation, and close with feedback.

```bash
python examples/sync_chat_agent.py
```

Expected output: 3 lines showing session open, chat turn, and session close with brief/feedback indicators.

### agent_brief_injection_demo.py

Side-by-side **no-memory vs with-memory** agent demo. Seeds preferences via `GardenSkill.remember()`, generates a real Garden Brief through `skill.before()`, shows message injection diff, and runs a deterministic fake agent (no API keys, default temp directory).

```bash
python examples/agent_brief_injection_demo.py
```

Expected output: five labeled sections — USER QUERY, NO-MEMORY RESPONSE, GARDEN BRIEF, MESSAGE INJECTION, WITH-MEMORY RESPONSE.

See also: [`docs/how_to/agent_brief_injection_demo.md`](../docs/how_to/agent_brief_injection_demo.md)

### garden_covenant_default.yaml

A reference Covenant configuration file. Shows all policy knobs with their default values. Use as a starting point for custom policy configuration.

```bash
# This is a YAML file, not directly executable.
# Load it from Python:
python -c "
from memory_garden.covenant.loader import load_covenant
c = load_covenant(source='examples/garden_covenant_default.yaml')
print(f'Loaded covenant version {c.covenant_version}')
"
```

## Adding New Examples

When adding an example:

1. Include a module docstring explaining what it demonstrates.
2. Provide a `main()` function or `if __name__ == "__main__"` block.
3. Use only local resources (no API keys, no network calls).
4. Add a `README.md` if the example needs more than a few lines of explanation.
5. Document the expected output.

## What These Examples Are Not

- They do not connect to real LLM providers.
- They do not require API keys or network access.
- They do not create persistent files (all use `:memory:` stores by default).
- They are not production deployment templates.

They are learning tools for understanding Memory Garden's API surface and integration patterns.
