"""Support for LibreSpeed binary sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
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
    """Set up the LibreSpeed binary sensor."""
    runtime_data: LibreSpeedRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator
    
    async_add_entities([LibreSpeedRunningSensor(coordinator, config_entry)])


class LibreSpeedRunningSensor(LibreSpeedBaseEntity, BinarySensorEntity):
    """Implementation of a LibreSpeed running status sensor."""
    
    _attr_name = "Speed Test Running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False  # We'll update based on coordinator callbacks
    
    def __init__(
        self,
        coordinator: LibreSpeedDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        # Create a binary sensor description for the base class
        description = BinarySensorEntityDescription(
            key="running",
            name="Speed Test Running",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        super().__init__(coordinator, description)
        self._entry = entry
        _LOGGER.debug("Binary sensor initialized, is_running: %s", coordinator.is_running)
    
    @property
    def available(self) -> bool:
        """Return if entity is available.
        
        Binary sensor should always be available to show running state.
        """
        return True
    
    @property
    def is_on(self) -> bool:
        """Return true if any speed test is running globally.
        
        We primarily rely on the global lock state, but also check our
        instance's waiting state to show activity during queue waiting.
        
        Note: We don't check is_running alone as it may be out of sync
        with the lock during transitions. The lock is the authoritative
        source for "any test running globally".
        """
        # Check if any instance holds the global lock
        global_lock = self.coordinator._global_lock
        global_lock_held = global_lock.locked()
        
        # Also show as "on" if we're waiting for the lock
        # This provides better UX by showing activity during wait
        is_waiting = self.coordinator.is_waiting
        
        # Return true if test is running or waiting
        is_any_running = global_lock_held or is_waiting
        
        _LOGGER.debug("Binary sensor: global_lock=%s, waiting=%s, result=%s", 
                     global_lock_held, is_waiting, is_any_running)
        return is_any_running
    
    @property
    def icon(self) -> str:
        """Return the icon."""
        if self.is_on:
            return "mdi:speedometer"
        return "mdi:speedometer-slow"
    
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Binary sensor handling coordinator update, is_running: %s", self.coordinator.is_running)
        self.async_write_ha_state()
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "this_instance_running": self.coordinator.is_running,
            "this_instance_waiting": self.coordinator.is_waiting,
            "instance_name": self.coordinator.entry_title,
        }