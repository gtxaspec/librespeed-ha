"""Tests for LibreSpeed repair flows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.repairs import ConfirmRepairFlow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.librespeed import LibreSpeedRuntimeData
from homeassistant.components.librespeed.const import DOMAIN
from homeassistant.components.librespeed.repairs import (
    CircuitBreakerRepairFlow,
    CLIDownloadRepairFlow,
    CustomServerRepairFlow,
    RepeatedFailuresRepairFlow,
    async_create_fix_flow,
)


# ---- Factory ----


async def test_create_fix_flow_cli_download(hass: HomeAssistant) -> None:
    """Test factory creates CLIDownloadRepairFlow."""
    flow = await async_create_fix_flow(hass, "cli_download_failed", None)
    assert isinstance(flow, CLIDownloadRepairFlow)


async def test_create_fix_flow_custom_server(hass: HomeAssistant) -> None:
    """Test factory creates CustomServerRepairFlow."""
    flow = await async_create_fix_flow(hass, "custom_server_unreachable", None)
    assert isinstance(flow, CustomServerRepairFlow)


async def test_create_fix_flow_repeated_failures(hass: HomeAssistant) -> None:
    """Test factory creates RepeatedFailuresRepairFlow."""
    flow = await async_create_fix_flow(hass, "repeated_test_failures", None)
    assert isinstance(flow, RepeatedFailuresRepairFlow)


async def test_create_fix_flow_circuit_breaker(hass: HomeAssistant) -> None:
    """Test factory creates CircuitBreakerRepairFlow."""
    flow = await async_create_fix_flow(hass, "circuit_breaker_open", None)
    assert isinstance(flow, CircuitBreakerRepairFlow)


async def test_create_fix_flow_unknown(hass: HomeAssistant) -> None:
    """Test factory falls back to ConfirmRepairFlow."""
    flow = await async_create_fix_flow(hass, "unknown_issue", None)
    assert isinstance(flow, ConfirmRepairFlow)


# ---- CLIDownloadRepairFlow ----


async def test_cli_download_show_form(hass: HomeAssistant) -> None:
    """Test CLI download repair shows form."""
    flow = CLIDownloadRepairFlow()
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"


async def test_cli_download_success(hass: HomeAssistant) -> None:
    """Test CLI download repair succeeds."""
    flow = CLIDownloadRepairFlow()
    flow.hass = hass
    with patch(
        "homeassistant.components.librespeed.repairs.LibreSpeedCLI",
    ) as mock_cls:
        mock_cls.return_value.ensure_cli_available = AsyncMock(return_value=True)
        result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"


async def test_cli_download_failure(hass: HomeAssistant) -> None:
    """Test CLI download repair fails."""
    flow = CLIDownloadRepairFlow()
    flow.hass = hass
    with patch(
        "homeassistant.components.librespeed.repairs.LibreSpeedCLI",
    ) as mock_cls:
        mock_cls.return_value.ensure_cli_available = AsyncMock(return_value=False)
        result = await flow.async_step_confirm({})
    assert result["type"] == "abort"
    assert result["reason"] == "cli_download_failed"


async def test_cli_download_exception(hass: HomeAssistant) -> None:
    """Test CLI download repair handles exception."""
    flow = CLIDownloadRepairFlow()
    flow.hass = hass
    with patch(
        "homeassistant.components.librespeed.repairs.LibreSpeedCLI",
    ) as mock_cls:
        mock_cls.return_value.ensure_cli_available = AsyncMock(
            side_effect=OSError("fail")
        )
        result = await flow.async_step_confirm({})
    assert result["type"] == "abort"
    assert result["reason"] == "cli_download_error"


# ---- CustomServerRepairFlow ----


async def test_custom_server_show_form(hass: HomeAssistant) -> None:
    """Test custom server repair shows form."""
    flow = CustomServerRepairFlow()
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"


async def test_custom_server_acknowledge(hass: HomeAssistant) -> None:
    """Test custom server repair acknowledges."""
    flow = CustomServerRepairFlow()
    flow.hass = hass
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"


# ---- RepeatedFailuresRepairFlow ----


def _setup_entry_with_coordinator(hass, failures=5):
    """Set up a config entry with mock coordinator."""
    coordinator = MagicMock()
    coordinator.consecutive_failures = failures
    coordinator.entry_title = "Test"

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="test")
    entry.add_to_hass(hass)
    entry.runtime_data = LibreSpeedRuntimeData(coordinator=coordinator)
    return coordinator


async def test_repeated_failures_show_form(hass: HomeAssistant) -> None:
    """Test repeated failures repair shows form."""
    flow = RepeatedFailuresRepairFlow()
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"


async def test_repeated_failures_reset(hass: HomeAssistant) -> None:
    """Test repeated failures repair resets counter."""
    coordinator = _setup_entry_with_coordinator(hass, failures=5)

    flow = RepeatedFailuresRepairFlow()
    flow.hass = hass
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    assert result["title"] == "Failure Counter Reset"
    assert coordinator.consecutive_failures == 0


async def test_repeated_failures_no_coordinator(hass: HomeAssistant) -> None:
    """Test repeated failures repair with no coordinator."""
    flow = RepeatedFailuresRepairFlow()
    flow.hass = hass
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    assert result["title"] == "Recovery Initiated"


# ---- CircuitBreakerRepairFlow ----


async def test_circuit_breaker_show_form(hass: HomeAssistant) -> None:
    """Test circuit breaker repair shows form."""
    flow = CircuitBreakerRepairFlow()
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"


async def test_circuit_breaker_reset_single(hass: HomeAssistant) -> None:
    """Test circuit breaker reset for single coordinator."""
    coordinator = _setup_entry_with_coordinator(hass, failures=10)

    flow = CircuitBreakerRepairFlow()
    flow.hass = hass
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    assert "1 instance" in result["title"]
    assert coordinator.consecutive_failures == 0


async def test_circuit_breaker_no_open_circuits(hass: HomeAssistant) -> None:
    """Test circuit breaker with no open circuits."""
    _setup_entry_with_coordinator(hass, failures=3)

    flow = CircuitBreakerRepairFlow()
    flow.hass = hass
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    assert result["title"] == "No Circuit Breakers Found"
