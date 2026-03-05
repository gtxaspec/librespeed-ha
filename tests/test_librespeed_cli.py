"""Tests for LibreSpeed CLI backend."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.librespeed.exceptions import (
    CLIExecutionError,
    CLINotFoundError,
    CLIOutputError,
    LibreSpeedError,
    SpeedTestTimeoutError,
)
from homeassistant.components.librespeed.librespeed_cli import LibreSpeedCLI


# ---- Platform info ----


def test_get_platform_info_amd64() -> None:
    """Test platform info for x86_64."""
    cli = LibreSpeedCLI("/fake/path")
    with patch("homeassistant.components.librespeed.librespeed_cli.platform") as mock_plat:
        mock_plat.machine.return_value = "x86_64"
        info = cli.get_platform_info()
    assert info["arch"] == "amd64"
    assert info["system"] == "linux"


def test_get_platform_info_arm64() -> None:
    """Test platform info for aarch64."""
    cli = LibreSpeedCLI("/fake/path")
    with patch("homeassistant.components.librespeed.librespeed_cli.platform") as mock_plat:
        mock_plat.machine.return_value = "aarch64"
        info = cli.get_platform_info()
    assert info["arch"] == "arm64"


def test_get_platform_info_cached() -> None:
    """Test platform info is cached after first call."""
    cli = LibreSpeedCLI("/fake/path")
    with patch("homeassistant.components.librespeed.librespeed_cli.platform") as mock_plat:
        mock_plat.machine.return_value = "x86_64"
        info1 = cli.get_platform_info()
        info2 = cli.get_platform_info()
    assert info1 is info2
    mock_plat.machine.assert_called_once()


# ---- is_cli_supported ----


def test_is_cli_supported_amd64() -> None:
    """Test CLI is supported on amd64."""
    cli = LibreSpeedCLI("/fake/path")
    with patch("homeassistant.components.librespeed.librespeed_cli.platform") as mock_plat:
        mock_plat.machine.return_value = "x86_64"
        assert cli.is_cli_supported() is True


def test_is_cli_supported_unsupported() -> None:
    """Test CLI is not supported on armv7l."""
    cli = LibreSpeedCLI("/fake/path")
    with patch("homeassistant.components.librespeed.librespeed_cli.platform") as mock_plat:
        mock_plat.machine.return_value = "armv7l"
        assert cli.is_cli_supported() is False


# ---- cli_path ----


def test_cli_path_default() -> None:
    """Test default cli_path."""
    cli = LibreSpeedCLI("/config")
    assert cli.cli_path == Path("/config/custom_components/librespeed/bin/librespeed-cli")


def test_cli_path_custom() -> None:
    """Test custom cli_path."""
    cli = LibreSpeedCLI("/config", cli_path="/usr/local/bin/librespeed-cli")
    assert cli.cli_path == Path("/usr/local/bin/librespeed-cli")


# ---- check_cli_exists ----


async def test_check_cli_exists_true() -> None:
    """Test CLI exists and is executable."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"1.0.12", b""))
    mock_proc.returncode = 0

    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ),
    ):
        assert await cli.check_cli_exists() is True


async def test_check_cli_exists_path_missing() -> None:
    """Test CLI returns False when path doesn't exist."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/nonexistent/librespeed-cli")
    with patch.object(Path, "exists", return_value=False):
        assert await cli.check_cli_exists() is False


async def test_check_cli_exists_execution_fails() -> None:
    """Test CLI returns False when execution fails."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
    mock_proc.returncode = 1

    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ),
    ):
        assert await cli.check_cli_exists() is False


async def test_check_cli_exists_os_error() -> None:
    """Test CLI returns False on OSError."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            side_effect=OSError("permission denied"),
        ),
    ):
        assert await cli.check_cli_exists() is False


# ---- run_speed_test ----

MOCK_CLI_OUTPUT = json.dumps(
    [
        {
            "download": 250.50,
            "upload": 50.25,
            "ping": 12.34,
            "jitter": 1.56,
            "server": {
                "name": "CLI Test Server",
                "url": "https://cli.librespeed.org/",
            },
            "timestamp": "2026-03-04T12:00:00+00:00",
            "bytes_sent": 50_000_000,
            "bytes_received": 250_000_000,
        }
    ]
)


def _mock_process(stdout=MOCK_CLI_OUTPUT, stderr="", returncode=0):
    """Create a mock subprocess."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(
        return_value=(stdout.encode() if isinstance(stdout, str) else stdout,
                      stderr.encode() if isinstance(stderr, str) else stderr)
    )
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


async def test_run_speed_test_success() -> None:
    """Test successful CLI speed test."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=_mock_process(),
        ),
    ):
        result = await cli.run_speed_test()
    assert result["download"] == 250.50
    assert result["upload"] == 50.25
    assert result["ping"] == 12.34


async def test_run_speed_test_with_server_id() -> None:
    """Test CLI speed test with server ID."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=_mock_process(),
        ) as mock_exec,
    ):
        await cli.run_speed_test(server_id=42)
    # Check --server 42 is in the command args
    call_args = mock_exec.call_args[0]
    assert "--server" in call_args
    idx = list(call_args).index("--server")
    assert call_args[idx + 1] == "42"


async def test_run_speed_test_cli_not_found() -> None:
    """Test error when CLI binary not found."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/nonexistent/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=False),
        pytest.raises(CLINotFoundError),
    ):
        await cli.run_speed_test()


async def test_run_speed_test_nonzero_exit() -> None:
    """Test error on non-zero exit code."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=_mock_process(stdout="", stderr="error", returncode=1),
        ),
        pytest.raises(CLIExecutionError),
    ):
        await cli.run_speed_test()


async def test_run_speed_test_empty_output() -> None:
    """Test error on empty JSON output."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=_mock_process(stdout="[]"),
        ),
        pytest.raises(CLIOutputError),
    ):
        await cli.run_speed_test()


async def test_run_speed_test_invalid_json() -> None:
    """Test error on invalid JSON output."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=_mock_process(stdout="not json at all"),
        ),
        pytest.raises(CLIOutputError),
    ):
        await cli.run_speed_test()


async def test_run_speed_test_timeout() -> None:
    """Test timeout during CLI execution."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()

    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ),
        pytest.raises(SpeedTestTimeoutError),
    ):
        await cli.run_speed_test(timeout=10)


async def test_run_speed_test_os_error() -> None:
    """Test OS error during subprocess creation."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        patch(
            "homeassistant.components.librespeed.librespeed_cli.asyncio.create_subprocess_exec",
            side_effect=OSError("no such file"),
        ),
        pytest.raises(CLIExecutionError),
    ):
        await cli.run_speed_test()


# ---- URL validation ----


def test_validate_url_valid_https() -> None:
    """Test valid HTTPS URL."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("https://example.com") is True


def test_validate_url_valid_http() -> None:
    """Test valid HTTP URL."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("http://example.com") is True


def test_validate_url_invalid_scheme() -> None:
    """Test invalid URL scheme."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("ftp://example.com") is False


def test_validate_url_no_netloc() -> None:
    """Test URL without netloc."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("https://") is False


def test_validate_url_too_long_hostname() -> None:
    """Test hostname exceeding max length."""
    cli = LibreSpeedCLI("/fake/path")
    long_host = "a" * 254 + ".com"
    assert cli._validate_url(f"https://{long_host}") is False


def test_validate_url_malicious_chars() -> None:
    """Test URL with injection characters."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("https://example.com;rm -rf /") is False


def test_validate_url_ip_address() -> None:
    """Test URL with IP address."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("https://192.168.1.1/backend") is True


def test_validate_url_empty() -> None:
    """Test empty URL."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._validate_url("") is False


# ---- _is_valid_ip ----


def test_is_valid_ip_v4() -> None:
    """Test valid IPv4."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._is_valid_ip("192.168.1.1") is True


def test_is_valid_ip_v6() -> None:
    """Test valid IPv6."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._is_valid_ip("::1") is True


def test_is_valid_ip_invalid() -> None:
    """Test invalid IP."""
    cli = LibreSpeedCLI("/fake/path")
    assert cli._is_valid_ip("not_an_ip") is False


# ---- ensure_cli_available ----


async def test_ensure_cli_available_exists() -> None:
    """Test returns True when CLI already exists."""
    cli = LibreSpeedCLI("/fake/path")
    cli.check_cli_exists = AsyncMock(return_value=True)
    assert await cli.ensure_cli_available() is True
    cli.check_cli_exists.assert_called_once()


async def test_ensure_cli_available_downloads() -> None:
    """Test downloads CLI when not found."""
    cli = LibreSpeedCLI("/fake/path")
    cli.check_cli_exists = AsyncMock(return_value=False)
    cli.download_cli = AsyncMock(return_value=True)
    assert await cli.ensure_cli_available() is True


async def test_ensure_cli_available_download_fails() -> None:
    """Test returns False when download fails."""
    cli = LibreSpeedCLI("/fake/path")
    cli.check_cli_exists = AsyncMock(return_value=False)
    cli.download_cli = AsyncMock(return_value=False)
    assert await cli.ensure_cli_available() is False


async def test_ensure_cli_available_force_download() -> None:
    """Test force_download skips exists check."""
    cli = LibreSpeedCLI("/fake/path")
    cli.check_cli_exists = AsyncMock(return_value=True)
    cli.download_cli = AsyncMock(return_value=True)
    await cli.ensure_cli_available(force_download=True)
    cli.download_cli.assert_called_once()


# ---- Server ID validation ----


async def test_run_speed_test_invalid_server_id_type() -> None:
    """Test error on non-integer server ID."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        pytest.raises(LibreSpeedError),
    ):
        await cli.run_speed_test(server_id="not_a_number")


async def test_run_speed_test_server_id_out_of_range() -> None:
    """Test error on out-of-range server ID."""
    cli = LibreSpeedCLI("/fake/path", cli_path="/fake/bin/librespeed-cli")
    with (
        patch.object(Path, "exists", return_value=True),
        pytest.raises(LibreSpeedError),
    ):
        await cli.run_speed_test(server_id=99999)
