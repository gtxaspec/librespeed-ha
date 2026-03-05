"""Tests for LibreSpeed config flow."""

from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from homeassistant.components.librespeed.config_flow import (
    _parse_server_selection,
    get_server_list,
)
from homeassistant.components.librespeed.const import (
    CONF_AUTO_UPDATE,
    CONF_BACKEND_TYPE,
    CONF_CUSTOM_SERVER,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_ID,
    CONF_SKIP_CERT_VERIFY,
    CONF_TEST_TIMEOUT,
    DEFAULT_TEST_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

from .conftest import MOCK_SERVER_LIST


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[None]:
    """Prevent actual integration setup during config flow tests."""
    with (
        patch(
            "homeassistant.components.librespeed.async_setup_entry",
            return_value=True,
        ),
        patch(
            "homeassistant.components.librespeed.async_unload_entry",
            return_value=True,
        ),
    ):
        yield


@pytest.fixture
def mock_server_list() -> Generator[None]:
    """Mock get_server_list to return test servers."""
    with patch(
        "homeassistant.components.librespeed.config_flow.get_server_list",
        return_value=deepcopy(MOCK_SERVER_LIST),
    ):
        yield


@pytest.fixture
def mock_cli_supported() -> Generator[None]:
    """Mock CLI as supported."""
    with patch(
        "homeassistant.components.librespeed.config_flow.LibreSpeedCLI",
    ) as mock_cls:
        mock_cls.return_value.is_cli_supported.return_value = True
        yield


# ---- User flow ----


async def test_user_flow_show_form(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test initial form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_automatic_server(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test selecting automatic server creates entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "automatic",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "LibreSpeed (Automatic)"
    assert result["data"][CONF_SERVER_ID] is None
    assert result["data"][CONF_CUSTOM_SERVER] is None


async def test_user_flow_specific_server(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test selecting a specific server."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "1",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERVER_ID] == 1
    assert "Server One" in result["title"]


async def test_user_flow_custom_server_redirect(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test selecting custom server redirects to custom_server step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "custom_server"


async def test_user_flow_abort_already_configured(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test abort when already configured."""
    # Set up first entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "automatic",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )

    # Try to set up duplicate
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "automatic",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---- Custom server step ----


async def test_custom_server_show_form(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test custom server form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "custom_server"


async def test_custom_server_success(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test custom server creates entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_CUSTOM_SERVER: "https://speedtest.example.com/",
            CONF_SKIP_CERT_VERIFY: False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CUSTOM_SERVER] == "https://speedtest.example.com/"
    assert "speedtest.example.com" in result["title"]


async def test_custom_server_empty_url(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test empty custom URL shows error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_CUSTOM_SERVER: "", CONF_SKIP_CERT_VERIFY: False},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_CUSTOM_SERVER] == "custom_server_required"


# ---- Helper functions ----


def test_parse_server_selection_automatic() -> None:
    """Test parsing 'automatic'."""
    assert _parse_server_selection("automatic") == (None, None)


def test_parse_server_selection_custom() -> None:
    """Test parsing 'custom'."""
    assert _parse_server_selection("custom") == (None, None)


def test_parse_server_selection_valid_id() -> None:
    """Test parsing valid server ID."""
    assert _parse_server_selection("42") == (42, None)


def test_parse_server_selection_invalid_string() -> None:
    """Test parsing invalid string returns None."""
    assert _parse_server_selection("abc") == (None, None)


def test_parse_server_selection_out_of_range() -> None:
    """Test parsing out-of-range ID returns None."""
    assert _parse_server_selection("99999") == (None, None)


def test_parse_server_selection_negative() -> None:
    """Test parsing negative ID returns None."""
    assert _parse_server_selection("-1") == (None, None)


async def test_get_server_list_success(hass: HomeAssistant) -> None:
    """Test get_server_list returns servers."""
    with patch(
        "homeassistant.components.librespeed.config_flow.async_get_clientsession",
    ), patch(
        "homeassistant.components.librespeed.config_flow.LibreSpeedClient",
    ) as mock_cls:
        mock_cls.return_value.get_servers = AsyncMock(
            return_value=deepcopy(MOCK_SERVER_LIST)
        )
        result = await get_server_list(hass)
    assert len(result) == 2


async def test_get_server_list_error(hass: HomeAssistant) -> None:
    """Test get_server_list returns empty on error."""
    import aiohttp

    with patch(
        "homeassistant.components.librespeed.config_flow.async_get_clientsession",
    ), patch(
        "homeassistant.components.librespeed.config_flow.LibreSpeedClient",
    ) as mock_cls:
        mock_cls.return_value.get_servers = AsyncMock(
            side_effect=aiohttp.ClientError()
        )
        result = await get_server_list(hass)
    assert result == []


# ---- Options flow ----


async def test_options_flow_show_form(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow shows form."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: None,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_automatic(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow with automatic server."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: None,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts2",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "server_selection": "automatic",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SERVER_ID] is None


async def test_options_flow_custom_server_redirect(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow redirects to custom server step."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: None,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts3",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "custom_server"


async def test_options_flow_custom_server_success(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow custom server step creates entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: None,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts4",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_CUSTOM_SERVER: "https://custom.example.com/",
            CONF_SKIP_CERT_VERIFY: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CUSTOM_SERVER] == "https://custom.example.com/"
    assert result["data"][CONF_SKIP_CERT_VERIFY] is True


async def test_options_flow_custom_server_empty(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow custom server empty URL shows error."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: None,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts5",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "server_selection": "custom",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_CUSTOM_SERVER: "", CONF_SKIP_CERT_VERIFY: False},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_CUSTOM_SERVER] == "custom_server_required"


async def test_options_flow_preserves_skip_cert(
    hass: HomeAssistant, mock_server_list, mock_cli_supported
) -> None:
    """Test options flow preserves skip_cert_verify from existing config."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MCE

    entry = MCE(
        domain=DOMAIN,
        data=deepcopy({
            CONF_SERVER_ID: None,
            CONF_CUSTOM_SERVER: "https://old.example.com/",
            CONF_SKIP_CERT_VERIFY: True,
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_BACKEND_TYPE: "native",
        }),
        unique_id="librespeed_opts6",
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "server_selection": "automatic",
            CONF_BACKEND_TYPE: "native",
            CONF_AUTO_UPDATE: True,
            CONF_SCAN_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_TEST_TIMEOUT: DEFAULT_TEST_TIMEOUT,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SKIP_CERT_VERIFY] is True
