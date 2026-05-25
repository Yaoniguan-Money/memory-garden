# Release Checklist

Steps for cutting a Memory Garden release.

## Before Release

- [ ] All tests pass: `python -m pytest tests -q`
- [ ] Lab smoke passes: smoke pack returns `passed`
- [ ] Lab safety passes: safety pack returns `passed`
- [ ] No uncommitted changes: `git status --short` is clean
- [ ] CHANGELOG.md has an [Unreleased] section with all changes
- [ ] ROADMAP.md is updated if completed items exist
- [ ] Version in pyproject.toml matches the release tag
- [ ] README reflects current version and release guidance
- [ ] No real API keys, .env files, or sensitive data in the repo
- [ ] No .memory_garden, garden.db, or export directories
- [ ] GitHub issue templates, PR template, `.gitattributes`, and `.editorconfig` are present
- [ ] If real providers changed, run the fake smoke and review [real_provider_trial_checklist.md](real_provider_trial_checklist.md)

## GitHub Release Steps

1. Move [Unreleased] section in CHANGELOG.md to new version section
2. Update version in pyproject.toml if not already done
3. Run full test suite: `python -m pytest tests -q`
4. Verify structural tests: `python -m pytest tests/test_manual_nursery_structure.py -q`
5. Commit any release-prep changes
6. Create annotated tag: `git tag -a vX.Y.Z-short-name -m "Release vX.Y.Z"`
7. Verify tag: `git tag --list "vX.Y.*"`
8. Publish a GitHub Release from that tag

## After Release

- [ ] Push commits and tags
- [ ] Create GitHub Release with CHANGELOG section
- [ ] Verify README renders correctly on GitHub
- [ ] Add new [Unreleased] section to CHANGELOG.md

## Optional Package Publication

- [ ] PyPI Trusted Publishing is configured for the GitHub `pypi` environment
- [ ] `python -m build` succeeds in a clean environment
- [ ] Built packages install in a clean virtualenv
- [ ] If enabled, confirm the `Publish to PyPI` workflow completed successfully

## Version Numbering

See [versioning.md](versioning.md).

## Emergency Rollback

If a tagged release has a critical issue:

1. Fix the issue on `main`
2. Create a new patch tag
3. Document the fix in CHANGELOG.md
4. Do NOT delete or move the old tag (it breaks downstream references)
