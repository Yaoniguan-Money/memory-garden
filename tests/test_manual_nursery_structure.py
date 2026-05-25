"""Structural integrity tests for Layer 9: Manual & Nursery.

These tests verify that required docs, examples, and community files exist
and have minimum content. They do NOT test the semantic correctness of
documentation content.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _exists(path: str) -> bool:
    return (REPO_ROOT / path).exists()


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _min_size(path: str, min_bytes: int) -> bool:
    try:
        return (REPO_ROOT / path).stat().st_size >= min_bytes
    except FileNotFoundError:
        return False


# --- Stage 9A: docs structure ---


def test_docs_index_exists():
    assert _exists("docs/index.md")


def test_docs_quickstart_exists():
    assert _exists("docs/quickstart.md")


def test_docs_installation_exists():
    assert _exists("docs/installation.md")


def test_docs_concepts_exists():
    assert _exists("docs/concepts.md")


def test_docs_architecture_exists():
    assert _exists("docs/architecture.md")


def test_docs_tutorials_index_exists():
    assert _exists("docs/tutorials/index.md")


def test_docs_tutorials_first_session_exists():
    assert _exists("docs/tutorials/first_session.md")


def test_docs_how_to_index_exists():
    assert _exists("docs/how_to/index.md")


def test_docs_how_to_integrate_sync_exists():
    assert _exists("docs/how_to/integrate_sync_agent.md")


def test_docs_how_to_integrate_async_exists():
    assert _exists("docs/how_to/integrate_async_agent.md")


def test_docs_reference_index_exists():
    assert _exists("docs/reference/index.md")


def test_docs_explanation_index_exists():
    assert _exists("docs/explanation/index.md")


def test_docs_explanation_limitations_exists():
    assert _exists("docs/explanation/limitations.md")


def test_docs_explanation_related_work_exists():
    assert _exists("docs/explanation/related_work.md")


def test_docs_explanation_garden_metaphor_exists():
    assert _exists("docs/explanation/garden_metaphor.md")


def test_examples_readme_exists():
    assert _exists("examples/README.md")


def test_mkdocs_yml_exists():
    assert _exists("mkdocs.yml")


# --- Stage 9B: README files ---


def test_readme_exists():
    assert _exists("README.md")


def test_readme_cn_exists():
    assert _exists("README_中文.md")


def test_readme_has_minimum_content():
    assert _min_size("README.md", 500)


def test_readme_cn_has_minimum_content():
    assert _min_size("README_中文.md", 300)


# --- Stage 9C: docs content minimums ---


def test_concepts_has_minimum_content():
    assert _min_size("docs/concepts.md", 1000)


def test_architecture_has_minimum_content():
    assert _min_size("docs/architecture.md", 800)


def test_quickstart_has_minimum_content():
    assert _min_size("docs/quickstart.md", 500)


def test_limitations_is_not_empty():
    text = _read("docs/explanation/limitations.md").strip()
    assert len(text) > 200


def test_related_work_does_not_denigrate():
    text = _read("docs/explanation/related_work.md")
    bad_words = ["garbage", "trash", "useless", "stupid", "terrible", "worst"]
    lower = text.lower()
    for w in bad_words:
        assert w not in lower, f"Related work contains derogatory term '{w}'"


# --- Stage 9D: examples ---


def test_sync_chat_agent_runnable():
    """Verify the example has a main() and __main__ guard."""
    text = _read("examples/sync_chat_agent.py")
    assert "def main()" in text
    assert 'if __name__ == "__main__"' in text


def test_examples_no_real_api_keys():
    """Verify examples don't contain real-looking API keys."""
    import re

    for py_file in (REPO_ROOT / "examples").glob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert not re.search(r'sk-[a-zA-Z0-9]{20,}', text), (
            f"{py_file.name} contains what looks like an API key"
        )
        assert not re.search(r'api_key\s*=\s*"[^"]{20,}"', text), (
            f"{py_file.name} contains what looks like a hardcoded key"
        )


def test_examples_no_real_env_file():
    assert not _exists(".env")
    assert not _exists("examples/.env")


# --- Stage 9E: community files ---


def test_contributing_exists():
    assert _exists("CONTRIBUTING.md")


def test_code_of_conduct_exists():
    assert _exists("CODE_OF_CONDUCT.md")


def test_security_exists():
    assert _exists("SECURITY.md")


def test_license_exists():
    assert _exists("LICENSE")


def test_pr_template_exists():
    assert _exists(".github/PULL_REQUEST_TEMPLATE.md")


def test_issue_templates_exist():
    templates_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
    assert templates_dir.is_dir()
    templates = list(templates_dir.glob("*.yml")) + list(templates_dir.glob("*.md"))
    assert len(templates) >= 3, f"Expected at least 3 issue templates, found {len(templates)}"


def test_issue_template_config_exists():
    assert _exists(".github/ISSUE_TEMPLATE/config.yml")


# --- Stage 9F: release / packaging ---


def test_changelog_exists():
    assert _exists("CHANGELOG.md")


def test_roadmap_exists():
    assert _exists("ROADMAP.md")


def test_release_checklist_exists():
    assert _exists("docs/release/release_checklist.md")


def test_editorconfig_exists():
    assert _exists(".editorconfig")


def test_gitattributes_exists():
    assert _exists(".gitattributes")


def test_pyproject_has_metadata():
    text = _read("pyproject.toml")
    assert "memory-garden" in text
    assert "pydantic" in text


# --- Content checks ---


def test_readme_contains_quickstart():
    text = _read("README.md").lower()
    assert "quickstart" in text or "quick start" in text or "getting started" in text


def test_readme_contains_garden_concepts():
    text = _read("README.md").lower()
    concepts = ["seed", "court", "dream", "harvest", "garden brief"]
    found = [c for c in concepts if c in text]
    assert len(found) >= 3, f"README mentions only {found} out of {concepts}"


def test_contributing_has_test_instructions():
    text = _read("CONTRIBUTING.md").lower()
    assert "pytest" in text or "test" in text


def test_changelog_has_unreleased():
    text = _read("CHANGELOG.md")
    assert "Unreleased" in text or "unreleased" in text


def test_limitations_is_not_trivial():
    text = _read("docs/explanation/limitations.md")
    assert len(text) > 400
    assert "no llm" in text.lower() or "vector" in text.lower() or "no ui" in text.lower()


def test_readme_cn_mentions_flower():
    text = _read("README_中文.md")
    assert "花花开" in text or "花花关" in text
