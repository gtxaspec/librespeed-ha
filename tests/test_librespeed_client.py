"""Tests for LibreSpeed native Python client."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.components.librespeed.exceptions import (
    NetworkError,
    ServerNotFoundError,
    SpeedTestError,
)
from homeassistant.components.librespeed.librespeed_client import LibreSpeedClient

from .conftest import MOCK_SERVER_LIST


def _mock_response(status=200, json_data=None, text="", read_data=b""):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.text = AsyncMock(return_value=text)
    resp.read = AsyncMock(return_value=read_data)
    resp.release = AsyncMock()
    return resp


def _mock_session():
    """Create a mock aiohttp ClientSession."""
    session = MagicMock(spec=aiohttp.ClientSession)
    return session


# ---- get_servers ----


async def test_get_servers_success() -> None:
    """Test getting server list successfully."""
    session = _mock_session()
    resp = _mock_response(json_data=deepcopy(MOCK_SERVER_LIST))
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    servers = await client.get_servers()
    assert len(servers) >= 2


async def test_get_servers_adds_protocol() -> None:
    """Test servers with // prefix get https: prepended."""
    server_data = [{"id": 1, "name": "S1", "server": "//example.com/"}]
    session = _mock_session()
    resp = _mock_response(json_data=server_data)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    servers = await client.get_servers()
    assert servers[0]["server"].startswith("https:")


async def test_get_servers_network_error() -> None:
    """Test get_servers falls back to defaults on network error."""
    session = _mock_session()
    session.get = MagicMock(side_effect=aiohttp.ClientError())

    client = LibreSpeedClient(session)
    servers = await client.get_servers()
    # Should return default servers
    assert len(servers) > 0


async def test_get_servers_timeout() -> None:
    """Test get_servers falls back on timeout."""
    session = _mock_session()
    session.get = MagicMock(side_effect=asyncio.TimeoutError())

    client = LibreSpeedClient(session)
    servers = await client.get_servers()
    assert len(servers) > 0


# ---- get_best_server ----


async def test_get_best_server_selects_lowest_latency() -> None:
    """Test best server selection by latency."""
    session = _mock_session()
    client = LibreSpeedClient(session)
    client.servers = deepcopy(MOCK_SERVER_LIST)

    # Mock latencies: server 1 = 10ms, server 2 = 5ms
    with patch.object(client, "_test_latency", side_effect=[10.0, 5.0]):
        best = await client.get_best_server()
    assert best["id"] == 2


async def test_get_best_server_no_working_servers() -> None:
    """Test returns first server when all have infinite latency."""
    session = _mock_session()
    client = LibreSpeedClient(session)
    client.servers = deepcopy(MOCK_SERVER_LIST)

    with patch.object(
        client, "_test_latency", return_value=float("inf")
    ):
        best = await client.get_best_server()
    assert best["id"] == 1  # Falls back to first


async def test_get_best_server_fetches_if_empty() -> None:
    """Test fetches server list if empty."""
    session = _mock_session()
    client = LibreSpeedClient(session)
    client.servers = []

    with (
        patch.object(client, "get_servers", return_value=deepcopy(MOCK_SERVER_LIST)),
        patch.object(client, "_test_latency", return_value=5.0),
    ):
        best = await client.get_best_server()
    assert best is not None


# ---- run_speed_test ----


async def test_run_speed_test_result_structure() -> None:
    """Test run_speed_test returns expected result structure."""
    session = _mock_session()
    client = LibreSpeedClient(session)

    mock_result = {
        "download": 100.0,
        "upload": 50.0,
        "ping": 10.0,
        "jitter": 1.0,
        "server": {"id": 1, "name": "S1"},
        "timestamp": MagicMock(),
        "bytes_sent": 1000,
        "bytes_received": 2000,
    }

    with (
        patch.object(client, "get_best_server", return_value=deepcopy(MOCK_SERVER_LIST[0])),
        patch.object(client, "_test_latency", return_value=10.0),
        patch.object(client, "_test_download", return_value=(100.0, 2000)),
        patch.object(client, "_test_upload", return_value=(50.0, 1000)),
    ):
        result = await client.run_speed_test()

    assert "download" in result
    assert "upload" in result
    assert "ping" in result
    assert "jitter" in result
    assert "server" in result
    assert "timestamp" in result
    assert "bytes_sent" in result
    assert "bytes_received" in result


async def test_run_speed_test_by_server_id() -> None:
    """Test speed test with specific server ID."""
    session = _mock_session()
    client = LibreSpeedClient(session)
    client.servers = deepcopy(MOCK_SERVER_LIST)

    with (
        patch.object(client, "_test_latency", return_value=10.0),
        patch.object(client, "_test_download", return_value=(100.0, 2000)),
        patch.object(client, "_test_upload", return_value=(50.0, 1000)),
    ):
        result = await client.run_speed_test(server_id=1)
    assert result["server"]["id"] == 1


async def test_run_speed_test_server_not_found() -> None:
    """Test error when server ID not found."""
    session = _mock_session()
    client = LibreSpeedClient(session)
    client.servers = deepcopy(MOCK_SERVER_LIST)

    with pytest.raises(ServerNotFoundError):
        await client.run_speed_test(server_id=999)


async def test_run_speed_test_cancelled() -> None:
    """Test CancelledError is re-raised."""
    session = _mock_session()
    client = LibreSpeedClient(session)

    with (
        patch.object(client, "get_best_server", side_effect=asyncio.CancelledError()),
        pytest.raises(asyncio.CancelledError),
    ):
        await client.run_speed_test()


# ---- _test_latency ----


async def test_test_latency_success() -> None:
    """Test latency measurement success."""
    session = _mock_session()
    resp = _mock_response(status=200)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    latency = await client._test_latency(MOCK_SERVER_LIST[0])
    assert isinstance(latency, float)
    assert latency >= 0


async def test_test_latency_failure() -> None:
    """Test latency returns inf on failure."""
    session = _mock_session()
    session.get = MagicMock(side_effect=aiohttp.ClientError())

    client = LibreSpeedClient(session)
    latency = await client._test_latency(MOCK_SERVER_LIST[0])
    assert latency == float("inf")


# ---- _download_chunk ----


async def test_download_chunk_success() -> None:
    """Test successful chunk download."""
    session = _mock_session()
    resp = _mock_response(status=200)

    # Mock async iterator for iter_chunked
    async def _iter_chunked(size):
        yield b"x" * 1024

    content = MagicMock()
    content.iter_chunked = _iter_chunked
    resp.content = content

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    bytes_count = await client._download_chunk("https://example.com/garbage.php")
    assert bytes_count == 1024


async def test_download_chunk_non_200() -> None:
    """Test download chunk returns 0 on non-200."""
    session = _mock_session()
    resp = _mock_response(status=500)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    bytes_count = await client._download_chunk("https://example.com/garbage.php")
    assert bytes_count == 0


async def test_download_chunk_timeout() -> None:
    """Test download chunk returns 0 on timeout."""
    session = _mock_session()
    session.get = MagicMock(side_effect=asyncio.TimeoutError())

    client = LibreSpeedClient(session)
    bytes_count = await client._download_chunk("https://example.com/garbage.php")
    assert bytes_count == 0


# ---- _upload_chunk ----


async def test_upload_chunk_success() -> None:
    """Test successful chunk upload."""
    session = _mock_session()
    resp = _mock_response(status=200)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    server = deepcopy(MOCK_SERVER_LIST[0])
    data = b"x" * 1024
    bytes_count = await client._upload_chunk(server, data)
    assert bytes_count == 1024


async def test_upload_chunk_non_200() -> None:
    """Test upload chunk returns 0 on non-200."""
    session = _mock_session()
    resp = _mock_response(status=500)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    server = deepcopy(MOCK_SERVER_LIST[0])
    bytes_count = await client._upload_chunk(server, b"data")
    assert bytes_count == 0


async def test_upload_chunk_timeout() -> None:
    """Test upload chunk returns 0 on timeout."""
    session = _mock_session()
    session.post = MagicMock(side_effect=asyncio.TimeoutError())

    client = LibreSpeedClient(session)
    server = deepcopy(MOCK_SERVER_LIST[0])
    bytes_count = await client._upload_chunk(server, b"data")
    assert bytes_count == 0


# ---- _detect_backend_type ----


async def test_detect_backend_rust() -> None:
    """Test Rust backend detection."""
    session = _mock_session()
    resp = _mock_response(status=200)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=ctx)

    client = LibreSpeedClient(session)
    result = await client._detect_backend_type("https://example.com/", has_backend_path=False)
    assert result == "rust"


async def test_detect_backend_default_php() -> None:
    """Test fallback to PHP when both fail."""
    session = _mock_session()
    session.get = MagicMock(side_effect=aiohttp.ClientError())

    client = LibreSpeedClient(session)
    result = await client._detect_backend_type("https://example.com/", has_backend_path=False)
    assert result == "php"
