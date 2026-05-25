# Forget Memory With Skill

Forgetting is a privileged operation. The Skill layer keeps it separate from
provider advice and calls Soil hard forget directly.

```python
result = skill.forget("深色模式", reason="用户显式要求忘记")
```

You can also pass an exact memory id:

```python
result = skill.forget("ignored text", memory_id="mem-123", reason="user request")
```

## Dry Run

```python
plan = skill.forget("深色模式", dry_run=True)
```

Dry run returns a normal `SkillOperationResult` with `preview=True` and the Soil
forget plan in metadata.

## What It Does

- Resolves the local MemoryCard.
- Does not call an LLM or advisor provider.
- Executes Soil hard forget.
- Removes the MemoryCard and FTS entries when present.
- Optionally cascades related rows when `cascade=True`.
- Runs **content-level forget proof** (Stage 14): salted hash + redacted token probes verify that title/essence tokens are not retrievable from SQLite, FTS, bundle export, or product tables.

## Content Proof vs ID Proof

`prove_forget()` always checks that the `memory_id` row is gone. When content probes are available (captured before delete), it also scans for **content probe** matches in:

- memory-scoped SQLite / product rows
- FTS and search surfaces
- exported bundle metadata

With `cascade=False`, related seed/court/event rows may **by design** retain plaintext; those hits are recorded as **skipped (warn-only)** and do not fail `proven`.

Proof records store fingerprints and redacted tokens only — **not** full forgotten plaintext.

## Audit Retention (Stage 14)

| Record | Plaintext risk | Notes |
|--------|----------------|-------|
| `garden_events` (hard forget) | No essence | Journal metadata only |
| `forget_plans` / `forget_proofs` | Redacted | Fingerprints + check verdicts |
| `memory_retrieval_events` | Query text only | Purged on forget when referencing the memory |
| seed / court (`cascade=false`) | **Yes** | By design; proof marks skip + warn |

## What It Does Not Guarantee

Without cascade cleanup, audit rows can still prove that a memory once existed.
Use cascade mode and forget proof tools when the product requirement is stronger
than normal MemoryCard deletion.
