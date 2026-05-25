"""Tests for the Memory Garden CLI (python -m memory_garden)."""

import os
import sys
from io import StringIO

from memory_garden.__main__ import main


def test_cli_no_command_shows_help():
    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main([])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    assert rc == 0
    assert "memory-garden" in output.lower() or "Memory Garden" in output


def test_cli_init_creates_garden(tmp_path, monkeypatch):
    path = str(tmp_path / "cli_garden")
    rc = main(["init", "--path", path])
    assert rc == 0
    assert os.path.isdir(path)
    assert os.path.isfile(os.path.join(path, "manifest.json"))


def test_cli_health_healthy(tmp_path, monkeypatch):
    path = str(tmp_path / "cli_garden")
    main(["init", "--path", path])

    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(["health", "--path", path])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    assert rc == 0
    assert "healthy" in output or "degraded" in output


def test_cli_health_nonexistent(tmp_path):
    path = str(tmp_path / "nonexistent")
    rc = main(["health", "--path", path])
    assert rc == 1  # unhealthy


def test_cli_doctor_healthy(tmp_path):
    path = str(tmp_path / "cli_garden")
    main(["init", "--path", path])

    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(["doctor", "--path", path])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old

    assert rc == 0
    assert "Memory Garden doctor" in output
    assert ".gitignore: ok" in output


def test_cli_doctor_nonexistent(tmp_path):
    path = str(tmp_path / "nonexistent")
    rc = main(["doctor", "--path", path])
    assert rc == 1


def test_cli_search_no_index(tmp_path):
    path = str(tmp_path / "cli_garden")
    main(["init", "--path", path])

    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(["search", "test", "--path", path])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    # Should report no index, not crash
    assert "No FTS index" in output or rc != 0


def test_cli_demo_runs_full_cycle(tmp_path):
    path = str(tmp_path / "demo_garden")
    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(["demo", "--path", path])
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    assert rc == 0
    assert "花花开" in output
    assert "花花关" in output
    assert "Demo complete" in output


def test_cli_does_not_create_memory_garden_in_cwd(tmp_path, monkeypatch):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    path = str(tmp_path / "cli_garden")
    main(["init", "--path", path])

    if not existed_before:
        assert not os.path.exists(cwd_mg)
