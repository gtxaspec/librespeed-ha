"""Diagnostics support for LibreSpeed."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CUSTOM_SERVER,
    CONF_SERVER_ID,
    DOMAIN,
)

TO_REDACT = {
    CONF_URL,
    CONF_CUSTOM_SERVER,
    "server_url",
    "ip_address",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    from . import LibreSpeedRuntimeData
    runtime_data: LibreSpeedRuntimeData = entry.runtime_data
    coordinator = runtime_data.coordinator
    
    # Get the last test results
    last_test_data = None
    if coordinator.data:
        last_test_data = {
            "download_speed": coordinator.data.get("download"),
            "upload_speed": coordinator.data.get("upload"),
            "ping": coordinator.data.get("ping"),
            "jitter": coordinator.data.get("jitter"),
            "server_name": coordinator.data.get("server_name"),
            "server_location": coordinator.data.get("server_location"),
            "timestamp": str(coordinator.data.get("timestamp")),
            "bytes_sent": coordinator.data.get("bytes_sent"),
            "bytes_received": coordinator.data.get("bytes_received"),
        }
    
    # Get server list if available
    server_list = []
    try:
        if hasattr(coordinator.client, "get_servers"):
            servers = await coordinator.client.get_servers()
            # Only include basic server info, redact sensitive data
            server_list = [
                {
                    "id": server.get("id"),
                    "name": server.get("name"),
                    "location": server.get("location"),
                    "country": server.get("country"),
                }
                for server in servers[:10]  # Limit to first 10 servers
            ]
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        server_list = "Failed to retrieve server list"
    
    # Check CLI availability if using CLI backend
    cli_info = None
    if coordinator.backend_type == "cli":
        cli_info = {
            "backend": "CLI",
            "cli_available": hasattr(coordinator.client, "cli_path") and coordinator.client.cli_path is not None,
            "cli_path": getattr(coordinator.client, "cli_path", None),
        }
    else:
        cli_info = {
            "backend": "Native Python",
        }
    
    diagnostics_data = {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "source": entry.source,
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "coordinator": {
            "backend_type": coordinator.backend_type,
            "auto_update": coordinator.auto_update,
            "scan_interval": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "is_running": coordinator.is_running,
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
        },
        "last_test": last_test_data,
        "cli_info": cli_info,
        "server_list_sample": server_list,
        "platform_info": {
            "platform": coordinator.hass.config.platform,
            "python_version": coordinator.hass.config.python_version,
        },
    }
    
    return async_redact_data(diagnostics_data, TO_REDACT)