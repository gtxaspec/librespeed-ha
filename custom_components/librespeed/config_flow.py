"""Config flow for LibreSpeed integration.

This module handles the configuration flow for the LibreSpeed integration,
including initial setup and options management. It provides a user-friendly
wizard for configuring speed test parameters, server selection, and backend
choices.

Key Features:
- Automatic server detection and listing
- Custom server URL support with SSL verification options  
- Backend selection (native Python or CLI)
- Options flow for reconfiguration after setup
- Comprehensive validation and error handling
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
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
    LOGGER_NAME,
    MAX_SCAN_INTERVAL,
    MAX_TEST_TIMEOUT,
    MIN_SCAN_INTERVAL,
    MIN_TEST_TIMEOUT,
    MIN_SERVER_ID,
    MAX_SERVER_ID,
)
from .librespeed_client import LibreSpeedClient
from .librespeed_cli import LibreSpeedCLI

_LOGGER = logging.getLogger(LOGGER_NAME)


async def get_server_list(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Get list of available servers."""
    try:
        session = async_get_clientsession(hass)
        client = LibreSpeedClient(session)
        return await client.get_servers()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return []


def _parse_server_selection(server_selection: str) -> tuple[int | None, str | None]:
    """Parse server selection and return server_id and custom_server.
    
    Args:
        server_selection: The selected server string ("automatic", "custom", or server ID as string)
        
    Returns:
        Tuple of (server_id, custom_server) where one is always None
    """
    if server_selection == "automatic":
        return None, None
    elif server_selection == "custom":
        # Custom server will be handled in next step
        return None, None
    else:
        # Try to parse server ID as integer with bounds checking
        try:
            server_id = int(server_selection)
            # Validate server ID is within reasonable bounds (0-10000)
            if server_id < MIN_SERVER_ID or server_id > MAX_SERVER_ID:
                raise ValueError(f"Invalid server ID: {server_id} (must be {MIN_SERVER_ID}-{MAX_SERVER_ID})")
            return server_id, None
        except (ValueError, IndexError) as e:
            _LOGGER.error("Failed to parse server selection '%s': %s", server_selection, e)
            return None, None


def _create_custom_server_data(
    custom_url: str, 
    skip_cert_verify: bool,
    base_input: dict[str, Any]
) -> dict[str, Any]:
    """Create configuration data for custom server.
    
    Args:
        custom_url: The custom server URL
        skip_cert_verify: Whether to skip certificate verification
        base_input: Base user input containing auto_update, scan_interval, backend_type
        
    Returns:
        Complete configuration data dictionary
    """
    return {
        CONF_SERVER_ID: None,
        CONF_CUSTOM_SERVER: custom_url,
        CONF_SKIP_CERT_VERIFY: skip_cert_verify,
        CONF_AUTO_UPDATE: base_input.get(CONF_AUTO_UPDATE, True),
        CONF_SCAN_INTERVAL: base_input.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        CONF_BACKEND_TYPE: base_input.get(CONF_BACKEND_TYPE, "native"),
    }


def _build_common_schema(
    servers: list[dict[str, Any]], 
    hass, 
    config: dict[str, Any] | None = None
) -> vol.Schema:
    """Build the common configuration schema used by both ConfigFlow and OptionsFlow."""
    if config is None:
        config = {}
    
    server_options = [
        {"value": "automatic", "label": "Automatic"}
    ]
    server_options.extend(
        [
            {"value": str(server['id']), "label": f"{server['name']} (ID: {server['id']})"}
            for server in servers
        ]
    )
    server_options.append(
        {"value": "custom", "label": "Custom Server"}
    )
    
    # Check if CLI backend is supported on this platform
    cli_backend = LibreSpeedCLI(hass.config.path())
    backend_options = []
    
    if cli_backend.is_cli_supported():
        backend_options.append(
            {"value": "cli", "label": "Official CLI (Recommended)"}
        )
    backend_options.append(
        {"value": "native", "label": "Native Python"}
    )
    
    schema = {
        vol.Required(
            CONF_BACKEND_TYPE,
            default=config.get(CONF_BACKEND_TYPE, "cli"),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=backend_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            "server_selection",
            default=config.get("server_selection", "automatic"),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=server_options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_AUTO_UPDATE,
            default=config.get(CONF_AUTO_UPDATE, True),
        ): bool,
        vol.Required(
            CONF_SCAN_INTERVAL,
            default=config.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                unit_of_measurement="minutes",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_TEST_TIMEOUT,
            default=config.get(CONF_TEST_TIMEOUT, DEFAULT_TEST_TIMEOUT),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=MIN_TEST_TIMEOUT,
                max=MAX_TEST_TIMEOUT,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
    
    return vol.Schema(schema)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LibreSpeed."""
    
    VERSION = 1
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        self._servers: list[dict[str, Any]] = []
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is None:
            self._servers = await get_server_list(self.hass)
            
            return self.async_show_form(
                step_id="user",
                data_schema=self._build_schema(),
                errors=errors,
            )
        
        # Process server selection first to generate unique ID
        server_selection = user_input.pop("server_selection", "automatic")
        
        # Store settings temporarily
        self._user_input = user_input
        self._server_selection = server_selection
        
        # If custom server is selected, show custom URL form
        if server_selection == "custom":
            return await self.async_step_custom_server()
        
        # Parse the server selection using helper function
        server_id, custom_server = _parse_server_selection(server_selection)
        data = {
            CONF_SERVER_ID: server_id,
            CONF_CUSTOM_SERVER: custom_server,
        }
        
        data[CONF_AUTO_UPDATE] = user_input.get(CONF_AUTO_UPDATE, True)
        data[CONF_SCAN_INTERVAL] = user_input.get(
            CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        data[CONF_BACKEND_TYPE] = user_input.get(CONF_BACKEND_TYPE, "native")
        
        # Generate unique ID based on configuration
        # This allows multiple instances with different servers
        if data[CONF_CUSTOM_SERVER]:
            unique_id = f"{DOMAIN}_{data[CONF_CUSTOM_SERVER]}"
            title = f"LibreSpeed - Custom"
        elif data[CONF_SERVER_ID] is not None:
            unique_id = f"{DOMAIN}_server_{data[CONF_SERVER_ID]}"
            # Try to get server name from the servers list
            server_name = f"Server {data[CONF_SERVER_ID]}"
            for server in self._servers:
                if server['id'] == data[CONF_SERVER_ID]:
                    server_name = server['name']
                    break
            title = f"LibreSpeed - {server_name}"
        else:
            unique_id = f"{DOMAIN}_automatic"
            title = "LibreSpeed (Automatic)"
        
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        
        return self.async_create_entry(
            title=title,
            data=data,
        )
    
    async def async_step_custom_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle custom server URL input."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            custom_url = user_input.get(CONF_CUSTOM_SERVER, "").strip()
            
            if not custom_url:
                errors[CONF_CUSTOM_SERVER] = "custom_server_required"
            else:
                # Create the entry with custom server using helper function
                data = _create_custom_server_data(
                    custom_url,
                    user_input.get(CONF_SKIP_CERT_VERIFY, False),
                    self._user_input
                )
                
                # Generate unique ID for custom server
                unique_id = f"{DOMAIN}_{custom_url}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                # Extract domain from URL for title
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(custom_url)
                    domain_name = parsed.netloc or custom_url
                except (ValueError, TypeError):
                    domain_name = custom_url
                
                return self.async_create_entry(
                    title=f"LibreSpeed - {domain_name}",
                    data=data,
                )
        
        return self.async_show_form(
            step_id="custom_server",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CUSTOM_SERVER,
                    default="https://",
                ): str,
                vol.Optional(
                    CONF_SKIP_CERT_VERIFY,
                    default=False,
                ): bool,
            }),
            errors=errors,
            description_placeholders={
                "example": "https://speedtest.example.com/"
            },
        )
    
    def _build_schema(self, config: dict[str, Any] | None = None) -> vol.Schema:
        """Build the configuration schema."""
        return _build_common_schema(self._servers, self.hass, config)
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for LibreSpeed."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # config_entry is automatically available as self.config_entry in parent class
        self._servers: list[dict[str, Any]] = []
    
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            _LOGGER.debug("Options form received user_input: %s", user_input)
            server_selection = user_input.pop("server_selection", "automatic")
            
            # Store settings temporarily
            self._user_input = user_input
            self._server_selection = server_selection
            
            # If custom server is selected, show custom URL form
            if server_selection == "custom":
                return await self.async_step_custom_server()
            
            # Parse the server selection using helper method
            server_id, custom_server = _parse_server_selection(server_selection)
            data = {
                CONF_SERVER_ID: server_id,
                CONF_CUSTOM_SERVER: custom_server,
            }
            
            data[CONF_AUTO_UPDATE] = user_input.get(CONF_AUTO_UPDATE, True)
            data[CONF_SCAN_INTERVAL] = user_input.get(
                CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL
            )
            data[CONF_BACKEND_TYPE] = user_input.get(CONF_BACKEND_TYPE, "native")
            # Preserve skip_cert_verify setting from existing config (check options first, then data)
            data[CONF_SKIP_CERT_VERIFY] = (
                self.config_entry.options.get(CONF_SKIP_CERT_VERIFY)
                if CONF_SKIP_CERT_VERIFY in self.config_entry.options
                else self.config_entry.data.get(CONF_SKIP_CERT_VERIFY, False)
            )
            
            # Store config but don't trigger immediate test
            _LOGGER.debug("Saving options data: %s", data)
            _LOGGER.info("LibreSpeed config updated - next test will use new settings")
            return self.async_create_entry(title="", data=data)
        
        self._servers = await get_server_list(self.hass)
        
        # Merge data and options, with options taking precedence
        current_config = dict(self.config_entry.data)
        current_config.update(self.config_entry.options)
        _LOGGER.debug("Current config from entry data: %s", self.config_entry.data)
        _LOGGER.debug("Current config from entry options: %s", self.config_entry.options)
        _LOGGER.debug("Merged current config: %s", current_config)
        
        if current_config.get(CONF_CUSTOM_SERVER):
            current_config["server_selection"] = "custom"
        elif current_config.get(CONF_SERVER_ID) is not None:
            # Set server_selection to just the ID as a string
            current_config["server_selection"] = str(current_config[CONF_SERVER_ID])
        else:
            current_config["server_selection"] = "automatic"
        
        _LOGGER.debug("Config for form with server_selection: %s", current_config)
        
        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(current_config),
            errors=errors,
        )
    
    async def async_step_custom_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle custom server URL input for options."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            custom_url = user_input.get(CONF_CUSTOM_SERVER, "").strip()
            
            if not custom_url:
                errors[CONF_CUSTOM_SERVER] = "custom_server_required"
            else:
                # Create the entry with custom server using helper function
                data = _create_custom_server_data(
                    custom_url,
                    user_input.get(CONF_SKIP_CERT_VERIFY, False),
                    self._user_input
                )
                
                _LOGGER.info("LibreSpeed config updated with custom server - next test will use new settings")
                return self.async_create_entry(title="", data=data)
        
        # Show current custom server URL and skip cert verify setting if editing
        # Check options first, then data
        current_url = (
            self.config_entry.options.get(CONF_CUSTOM_SERVER) or
            self.config_entry.data.get(CONF_CUSTOM_SERVER, "https://")
        )
        skip_cert = (
            self.config_entry.options.get(CONF_SKIP_CERT_VERIFY) 
            if CONF_SKIP_CERT_VERIFY in self.config_entry.options
            else self.config_entry.data.get(CONF_SKIP_CERT_VERIFY, False)
        )
        
        return self.async_show_form(
            step_id="custom_server",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_CUSTOM_SERVER,
                    default=current_url,
                ): str,
                vol.Optional(
                    CONF_SKIP_CERT_VERIFY,
                    default=skip_cert,
                ): bool,
            }),
            errors=errors,
            description_placeholders={
                "example": "https://speedtest.example.com/"
            },
        )
    
    def _build_options_schema(self, config: dict[str, Any]) -> vol.Schema:
        """Build the options schema."""
        return _build_common_schema(self._servers, self.hass, config)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""