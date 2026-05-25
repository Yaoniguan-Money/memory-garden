# Agent Brief Injection Demo

Demonstrates how Memory Garden helps an agent recover key context in multi-turn tasks.

## Run

From the repository root:

```bash
python examples/agent_brief_injection_demo.py
```

Optional persistent garden path (for inspection):

```bash
python examples/agent_brief_injection_demo.py --path /tmp/mg_brief_demo
```

Default behavior uses a **temporary directory** that is deleted when the script exits. No API keys or network access are required.

## What It Shows

The script runs the same user query twice:

1. **No-memory agent** — answers from the current query only (generic stack / cloud / metrics advice).
2. **With Memory Garden** — seeds preferences via `GardenSkill.remember()`, calls `GardenSkill.before()` to harvest a **Garden Brief**, injects it into OpenAI-style messages, and runs a deterministic fake agent that cites the brief + resolved memory excerpts.

### Demo scenario (seeded memories)

- Prefer **Python + TypeScript**
- **Local-first**, no cloud dependency
- Project name: **Memory Garden**
- Do **not invent benchmark numbers**

### Output sections

| Section | Meaning |
|---------|---------|
| `USER QUERY` | Fixed evaluation question |
| `NO-MEMORY RESPONSE` | Fake agent without brief |
| `GARDEN BRIEF` | Real `[use]/[avoid]/...` slots from `skill.before()` |
| `MESSAGE INJECTION` | `inject_into_messages()` before/after diff |
| `WITH-MEMORY RESPONSE` | Fake agent using brief + memory excerpts |

## Integration Path (Production)

This demo uses the **Skill layer**:

```python
from memory_garden.sdk import MemoryGarden

garden = MemoryGarden.local("./my_garden")
skill = garden.as_skill()
skill.open()

ctx = skill.before(user_message, messages=openai_messages)
# ctx.brief_text  → system prefix
# ctx.inject_into_messages(messages) → messages with brief

reply = your_llm(ctx, user_message)
skill.after(user_message, reply)
skill.close()
```

### Optional: OpenAI-compatible client

When using a real OpenAI-compatible API, pass injected messages:

```python
sys_msg = ctx.to_openai_system_message()
if sys_msg:
    messages = [sys_msg, *messages]
# client.chat.completions.create(model=..., messages=messages)
```

The default demo does **not** import or call any cloud provider.

## Notes

- `skill.before()` internally calls `MemoryGarden.chat()` once to run `before_reply` harvest; the demo sets a silent host agent so that internal turn does not clutter output.
- Rule-only Harvest briefs use **memory id placeholders** in `[use]`; integrators typically resolve `source_memory_ids` to card excerpts (the demo shows this under *resolved memory excerpts*).

## Tests

```bash
python -m pytest tests/test_agent_brief_injection_demo.py -q
```
