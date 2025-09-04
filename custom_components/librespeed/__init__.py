"""The LibreSpeed integration.

This integration provides network speed testing capabilities for Home Assistant
using LibreSpeed, supporting both native Python and CLI backend implementations.
It creates sensors for speed metrics, a button for manual tests, and a binary
sensor for test status indication.

Key Features:
- Dual backend support (native Python or official CLI)
- Automatic and manual speed testing
- Server selection (automatic, specific, or custom)
- Retry logic with exponential backoff
- Connection pooling and performance optimizations
- Comprehensive error handling and recovery
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, TypeVar

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    DOMAIN,
    LOGGER_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_TEST_TIMEOUT,
    CONF_BACKEND_TYPE,
    CONF_SERVER_ID,
    CONF_CUSTOM_SERVER,
    CONF_SCAN_INTERVAL,
    CONF_AUTO_UPDATE,
    CONF_SKIP_CERT_VERIFY,
    CONF_TEST_TIMEOUT,
    ATTR_LIFETIME_DOWNLOAD,
    ATTR_LIFETIME_UPLOAD,
    NETWORK_STABILIZATION_DELAY,
    FIRST_TEST_DELAY,
    CONNECTION_POOL_LIMIT,
    CONNECTION_POOL_LIMIT_PER_HOST,
    DNS_CACHE_TTL,
    KEEPALIVE_TIMEOUT,
    READ_BUFFER_SIZE,
    SESSION_TIMEOUT_TOTAL,
    SESSION_TIMEOUT_CONNECT,
    SESSION_TIMEOUT_READ,
)
from .exceptions import (
    CLIError,
    LibreSpeedError,
    NetworkError,
    SpeedTestError,
    SpeedTestTimeoutError,
)
from .coordinator import LibreSpeedDataUpdateCoordinator
from .librespeed_client import LibreSpeedClient
from .librespeed_cli import LibreSpeedCLI

_LOGGER: Final = logging.getLogger(LOGGER_NAME)

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]

# Type variable for generic config value return type
# Used to maintain type safety when retrieving configuration values
T = TypeVar("T")

# Type alias for LibreSpeed config entries with runtime data
type LibreSpeedConfigEntry = ConfigEntry[LibreSpeedRuntimeData]

# Performance optimization constants are now in const.py


@dataclass
class LibreSpeedRuntimeData:
    """Runtime data for LibreSpeed integration.
    
    Stores all runtime components needed by the integration,
    following Home Assistant's best practices for ConfigEntry.runtime_data.
    This replaces the old pattern of storing data in hass.data[DOMAIN].
    """
    
    coordinator: LibreSpeedDataUpdateCoordinator
    session: aiohttp.ClientSession | None = None


def get_config_value(entry: ConfigEntry, key: str, default: T = None) -> T | Any:
    """Get config value, preferring options over data.
    
    Args:
        entry: The config entry to get the value from.
        key: The configuration key to retrieve.
        default: Default value if key not found.
        
    Returns:
        The configuration value, with options taking precedence over data.
    """
    # Options take precedence over data (user can change these)
    if key in entry.options:
        return entry.options[key]
    # Fall back to data (initial config)
    return entry.data.get(key, default)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LibreSpeed from a config entry.
    
    Args:
        hass: Home Assistant instance.
        entry: Config entry for this integration.
        
    Returns:
        True if setup successful.
        
    Raises:
        ConfigEntryNotReady: If CLI backend setup fails.
    """
    _LOGGER.info("Setting up LibreSpeed integration")
    _LOGGER.debug("Entry data: %s", entry.data)
    _LOGGER.debug("Entry options: %s", entry.options)
    
    # Initialize domain data storage if not already present
    # This creates a dictionary to store integration-specific data
    hass.data.setdefault(DOMAIN, {})
    
    # Create global test lock if it doesn't exist
    # This ensures only one speed test runs across all instances
    if "test_lock" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["test_lock"] = asyncio.Lock()
        _LOGGER.debug("Created global test lock for LibreSpeed")
    
    # Retrieve SSL certificate verification preference from configuration
    # This allows users to connect to servers with self-signed certificates
    skip_cert_verify: bool = get_config_value(entry, CONF_SKIP_CERT_VERIFY, False)
    
    # Create appropriate backend based on configuration
    backend_type = get_config_value(entry, CONF_BACKEND_TYPE, "cli")
    session: aiohttp.ClientSession | None = None
    
    if backend_type == "cli":
        # Use CLI backend - no session needed
        _LOGGER.info("Using LibreSpeed CLI backend")
        client = LibreSpeedCLI(hass.config.path(), hass=hass)
        
        # Ensure CLI is available during setup
        _LOGGER.info("Checking for LibreSpeed CLI binary...")
        
        # Small delay on first setup to allow network stack to stabilize
        # This helps with DNS resolution issues during HA startup
        if not await client.check_cli_exists():
            _LOGGER.info("CLI not found, will download. Waiting 2 seconds for network to stabilize...")
            await asyncio.sleep(NETWORK_STABILIZATION_DELAY)
        
        if not await client.ensure_cli_available():
            _LOGGER.error("Failed to setup LibreSpeed CLI backend - will retry on next restart")
            raise ConfigEntryNotReady(
                "Failed to download LibreSpeed CLI. This often happens during startup due to "
                "DNS not being ready. The integration will retry automatically."
            )
        _LOGGER.info("LibreSpeed CLI is ready")
    else:
        # Use native Python backend - create session
        _LOGGER.info("Using native Python backend")
        
        # Configure SSL context based on user preference
        # False = skip verification, None = use default verification
        ssl_context: bool | None = False if skip_cert_verify else None
        
        if skip_cert_verify:
            _LOGGER.warning("SSL certificate verification is disabled for custom server")
        
        # Create an optimized TCP connector for HTTP connections
        # This connector is configured for high-throughput speed testing
        # with connection pooling, DNS caching, and keepalive settings
        try:
            connector: aiohttp.TCPConnector = aiohttp.TCPConnector(
                limit=CONNECTION_POOL_LIMIT,
                limit_per_host=CONNECTION_POOL_LIMIT_PER_HOST,
                force_close=False,  # Reuse connections for better performance
                enable_cleanup_closed=True,  # Clean up closed connections
                ttl_dns_cache=DNS_CACHE_TTL,
                keepalive_timeout=KEEPALIVE_TIMEOUT,
                ssl=ssl_context,
            )
            
            # Create session with optimized settings
            session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(
                    total=SESSION_TIMEOUT_TOTAL,
                    connect=SESSION_TIMEOUT_CONNECT,
                    sock_read=SESSION_TIMEOUT_READ
                ),
                read_bufsize=READ_BUFFER_SIZE,
            )
            
            # Session will be stored in runtime_data for cleanup  
        except Exception as e:  # Keep broad for session creation failures
            _LOGGER.error("Failed to create HTTP session: %s", e)
            raise ConfigEntryNotReady(f"Failed to initialize HTTP session: {e}")
        
        client = LibreSpeedClient(session)
    
    # Wrap coordinator creation and setup in try/except to ensure session cleanup on failure
    try:
        coordinator = LibreSpeedDataUpdateCoordinator(
            hass,
            client,
            get_config_value(entry, CONF_SERVER_ID),
            get_config_value(entry, CONF_CUSTOM_SERVER),
            get_config_value(entry, CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            get_config_value(entry, CONF_AUTO_UPDATE, True),
            get_config_value(entry, CONF_SKIP_CERT_VERIFY, False),
            backend_type,
            entry.entry_id,  # Pass entry ID for unique storage
            entry.title,  # Pass title for logging
            get_config_value(entry, CONF_TEST_TIMEOUT, DEFAULT_TEST_TIMEOUT),  # Pass test timeout
        )
        
        # Set the config entry reference
        coordinator.config_entry = entry
        
        # Load stored data BEFORE setting up platforms so sensors have data
        await coordinator._async_load_lifetime_data()
        
        if coordinator.auto_update:
            # Delay first refresh by 60 seconds to avoid lag during setup
            _LOGGER.info("Scheduling first automatic speed test in 60 seconds")
            async def delayed_first_refresh():
                """Delay the first refresh to avoid setup lag."""
                await asyncio.sleep(FIRST_TEST_DELAY)
                _LOGGER.info("Running first automatic speed test")
                await coordinator.async_refresh()
            
            hass.async_create_task(delayed_first_refresh())
        else:
            _LOGGER.info("Automatic speed tests disabled")
        
        # Store runtime data in ConfigEntry using the new pattern
        # This replaces the old hass.data[DOMAIN] storage method
        entry.runtime_data = LibreSpeedRuntimeData(
            coordinator=coordinator,
            session=session,  # Will be None for CLI backend, ClientSession for native
        )
        
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
        
        return True
        
    except Exception:
        # Clean up session if setup fails at any point
        if session is not None:
            await session.close()
            _LOGGER.debug("Cleaned up session after setup failure")
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.
    
    This function cleanly unloads the integration by:
    1. Saving lifetime data before unload
    2. Unloading all platforms (sensors, buttons, binary_sensors)
    3. Closing the HTTP session to free resources
    4. Removing the coordinator from memory
    
    Args:
        hass: Home Assistant instance.
        entry: Config entry to unload.
        
    Returns:
        True if unload was successful, False otherwise.
    """
    _LOGGER.info("Unloading LibreSpeed integration")
    
    # Save lifetime data before unloading
    runtime_data: LibreSpeedRuntimeData = entry.runtime_data
    if runtime_data.coordinator:
        await runtime_data.coordinator._async_save_lifetime_data()
    
    # Attempt to unload all platforms associated with this integration
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Close the custom HTTP session if one was created
        # This prevents resource leaks and connection pool exhaustion
        if runtime_data.session:
            await runtime_data.session.close()
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry.
    
    Called when the user changes configuration options.
    This will unload and reload the integration with new settings.
    
    Args:
        hass: Home Assistant instance.
        entry: Config entry to reload.
    """
    _LOGGER.info("Reloading LibreSpeed integration due to config change")
    await hass.config_entries.async_reload(entry.entry_id)
