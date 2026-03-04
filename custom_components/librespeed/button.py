"""Support for LibreSpeed button."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LibreSpeedConfigEntry
from .const import LOGGER_NAME
from .coordinator import LibreSpeedDataUpdateCoordinator
from .entity import LibreSpeedBaseEntity

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LibreSpeedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LibreSpeed button."""
    coordinator = config_entry.runtime_data.coordinator

    async_add_entities([LibreSpeedButton(coordinator, config_entry)])


class LibreSpeedButton(LibreSpeedBaseEntity, ButtonEntity):
    """Implementation of a LibreSpeed button."""

    def __init__(
        self,
        coordinator: LibreSpeedDataUpdateCoordinator,
        entry: LibreSpeedConfigEntry,
    ) -> None:
        """Initialize the button."""
        description = ButtonEntityDescription(
            key="run_test",
            translation_key="run_test",
        )
        super().__init__(coordinator, description)
        self._entry = entry

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            not self.coordinator.global_lock.locked()
            and not self.coordinator.is_waiting
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Manual speed test button pressed")
        if self.coordinator.is_running:
            _LOGGER.warning("Speed test already in progress, ignoring button press")
            return
        await self.coordinator.async_refresh()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.is_running:
            status = "Running test"
        elif self.coordinator.is_waiting:
            status = "Waiting in queue"
        elif self.coordinator.global_lock.locked():
            status = "Another instance testing"
        else:
            status = "Ready"

        return {
            "status": status,
            "test_running": self.coordinator.is_running,
            "waiting_in_queue": self.coordinator.is_waiting,
        }
