"""第二层 Stage 2B：运行时控制口令解析。"""

import inspect

from memory_garden.runtime.commands import CommandResult, CommandType, parse_runtime_command


def test_huahua_open() -> None:
    r = parse_runtime_command("花花开")
    assert r is not None
    assert r.command_type == CommandType.OPEN
    assert r.matched_alias == "花花开"
    assert r.is_runtime_command is True


def test_huahua_close() -> None:
    r = parse_runtime_command("花花关")
    assert r is not None
    assert r.command_type == CommandType.CLOSE


def test_garden_on_whitespace() -> None:
    r = parse_runtime_command(" /garden on ")
    assert r is not None
    assert r.command_type == CommandType.OPEN
    assert r.normalized_text == "/garden on"


def test_garden_off_casefold() -> None:
    r = parse_runtime_command("/GARDEN OFF")
    assert r is not None
    assert r.command_type == CommandType.CLOSE


def test_empty_returns_none() -> None:
    assert parse_runtime_command("") is None
    assert parse_runtime_command("   ") is None


def test_plain_chat_not_command() -> None:
    assert parse_runtime_command("你好，今天天气不错") is None


def test_substring_huahua_not_command() -> None:
    assert parse_runtime_command("我觉得花花开这个词很可爱") is None


def test_debug_phrases_not_runtime_commands() -> None:
    for text in ("花花审判", "花花做梦", "花花采摘"):
        assert parse_runtime_command(text) is None


def test_command_result_json_roundtrip() -> None:
    r = parse_runtime_command("花花开")
    assert r is not None
    data = r.model_dump(mode="json")
    r2 = CommandResult.model_validate(data)
    assert r2.command_type == CommandType.OPEN


def test_commands_module_has_no_core_imports() -> None:
    import memory_garden.runtime.commands as cmd

    src = inspect.getsource(cmd)
    assert "SeedObserver" not in src
    assert "MemoryGardenCore" not in src
    assert "SQLiteGardenRepository" not in src
    assert "memory_garden.core" not in src


def test_parse_is_pure_no_seed_memory_side_channel() -> None:
    """解析为纯函数实现：源码未引用 Observer / 仓储 API，故不会创建 Seed 或 MemoryCard。"""
    import memory_garden.runtime.commands as cmd

    src = inspect.getsource(cmd)
    for needle in ("SeedObserver", "save_seed", "save_memory_card", "MemoryGardenCore", "GardenRepository"):
        assert needle not in src
