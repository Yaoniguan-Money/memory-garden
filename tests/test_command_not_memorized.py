"""第二层 Stage 2G：控制口令不得写入记忆层（observe / Seed / MemoryCard）。"""

from unittest.mock import MagicMock

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    RuntimeState,
    TemplateBriefWriter,
)
from memory_garden.runtime.commands import parse_runtime_command
from memory_garden.runtime.runtime import GardenRuntime


@pytest.fixture
def core() -> MemoryGardenCore:
    return MemoryGardenCore()


@pytest.fixture
def manager() -> GardenSessionManager:
    return GardenSessionManager()


@pytest.fixture
def hooks(core: MemoryGardenCore, manager: GardenSessionManager) -> RuntimeHooks:
    return RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)


@pytest.fixture
def runtime(core: MemoryGardenCore, manager: GardenSessionManager, hooks: RuntimeHooks) -> GardenRuntime:
    return GardenRuntime(core, manager, hooks)


def test_huahua_open_does_not_create_seed(core: MemoryGardenCore, manager: GardenSessionManager) -> None:
    assert parse_runtime_command("花花开") is not None
    manager.open_session()
    assert len(core.repository.list_seeds()) == 0


def test_huahua_close_does_not_create_seed(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    runtime.try_close_control_command("花花关")
    assert len(core.repository.list_seeds()) == 0


def test_huahua_close_does_not_create_memory_card(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    before = len(core.repository.list_memory_cards())
    runtime.try_close_control_command("花花关")
    assert len(core.repository.list_memory_cards()) == before


def test_huahua_close_does_not_call_observe(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    mock_observe = MagicMock()
    core.observe = mock_observe  # type: ignore[method-assign]
    runtime.try_close_control_command("花花关")
    mock_observe.assert_not_called()


def test_huahua_close_sets_closed(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    runtime.try_close_control_command("花花关")
    assert manager.current_session().state == RuntimeState.CLOSED


def test_repeat_huahua_close_is_idempotent_for_memory_layer(
    core: MemoryGardenCore,
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    runtime.try_close_control_command("花花关")
    n_seeds = len(core.repository.list_seeds())
    n_cards = len(core.repository.list_memory_cards())
    runtime.try_close_control_command("花花关")
    assert len(core.repository.list_seeds()) == n_seeds
    assert len(core.repository.list_memory_cards()) == n_cards


def test_plain_chat_is_not_close_command(
    manager: GardenSessionManager,
    runtime: GardenRuntime,
) -> None:
    manager.open_session()
    assert runtime.try_close_control_command("顺便说下花花关很难演") is None
