"""Base entity for LibreSpeed integration."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LibreSpeedDataUpdateCoordinator
from .const import DOMAIN


class LibreSpeedBaseEntity(CoordinatorEntity[LibreSpeedDataUpdateCoordinator]):
    """Base entity for LibreSpeed integration.
    
    All LibreSpeed entities should inherit from this base class.
    It provides common functionality including:
    - Device information
    - Entity naming
    - Unique ID generation
    - Coordinator integration
    """
    
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LibreSpeedDataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the base entity.
        
        Args:
            coordinator: The data update coordinator
            entity_description: The entity description
        """
        super().__init__(coordinator)
        self.entity_description = entity_description
        
        # Generate unique ID based on config entry and entity key
        config_entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{config_entry_id}_{entity_description.key}"
        
        # Set device info for grouping entities
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            name=coordinator.entry_title,
            manufacturer="LibreSpeed",
            model="Speed Test",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://librespeed.org/",
        )
    
    @property
    def available(self) -> bool:
        """Return if entity is available.
        
        Entity is available if coordinator has data.
        """
        return self.coordinator.last_update_success and self.coordinator.data is not None