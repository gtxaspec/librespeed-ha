"""Tests for LibreSpeed button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed.exceptions import SpeedTestError

BUTTON_ENTITY_ID = "button.librespeed_manual_run_speed_test"


async def test_button_entity_created(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button entity is created through HA setup pipeline."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state is not None


async def test_button_press_triggers_speed_test(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test pressing button triggers a speed test through the coordinator."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "button", "press",
        {"entity_id": BUTTON_ENTITY_ID},
        blocking=True,
    )

    mock_native_client.run_speed_test.assert_called()


async def test_button_extra_attributes_ready(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button shows Ready status when idle."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state.attributes["status"] == "Ready"
    assert state.attributes["test_running"] is False
    assert state.attributes["waiting_in_queue"] is False


async def test_button_unavailable_when_lock_held(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button becomes unavailable when global lock is held."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry_no_auto.runtime_data.coordinator

    await coordinator.global_lock.acquire()
    try:
        coordinator.async_update_listeners()
        await hass.async_block_till_done()

        state = hass.states.get(BUTTON_ENTITY_ID)
        assert state.state == "unavailable"
    finally:
        coordinator.global_lock.release()


async def test_button_press_ignored_when_running(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button press is ignored when a speed test is already running."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    coordinator.is_running = True
    mock_native_client.run_speed_test.reset_mock()

    await hass.services.async_call(
        "button", "press",
        {"entity_id": BUTTON_ENTITY_ID},
        blocking=True,
    )

    mock_native_client.run_speed_test.assert_not_called()


async def test_button_attributes_show_running(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button attributes show Running when is_running is True."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    coordinator.is_running = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state.attributes["status"] == "Running test"
    assert state.attributes["test_running"] is True


async def test_button_available_after_failed_test(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test button returns to available state after a failed speed test."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    # Make speed test fail
    mock_native_client.run_speed_test.side_effect = SpeedTestError("Test failed")

    await hass.services.async_call(
        "button", "press",
        {"entity_id": BUTTON_ENTITY_ID},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Button should be available again (not stuck in running state)
    state = hass.states.get(BUTTON_ENTITY_ID)
    assert state.attributes["status"] == "Ready"
    assert state.attributes["test_running"] is False
