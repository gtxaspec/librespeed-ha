"""Device actions for LibreSpeed integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import LibreSpeedRuntimeData
from .const import DOMAIN

ACTION_TYPES = {"run_speed_test"}

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
    }
)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions for LibreSpeed devices."""
    return [
        {
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "run_speed_test",
        }
    ]


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: dict[str, Any],
    context: Context | None,
) -> None:
    """Execute a device action."""
    if config[CONF_TYPE] not in ACTION_TYPES:
        raise InvalidDeviceAutomationConfig(
            f"Unsupported action type {config[CONF_TYPE]}"
        )
    
    # Find the coordinator for this device
    device_id = config[CONF_DEVICE_ID]
    
    # Search through all config entries to find the one for this device
    for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
        if isinstance(entry_data, LibreSpeedRuntimeData):
            coordinator = entry_data.coordinator
            # Check if this coordinator's device matches
            if (DOMAIN, coordinator.config_entry.entry_id) in \
               hass.data.get("device_registry", {}).get("devices", {}).get(device_id, {}).get("identifiers", set()):
                # Found the right coordinator, trigger speed test
                await coordinator.async_run_speedtest()
                return
    
    raise InvalidDeviceAutomationConfig(
        f"Could not find LibreSpeed instance for device {device_id}"
    )


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return {}