"""Support for LibreSpeed button."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LibreSpeedConfigEntry, LibreSpeedRuntimeData
from .coordinator import LibreSpeedDataUpdateCoordinator
from .entity import LibreSpeedBaseEntity
from .const import DOMAIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LibreSpeed button."""
    runtime_data: LibreSpeedRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator
    
    async_add_entities([LibreSpeedButton(coordinator, config_entry)])


class LibreSpeedButton(LibreSpeedBaseEntity, ButtonEntity):
    """Implementation of a LibreSpeed button."""
    
    _attr_name = "Manual Speed Test"
    
    def __init__(
        self,
        coordinator: LibreSpeedDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the button."""
        # Create a button description for the base class
        description = ButtonEntityDescription(
            key="run_test",
            name="Manual Speed Test",
        )
        super().__init__(coordinator, description)
        self._entry = entry
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Button is unavailable when any test is running (global)
        global_lock = self.coordinator._global_lock
        return not global_lock.locked() and not self.coordinator.is_waiting
    
    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual speed test button pressed")
        
        # Double-check if a test is already running (shouldn't happen with available property)
        if self.coordinator.is_running:
            _LOGGER.warning("Speed test already in progress, ignoring button press")
            return
            
        try:
            await self.coordinator.async_refresh()
            _LOGGER.info("Manual speed test completed successfully")
        except (asyncio.TimeoutError, aiohttp.ClientError, ValueError) as e:
            _LOGGER.error("Manual speed test failed: %s", e, exc_info=True)
            raise
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        global_lock = self.coordinator._global_lock
        
        if self.coordinator.is_running:
            status = "Running test"
        elif self.coordinator.is_waiting:
            status = "Waiting in queue"
        elif global_lock.locked():
            status = "Another instance testing"
        else:
            status = "Ready"
        
        return {
            "status": status,
            "test_running": self.coordinator.is_running,
            "waiting_in_queue": self.coordinator.is_waiting,
        }