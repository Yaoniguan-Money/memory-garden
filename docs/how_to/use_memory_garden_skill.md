# Use Memory Garden Skill

Memory Garden Skill wraps the SDK as an agent-facing memory layer. It is local
by default and does not call external providers unless the caller explicitly
injects one.

## Basic Flow

```python
from memory_garden.sdk import MemoryGarden

garden = MemoryGarden.local("./my_garden")
skill = garden.as_skill()

opened = skill.open_session()
remembered = skill.remember("我喜欢深色模式，以后界面相关回答请优先考虑这一点")
harvested = skill.harvest("深色模式")
closed = skill.close_session()

garden.close()
```

## Before / After Hook Flow

```python
ctx = skill.before(
    "请按我的界面偏好回答",
    messages=[{"role": "user", "content": "请按我的界面偏好回答"}],
)

reply = call_your_model(ctx.messages)
skill.after("请按我的界面偏好回答", reply)
```

`before()` can inject a Garden Brief into OpenAI-style messages. The brief keeps
`source_memory_ids` so callers can audit where it came from.

## Remember

`remember()` observes text, opens the rule Court, and applies safe rule verdicts.
The default write mode is `court`.

```python
result = skill.remember("我喜欢深色模式")
assert result.ok
```

Use preview mode to inspect Court output without applying Growth actions:

```python
result = skill.remember("我喜欢深色模式", mode="preview")
```

## Forget

`forget()` never calls providers. It resolves a memory id or local substring
match, then delegates to Soil hard forget.

```python
result = skill.forget("深色模式", reason="用户显式要求忘记")
```

## Harvest

`harvest()` is rule-only at the Skill layer. It returns a `SkillHarvestResult`
with a `GardenBrief`, candidate ids, and source ids.

```python
harvest = skill.harvest("深色模式")
print(harvest.source_memory_ids)
```

## Audit

```python
audit = skill.audit()
print(audit.config)
print(audit.events)
```

Audit snapshots are serializable and include recent event summaries without
dumping provider secrets.
