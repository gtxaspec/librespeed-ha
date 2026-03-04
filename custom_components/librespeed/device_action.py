"""Device actions for LibreSpeed integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import InvalidDeviceAutomationConfig
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
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
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)

    if device_entry:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if (DOMAIN, entry.entry_id) in device_entry.identifiers:
                if hasattr(entry, "runtime_data") and isinstance(
                    entry.runtime_data, LibreSpeedRuntimeData
                ):
                    await entry.runtime_data.coordinator.async_run_speedtest()
                    return

    raise InvalidDeviceAutomationConfig(
        f"Could not find LibreSpeed instance for device {device_id}"
    )


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return {}
