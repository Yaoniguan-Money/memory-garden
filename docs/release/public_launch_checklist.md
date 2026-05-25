# Public Launch Checklist

Things to complete before a public GitHub launch. Package publication steps are optional and separate.

## GitHub Repository Launch

- [ ] Package installs cleanly: `pip install -e .` with no errors
- [ ] All tests pass on a clean checkout
- [ ] README and README.zh-CN are accurate and complete
- [ ] Quickstart works from scratch (clone -> install -> run demo)
- [ ] No broken links in documentation
- [ ] LICENSE file present and correct
- [ ] pyproject.toml has complete metadata:
  - [ ] name, version, requires-python
  - [ ] authors or maintainer support path is clear
  - [ ] description and keywords
  - [ ] classifiers (license, Python versions, topic)
  - [ ] URLs (homepage, repository, documentation)
- [ ] .gitignore excludes all generated and sensitive files
- [ ] No secrets, tokens, or keys in repository history
- [ ] No large binary, cache, or editor-local files committed (`*.pyc`, `__pycache__/`, `.pytest_cache/`, `.claude/`, etc.)
- [ ] Dependency versions are reasonably pinned
- [ ] GitHub issue templates and PR template are present
- [ ] `.gitattributes` and `.editorconfig` are present for clean cross-platform contributions

## Optional Package Publication

- [ ] Build package: `python -m build`
- [ ] Verify package contents: `tar tvf dist/*.tar.gz`
- [ ] Test install from built package in a clean virtualenv
- [ ] Upload to Test PyPI and verify
- [ ] Upload to PyPI

## Post-Launch

- [ ] Tag the release commit
- [ ] Create GitHub Release with notes
- [ ] Verify GitHub metadata (description, topics, website)
- [ ] Announce in relevant channels
- [ ] Monitor issues for install problems
- [ ] If publishing packages, verify README renders on the package index

## Things to Not Do

- Do not claim production-readiness or enterprise-grade quality
- Do not overpromise on roadmap items
- Do not publish without reviewing the full git history for secrets
