"""Support for LibreSpeed sensors."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LibreSpeedConfigEntry
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
    LOGGER_NAME,
)
from .coordinator import LibreSpeedDataUpdateCoordinator
from .entity import LibreSpeedBaseEntity

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
        translation_key="download",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_DOWNLOAD,
    ),
    LibreSpeedSensorEntityDescription(
        key="upload",
        translation_key="upload",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_UPLOAD,
    ),
    LibreSpeedSensorEntityDescription(
        key="ping",
        translation_key="ping",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_PING,
    ),
    LibreSpeedSensorEntityDescription(
        key="jitter",
        translation_key="jitter",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_JITTER,
    ),
    LibreSpeedSensorEntityDescription(
        key="data_downloaded",
        translation_key="data_downloaded",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_BYTES_RECEIVED,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="data_uploaded",
        translation_key="data_uploaded",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        attribute=ATTR_BYTES_SENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="server_name",
        translation_key="server_name",
        attribute=ATTR_SERVER_NAME,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="last_test",
        translation_key="last_test",
        device_class=SensorDeviceClass.TIMESTAMP,
        attribute=ATTR_TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="lifetime_download",
        translation_key="lifetime_download",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        attribute=ATTR_LIFETIME_DOWNLOAD,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LibreSpeedSensorEntityDescription(
        key="lifetime_upload",
        translation_key="lifetime_upload",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        attribute=ATTR_LIFETIME_UPLOAD,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LibreSpeedConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the LibreSpeed sensors."""
    coordinator = config_entry.runtime_data.coordinator

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
        entry: LibreSpeedConfigEntry,
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
        if self.entity_description.key == "upload":
            return {
                "bytes_sent": self.coordinator.data.get(ATTR_BYTES_SENT, 0),
            }
        if self.entity_description.key == "server_name":
            return {
                "location": self.coordinator.data.get(ATTR_SERVER_LOCATION, "Unknown"),
                "sponsor": self.coordinator.data.get(ATTR_SERVER_SPONSOR, "Unknown"),
            }

        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
