"""Custom exceptions for LibreSpeed integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class LibreSpeedError(HomeAssistantError):
    """Base exception for LibreSpeed integration."""


class ServerNotFoundError(LibreSpeedError):
    """Raised when a requested server is not found."""


class NetworkError(LibreSpeedError):
    """Raised when network operations fail."""


class SpeedTestError(LibreSpeedError):
    """Raised when a speed test fails."""


class SpeedTestTimeoutError(SpeedTestError):
    """Raised when speed test times out."""


class CLIError(LibreSpeedError):
    """Base exception for CLI backend errors."""


class CLINotFoundError(CLIError):
    """Raised when CLI binary is not found."""


class CLIExecutionError(CLIError):
    """Raised when CLI execution fails."""


class CLIOutputError(CLIError):
    """Raised when CLI output cannot be parsed."""
