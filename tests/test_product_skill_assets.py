from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_SKILL = ROOT / "packaging" / "codex-skills" / "memory-garden"


def _read_skill_frontmatter() -> tuple[dict, str]:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---\n", 2)
    return yaml.safe_load(frontmatter), body


def test_skill_md_has_product_frontmatter() -> None:
    meta, body = _read_skill_frontmatter()

    assert meta == {
        "name": "memory-garden",
        "description": (
            "Product-grade local-first agent memory with Memory Garden. Use when Codex needs "
            "to create reviewable memory proposals, persist approved memories, retrieve "
            "relevant local memories, prepare a source-id-preserving brief before an LLM call, "
            "manage memory versions and relations, hard-forget memories with proof, audit the "
            "local garden, or check garden health. External LLM, embedding, reranker, and "
            "secret providers are caller-owned and opt-in only."
        ),
    }
    assert "## Operating Rules" in body
    assert "## Validation" in body


def test_skill_md_has_no_machine_specific_bootstrap() -> None:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")

    forbidden = [
        "C:\\Users\\",
        "sys.path.insert",
        "Desktop",
        "execute_code",
        "\ufffd",
    ]
    for token in forbidden:
        assert token not in text


def test_skill_references_exist_and_are_linked() -> None:
    _, body = _read_skill_frontmatter()

    for rel in [
        "references/api.md",
        "references/privacy-and-safety.md",
        "references/storage-and-health.md",
        "references/troubleshooting.md",
    ]:
        path = ROOT / rel
        assert path.is_file()
        assert rel in body
        assert path.read_text(encoding="utf-8").strip()


def test_openai_agent_metadata_is_valid() -> None:
    payload = yaml.safe_load((ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))

    assert payload["interface"]["display_name"] == "记忆花园 Memory Garden"
    assert "$memory-garden" in payload["interface"]["default_prompt"]
    assert payload["policy"]["allow_implicit_invocation"] is False


def test_external_skill_package_is_minimal_and_synced() -> None:
    expected_files = {
        "SKILL.md",
        "agents/openai.yaml",
        "references/api.md",
        "references/privacy-and-safety.md",
        "references/storage-and-health.md",
        "references/troubleshooting.md",
        "scripts/memory_garden_skill_smoke.py",
    }

    actual_files = {
        path.relative_to(EXTERNAL_SKILL).as_posix()
        for path in EXTERNAL_SKILL.rglob("*")
        if path.is_file()
    }

    assert actual_files == expected_files
    for rel in expected_files:
        assert (EXTERNAL_SKILL / rel).read_text(encoding="utf-8") == (ROOT / rel).read_text(encoding="utf-8")


def test_memory_garden_skill_smoke_script(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "memory_garden_skill_smoke.py")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert '"ok": true' in result.stdout
