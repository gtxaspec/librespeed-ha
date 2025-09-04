"""Support for LibreSpeed sensors.

This module provides sensor entities for displaying speed test results
including download/upload speeds, latency, data transferred, and server
information. All sensors update automatically based on the coordinator's
data and properly handle unavailable states.

Sensor Types:
- Speed sensors: Download/Upload (Mbps)
- Latency sensors: Ping/Jitter (ms)
- Data sensors: Bytes sent/received (MB)
- Information sensors: Server details, timestamps
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import LibreSpeedConfigEntry, LibreSpeedRuntimeData
from .coordinator import LibreSpeedDataUpdateCoordinator
from .entity import LibreSpeedBaseEntity
from .const import (
    ATTR_BYTES_RECEIVED,
    ATTR_BYTES_SENT,
    ATTR_DOWNLOAD,
    ATTR_JITTER,
    ATTR_LIFETIME_DOWNLOAD,
    ATTR_LIFETIME_UPLOAD,
    ATTR_PING,
    ATTR_SERVER_LOCATION,
    ATTR_SERVER_NAME,
    ATTR_SERVER_SPONSOR,
    ATTR_TIMESTAMP,
    ATTR_UPLOAD,
    DOMAIN,
    LOGGER_NAME,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True, kw_only=True)
class LibreSpeedSensorEntityDescription(SensorEntityDescription):
    """Describes LibreSpeed sensor entity.
    
    Extends the base SensorEntityDescription with an optional
    attribute field to map sensor values to specific data attributes
    from the coordinator's data dictionary.
    """
    
    # The attribute key in coordinator data to extract the value from
    # If None, the sensor's key is used as the attribute name
    attribute: str | None = None


# Define all available sensor types with their configurations
# Each sensor maps to a specific metric from the speed test results
SENSOR_TYPES: tuple[LibreSpeedSensorEntityDescription, ...] = (
    LibreSpeedSensorEntityDescription(
        key="download",
        name="Download Speed",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_DOWNLOAD,
        # Primary measurement - no category
    ),
    LibreSpeedSensorEntityDescription(
        key="upload",
        name="Upload Speed",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_UPLOAD,
        # Primary measurement - no category
    ),
    LibreSpeedSensorEntityDescription(
        key="ping",
        name="Ping",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_PING,
        # Primary measurement - no category
    ),
    LibreSpeedSensorEntityDescription(
        key="jitter",
        name="Jitter",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_JITTER,
        # Important metric - users want to see jitter
    ),
    LibreSpeedSensorEntityDescription(
        key="data_downloaded",
        name="Data Downloaded",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_BYTES_RECEIVED,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Keep enabled - users want to see data transferred
    ),
    LibreSpeedSensorEntityDescription(
        key="data_uploaded",
        name="Data Uploaded",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_BYTES_SENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Keep enabled - users want to see data transferred
    ),
    LibreSpeedSensorEntityDescription(
        key="server_name",
        name="Server Name",
        attribute=ATTR_SERVER_NAME,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Keep enabled - users want to know which server was used
    ),
    LibreSpeedSensorEntityDescription(
        key="last_test",
        name="Last Test",
        device_class=SensorDeviceClass.TIMESTAMP,
        attribute=ATTR_TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="lifetime_download",
        name="Lifetime Download",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        attribute=ATTR_LIFETIME_DOWNLOAD,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="lifetime_upload",
        name="Lifetime Upload",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        attribute=ATTR_LIFETIME_UPLOAD,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LibreSpeed sensors."""
    runtime_data: LibreSpeedRuntimeData = config_entry.runtime_data
    coordinator = runtime_data.coordinator
    
    async_add_entities(
        LibreSpeedSensor(coordinator, description, config_entry) 
        for description in SENSOR_TYPES
    )


class LibreSpeedSensor(LibreSpeedBaseEntity, SensorEntity):
    """Implementation of a LibreSpeed sensor."""
    
    entity_description: LibreSpeedSensorEntityDescription
    
    def __init__(
        self,
        coordinator: LibreSpeedDataUpdateCoordinator,
        description: LibreSpeedSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        # Base class handles coordinator, unique_id, and device_info
        super().__init__(coordinator, description)
        self._entry = entry
    
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        if self.entity_description.attribute:
            value = self.coordinator.data.get(self.entity_description.attribute)
            
            # Convert bytes to megabytes for data size sensors
            if self.entity_description.key in ("data_downloaded", "data_uploaded"):
                if value is not None:
                    return round(value / 1_000_000, 2)  # Convert bytes to MB
            
            # Return lifetime data as-is (already in GB)
            return value
        
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        
        if self.entity_description.key == "download":
            return {
                "bytes_received": self.coordinator.data.get(ATTR_BYTES_RECEIVED, 0),
            }
        elif self.entity_description.key == "upload":
            return {
                "bytes_sent": self.coordinator.data.get(ATTR_BYTES_SENT, 0),
            }
        elif self.entity_description.key == "server_name":
            return {
                "location": self.coordinator.data.get(ATTR_SERVER_LOCATION, "Unknown"),
                "sponsor": self.coordinator.data.get(ATTR_SERVER_SPONSOR, "Unknown"),
            }
        
        return {}
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()