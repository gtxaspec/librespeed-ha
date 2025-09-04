"""Data update coordinator for LibreSpeed integration.

This module contains the coordinator that manages speed test execution,
data updates, and state synchronization across all LibreSpeed entities.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

if TYPE_CHECKING:
    from .librespeed_client import LibreSpeedClient
    from .librespeed_cli import LibreSpeedCLI

from .const import (
    DOMAIN,
    LOGGER_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_TEST_TIMEOUT,
    ATTR_LIFETIME_DOWNLOAD,
    ATTR_LIFETIME_UPLOAD,
    CIRCUIT_BREAKER_WARNING_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_THRESHOLD,
    GLOBAL_TEST_LOCK_TIMEOUT,
    CUSTOM_SERVER_ERROR_COOLDOWN,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
    MAX_LIFETIME_GB,
)
from .exceptions import (
    CLIError,
    LibreSpeedError,
    NetworkError,
    SpeedTestError,
    SpeedTestTimeoutError,
)

_LOGGER: Final = logging.getLogger(LOGGER_NAME)

# Performance optimization constants are now in const.py


class LibreSpeedDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching LibreSpeed data.
    
    This coordinator handles speed test execution with proper locking,
    retry logic, and error handling for both native and CLI backends.
    """
    
    def __init__(
        self,
        hass: HomeAssistant,
        client: LibreSpeedClient | LibreSpeedCLI,
        server_id: int | None,
        custom_server: str | None,
        scan_interval: int,
        auto_update: bool,
        skip_cert_verify: bool = False,
        backend_type: str = "native",
        entry_id: str | None = None,
        entry_title: str | None = None,
        test_timeout: int = DEFAULT_TEST_TIMEOUT,
    ) -> None:
        """Initialize the coordinator.
        
        Args:
            hass: Home Assistant instance.
            client: LibreSpeed client instance (native or CLI).
            server_id: Optional server ID for testing.
            custom_server: Optional custom server URL.
            scan_interval: Interval between automatic tests in minutes.
            auto_update: Whether to run automatic tests.
            skip_cert_verify: Whether to skip SSL certificate verification.
            backend_type: Type of backend ("native" or "cli").
            entry_id: Config entry ID for unique storage.
            entry_title: Config entry title for logging.
            test_timeout: Maximum time allowed for a speed test in seconds.
        """
        self.client: LibreSpeedClient | LibreSpeedCLI = client
        self.server_id: int | None = server_id
        self.custom_server: str | None = custom_server
        self.auto_update: bool = auto_update
        self.skip_cert_verify: bool = skip_cert_verify
        self.backend_type: str = backend_type
        self.entry_title: str = entry_title or "LibreSpeed"
        self.test_timeout: int = test_timeout
        self.config_entry: ConfigEntry | None = None  # Will be set after initialization
        self.is_running: bool = False
        self.is_waiting: bool = False  # Track if waiting for global lock
        self.lifetime_download: float = 0.0  # GB - will be loaded from storage
        self.lifetime_upload: float = 0.0  # GB - will be loaded from storage
        self._first_refresh_done: bool = False
        self._test_lock: asyncio.Lock = asyncio.Lock()  # Local lock (kept for compatibility)
        self._global_lock: asyncio.Lock = hass.data[DOMAIN]["test_lock"]  # Global lock
        # Use entry_id for unique storage key per instance
        storage_key = f"{DOMAIN}_lifetime_data_{entry_id}" if entry_id else f"{DOMAIN}_lifetime_data"
        self._store: Store = Store(hass, 1, storage_key)
        
        # Failure tracking for repair flows
        self._consecutive_failures: int = 0
        self._last_custom_server_error: float = 0.0
        
        # Calculate update interval
        update_interval: timedelta | None = (
            timedelta(minutes=scan_interval) if auto_update else None
        )
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
    
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from LibreSpeed with retry logic and circuit breaker.
        
        This is the main data update method called by Home Assistant.
        It implements:
        - Circuit breaker pattern (stops after 10 consecutive failures)
        - Concurrency prevention (only one test at a time)
        - Retry logic with exponential backoff
        - Error handling and logging
        - State management (is_running flag)
        
        Returns:
            Dictionary containing speed test results.
            
        Raises:
            UpdateFailed: If all retry attempts fail or circuit is open.
        """
        # Circuit breaker: stop attempting after 10 consecutive failures
        if self._consecutive_failures >= CIRCUIT_BREAKER_OPEN_THRESHOLD:
            _LOGGER.warning("Circuit breaker open - too many consecutive failures (%d). Skipping test.", 
                          self._consecutive_failures)
            if self.data:
                # Return last known good data
                return self.data
            raise UpdateFailed("Circuit breaker open - service unavailable after 10 consecutive failures")
        
        # Check if another instance is already testing
        if self._global_lock.locked():
            _LOGGER.info("%s: Another LibreSpeed instance is running, waiting...", self.entry_title)
            self.is_waiting = True
            self.async_update_listeners()  # Update UI to show waiting status
            
            try:
                # Wait up to 5 minutes for our turn
                async with asyncio.timeout(GLOBAL_TEST_LOCK_TIMEOUT):
                    async with self._global_lock:
                        self.is_waiting = False
                        return await self._run_speed_test()
            except asyncio.TimeoutError:
                self.is_waiting = False
                _LOGGER.warning("%s: Timed out waiting for other speed test", self.entry_title)
                if self.data:
                    return self.data
                raise UpdateFailed("Timed out waiting for other speed test")
        else:
            # No other test running, proceed immediately
            async with self._global_lock:
                return await self._run_speed_test()
    
    async def _run_speed_test(self) -> dict[str, Any]:
        """Run the actual speed test (called with global lock held)."""
        async with self._test_lock:
            _LOGGER.info("%s: Starting speed test...", self.entry_title)
            
            # Initialize retry parameters
            last_error: Exception | None = None
            
            try:
                self.is_running = True
                # Notify listeners that test is starting
                self.async_update_listeners()
                
                for attempt in range(MAX_RETRIES):
                    try:
                        _LOGGER.info(
                            "%s: Starting test (attempt %d/%d) - Server: %s",
                            self.entry_title,
                            attempt + 1,
                            MAX_RETRIES,
                            self.custom_server or f"ID {self.server_id}" or "Automatic"
                        )
                        
                        # Call appropriate method based on backend type
                        if self.backend_type == "cli":
                            # CLI backend takes skip_cert_verify parameter
                            result = await self.client.run_speed_test(
                                server_id=self.server_id,
                                custom_server=self.custom_server,
                                skip_cert_verify=self.skip_cert_verify,
                                timeout=self.test_timeout,
                            )
                        else:
                            # Native backend uses custom_server_url parameter
                            result = await self.client.run_speed_test(
                                server_id=self.server_id,
                                custom_server_url=self.custom_server,
                                timeout=self.test_timeout,
                            )
                        
                        _LOGGER.debug("Raw speed test result: %s", result)
                        
                        # Parse and validate result
                        parsed_result: dict[str, Any] = self._parse_result(result)
                        
                        # Update lifetime statistics (convert bytes to GB using decimal units)
                        # Cap at 1 Petabyte (1,000,000 GB) to prevent overflow
                        # MAX_LIFETIME_GB is now in const.py  
                        
                        if 'bytes_received' in parsed_result:
                            new_download = self.lifetime_download + (parsed_result['bytes_received'] / 1_000_000_000)
                            self.lifetime_download = min(new_download, MAX_LIFETIME_GB)
                        if 'bytes_sent' in parsed_result:
                            new_upload = self.lifetime_upload + (parsed_result['bytes_sent'] / 1_000_000_000)
                            self.lifetime_upload = min(new_upload, MAX_LIFETIME_GB)
                        
                        # Save lifetime data to storage
                        await self._async_save_lifetime_data()
                        
                        # Add lifetime data to result
                        parsed_result[ATTR_LIFETIME_DOWNLOAD] = self.lifetime_download
                        parsed_result[ATTR_LIFETIME_UPLOAD] = self.lifetime_upload
                        
                        # Reset failure counter on success and clear any repair issues
                        self._consecutive_failures = 0
                        from homeassistant.helpers import issue_registry as ir
                        ir.async_delete_issue(self.hass, DOMAIN, "custom_server_unreachable")
                        ir.async_delete_issue(self.hass, DOMAIN, "repeated_test_failures")
                        
                        # Log success
                        _LOGGER.info(
                            "Speed test completed: ↓ %.1f Mbps | ↑ %.1f Mbps | Ping: %.1f ms",
                            parsed_result.get('download', 0),
                            parsed_result.get('upload', 0),
                            parsed_result.get('ping', 0)
                        )
                        return parsed_result
                        
                    except asyncio.TimeoutError as err:
                        last_error = err
                        _LOGGER.warning(
                            "Speed test timeout (attempt %d/%d)",
                            attempt + 1,
                            MAX_RETRIES
                        )
                        if attempt < MAX_RETRIES - 1:
                            # Exponential backoff with jitter
                            delay: float = RETRY_DELAY_BASE * (2 ** attempt)
                            await asyncio.sleep(delay)
                            continue
                        
                    except aiohttp.ClientError as err:
                        last_error = err
                        _LOGGER.warning(
                            "Network error (attempt %d/%d): %s",
                            attempt + 1,
                            MAX_RETRIES,
                            err.__class__.__name__
                        )
                        if attempt < MAX_RETRIES - 1:
                            # Exponential backoff with jitter
                            delay: float = RETRY_DELAY_BASE * (2 ** attempt)
                            await asyncio.sleep(delay)
                            continue
                        
                    except (SpeedTestError, NetworkError, CLIError) as err:
                        # Don't retry on known errors
                        _LOGGER.error("Speed test error: %s", err)
                        raise UpdateFailed(f"Speed test error: {err}") from err
                    except (ValueError, TypeError, KeyError, AttributeError) as err:
                        # Don't retry on data/parsing errors
                        _LOGGER.error("Data processing error during speed test: %s", err, exc_info=True)
                        raise UpdateFailed(f"Data processing error: {err}") from err
                
                # If we get here, all retries failed - track failures for repair issues
                self._consecutive_failures += 1
                import time
                
                # Check for custom server issues (only if using custom server)
                if self.custom_server and isinstance(last_error, (aiohttp.ClientError, NetworkError)):
                    current_time = time.time()
                    # Create repair issue if we haven't created one recently (last 6 hours)
                    if current_time - self._last_custom_server_error > CUSTOM_SERVER_ERROR_COOLDOWN:
                        self._last_custom_server_error = current_time
                        from homeassistant.helpers import issue_registry as ir
                        ir.async_create_issue(
                            self.hass,
                            DOMAIN,
                            "custom_server_unreachable",
                            is_fixable=False,
                            severity=ir.IssueSeverity.WARNING,
                            translation_key="custom_server_unreachable",
                            translation_placeholders={
                                "options_path": "Settings → Devices & Services → LibreSpeed → Configure"
                            }
                        )
                
                # Check for repeated failures and create repair issues
                from homeassistant.helpers import issue_registry as ir
                
                if self._consecutive_failures == CIRCUIT_BREAKER_WARNING_THRESHOLD:
                    # First warning at 5 failures
                    backend_switch = "Try switching from CLI to Native Python backend" if self.backend_type == "cli" else "Try switching from Native Python to CLI backend"
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        "repeated_test_failures",
                        is_fixable=True,  # Make it fixable since we have a repair flow
                        severity=ir.IssueSeverity.WARNING,
                        translation_key="repeated_test_failures",
                        translation_placeholders={
                            "backend_switch": backend_switch,
                            "options_path": "Settings → Devices & Services → LibreSpeed → Configure"
                        }
                    )
                elif self._consecutive_failures == CIRCUIT_BREAKER_OPEN_THRESHOLD:
                    # Circuit breaker opened at 10 failures
                    ir.async_create_issue(
                        self.hass,
                        DOMAIN,
                        "circuit_breaker_open",
                        is_fixable=True,
                        severity=ir.IssueSeverity.ERROR,
                        translation_key="circuit_breaker_open",
                        translation_placeholders={
                            "failure_count": str(self._consecutive_failures),
                            "manual_test": "You can try a manual test to reset the circuit breaker"
                        }
                    )
                
                if isinstance(last_error, asyncio.TimeoutError):
                    raise UpdateFailed("Speed test timed out after multiple attempts") from last_error
                elif isinstance(last_error, aiohttp.ClientError):
                    raise UpdateFailed(f"Network error after multiple attempts: {last_error}") from last_error
                    
            finally:
                self.is_running = False
                # Update listeners again to notify binary sensor test is done
                self.async_update_listeners()
                _LOGGER.debug("Speed test finished, is_running set to False")
    
    def _parse_result(self, result: dict) -> dict[str, Any]:
        """Parse the speedtest result into a standardized format."""
        return {
            "download": result.get("download", 0),
            "upload": result.get("upload", 0),
            "ping": result.get("ping", 0),
            "jitter": result.get("jitter", 0),
            "server_name": result.get("server", {}).get("name", "Unknown"),
            "server_location": result.get("server", {}).get("location", "Unknown"),
            "server_sponsor": result.get("server", {}).get("sponsor", "Unknown"),
            "timestamp": result.get("timestamp"),  # This is already a datetime object
            "bytes_sent": result.get("bytes_sent", 0),
            "bytes_received": result.get("bytes_received", 0),
        }
    
    async def async_get_server_list(self) -> list[dict[str, Any]]:
        """Get list of available servers."""
        try:
            # CLI backend doesn't support server discovery
            if hasattr(self.client, 'get_servers'):
                return await self.client.get_servers()
            else:
                _LOGGER.debug("Server list not supported by %s backend", self.backend_type)
                return []
        except (NetworkError, aiohttp.ClientError, asyncio.TimeoutError):
            _LOGGER.debug("Failed to fetch server list")
            return []
    
    async def async_run_speedtest(self) -> None:
        """Manually trigger a speedtest.
        
        Manual tests reset the circuit breaker to allow recovery attempts.
        """
        # Reset circuit breaker on manual test - user wants to try again
        if self._consecutive_failures >= CIRCUIT_BREAKER_OPEN_THRESHOLD:
            _LOGGER.info("Resetting circuit breaker for manual test attempt")
            self._consecutive_failures = CIRCUIT_BREAKER_OPEN_THRESHOLD - 1  # Set to threshold-1 so next failure hits threshold again
        
        await self.async_refresh()
    
    async def _async_load_lifetime_data(self) -> None:
        """Load lifetime data and last test results from storage."""
        try:
            stored_data = await self._store.async_load()
            if stored_data:
                self.lifetime_download = stored_data.get("lifetime_download", 0.0)
                self.lifetime_upload = stored_data.get("lifetime_upload", 0.0)
                
                # Restore ALL test data to avoid "Unknown" sensors after reload
                if last_test_data := stored_data.get("last_test_data"):
                    # Convert timestamp string back to datetime if present
                    timestamp = last_test_data.get("timestamp")
                    if timestamp and isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp)
                        except (ValueError, TypeError):
                            timestamp = None
                    
                    # Ensure ALL fields are present with proper types
                    self.data = {
                        "download": last_test_data.get("download", 0),
                        "upload": last_test_data.get("upload", 0),
                        "ping": last_test_data.get("ping", 0),
                        "jitter": last_test_data.get("jitter", 0),
                        "server_name": last_test_data.get("server_name", "Unknown"),
                        "server_location": last_test_data.get("server_location", "Unknown"),
                        "server_sponsor": last_test_data.get("server_sponsor", "Unknown"),
                        "timestamp": timestamp,
                        "bytes_sent": last_test_data.get("bytes_sent", 0),
                        "bytes_received": last_test_data.get("bytes_received", 0),
                        ATTR_LIFETIME_DOWNLOAD: self.lifetime_download,
                        ATTR_LIFETIME_UPLOAD: self.lifetime_upload,
                    }
                    _LOGGER.info(
                        "Restored complete test data: ↓ %.1f Mbps | ↑ %.1f Mbps | Ping: %.1f ms | Jitter: %.1f ms | Server: %s",
                        self.data.get("download", 0),
                        self.data.get("upload", 0),
                        self.data.get("ping", 0),
                        self.data.get("jitter", 0),
                        self.data.get("server_name", "Unknown")
                    )
                
                _LOGGER.info(
                    "Loaded lifetime data: ↓ %.2f GB | ↑ %.2f GB",
                    self.lifetime_download,
                    self.lifetime_upload
                )
                
                # Notify listeners that we have data
                if self.data:
                    self.async_set_updated_data(self.data)
        except Exception as err:  # Keep broad for storage operations
            _LOGGER.warning("Failed to load lifetime data: %s", err)
    
    async def _async_save_lifetime_data(self) -> None:
        """Save lifetime data and last test results to storage."""
        try:
            # Prepare data for JSON serialization
            save_data = {
                "lifetime_download": self.lifetime_download,
                "lifetime_upload": self.lifetime_upload,
            }
            
            # Convert datetime to string for JSON serialization
            if self.data:
                last_test_data = self.data.copy()
                if "timestamp" in last_test_data and isinstance(last_test_data["timestamp"], datetime):
                    last_test_data["timestamp"] = last_test_data["timestamp"].isoformat()
                save_data["last_test_data"] = last_test_data
            
            await self._store.async_save(save_data)
        except Exception as err:  # Keep broad for storage operations
            _LOGGER.warning("Failed to save lifetime data: %s", err)