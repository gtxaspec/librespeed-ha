"""Common fixtures for LibreSpeed tests."""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed.const import (
    CONF_AUTO_UPDATE,
    CONF_BACKEND_TYPE,
    CONF_CUSTOM_SERVER,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_ID,
    CONF_SKIP_CERT_VERIFY,
    CONF_TEST_TIMEOUT,
    DEFAULT_TEST_TIMEOUT,
    DOMAIN,
)

# ---- Mock Constants ----

MOCK_ENTRY_ID = "test_entry_id_12345"
MOCK_CUSTOM_SERVER = "https://speedtest.example.com/backend"
MOCK_TIMESTAMP = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)

MOCK_SPEED_TEST_RESULT = {
    "download": 250.50,
    "upload": 50.25,
    "ping": 12.34,
    "jitter": 1.56,
    "server": {
        "id": 1,
        "name": "Test Server",
        "server": "https://test.librespeed.org/",
        "location": "Test City",
        "sponsor": "Test Sponsor",
    },
    "timestamp": MOCK_TIMESTAMP,
    "bytes_sent": 50_000_000,
    "bytes_received": 250_000_000,
}

MOCK_PARSED_RESULT = {
    "download": 250.50,
    "upload": 50.25,
    "ping": 12.34,
    "jitter": 1.56,
    "server_name": "Test Server",
    "server_location": "Test City",
    "server_sponsor": "Test Sponsor",
    "timestamp": MOCK_TIMESTAMP,
    "bytes_sent": 50_000_000,
    "bytes_received": 250_000_000,
    "lifetime_download": 1.5,
    "lifetime_upload": 0.5,
}

MOCK_SERVER_LIST = [
    {
        "id": 1,
        "name": "Server One",
        "server": "https://s1.librespeed.org/",
        "location": "City A",
        "sponsor": "Sponsor A",
        "dlURL": "backend/garbage.php",
        "ulURL": "backend/empty.php",
        "pingURL": "backend/empty.php",
        "getIpURL": "backend/getIP.php",
    },
    {
        "id": 2,
        "name": "Server Two",
        "server": "https://s2.librespeed.org/",
        "location": "City B",
        "sponsor": "Sponsor B",
        "dlURL": "backend/garbage.php",
        "ulURL": "backend/empty.php",
        "pingURL": "backend/empty.php",
        "getIpURL": "backend/getIP.php",
    },
]

MOCK_STORED_DATA = {
    "lifetime_download": 1.5,
    "lifetime_upload": 0.5,
    "last_test_data": {
        "download": 250.50,
        "upload": 50.25,
        "ping": 12.34,
        "jitter": 1.56,
        "server_name": "Test Server",
        "server_location": "Test City",
        "server_sponsor": "Test Sponsor",
        "timestamp": "2026-03-04T12:00:00+00:00",
        "bytes_sent": 50_000_000,
        "bytes_received": 250_000_000,
        "lifetime_download": 1.5,
        "lifetime_upload": 0.5,
    },
}

# ---- Config Entry Data Variants ----

MOCK_CONFIG_DATA_AUTOMATIC = {
    CONF_SERVER_ID: None,
    CONF_CUSTOM_SERVER: None,
    CONF_AUTO_UPDATE: True,
    CONF_SCAN_INTERVAL: 60,
    CONF_BACKEND_TYPE: "native",
    CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
}

MOCK_CONFIG_DATA_CLI = {
    CONF_SERVER_ID: None,
    CONF_CUSTOM_SERVER: None,
    CONF_AUTO_UPDATE: True,
    CONF_SCAN_INTERVAL: 60,
    CONF_BACKEND_TYPE: "cli",
    CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
}

MOCK_CONFIG_DATA_CUSTOM_SERVER = {
    CONF_SERVER_ID: None,
    CONF_CUSTOM_SERVER: MOCK_CUSTOM_SERVER,
    CONF_SKIP_CERT_VERIFY: False,
    CONF_AUTO_UPDATE: True,
    CONF_SCAN_INTERVAL: 60,
    CONF_BACKEND_TYPE: "native",
    CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
}

MOCK_CONFIG_DATA_NO_AUTO = {
    CONF_SERVER_ID: None,
    CONF_CUSTOM_SERVER: None,
    CONF_AUTO_UPDATE: False,
    CONF_SCAN_INTERVAL: 60,
    CONF_BACKEND_TYPE: "native",
    CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
}


# ---- Fixtures ----


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a mock config entry (native, automatic)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LibreSpeed (Automatic)",
        data=deepcopy(MOCK_CONFIG_DATA_AUTOMATIC),
        unique_id="librespeed_automatic",
        entry_id=MOCK_ENTRY_ID,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_cli(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a mock config entry (CLI backend)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LibreSpeed (CLI)",
        data=deepcopy(MOCK_CONFIG_DATA_CLI),
        unique_id="librespeed_cli",
        entry_id="cli_entry_id",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_custom(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a mock config entry (custom server)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LibreSpeed - Custom",
        data=deepcopy(MOCK_CONFIG_DATA_CUSTOM_SERVER),
        unique_id=f"librespeed_{MOCK_CUSTOM_SERVER}",
        entry_id="custom_entry_id",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_no_auto(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a mock config entry (auto_update=False)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LibreSpeed (Manual)",
        data=deepcopy(MOCK_CONFIG_DATA_NO_AUTO),
        unique_id="librespeed_manual",
        entry_id="manual_entry_id",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_native_client() -> Generator[AsyncMock]:
    """Return a mocked LibreSpeedClient (native backend)."""
    with patch(
        "homeassistant.components.librespeed.LibreSpeedClient",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.get_servers = AsyncMock(return_value=deepcopy(MOCK_SERVER_LIST))
        client.get_best_server = AsyncMock(
            return_value=deepcopy(MOCK_SERVER_LIST[0])
        )
        client.run_speed_test = AsyncMock(
            return_value=deepcopy(MOCK_SPEED_TEST_RESULT)
        )
        client.servers = deepcopy(MOCK_SERVER_LIST)
        client.session = MagicMock()
        yield client


@pytest.fixture
def mock_cli_client() -> Generator[AsyncMock]:
    """Return a mocked LibreSpeedCLI (CLI backend)."""
    with patch(
        "homeassistant.components.librespeed.LibreSpeedCLI",
        autospec=True,
    ) as mock_cls:
        client = mock_cls.return_value
        client.check_cli_exists = AsyncMock(return_value=True)
        client.ensure_cli_available = AsyncMock(return_value=True)
        client.is_cli_supported = MagicMock(return_value=True)
        client.run_speed_test = AsyncMock(
            return_value=deepcopy(MOCK_SPEED_TEST_RESULT)
        )
        client.cli_path = MagicMock()
        client.cli_path.exists.return_value = True
        yield client


@pytest.fixture
def mock_store() -> Generator[AsyncMock]:
    """Return a mocked Store for lifetime data."""
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
        autospec=True,
    ) as mock_store_cls:
        store = mock_store_cls.return_value
        store.async_load = AsyncMock(return_value=deepcopy(MOCK_STORED_DATA))
        store.async_save = AsyncMock()
        yield store
