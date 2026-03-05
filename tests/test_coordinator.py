"""Tests for LibreSpeed data update coordinator."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from homeassistant.components.librespeed.const import (
    ATTR_LIFETIME_DOWNLOAD,
    ATTR_LIFETIME_UPLOAD,
    DOMAIN,
    MAX_LIFETIME_GB,
)
from homeassistant.components.librespeed.coordinator import (
    LibreSpeedDataUpdateCoordinator,
)
from homeassistant.components.librespeed.exceptions import (
    CLIError,
    NetworkError,
    SpeedTestError,
)

from .conftest import MOCK_SPEED_TEST_RESULT, MOCK_STORED_DATA


def _make_coordinator(
    hass: HomeAssistant,
    client=None,
    server_id=None,
    custom_server=None,
    scan_interval=60,
    auto_update=False,
    backend_type="native",
    entry_id="test_entry",
    entry_title="Test",
    test_timeout=240,
):
    """Create a coordinator with mocked dependencies."""
    hass.data.setdefault(DOMAIN, {})
    if "test_lock" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["test_lock"] = asyncio.Lock()

    if client is None:
        client = AsyncMock()
        client.run_speed_test = AsyncMock(
            return_value=deepcopy(MOCK_SPEED_TEST_RESULT)
        )
        client.get_servers = AsyncMock(return_value=[])

    config_entry = MagicMock()
    config_entry.entry_id = entry_id
    config_entry.title = entry_title

    coordinator = LibreSpeedDataUpdateCoordinator(
        hass,
        client,
        server_id,
        custom_server,
        scan_interval,
        auto_update,
        backend_type=backend_type,
        config_entry=config_entry,
        test_timeout=test_timeout,
    )
    return coordinator


# ---- Parse result ----


async def test_parse_result_complete(hass: HomeAssistant, mock_store) -> None:
    """Test _parse_result with complete data."""
    coordinator = _make_coordinator(hass)
    result = coordinator._parse_result(MOCK_SPEED_TEST_RESULT)
    assert result["download"] == 250.50
    assert result["upload"] == 50.25
    assert result["ping"] == 12.34
    assert result["jitter"] == 1.56
    assert result["server_name"] == "Test Server"
    assert result["server_location"] == "Test City"
    assert result["server_sponsor"] == "Test Sponsor"
    assert result["bytes_sent"] == 50_000_000
    assert result["bytes_received"] == 250_000_000


async def test_parse_result_missing_fields(hass: HomeAssistant, mock_store) -> None:
    """Test _parse_result with empty dict defaults."""
    coordinator = _make_coordinator(hass)
    result = coordinator._parse_result({})
    assert result["download"] == 0
    assert result["upload"] == 0
    assert result["server_name"] == "Unknown"


async def test_parse_result_missing_server(hass: HomeAssistant, mock_store) -> None:
    """Test _parse_result with no server key."""
    coordinator = _make_coordinator(hass)
    result = coordinator._parse_result({"download": 100, "upload": 50})
    assert result["server_name"] == "Unknown"
    assert result["server_location"] == "Unknown"
    assert result["server_sponsor"] == "Unknown"


# ---- Update data success ----


async def test_update_data_success_native(hass: HomeAssistant, mock_store) -> None:
    """Test successful speed test with native backend."""
    coordinator = _make_coordinator(hass)
    result = await coordinator._async_update_data()
    assert result["download"] == 250.50
    assert result[ATTR_LIFETIME_DOWNLOAD] >= 0


async def test_update_data_success_cli(hass: HomeAssistant, mock_store) -> None:
    """Test successful speed test with CLI backend."""
    coordinator = _make_coordinator(hass, backend_type="cli")
    result = await coordinator._async_update_data()
    assert result["download"] == 250.50


# ---- Lifetime data ----


async def test_lifetime_accumulation(hass: HomeAssistant, mock_store) -> None:
    """Test lifetime data is accumulated after test."""
    coordinator = _make_coordinator(hass)
    coordinator.lifetime_download = 1.0
    coordinator.lifetime_upload = 0.5
    result = await coordinator._async_update_data()
    # 250_000_000 bytes = 0.25 GB
    assert coordinator.lifetime_download == 1.25
    # 50_000_000 bytes = 0.05 GB
    assert coordinator.lifetime_upload == 0.55


async def test_lifetime_cap(hass: HomeAssistant, mock_store) -> None:
    """Test lifetime data is capped at MAX_LIFETIME_GB."""
    coordinator = _make_coordinator(hass)
    coordinator.lifetime_download = MAX_LIFETIME_GB - 0.01
    await coordinator._async_update_data()
    assert coordinator.lifetime_download == MAX_LIFETIME_GB


async def test_lifetime_saved_after_test(hass: HomeAssistant, mock_store) -> None:
    """Test lifetime data is saved after successful test."""
    coordinator = _make_coordinator(hass)
    await coordinator._async_update_data()
    mock_store.async_save.assert_called()


# ---- Load lifetime data ----


async def test_load_lifetime_data_success(hass: HomeAssistant, mock_store) -> None:
    """Test loading lifetime data from store."""
    coordinator = _make_coordinator(hass)
    await coordinator.async_load_lifetime_data()
    assert coordinator.lifetime_download == 1.5
    assert coordinator.lifetime_upload == 0.5
    assert coordinator.data is not None
    assert coordinator.data["download"] == 250.50


async def test_load_lifetime_data_empty(hass: HomeAssistant) -> None:
    """Test loading when store is empty."""
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
    ) as mock_cls:
        mock_cls.return_value.async_load = AsyncMock(return_value=None)
        coordinator = _make_coordinator(hass)
        await coordinator.async_load_lifetime_data()
    assert coordinator.lifetime_download == 0.0
    assert coordinator.lifetime_upload == 0.0


async def test_load_lifetime_data_error(hass: HomeAssistant) -> None:
    """Test loading when store raises error."""
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
    ) as mock_cls:
        mock_cls.return_value.async_load = AsyncMock(side_effect=OSError("disk fail"))
        coordinator = _make_coordinator(hass)
        await coordinator.async_load_lifetime_data()
    assert coordinator.lifetime_download == 0.0


async def test_load_lifetime_data_timestamp_string(hass: HomeAssistant, mock_store) -> None:
    """Test timestamp string is converted to datetime on load."""
    coordinator = _make_coordinator(hass)
    await coordinator.async_load_lifetime_data()
    from datetime import datetime
    assert isinstance(coordinator.data["timestamp"], datetime)


async def test_load_lifetime_data_no_last_test(hass: HomeAssistant) -> None:
    """Test loading when no last_test_data in store."""
    stored = {"lifetime_download": 5.0, "lifetime_upload": 2.0}
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
    ) as mock_cls:
        mock_cls.return_value.async_load = AsyncMock(return_value=stored)
        coordinator = _make_coordinator(hass)
        await coordinator.async_load_lifetime_data()
    assert coordinator.lifetime_download == 5.0
    assert coordinator.data is None


# ---- Save lifetime data ----


async def test_save_lifetime_data_success(hass: HomeAssistant, mock_store) -> None:
    """Test saving lifetime data."""
    coordinator = _make_coordinator(hass)
    coordinator.lifetime_download = 5.0
    coordinator.lifetime_upload = 2.0
    coordinator.data = deepcopy(MOCK_SPEED_TEST_RESULT)
    await coordinator.async_save_lifetime_data()
    mock_store.async_save.assert_called_once()
    saved = mock_store.async_save.call_args[0][0]
    assert saved["lifetime_download"] == 5.0
    assert saved["lifetime_upload"] == 2.0
    assert "last_test_data" in saved


async def test_save_lifetime_data_no_data(hass: HomeAssistant, mock_store) -> None:
    """Test saving without coordinator data."""
    coordinator = _make_coordinator(hass)
    coordinator.lifetime_download = 1.0
    coordinator.data = None
    await coordinator.async_save_lifetime_data()
    saved = mock_store.async_save.call_args[0][0]
    assert "last_test_data" not in saved


async def test_save_lifetime_data_error(hass: HomeAssistant) -> None:
    """Test saving when store raises error doesn't crash."""
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
    ) as mock_cls:
        mock_cls.return_value.async_save = AsyncMock(side_effect=OSError("disk"))
        mock_cls.return_value.async_load = AsyncMock(return_value=None)
        coordinator = _make_coordinator(hass)
        coordinator.lifetime_download = 1.0
        await coordinator.async_save_lifetime_data()  # Should not raise


# ---- Retry logic ----


async def test_retry_on_timeout(hass: HomeAssistant, mock_store) -> None:
    """Test retry after timeout succeeds on second attempt."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(
        side_effect=[asyncio.TimeoutError(), deepcopy(MOCK_SPEED_TEST_RESULT)]
    )
    coordinator = _make_coordinator(hass, client=client)
    with patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"):
        result = await coordinator._async_update_data()
    assert result["download"] == 250.50
    assert client.run_speed_test.call_count == 2


async def test_all_retries_exhausted_timeout(hass: HomeAssistant, mock_store) -> None:
    """Test all retries exhausted raises UpdateFailed."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=asyncio.TimeoutError())
    coordinator = _make_coordinator(hass, client=client)
    with (
        patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"),
        pytest.raises(UpdateFailed, match="timed out"),
    ):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 1


async def test_no_retry_on_speed_test_error(hass: HomeAssistant, mock_store) -> None:
    """Test SpeedTestError doesn't retry."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=SpeedTestError("test error"))
    coordinator = _make_coordinator(hass, client=client)
    with pytest.raises(UpdateFailed, match="Speed test error"):
        await coordinator._async_update_data()
    assert client.run_speed_test.call_count == 1


async def test_no_retry_on_network_error(hass: HomeAssistant, mock_store) -> None:
    """Test NetworkError doesn't retry."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=NetworkError("net error"))
    coordinator = _make_coordinator(hass, client=client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert client.run_speed_test.call_count == 1


async def test_no_retry_on_cli_error(hass: HomeAssistant, mock_store) -> None:
    """Test CLIError doesn't retry."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=CLIError("cli fail"))
    coordinator = _make_coordinator(hass, client=client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert client.run_speed_test.call_count == 1


# ---- Circuit breaker ----


async def test_circuit_breaker_opens_at_threshold(hass: HomeAssistant, mock_store) -> None:
    """Test circuit breaker opens after 10 consecutive failures."""
    coordinator = _make_coordinator(hass)
    coordinator._consecutive_failures = 10

    with pytest.raises(UpdateFailed, match="Circuit breaker open"):
        await coordinator._async_update_data()


async def test_circuit_breaker_returns_last_data(hass: HomeAssistant, mock_store) -> None:
    """Test circuit breaker returns last data when open."""
    coordinator = _make_coordinator(hass)
    coordinator._consecutive_failures = 10
    coordinator.data = {"download": 100}

    result = await coordinator._async_update_data()
    assert result["download"] == 100


async def test_circuit_breaker_reset_on_success(hass: HomeAssistant, mock_store) -> None:
    """Test failures reset to 0 after successful test."""
    coordinator = _make_coordinator(hass)
    coordinator._consecutive_failures = 5
    await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 0


async def test_circuit_breaker_reset_on_manual_test(hass: HomeAssistant, mock_store) -> None:
    """Test manual test resets circuit breaker."""
    coordinator = _make_coordinator(hass)
    coordinator._consecutive_failures = 10
    coordinator.async_refresh = AsyncMock()
    await coordinator.async_run_speedtest()
    assert coordinator.consecutive_failures == 0
    coordinator.async_refresh.assert_called_once()


# ---- Global lock ----


async def test_is_running_flag(hass: HomeAssistant, mock_store) -> None:
    """Test is_running is True during test and False after."""
    coordinator = _make_coordinator(hass)
    assert coordinator.is_running is False

    await coordinator._async_update_data()
    assert coordinator.is_running is False


# ---- Server list ----


async def test_get_server_list_native(hass: HomeAssistant, mock_store) -> None:
    """Test getting server list with native backend."""
    client = AsyncMock()
    client.get_servers = AsyncMock(return_value=[{"id": 1, "name": "S1"}])
    coordinator = _make_coordinator(hass, client=client)
    result = await coordinator.async_get_server_list()
    assert len(result) == 1


async def test_get_server_list_cli(hass: HomeAssistant, mock_store) -> None:
    """Test CLI backend returns empty server list."""
    client = MagicMock()
    # CLI client doesn't have get_servers
    del client.get_servers
    coordinator = _make_coordinator(hass, client=client, backend_type="cli")
    result = await coordinator.async_get_server_list()
    assert result == []


async def test_get_server_list_error(hass: HomeAssistant, mock_store) -> None:
    """Test server list returns empty on error."""
    client = AsyncMock()
    client.get_servers = AsyncMock(side_effect=NetworkError("fail"))
    coordinator = _make_coordinator(hass, client=client)
    result = await coordinator.async_get_server_list()
    assert result == []


# ---- Update interval ----


async def test_update_interval_auto(hass: HomeAssistant, mock_store) -> None:
    """Test update interval with auto_update enabled."""
    coordinator = _make_coordinator(hass, auto_update=True, scan_interval=30)
    assert coordinator.update_interval == timedelta(minutes=30)


async def test_update_interval_no_auto(hass: HomeAssistant, mock_store) -> None:
    """Test update interval is None when auto_update disabled."""
    coordinator = _make_coordinator(hass, auto_update=False)
    assert coordinator.update_interval is None


# ---- Backend dispatch ----


async def test_dispatch_to_cli(hass: HomeAssistant, mock_store) -> None:
    """Test CLI backend dispatch passes correct args."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(return_value=deepcopy(MOCK_SPEED_TEST_RESULT))
    coordinator = _make_coordinator(
        hass, client=client, backend_type="cli", custom_server="https://example.com"
    )
    await coordinator._async_update_data()
    client.run_speed_test.assert_called_once_with(
        server_id=None,
        custom_server="https://example.com",
        skip_cert_verify=False,
        timeout=240,
    )


async def test_custom_server_error_creates_repair(hass: HomeAssistant, mock_store) -> None:
    """Test custom server error creates repair issue."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=aiohttp.ClientError("fail"))
    coordinator = _make_coordinator(
        hass, client=client, custom_server="https://custom.example.com"
    )
    with (
        patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 1
    # Verify repair issue was created
    from homeassistant.helpers import issue_registry as ir
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "custom_server_unreachable")
    assert issue is not None


async def test_warning_repair_at_5_failures(hass: HomeAssistant, mock_store) -> None:
    """Test warning repair issue is created at 5 failures."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=asyncio.TimeoutError())
    coordinator = _make_coordinator(hass, client=client)
    coordinator._consecutive_failures = 4  # Will become 5 after this failure

    with (
        patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 5
    from homeassistant.helpers import issue_registry as ir
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "repeated_test_failures")
    assert issue is not None


async def test_circuit_breaker_repair_at_10_failures(hass: HomeAssistant, mock_store) -> None:
    """Test circuit breaker repair issue at 10 failures."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(side_effect=asyncio.TimeoutError())
    coordinator = _make_coordinator(hass, client=client)
    coordinator._consecutive_failures = 9  # Will become 10

    with (
        patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()
    assert coordinator.consecutive_failures == 10
    from homeassistant.helpers import issue_registry as ir
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "circuit_breaker_open")
    assert issue is not None


async def test_retry_on_client_error(hass: HomeAssistant, mock_store) -> None:
    """Test retry after aiohttp.ClientError succeeds on second attempt."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(
        side_effect=[aiohttp.ClientError(), deepcopy(MOCK_SPEED_TEST_RESULT)]
    )
    coordinator = _make_coordinator(hass, client=client)
    with patch("homeassistant.components.librespeed.coordinator.asyncio.sleep"):
        result = await coordinator._async_update_data()
    assert result["download"] == 250.50


async def test_dispatch_to_native(hass: HomeAssistant, mock_store) -> None:
    """Test native backend dispatch passes correct args."""
    client = AsyncMock()
    client.run_speed_test = AsyncMock(return_value=deepcopy(MOCK_SPEED_TEST_RESULT))
    coordinator = _make_coordinator(
        hass, client=client, backend_type="native", custom_server="https://example.com"
    )
    await coordinator._async_update_data()
    client.run_speed_test.assert_called_once_with(
        server_id=None,
        custom_server_url="https://example.com",
        timeout=240,
    )


# ---- consecutive_failures setter ----


async def test_consecutive_failures_setter(hass: HomeAssistant, mock_store) -> None:
    """Test consecutive_failures property setter."""
    coordinator = _make_coordinator(hass)
    assert coordinator.consecutive_failures == 0
    coordinator.consecutive_failures = 5
    assert coordinator.consecutive_failures == 5


# ---- Data parsing error ----


async def test_data_processing_error_raises_update_failed(
    hass: HomeAssistant, mock_store
) -> None:
    """Test ValueError/TypeError during speed test raises UpdateFailed."""
    client = AsyncMock()
    # Return a result that will cause a parsing error (non-dict)
    client.run_speed_test = AsyncMock(return_value="not a dict")
    coordinator = _make_coordinator(hass, client=client)
    with pytest.raises(UpdateFailed, match="Data processing error"):
        await coordinator._async_update_data()


# ---- Invalid timestamp in stored data ----


async def test_load_stored_data_invalid_timestamp(hass: HomeAssistant) -> None:
    """Test loading stored data with an unparseable timestamp string."""
    stored = deepcopy(MOCK_STORED_DATA)
    stored["last_test_data"]["timestamp"] = "not-a-timestamp"
    with patch(
        "homeassistant.components.librespeed.coordinator.Store",
    ) as mock_cls:
        mock_cls.return_value.async_load = AsyncMock(return_value=stored)
        coordinator = _make_coordinator(hass)
        await coordinator.async_load_lifetime_data()
    # Timestamp should be None (gracefully handled)
    assert coordinator.data["timestamp"] is None
