# Why ten layers?

Memory Garden is organized into ten layers. This can seem like over-engineering for a memory library. Here's why.

## Each Layer Has a Specific Reason to Exist

| Layer | Why Separate |
|---|---|
| Core | The memory lifecycle kernel. Must be frozen and never depend on runtime concerns. |
| Runtime | Session orchestration. Connects Core to conversation rhythm without modifying Core. |
| Harvest | Retrieval pipeline. Separated from Runtime so Harvest can be swapped or improved independently. |
| Observatory | Read-only traces. Separated so trace logic doesn't leak into business logic. |
| Integration | Chat adapters. Separated so adapter protocols don't couple to Core internals. |
| Lab | Snapshot regression. Separated so Lab doesn't depend on the running system. |
| Cookbook | CI tooling. Separated so catalog/coverage logic doesn't bloat Lab models. |
| Covenant | Memory policy. Separated so policy rules are centralized, not scattered across modules. |
| Manual | Documentation. Separated so docs can evolve without touching code. |
| Soil | Local-first home, manifest, snapshot, health, search index, and hard-forget proof. |

## The Alternative

The alternative is a flat structure where "memory" is a single module with mixed concerns: storage, retrieval, judgment, policy, and session management all in one place. This is simpler to start but becomes hard to:

- **Test independently**: Can't test judgment without setting up storage and sessions.
- **Modify safely**: Changing retrieval might break session management.
- **Audit**: Hard to verify that policy rules are consistently applied when they're scattered across files.

## The Cost

ten layers means more files, more imports, and a steeper learning curve. The project accepts this cost because:

1. Each layer is small (most are 5-10 files).
2. The layer boundaries are mechanical (import rules) not aspirational.
3. Contributors can understand one layer without reading all ten.

