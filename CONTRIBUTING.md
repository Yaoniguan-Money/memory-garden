# Contributing to 记忆花园 Memory Garden

Thank you for your interest in contributing. 记忆花园 Memory Garden is an experimental, local-first memory layer for AI agents. Contributions that respect the project's boundaries are welcome.

## Project Boundaries

Before contributing, please understand what Memory Garden is and is not:

**In scope**:
- Improvements to the rule-based Court, Dream, Harvest, or Covenant engines
- New deterministic assertion types for the Lab layer
- Documentation, examples, and tutorials
- Bug fixes within existing layers
- Test coverage improvements

**Out of scope** (will not be merged):
- Heavy provider SDK dependencies in the core package
- Vector database or embedding dependencies
- Web UI, FastAPI services, or CLI products
- Cloud sync, multi-user, or SaaS features
- Changes that add heavy dependencies beyond Pydantic and PyYAML

## Setup

```bash
git clone <repository-url> memory-garden
cd memory-garden
pip install -e ".[dev]"
```

## Running Tests

```bash
# Full suite
python -m pytest tests -q

# With coverage (if pytest-cov is installed)
python -m pytest tests -q --cov=memory_garden --cov-report=term-missing
```

All tests must pass before submitting a PR. New code should include tests.

## Secret Safety

Before opening a PR, make sure you did not add local garden data or secrets:

```bash
detect-secrets-hook --baseline .secrets.baseline $(git ls-files)
git log --all --full-history -- "*.db" "*.key" "*_state.json" "provider_config.json"
```

Never commit `.memory_garden/`, SQLite database files, state files, `.env` files, provider config files, `__pycache__/`, `.pytest_cache/`, or local editor/agent config directories such as `.claude/`.

## Running Lab Checks

```bash
# Smoke (fast, pre-commit)
python -c "
from memory_garden.lab.suite_packs import smoke_pack
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.report import format_lab_run_report

suites = smoke_pack(default_lab_suites())
run = SnapshotLabRunner().run_suites(suites, {})
print(format_lab_run_report(run))
"

# Safety
python -c "
from memory_garden.lab.suite_packs import safety_pack
from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.runner import SnapshotLabRunner
from memory_garden.lab.report import format_lab_run_report

suites = safety_pack(default_lab_suites())
run = SnapshotLabRunner().run_suites(suites, {})
print(format_lab_run_report(run))
"
```

## Code Style

- Follow existing patterns in the file you're editing.
- Use type hints.
- Keep functions small and testable.
- No comments that describe what the code does (names should do that). Comments are for why.
- Avoid premature abstraction. Three similar lines is better than an unnecessary helper.

## Commit Messages

- Keep subject under 72 characters.
- Use imperative mood ("Add X" not "Added X").
- Reference layer or component if relevant.

## Pull Requests

1. Create a branch from `main`.
2. Make focused changes: one concern per PR.
3. Ensure all tests pass.
4. If adding a new feature, add tests and update relevant docs.
5. Use the PR template.

See [docs/release/branching_strategy.md](docs/release/branching_strategy.md) for the branch, pull request, tag, and release workflow.

## Documentation

- New public APIs should be documented in the relevant `docs/reference/` file.
- Design decisions go in `docs/explanation/`.
- How-to guides for new workflows go in `docs/how_to/`.

## Adding Lab Cases

If your change affects a behavior that is covered by a Lab contract (seed extraction, command short-circuit, court verdict, harvest brief, observatory redaction), update the relevant fixture suite in `memory_garden/lab/fixtures.py`.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
