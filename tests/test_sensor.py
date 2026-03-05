"""Tests for LibreSpeed sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed.exceptions import SpeedTestError
from homeassistant.components.librespeed.sensor import SENSOR_TYPES

from .conftest import MOCK_TIMESTAMP

# Entity IDs for mock_config_entry_no_auto (title="LibreSpeed (Manual)")
PREFIX = "sensor.librespeed_manual"


async def test_setup_creates_all_sensors(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test all 10 sensors are created through HA setup pipeline."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    expected = [
        f"{PREFIX}_download_speed",
        f"{PREFIX}_upload_speed",
        f"{PREFIX}_ping",
        f"{PREFIX}_jitter",
        f"{PREFIX}_test_data_downloaded",
        f"{PREFIX}_test_data_uploaded",
        f"{PREFIX}_lifetime_data_downloaded",
        f"{PREFIX}_lifetime_data_uploaded",
        f"{PREFIX}_server_name",
        f"{PREFIX}_last_test_time",
    ]
    for entity_id in expected:
        state = hass.states.get(entity_id)
        assert state is not None, f"Entity {entity_id} not found"


async def test_download_speed_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test download speed sensor state from stored data."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "250.5"
    assert state.attributes["unit_of_measurement"] == "Mbit/s"
    assert state.attributes["bytes_received"] == 250_000_000


async def test_upload_speed_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test upload speed sensor state and extra attributes."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_upload_speed")
    assert state.state == "50.25"
    assert state.attributes["bytes_sent"] == 50_000_000


async def test_ping_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test ping sensor state."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_ping")
    assert state.state == "12.34"
    assert state.attributes["unit_of_measurement"] == "ms"


async def test_jitter_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test jitter sensor state."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_jitter")
    assert state.state == "1.56"


async def test_data_downloaded_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test data downloaded sensor converts bytes to MB."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_test_data_downloaded")
    assert state.state == "250.0"
    assert state.attributes["unit_of_measurement"] == "MB"


async def test_data_uploaded_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test data uploaded sensor converts bytes to MB."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_test_data_uploaded")
    assert state.state == "50.0"


async def test_server_name_state_and_attributes(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test server name sensor state and extra attributes."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_server_name")
    assert state.state == "Test Server"
    assert state.attributes["location"] == "Test City"
    assert state.attributes["sponsor"] == "Test Sponsor"


async def test_last_test_time_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test last test time sensor shows ISO timestamp."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_last_test_time")
    assert state.state == "2026-03-04T12:00:00+00:00"


async def test_lifetime_download_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test lifetime download sensor shows value in GB."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_lifetime_data_downloaded")
    assert state.state == "1.5"
    assert state.attributes["unit_of_measurement"] == "GB"


async def test_lifetime_upload_state(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test lifetime upload sensor shows value in GB."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_lifetime_data_uploaded")
    assert state.state == "0.5"


async def test_sensors_unavailable_without_data(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
) -> None:
    """Test sensors show unavailable when no stored data exists."""
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
        autospec=True,
    ) as mock_store_cls:
        store = mock_store_cls.return_value
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()

        await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "unavailable"


async def test_sensor_states_update_after_speed_test(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test sensor states update when a new speed test completes."""
    mock_native_client.run_speed_test.return_value = {
        "download": 500.0,
        "upload": 100.0,
        "ping": 5.0,
        "jitter": 0.5,
        "server": {"id": 2, "name": "New Server", "location": "New City", "sponsor": "New Sponsor"},
        "timestamp": MOCK_TIMESTAMP,
        "bytes_sent": 100_000_000,
        "bytes_received": 500_000_000,
    }

    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    # Trigger a speed test via button press
    await hass.services.async_call(
        "button", "press",
        {"entity_id": "button.librespeed_manual_run_speed_test"},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "500.0"

    state = hass.states.get(f"{PREFIX}_server_name")
    assert state.state == "New Server"


async def test_sensors_unavailable_after_failed_update(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test sensors become unavailable after a failed coordinator update."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    # Verify sensors have data initially
    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "250.5"

    # Make the next speed test fail
    mock_native_client.run_speed_test.side_effect = SpeedTestError("Connection lost")

    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Sensors should be unavailable (last_update_success = False)
    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "unavailable"


async def test_sensors_recover_after_successful_update(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test sensors recover with new data after a failure then success."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    # Fail first
    mock_native_client.run_speed_test.side_effect = SpeedTestError("Temporary failure")
    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(f"{PREFIX}_download_speed").state == "unavailable"

    # Recover with new data
    mock_native_client.run_speed_test.side_effect = None
    mock_native_client.run_speed_test.return_value = {
        "download": 300.0,
        "upload": 75.0,
        "ping": 8.0,
        "jitter": 0.8,
        "server": {"id": 1, "name": "Test Server", "location": "Test City", "sponsor": "Test Sponsor"},
        "timestamp": MOCK_TIMESTAMP,
        "bytes_sent": 75_000_000,
        "bytes_received": 300_000_000,
    }
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(f"{PREFIX}_download_speed")
    assert state.state == "300.0"


# -- Entity description static tests --


def test_download_description() -> None:
    """Test download sensor description properties."""
    desc = next(d for d in SENSOR_TYPES if d.key == "download")
    assert desc.native_unit_of_measurement == UnitOfDataRate.MEGABITS_PER_SECOND
    assert desc.device_class == SensorDeviceClass.DATA_RATE
    assert desc.state_class == SensorStateClass.MEASUREMENT


def test_ping_description() -> None:
    """Test ping sensor description properties."""
    desc = next(d for d in SENSOR_TYPES if d.key == "ping")
    assert desc.native_unit_of_measurement == UnitOfTime.MILLISECONDS
    assert desc.state_class == SensorStateClass.MEASUREMENT


def test_diagnostic_category() -> None:
    """Test diagnostic sensors have correct entity category."""
    diagnostic_keys = {"data_downloaded", "data_uploaded", "server_name", "last_test", "lifetime_download", "lifetime_upload"}
    for desc in SENSOR_TYPES:
        if desc.key in diagnostic_keys:
            assert desc.entity_category == EntityCategory.DIAGNOSTIC, f"{desc.key} should be diagnostic"


def test_lifetime_sensors_description() -> None:
    """Test lifetime sensors use TOTAL_INCREASING state class."""
    for key in ("lifetime_download", "lifetime_upload"):
        desc = next(d for d in SENSOR_TYPES if d.key == key)
        assert desc.state_class == SensorStateClass.TOTAL_INCREASING
        assert desc.native_unit_of_measurement == UnitOfInformation.GIGABYTES
