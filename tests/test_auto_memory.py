"""Tests for AutoMemory: one-line drop-in memory layer."""

import os

from memory_garden.auto import AutoMemory


def test_auto_start_stop(tmp_path):
    auto = AutoMemory(garden_path=tmp_path / "garden")
    auto.start()
    assert auto.skill.is_open
    auto.stop()
    assert not auto.skill.is_open


def test_auto_context_manager(tmp_path):
    with AutoMemory(garden_path=tmp_path / "garden") as auto:
        assert auto.skill.is_open
    assert not auto.skill.is_open


def test_auto_hook_wraps_function(tmp_path):
    called = []

    def my_llm(prompt):
        called.append(("called", prompt))
        return "reply"

    with AutoMemory(garden_path=tmp_path / "garden") as auto:
        wrapped = auto.hook(
            my_llm,
            extract_user_msg=lambda a, kw: kw.get("prompt", ""),
            extract_reply=lambda r: r,
        )
        result = wrapped(prompt="I prefer dark mode.")
        assert result == "reply"
        assert len(called) == 1

    assert not auto.skill.is_open


def test_auto_no_memory_garden_created(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed = os.path.exists(cwd_mg)
    with AutoMemory(garden_path=tmp_path / "garden"):
        pass
    if not existed:
        assert not os.path.exists(cwd_mg)


def test_auto_double_start_idempotent(tmp_path):
    auto = AutoMemory(garden_path=tmp_path / "garden")
    auto.start()
    sid_before = auto.skill.session_id
    auto.start()  # second start should be no-op
    assert auto.skill.session_id == sid_before
    auto.stop()


def test_auto_does_not_crash_without_clients(tmp_path):
    auto = AutoMemory(garden_path=tmp_path / "garden", auto_discover=False)
    auto.start()
    assert auto.skill.is_open
    auto.stop()


def test_auto_memory_records_openai_patch_failure(tmp_path):
    class BrokenOpenAI:
        @property
        def chat(self):
            raise RuntimeError("openai patch failed")

    auto = AutoMemory(
        garden_path=tmp_path / "garden",
        open_client=BrokenOpenAI(),
        auto_discover=False,
    )
    try:
        assert auto.start() is auto
        assert auto.diagnostics["patched"]["openai"] is False
        assert auto.patch_errors == [
            {
                "provider": "openai",
                "stage": "patch_create",
                "error_type": "RuntimeError",
                "message": "openai patch failed",
            }
        ]
    finally:
        auto.stop()


def test_auto_memory_records_anthropic_patch_failure(tmp_path):
    class BrokenAnthropic:
        @property
        def messages(self):
            raise RuntimeError("anthropic patch failed")

    auto = AutoMemory(
        garden_path=tmp_path / "garden",
        anthropic_client=BrokenAnthropic(),
        auto_discover=False,
    )
    try:
        auto.start()
        assert auto.diagnostics["patched"]["anthropic"] is False
        assert auto.patch_errors == [
            {
                "provider": "anthropic",
                "stage": "patch_create",
                "error_type": "RuntimeError",
                "message": "anthropic patch failed",
            }
        ]
    finally:
        auto.stop()


def test_auto_memory_diagnostics_empty_on_success(tmp_path):
    class Completions:
        def create(self, *args, **kwargs):
            return None

    class Chat:
        def __init__(self):
            self.completions = Completions()

    class OpenAIClient:
        def __init__(self):
            self.chat = Chat()

    auto = AutoMemory(
        garden_path=tmp_path / "garden",
        open_client=OpenAIClient(),
        auto_discover=False,
    )
    try:
        auto.start()
        assert auto.diagnostics == {
            "started": True,
            "patched": {"openai": True, "anthropic": False},
            "patch_errors": [],
        }
    finally:
        auto.stop()


def test_auto_memory_start_still_returns_self(tmp_path):
    auto = AutoMemory(garden_path=tmp_path / "garden", auto_discover=False)
    try:
        assert auto.start() is auto
    finally:
        auto.stop()
