# Branching Strategy

Memory Garden uses a small GitHub-flow workflow. The goal is a reviewable
history without heavy release ceremony.

## Branches

- `main` is the integration branch. It should stay releasable.
- Feature and fix work happens on short-lived branches named by scope, for
  example `feature/soil-forget-proof` or `fix/sqlite-repository-errors`.
- Release preparation can use `release/vX.Y.Z-short-name` when changelog,
  version, and documentation updates need a focused review before tagging.

## Pull Requests

- Open a pull request for every non-trivial change.
- Keep one behavioral concern per PR.
- CI must pass before merge.
- Update tests and docs in the same PR when behavior changes.
- Prefer squash merge for focused feature branches unless preserving multiple
  commits adds useful review context.

## Tags

- Releases use annotated tags in the format documented in
  [versioning.md](versioning.md).
- Tags are created only after the release checklist passes.
- Do not move or delete published tags. Cut a new patch release instead.

## PyPI Releases

Publishing is driven by GitHub Releases. After a release is published, the
`Publish to PyPI` workflow builds the package, verifies the distributions, and
publishes with PyPI Trusted Publishing.
