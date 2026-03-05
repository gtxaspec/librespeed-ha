"""Tests for LibreSpeed integration setup and unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed import get_config_value
from homeassistant.components.librespeed.const import DOMAIN


async def test_setup_entry_native_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test successful setup with native backend."""
    with patch("homeassistant.components.librespeed.asyncio.sleep"):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None
    assert mock_config_entry.runtime_data.coordinator is not None
    assert mock_config_entry.runtime_data.session is not None


async def test_setup_entry_cli_success(
    hass: HomeAssistant,
    mock_config_entry_cli: MockConfigEntry,
    mock_cli_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test successful setup with CLI backend."""
    with patch("homeassistant.components.librespeed.asyncio.sleep"):
        await hass.config_entries.async_setup(mock_config_entry_cli.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry_cli.state is ConfigEntryState.LOADED
    assert mock_config_entry_cli.runtime_data is not None
    assert mock_config_entry_cli.runtime_data.session is None


async def test_setup_entry_cli_download_fails(
    hass: HomeAssistant,
    mock_config_entry_cli: MockConfigEntry,
    mock_store: AsyncMock,
) -> None:
    """Test CLI setup fails when download fails."""
    with (
        patch(
            "homeassistant.components.librespeed.LibreSpeedCLI",
            autospec=True,
        ) as mock_cls,
        patch("homeassistant.components.librespeed.asyncio.sleep"),
    ):
        client = mock_cls.return_value
        client.check_cli_exists = AsyncMock(return_value=False)
        client.ensure_cli_available = AsyncMock(return_value=False)

        await hass.config_entries.async_setup(mock_config_entry_cli.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry_cli.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_no_auto_update(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test setup with auto_update disabled doesn't schedule first test."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry_no_auto.state is ConfigEntryState.LOADED
    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    assert coordinator.update_interval is None


async def test_setup_entry_loads_lifetime_data(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test setup loads lifetime data from storage."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    mock_store.async_load.assert_called_once()
    coordinator = mock_config_entry_no_auto.runtime_data.coordinator
    assert coordinator.lifetime_download == 1.5
    assert coordinator.lifetime_upload == 0.5


async def test_unload_entry_native(
    hass: HomeAssistant,
    mock_config_entry_no_auto: MockConfigEntry,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test unload saves lifetime data and closes session."""
    await hass.config_entries.async_setup(mock_config_entry_no_auto.entry_id)
    await hass.async_block_till_done()

    session = mock_config_entry_no_auto.runtime_data.session
    assert session is not None

    result = await hass.config_entries.async_unload(mock_config_entry_no_auto.entry_id)
    assert result is True
    mock_store.async_save.assert_called()
    assert session.closed


async def test_unload_entry_cli(
    hass: HomeAssistant,
    mock_config_entry_cli: MockConfigEntry,
    mock_cli_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test unload CLI backend (no session to close)."""
    with patch("homeassistant.components.librespeed.asyncio.sleep"):
        await hass.config_entries.async_setup(mock_config_entry_cli.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.async_unload(mock_config_entry_cli.entry_id)
    assert result is True
    mock_store.async_save.assert_called()


async def test_global_lock_created_once(
    hass: HomeAssistant,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
) -> None:
    """Test global lock is created once and reused across entries."""
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        title="Instance 1",
        data={"server_id": None, "custom_server": None, "auto_update": False,
              "scan_interval": 60, "backend_type": "native", "test_timeout": 240},
        unique_id="librespeed_1",
        entry_id="entry_1",
    )
    entry1.add_to_hass(hass)

    await hass.config_entries.async_setup(entry1.entry_id)
    await hass.async_block_till_done()

    entry2 = MockConfigEntry(
        domain=DOMAIN,
        title="Instance 2",
        data={"server_id": None, "custom_server": None, "auto_update": False,
              "scan_interval": 60, "backend_type": "native", "test_timeout": 240},
        unique_id="librespeed_2",
        entry_id="entry_2",
    )
    entry2.add_to_hass(hass)

    await hass.config_entries.async_setup(entry2.entry_id)
    await hass.async_block_till_done()

    lock1 = entry1.runtime_data.coordinator.global_lock
    lock2 = entry2.runtime_data.coordinator.global_lock
    assert lock1 is lock2


def test_get_config_value_from_options() -> None:
    """Test get_config_value returns options value when present."""
    entry = MagicMock()
    entry.options = {"key": "from_options"}
    entry.data = {"key": "from_data"}
    assert get_config_value(entry, "key") == "from_options"


def test_get_config_value_from_data() -> None:
    """Test get_config_value falls back to data."""
    entry = MagicMock()
    entry.options = {}
    entry.data = {"key": "from_data"}
    assert get_config_value(entry, "key") == "from_data"


def test_get_config_value_default() -> None:
    """Test get_config_value returns default when key not found."""
    entry = MagicMock()
    entry.options = {}
    entry.data = {}
    assert get_config_value(entry, "key", "default_val") == "default_val"


async def test_setup_entry_skip_cert_verify_warning(
    hass: HomeAssistant,
    mock_native_client: AsyncMock,
    mock_store: AsyncMock,
    caplog,
) -> None:
    """Test SSL warning is logged when skip_cert_verify is True."""
    from homeassistant.components.librespeed.const import (
        CONF_AUTO_UPDATE,
        CONF_BACKEND_TYPE,
        CONF_CUSTOM_SERVER,
        CONF_SCAN_INTERVAL,
        CONF_SERVER_ID,
        CONF_SKIP_CERT_VERIFY,
        CONF_TEST_TIMEOUT,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LibreSpeed - Custom SSL",
        data={
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: "https://speedtest.example.com/backend",
            CONF_SKIP_CERT_VERIFY: True,
            CONF_AUTO_UPDATE: False,
            CONF_SCAN_INTERVAL: 60,
            CONF_BACKEND_TYPE: "native",
            CONF_TEST_TIMEOUT: 240,
        },
        unique_id="librespeed_custom_ssl",
        entry_id="custom_ssl_entry",
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert "SSL certificate verification is disabled" in caplog.text


async def test_setup_entry_session_creation_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_store: AsyncMock,
) -> None:
    """Test setup fails gracefully when session creation fails."""
    with patch(
        "homeassistant.components.librespeed.aiohttp.TCPConnector",
        side_effect=OSError("Connection failed"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
