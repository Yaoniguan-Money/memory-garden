"""Stage 15：Agent Brief 注入演示脚本测试。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE = _ROOT / "examples" / "agent_brief_injection_demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("mg_agent_brief_demo", _EXAMPLE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _section(stdout: str, header: str) -> str:
    start = stdout.index(header) + len(header)
    rest = stdout[start:].lstrip("\n")
    next_idx = rest.find("==========")
    return rest[:next_idx].strip() if next_idx >= 0 else rest.strip()


def test_demo_module_import_no_side_effects() -> None:
    mod = _load_demo()
    assert hasattr(mod, "run_demo")
    assert mod.DEMO_MARKER == "MG_STAGE15_DEMO"


def test_run_demo_returns_success(tmp_path: Path) -> None:
    mod = _load_demo()
    result = mod.run_demo(garden_home=tmp_path / "garden", quiet=True)
    assert result.ok is True
    assert result.garden_brief.strip()
    assert result.memory_ids


def test_stdout_contains_garden_brief(tmp_path: Path) -> None:
    mod = _load_demo()
    result = mod.run_demo(garden_home=tmp_path / "garden2", quiet=True)
    assert mod.SECTION_GARDEN_BRIEF in result.stdout
    assert "[use]" in result.garden_brief


def test_with_memory_uses_seeded_cues(tmp_path: Path) -> None:
    mod = _load_demo()
    result = mod.run_demo(garden_home=tmp_path / "garden3", quiet=True)
    with_section = _section(result.stdout, mod.SECTION_WITH_MEMORY).casefold()
    hits = sum(
        1
        for cue in ("python", "typescript", "local-first", "memory garden", "benchmark")
        if cue in with_section
    )
    assert hits >= 2


def test_no_memory_lacks_seeded_marker(tmp_path: Path) -> None:
    mod = _load_demo()
    result = mod.run_demo(garden_home=tmp_path / "garden4", quiet=True)
    no_section = _section(result.stdout, mod.SECTION_NO_MEMORY).casefold()
    assert mod.DEMO_MARKER.casefold() not in no_section
    assert "python" not in no_section or "typescript" not in no_section


def test_main_cli_exit_zero(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(_EXAMPLE), "--path", str(tmp_path / "cli_garden"), "--quiet"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_no_cwd_pollution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    mod = _load_demo()
    mod.run_demo(garden_home=tmp_path / "isolated_garden", quiet=True)
    assert not (tmp_path / "garden.db").exists()
    assert not (tmp_path / ".memory_garden").exists()


def test_example_source_no_provider_or_api_key_tokens() -> None:
    text = _EXAMPLE.read_text(encoding="utf-8").lower()
    for bad in (
        "api_key",
        "apikey",
        "sk-",
        "bearer ",
        "deepseek",
        "live-key-token",
    ):
        assert bad not in text, bad
