"""Tests for LibreSpeed device actions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed import LibreSpeedRuntimeData
from homeassistant.components.librespeed.const import DOMAIN
from homeassistant.components.librespeed.device_action import (
    async_call_action_from_config,
    async_get_action_capabilities,
    async_get_actions,
)


async def test_get_actions(hass: HomeAssistant) -> None:
    """Test get_actions returns run_speed_test."""
    actions = await async_get_actions(hass, "device_123")
    assert len(actions) == 1
    assert actions[0]["type"] == "run_speed_test"
    assert actions[0]["domain"] == DOMAIN


async def test_call_action_success(hass: HomeAssistant) -> None:
    """Test call_action runs speedtest for correct device."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="test")
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.async_run_speedtest = AsyncMock()
    entry.runtime_data = LibreSpeedRuntimeData(coordinator=coordinator)

    device_reg = dr.async_get(hass)
    device = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
    )

    config = {
        "device_id": device.id,
        "domain": DOMAIN,
        "type": "run_speed_test",
    }
    await async_call_action_from_config(hass, config, {}, None)
    coordinator.async_run_speedtest.assert_called_once()


async def test_call_action_invalid_type(hass: HomeAssistant) -> None:
    """Test invalid action type raises error."""
    config = {
        "device_id": "any",
        "domain": DOMAIN,
        "type": "invalid_action",
    }
    with pytest.raises(InvalidDeviceAutomationConfig):
        await async_call_action_from_config(hass, config, {}, None)


async def test_call_action_device_not_found(hass: HomeAssistant) -> None:
    """Test missing device raises error."""
    config = {
        "device_id": "nonexistent_device",
        "domain": DOMAIN,
        "type": "run_speed_test",
    }
    with pytest.raises(InvalidDeviceAutomationConfig):
        await async_call_action_from_config(hass, config, {}, None)


async def test_get_action_capabilities(hass: HomeAssistant) -> None:
    """Test capabilities returns empty dict."""
    result = await async_get_action_capabilities(hass, {})
    assert result == {}
