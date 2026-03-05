"""Tests for LibreSpeed diagnostics."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed import LibreSpeedRuntimeData
from homeassistant.components.librespeed.const import DOMAIN
from homeassistant.components.librespeed.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import MOCK_PARSED_RESULT


def _make_entry_with_coordinator(hass, data=None, backend_type="native", auto_update=True):
    """Create a config entry with mock coordinator for diagnostics."""
    coordinator = MagicMock()
    coordinator.data = deepcopy(data) if data else None
    coordinator.backend_type = backend_type
    coordinator.auto_update = auto_update
    coordinator.is_running = False
    coordinator.last_update_success = True
    coordinator.last_exception = None
    if auto_update:
        from datetime import timedelta
        coordinator.update_interval = timedelta(minutes=60)
    else:
        coordinator.update_interval = None

    client = AsyncMock()
    client.get_servers = AsyncMock(return_value=[])
    coordinator.client = client

    if backend_type == "cli":
        coordinator.client.cli_path = "/config/bin/librespeed-cli"
        del coordinator.client.get_servers

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"backend_type": backend_type, "auto_update": auto_update},
        unique_id="diag_test",
    )
    entry.add_to_hass(hass)
    entry.runtime_data = LibreSpeedRuntimeData(
        coordinator=coordinator, session=MagicMock()
    )
    return entry


async def test_diagnostics_with_data(hass: HomeAssistant) -> None:
    """Test diagnostics includes all sections with data."""
    entry = _make_entry_with_coordinator(hass, data=MOCK_PARSED_RESULT)
    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "entry" in result
    assert "coordinator" in result
    assert "last_test" in result
    assert "cli_info" in result
    assert "platform_info" in result
    assert result["last_test"] is not None
    assert result["last_test"]["download_speed"] == 250.50


async def test_diagnostics_without_data(hass: HomeAssistant) -> None:
    """Test diagnostics when no test data available."""
    entry = _make_entry_with_coordinator(hass, data=None)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["last_test"] is None


async def test_diagnostics_cli_backend(hass: HomeAssistant) -> None:
    """Test CLI backend diagnostics info."""
    entry = _make_entry_with_coordinator(hass, backend_type="cli")
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["cli_info"]["backend"] == "CLI"


async def test_diagnostics_native_backend(hass: HomeAssistant) -> None:
    """Test native backend diagnostics info."""
    entry = _make_entry_with_coordinator(hass, backend_type="native")
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["cli_info"]["backend"] == "Native Python"


async def test_diagnostics_platform_info(hass: HomeAssistant) -> None:
    """Test platform info is included."""
    entry = _make_entry_with_coordinator(hass)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert "platform" in result["platform_info"]
    assert "python_version" in result["platform_info"]


async def test_diagnostics_no_auto_update(hass: HomeAssistant) -> None:
    """Test scan_interval is None when auto_update disabled."""
    entry = _make_entry_with_coordinator(hass, auto_update=False)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["coordinator"]["scan_interval"] is None
