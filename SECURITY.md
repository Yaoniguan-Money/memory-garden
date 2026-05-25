# Security Policy

## Reporting A Vulnerability

Please do not disclose exploitable vulnerabilities in a public issue.

Report security issues by email to `security@memory-garden.dev`. Include:

- A short description of the issue.
- A minimal reproduction, if possible.
- Whether any local data, API keys, or git history could be exposed.

We aim to acknowledge reports within 48 hours.

## Supported Versions

| Version | Supported |
|---|---|
| Latest `main` branch | Yes, experimental |
| Tagged releases | Best effort |
| Older versions | No |

## Security Model

Memory Garden is local-first. The default rules-only path does not make network calls and does not require API keys.

Core assumptions:

- The user controls the local machine.
- The garden SQLite database is plaintext on disk.
- Optional LLM, embedding, and reranker providers are explicitly configured by the caller.
- API keys should be supplied through environment variables. `~/.memory_garden/provider_config.json` is a local fallback only and must not be committed.
- Adapter hook CLIs remain rules-only unless the user explicitly opts in to provider autoload with `MEMORY_GARDEN_ENABLE_PROVIDER_AUTOLOAD=1`.
- Long-term memory must remain traceable to source ids. Non-traceable content cannot enter durable memory.

## Data That Must Never Be Committed

Do not commit:

```text
.memory_garden/
*.db
*.db-wal
*.db-shm
*_state.json
provider_config.json
.env
.env.*
```

Before publishing a repository, audit git history:

```bash
git log --all --full-history -- "*.db" "*.key" "*_state.json" "provider_config.json"
```

If sensitive files appear in history, remove them with a history-rewrite tool such as BFG Repo-Cleaner or `git filter-repo` before pushing.

## SQL Safety Notes

Memory Garden uses parameterized SQL for user-provided values.

Dynamic table cleanup is restricted by allowlists:

- `memory_garden.product.storage._MODEL_TABLES = {"memory_proposals", "forget_plans"}`
- `memory_garden.storage.sqlite_support.ALLOWED_TABLES = {"seeds", "memory_cards", "court_cases", "dream_records", "compost_records", "greenhouse_records", "pruning_records", "garden_events"}`

The hard-forget FTS cleanup in `memory_garden.soil.forget` interpolates only the internal `FTS_TABLE` constant. User-controlled ids and types remain parameterized.

## Known Limitations

- No encryption at rest: anyone with filesystem access can read the SQLite database.
- No authentication: the library assumes a single trusted local user.
- No sandbox against malicious local Python code running in the same process.
- Optional provider calls can send selected user text to caller-configured remote services.

## Secret Scanning

The repository includes a pre-commit hook for `detect-secrets`. Before launch, initialize and audit the baseline:

```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline
```

Treat any real key as a true positive and rotate it.
