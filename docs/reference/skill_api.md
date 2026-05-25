# Skill API Reference

## SkillConfig

```python
SkillConfig(
    garden_home=None,
    enable_harvest_brief=True,
    enable_dream=False,
    enable_court_shadow=False,
    enable_cognitive_harvest=False,
    provider_mode="disabled",
    redaction_level="basic",
    default_write_mode="court",
    allow_hard_forget=True,
    audit_events_limit=50,
)
```

## GardenSkill

### open_session

Returns `SkillOperationResult`.

```python
skill.open_session()
```

### close_session

Returns `SkillOperationResult`.

```python
skill.close_session()
```

### before

Returns `SkillContext`.

```python
skill.before("message", messages=[{"role": "user", "content": "message"}])
```

### remember

Returns `SkillOperationResult`.

```python
skill.remember("我喜欢深色模式", mode="court")
skill.remember("我喜欢深色模式", mode="preview")
```

### forget

Returns `SkillOperationResult`.

```python
skill.forget("深色模式", reason="user request")
skill.forget("ignored", memory_id="mem-123", dry_run=True)
```

### harvest

Returns `SkillHarvestResult`.

```python
skill.harvest("深色模式", limit=5)
```

### audit

Returns `SkillAuditView`.

```python
skill.audit(limit=50)
```

## Error Model

Skill APIs return structured errors instead of exposing backend exception types.

```python
SkillError(
    code="invalid_input",
    message="text must be non-empty",
    details={},
)
```

Stable error codes:

- `invalid_input`
- `permission_denied`
- `not_found`
- `runtime_error`
