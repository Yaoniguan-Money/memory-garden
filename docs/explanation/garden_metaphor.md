# Why a Garden Metaphor?

Most memory systems use database metaphors: CRUD, tables, queries. Memory Garden uses a garden metaphor instead. This is not just aesthetic; it encodes specific design commitments.

## The Metaphor Mappings

| Garden Concept | Memory System Meaning |
|---|---|
| Seed | A candidate memory that has not been judged yet |
| Court | A judgment process: should this seed grow? |
| Plant | Promote a seed to a long-term memory |
| Compost | Discard the memory but keep the "nutrient" (reason for discarding) |
| Greenhouse | Isolate a sensitive memory for later review |
| Prune | Soft-delete a memory that no longer serves |
| Forget | Hard-delete a memory |
| Dream | Batch review and reorganization of pending seeds and memories |
| Harvest | Gather relevant memories for the current conversation turn |
| Brief | A short summary of what was harvested |
| Journal | An append-only log of everything that happened |

## Why This Matters

The metaphor forces a lifecycle. You can't just "insert" a memory. It must be:

1. **Observed** (seed falls)
2. **Judged** (court decides)
3. **Acted upon** (plant, compost, greenhouse)
4. **Reviewed** (dream cycle)
5. **Harvested** (when relevant)

This lifecycle is the core value proposition. It prevents the "everything is remembered forever" anti-pattern and creates natural audit points.

## What the Metaphor Prevents

- **Bypassing judgment**: No API to directly create a MemoryCard from user text without going through Court.
- **Silent forgetting**: Compost and forget actions leave records explaining why.
- **Unrestricted retrieval**: Harvest respects greenhouse isolation and pruning status.
