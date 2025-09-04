"""Repair flows for LibreSpeed integration."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    LOGGER_NAME,
    CIRCUIT_BREAKER_WARNING_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_THRESHOLD,
)
from .librespeed_cli import LibreSpeedCLI

_LOGGER = logging.getLogger(LOGGER_NAME)


class CLIDownloadRepairFlow(RepairsFlow):
    """Handler for CLI download failure repair flow."""
    
    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of CLI download repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step to retry CLI download."""
        if user_input is not None:
            # Attempt to re-download CLI
            _LOGGER.info("User initiated CLI download retry via repair flow")
            cli = LibreSpeedCLI(self.hass.config.path())
            
            try:
                if await cli.ensure_cli_available(force_download=True):
                    _LOGGER.info("CLI download successful via repair flow")
                    # Delete the repair issue since it's fixed
                    ir.async_delete_issue(self.hass, DOMAIN, "cli_download_failed")
                    return self.async_create_entry(
                        title="CLI Download Successful",
                        data={}
                    )
                else:
                    _LOGGER.error("CLI download failed again via repair flow")
                    return self.async_abort(reason="cli_download_failed")
            except (OSError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                _LOGGER.error("CLI download repair failed with exception: %s", e)
                return self.async_abort(reason="cli_download_error")
                
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "alternative": "You can also switch to Native Python backend in integration options"
            }
        )


class CustomServerRepairFlow(RepairsFlow):
    """Handler for custom server unreachable repair flow."""
    
    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of custom server repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step to guide user to options."""
        if user_input is not None:
            _LOGGER.info("User acknowledged custom server issue via repair flow")
            # We can't automatically fix server issues, just guide user to options
            return self.async_create_entry(
                title="Server Configuration",
                data={}
            )
                
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "options_path": "Settings → Devices & Services → LibreSpeed → Configure"
            }
        )


class RepeatedFailuresRepairFlow(RepairsFlow):
    """Handler for repeated test failures repair flow."""
    
    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of repeated failures repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step to reset failure counter and suggest fixes."""
        if user_input is not None:
            _LOGGER.info("User initiated failure recovery via repair flow")
            
            # Reset the failure counter in the coordinator
            # This allows the integration to try again
            from . import LibreSpeedRuntimeData
            
            # Find the config entry with this issue
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if isinstance(entry_data, LibreSpeedRuntimeData):
                    coordinator = entry_data.coordinator
                    if coordinator._consecutive_failures >= CIRCUIT_BREAKER_WARNING_THRESHOLD:
                        _LOGGER.info("Resetting failure counter from %d to 0", 
                                   coordinator._consecutive_failures)
                        coordinator._consecutive_failures = 0
                        
                        # Delete the repair issue
                        ir.async_delete_issue(self.hass, DOMAIN, "repeated_test_failures")
                        ir.async_delete_issue(self.hass, DOMAIN, "circuit_breaker_open")
                        
                        return self.async_create_entry(
                            title="Failure Counter Reset",
                            data={}
                        )
            
            return self.async_create_entry(
                title="Recovery Initiated",
                data={}
            )
                
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "action": "Reset failure counter and allow retries",
                "backend_switch": "Consider switching between CLI and Native Python backends",
                "options_path": "Settings → Devices & Services → LibreSpeed → Configure"
            }
        )


class CircuitBreakerRepairFlow(RepairsFlow):
    """Handler for circuit breaker open repair flow."""
    
    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of circuit breaker repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step to reset circuit breaker."""
        if user_input is not None:
            _LOGGER.info("User initiated circuit breaker reset via repair flow")
            
            # Reset the circuit breaker
            from . import LibreSpeedRuntimeData
            
            # Find and reset all coordinators with open circuit
            reset_count = 0
            for entry_id, entry_data in self.hass.data.get(DOMAIN, {}).items():
                if isinstance(entry_data, LibreSpeedRuntimeData):
                    coordinator = entry_data.coordinator
                    if coordinator._consecutive_failures >= CIRCUIT_BREAKER_OPEN_THRESHOLD:
                        _LOGGER.info("Resetting circuit breaker for %s (failures: %d)", 
                                   coordinator.entry_title, coordinator._consecutive_failures)
                        coordinator._consecutive_failures = 0
                        reset_count += 1
            
            if reset_count > 0:
                # Delete the repair issue
                ir.async_delete_issue(self.hass, DOMAIN, "circuit_breaker_open")
                ir.async_delete_issue(self.hass, DOMAIN, "repeated_test_failures")
                
                return self.async_create_entry(
                    title=f"Circuit Breaker Reset ({reset_count} instance{'s' if reset_count > 1 else ''})",
                    data={}
                )
            
            return self.async_create_entry(
                title="No Circuit Breakers Found",
                data={}
            )
                
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "action": "Reset the circuit breaker to allow speed tests to resume",
                "note": "The integration will attempt tests again on the next scheduled interval"
            }
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create repair flow based on issue ID."""
    _LOGGER.debug("Creating repair flow for issue: %s", issue_id)
    
    if issue_id == "cli_download_failed":
        return CLIDownloadRepairFlow()
    elif issue_id == "custom_server_unreachable":
        return CustomServerRepairFlow()
    elif issue_id == "repeated_test_failures":
        return RepeatedFailuresRepairFlow()
    elif issue_id == "circuit_breaker_open":
        return CircuitBreakerRepairFlow()
    
    # Fallback to simple confirmation flow
    return ConfirmRepairFlow()