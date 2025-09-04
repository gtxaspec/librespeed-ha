"""Pure Python implementation of LibreSpeed client."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import aiohttp
import async_timeout

from .const import (
    DEFAULT_CHUNKS,
    SPEED_TEST_DURATION,
    PING_COUNT,
    PING_INTERVAL,
    SERVER_LIST_TIMEOUT,
    PING_TIMEOUT,
    CHUNK_UPLOAD_TIMEOUT,
    UPLOAD_CHUNK_SIZE,
    DOWNLOAD_CHUNK_SIZE,
    RUST_BACKEND_THRESHOLD,
    MAX_CONCURRENT_DOWNLOADS,
    MAX_CONCURRENT_UPLOADS,
    HTTP_OK,
    STREAM_START_DELAY,
    DOWNLOAD_LOG_INTERVAL_INITIAL,
    DOWNLOAD_LOG_INTERVAL_FREQUENT,
    UPLOAD_LOG_INTERVAL,
    DEFAULT_SPEED_TEST_TIMEOUT,
    DOWNLOAD_CHUNK_PARAM,
    PHP_BACKEND_THRESHOLD,
    ELAPSED_TIME_THRESHOLD,
)
from .exceptions import (
    NetworkError,
    ServerNotFoundError,
    SpeedTestError,
    SpeedTestTimeoutError,
)

LOGGER_NAME = "custom_components.librespeed"
_LOGGER = logging.getLogger(LOGGER_NAME)

# Concurrency control constants are now in const.py

DEFAULT_SERVERS = [
    {
        "id": 1,
        "name": "LibreSpeed Test Server",
        "server": "https://librespeed.org/",
        "location": "Global",
        "sponsor": "LibreSpeed",
        "dlURL": "backend/garbage.php",
        "ulURL": "backend/empty.php",
        "pingURL": "backend/empty.php",
        "getIpURL": "backend/getIP.php",
    }
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LibreSpeed/HomeAssistant",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


class LibreSpeedClient:
    """LibreSpeed test client."""
    
    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the client."""
        self.session = session
        self.servers: list[dict[str, Any]] = []
        
    async def get_servers(self) -> list[dict[str, Any]]:
        """Get list of available test servers."""
        servers = []
        
        # Try to fetch server list from LibreSpeed - it returns JSON
        try:
            _LOGGER.info("Fetching server list from LibreSpeed...")
            async with async_timeout.timeout(SERVER_LIST_TIMEOUT):
                async with self.session.get(
                    "https://librespeed.org/backend-servers/servers.php",
                    headers=HEADERS,
                ) as response:
                    _LOGGER.info("Server list response status: %s", response.status)
                    if response.status == HTTP_OK:
                        # Use response.json() which is already optimized in aiohttp
                        data = await response.json()
                        _LOGGER.debug("Received %d servers from API", len(data) if isinstance(data, list) else 0)
                        # Parse the JSON server list
                        for idx, server in enumerate(data):
                            if isinstance(server, dict):
                                server_url = server.get("server", "").rstrip('/')
                                # Ensure server URL has protocol
                                if server_url.startswith("//"):
                                    server_url = "https:" + server_url
                                elif not server_url.startswith(("http://", "https://")):
                                    server_url = "https://" + server_url
                                    
                                servers.append({
                                    "id": server.get("id", idx + 1),
                                    "name": server.get("name", "Unknown Server"),
                                    "server": server_url,
                                    "location": server.get("location", server.get("name", "Unknown")),
                                    "sponsor": server.get("sponsor", "Unknown"),
                                    # Store the endpoint URLs from the server list
                                    "dlURL": server.get("dlURL", "backend/garbage.php"),
                                    "ulURL": server.get("ulURL", "backend/empty.php"),
                                    "pingURL": server.get("pingURL", "backend/empty.php"),
                                    "getIpURL": server.get("getIpURL", "backend/getIP.php"),
                                })
                        # Sort servers by ID in ascending order
                        servers.sort(key=lambda x: x["id"])
                        _LOGGER.info("Successfully loaded %d servers", len(servers))
        except aiohttp.ClientError as e:
            _LOGGER.error("Network error fetching server list: %s", e)
        except json.JSONDecodeError as e:
            _LOGGER.error("Failed to parse server list JSON: %s", e)
        except asyncio.TimeoutError:
            _LOGGER.error("Server list fetch timed out")
        
        # If no servers found, use defaults
        if not servers:
            servers = DEFAULT_SERVERS.copy()
            
        self.servers = servers
        return servers
    
    async def get_best_server(self) -> dict[str, Any]:
        """Find the best server based on latency.
        
        Follows LibreSpeed's approach: tests servers in parallel with limited concurrency.
        """
        if not self.servers:
            await self.get_servers()
        
        if not self.servers:
            return DEFAULT_SERVERS[0]
        
        _LOGGER.info("Testing latency to %d servers...", len(self.servers))
        
        # LibreSpeed uses CONCURRENCY=6 for parallel testing
        CONCURRENCY = 6
        best_server = None
        best_latency = float('inf')
        working_servers = 0
        
        # Process servers in batches with limited concurrency
        for i in range(0, len(self.servers), CONCURRENCY):
            batch = self.servers[i:i + CONCURRENCY]
            
            # Test this batch of servers concurrently
            async def test_server(server):
                latency = await self._test_latency(server)
                return server, latency
            
            tasks = [test_server(server) for server in batch]
            results = await asyncio.gather(*tasks)
            
            # Check results from this batch
            for server, latency in results:
                if latency != float('inf'):
                    working_servers += 1
                    if latency < best_latency:
                        best_latency = latency
                        best_server = server
                        _LOGGER.debug("New best: %s (%.2f ms)", server['name'], latency)
            
            # Log progress
            servers_tested = min(i + CONCURRENCY, len(self.servers))
            _LOGGER.info("Tested %d/%d servers, found %d working, current best: %s", 
                        servers_tested, len(self.servers), working_servers,
                        best_server['name'] if best_server else 'None')
        
        if best_server:
            _LOGGER.info("Selected server: %s with %.2f ms latency", best_server['name'], best_latency)
        else:
            _LOGGER.warning("No working servers found, using fallback")
        
        return best_server or self.servers[0]
    
    async def _create_custom_server(self, custom_server_url: str) -> dict[str, Any]:
        """Create a custom server object, detecting the backend type."""
        from urllib.parse import urlparse
        parsed = urlparse(custom_server_url.rstrip('/'))
        
        # Check if the path indicates this is already a backend endpoint
        # Common backend paths: /backend, /rs, /speedtest, etc.
        has_backend_path = bool(parsed.path and parsed.path != '/')
        
        # Build base server object
        server = {
            "id": 0,
            "name": "Custom Server",
            "server": custom_server_url.rstrip('/'),
            "location": "Custom",
            "sponsor": "User Defined"
        }
        
        # Try to detect backend type by testing common endpoints
        backend_type = await self._detect_backend_type(custom_server_url, has_backend_path)
        
        if backend_type == 'rust':
            # Rust/Go backend - no file extensions
            if has_backend_path:
                server.update({
                    "dlURL": "garbage",
                    "ulURL": "empty",
                    "pingURL": "empty",
                    "getIpURL": "getIP"
                })
            else:
                # Base URL - unlikely for Rust but handle it
                server.update({
                    "dlURL": "backend/garbage",
                    "ulURL": "backend/empty",
                    "pingURL": "backend/empty",
                    "getIpURL": "backend/getIP"
                })
            _LOGGER.info("Detected Rust/Go backend for custom server")
        else:
            # PHP backend - uses .php extensions
            if has_backend_path:
                # URL already includes backend path
                server.update({
                    "dlURL": "garbage.php",
                    "ulURL": "empty.php",
                    "pingURL": "empty.php",
                    "getIpURL": "getIP.php"
                })
            else:
                # URL is just the base
                server.update({
                    "dlURL": "backend/garbage.php",
                    "ulURL": "backend/empty.php",
                    "pingURL": "backend/empty.php",
                    "getIpURL": "backend/getIP.php"
                })
            _LOGGER.info("Detected PHP backend for custom server")
        
        return server
    
    async def _detect_backend_type(self, server_url: str, has_backend_path: bool) -> str:
        """Detect if the server is using PHP or Rust/Go backend."""
        server_url = server_url.rstrip('/')
        
        # Test endpoints to check
        if has_backend_path:
            # Try Rust/Go endpoints first (no extensions)
            rust_test = f"{server_url}/empty"
            php_test = f"{server_url}/empty.php"
        else:
            rust_test = f"{server_url}/backend/empty"
            php_test = f"{server_url}/backend/empty.php"
        
        # Try Rust/Go endpoint first
        try:
            async with async_timeout.timeout(PING_TIMEOUT):
                async with self.session.get(rust_test, headers=HEADERS) as response:
                    if response.status == HTTP_OK:
                        _LOGGER.debug("Rust/Go backend detected at %s", rust_test)
                        return 'rust'
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.debug("Rust/Go endpoint test failed: %s", e)
        
        # Try PHP endpoint
        try:
            async with async_timeout.timeout(PING_TIMEOUT):
                async with self.session.get(php_test, headers=HEADERS) as response:
                    if response.status == HTTP_OK:
                        _LOGGER.debug("PHP backend detected at %s", php_test)
                        return 'php'
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.debug("PHP endpoint test failed: %s", e)
        
        # Default to PHP if we can't detect
        _LOGGER.warning("Could not detect backend type, defaulting to PHP")
        return 'php'
    
    async def _test_latency(self, server: str | dict) -> float:
        """Test latency to a server."""
        try:
            # Handle both string URL and dict server objects
            if isinstance(server, dict):
                server_url = server.get('server', '')
                ping_path = server.get('pingURL', 'backend/empty.php')
            else:
                server_url = server
                ping_path = 'backend/empty.php'
            
            # Ensure server URL has protocol
            if server_url.startswith("//"):
                server_url = "https:" + server_url
            elif not server_url.startswith(("http://", "https://")):
                server_url = "https://" + server_url
                
            start = time.time()
            # LibreSpeed uses 2 second timeout for ping tests
            async with async_timeout.timeout(PING_TIMEOUT):
                # Build the ping URL using the server's specific endpoint
                ping_url = f"{server_url.rstrip('/')}/{ping_path}"
                
                _LOGGER.debug("Testing latency to: %s", ping_url)
                async with self.session.get(
                    ping_url,
                    headers=HEADERS,
                ) as response:
                    if response.status != HTTP_OK:
                        _LOGGER.warning("Latency test got status %s from %s", response.status, ping_url)
                        return float('inf')
                    await response.read()
                    latency = (time.time() - start) * 1000  # Convert to ms
                    _LOGGER.debug("Latency test response status: %s, time: %.2f ms", response.status, latency)
            return latency
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            _LOGGER.warning("Latency test failed to %s: %s", server_url if isinstance(server, str) else server.get('name', 'Unknown'), str(e))
            return float('inf')
    
    async def run_speed_test(
        self, 
        server: dict[str, Any] | None = None,
        server_id: int | None = None,
        custom_server_url: str | None = None,
        timeout: int = DEFAULT_SPEED_TEST_TIMEOUT,
    ) -> dict[str, Any]:
        """Run a complete speed test."""
        _LOGGER.info("Starting speed test...")
        
        # Determine which server to use
        if custom_server_url:
            # For custom servers, we need to detect the backend type
            # We'll do this by attempting a test request
            server = await self._create_custom_server(custom_server_url)
            _LOGGER.info("Using custom server: %s", custom_server_url)
        elif server_id is not None:
            if not self.servers:
                await self.get_servers()
            server = next((s for s in self.servers if s['id'] == server_id), None)
            if not server:
                _LOGGER.error("Server ID %d not found in %d available servers", server_id, len(self.servers))
                raise ServerNotFoundError(f"Server ID {server_id} not found")
            _LOGGER.info("Using server ID %d: %s", server_id, server.get('name'))
        elif not server:
            _LOGGER.debug("No server specified, finding best server...")
            server = await self.get_best_server()
        
        _LOGGER.info("Selected server: %s (%s)", server.get('name'), server.get('server'))
        
        # Run the speed test
        result = {
            "download": 0,
            "upload": 0,
            "ping": 0,
            "jitter": 0,
            "server": server,
            "timestamp": datetime.now(timezone.utc),  # Return datetime object
            "bytes_sent": 0,
            "bytes_received": 0,
        }
        
        try:
            # Wrap entire test in timeout
            async with async_timeout.timeout(timeout):
                # Test ping and jitter
                _LOGGER.debug("Testing ping and jitter...")
                ping_results = []
                for i in range(PING_COUNT):
                    latency = await self._test_latency(server)  # Pass the whole server dict
                    if latency != float('inf'):
                        ping_results.append(latency)
                        _LOGGER.debug("Ping %d: %.2f ms", i+1, latency)
                    await asyncio.sleep(PING_INTERVAL)
                
                if ping_results:
                    result['ping'] = round(min(ping_results), 2)
                    result['jitter'] = round(
                        sum(abs(ping_results[i] - ping_results[i-1]) 
                            for i in range(1, len(ping_results))) / (len(ping_results) - 1),
                        2
                    ) if len(ping_results) > 1 else 0
                    _LOGGER.info("Ping: %.2f ms, Jitter: %.2f ms", result['ping'], result['jitter'])
                else:
                    _LOGGER.warning("No successful ping measurements")
                
                # Test download speed
                _LOGGER.info("Testing download speed...")
                download_speed, bytes_received = await self._test_download(server)
                result['download'] = round(download_speed, 2)
                result['bytes_received'] = bytes_received
                _LOGGER.info("Download speed: %.2f Mbps (%d bytes)", download_speed, bytes_received)
                
                # Test upload speed
                _LOGGER.info("Testing upload speed...")
                upload_speed, bytes_sent = await self._test_upload(server)
                result['upload'] = round(upload_speed, 2)
                result['bytes_sent'] = bytes_sent
                _LOGGER.info("Upload speed: %.2f Mbps (%d bytes)", upload_speed, bytes_sent)
            
        except (SpeedTestError, ServerNotFoundError):
            # Re-raise our custom exceptions
            raise
        except asyncio.TimeoutError:
            _LOGGER.error("Speed test timed out after %d seconds", timeout)
            raise NetworkError(f"Speed test timed out after {timeout} seconds")
        except asyncio.CancelledError:
            _LOGGER.info("Speed test was cancelled")
            raise
        except (aiohttp.ClientError) as e:
            _LOGGER.error("Network error during speed test: %s", e)
            raise NetworkError(f"Speed test network error: {e}")
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            _LOGGER.error("Data processing error during speed test: %s", e, exc_info=True)
            raise SpeedTestError(f"Speed test data error: {e}")
        
        return result
    
    async def _test_download(self, server: dict) -> tuple[float, int]:
        """Test download speed using LibreSpeed protocol."""
        # Build the download URL using the server's specific endpoint
        server_url = server.get('server', '')
        if server_url.startswith("//"):
            server_url = "https:" + server_url
        elif not server_url.startswith(("http://", "https://")):
            server_url = "https://" + server_url
        
        dl_path = server.get('dlURL', 'backend/garbage.php')
        base_url = f"{server_url.rstrip('/')}/{dl_path}"
            
        total_bytes = 0
        start_time = time.time()
        test_duration = SPEED_TEST_DURATION
        concurrent_requests = min(3, MAX_CONCURRENT_DOWNLOADS)  # Limit concurrent requests
        chunks = DEFAULT_CHUNKS  # Server decides actual size per chunk
        
        _LOGGER.info("Starting download test (15 seconds) with %d concurrent requests", concurrent_requests)
        _LOGGER.debug("Download URL: %s", base_url)
        
        active_tasks = []
        downloads_completed = 0
        
        # Create a semaphore to limit concurrent downloads
        download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        
        async def do_download(stream_id: int):
            """Download function that continuously downloads until time expires."""
            nonlocal total_bytes, downloads_completed
            
            while (time.time() - start_time) < test_duration:
                async with download_semaphore:  # Acquire semaphore before downloading
                    try:
                        # Start with smaller chunks for all backends to be safe
                        # We'll adapt based on response size
                        if not hasattr(self, '_detected_backend_type'):
                            # Start with smaller chunks until we detect the backend type
                            chunk_param = DOWNLOAD_CHUNK_PARAM
                        elif self._detected_backend_type == 'rust':
                            # Rust backend - request smaller chunks more frequently
                            chunk_param = DOWNLOAD_CHUNK_PARAM  # Request 20 chunks at a time (~10MB)
                        else:
                            # PHP backend - use default
                            chunk_param = chunks
                        
                        # Generate unique URL for each request
                        url = f"{base_url}?r={random.random()}&ckSize={chunk_param}"
                        bytes_received = await self._download_chunk(url)
                        
                        if bytes_received > 0:
                            total_bytes += bytes_received
                            downloads_completed += 1
                            
                            # Try to detect backend type based on response size
                            if not hasattr(self, '_detected_backend_type'):
                                if bytes_received > RUST_BACKEND_THRESHOLD:  # Suggests Rust backend
                                    self._detected_backend_type = 'rust'
                                    _LOGGER.debug("Detected Rust backend based on large response size: %d bytes", bytes_received)
                                elif downloads_completed > PHP_BACKEND_THRESHOLD:  # Assume PHP backend
                                    self._detected_backend_type = 'php'
                                    _LOGGER.debug("Detected PHP backend based on smaller responses")
                            
                            # Log progress periodically
                            elapsed = time.time() - start_time
                            if elapsed > 0 and (downloads_completed % DOWNLOAD_LOG_INTERVAL_INITIAL == 0 or (elapsed > ELAPSED_TIME_THRESHOLD and downloads_completed % DOWNLOAD_LOG_INTERVAL_FREQUENT == 0)):
                                current_speed = (total_bytes * 8) / elapsed / 1_000_000
                                _LOGGER.info("Download progress: %.2f Mbps (%d MB in %.1fs, %d requests)", 
                                           current_speed, total_bytes / 1_000_000, elapsed, downloads_completed)
                    except asyncio.CancelledError:
                        break
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        _LOGGER.warning("Download stream %d network error: %s", stream_id, e)
                        await asyncio.sleep(PING_INTERVAL)
                    
        # Start concurrent download streams with 200ms delay between each
        for i in range(concurrent_requests):
            task = asyncio.create_task(do_download(i))
            active_tasks.append(task)
            if i < concurrent_requests - 1:
                await asyncio.sleep(STREAM_START_DELAY)  # Delay as per CLI
        
        try:
            # Let downloads run for test duration
            try:
                await asyncio.sleep(test_duration)
            except asyncio.CancelledError:
                pass
        finally:
            # Always cleanup tasks, even on exception
            for task in active_tasks:
                task.cancel()
            
            # Wait for cancellations to complete
            await asyncio.gather(*active_tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        if total_bytes > 0 and elapsed > 0:
            # Calculate average speed
            speed = (total_bytes * 8) / elapsed / 1_000_000
            _LOGGER.info("Download test complete: %.2f Mbps (%d MB in %.1f seconds)", 
                        speed, total_bytes / 1_000_000, elapsed)
        else:
            speed = 0
            _LOGGER.warning("Download test failed: elapsed=%.1f, bytes=%d", elapsed, total_bytes)
        
        return speed, total_bytes
    
    async def _download_chunk(self, url: str) -> int:
        """Download a chunk and return bytes received."""
        try:
            # Ensure URL has protocol
            if url.startswith("//"):
                url = "https:" + url
            elif not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            async with async_timeout.timeout(CHUNK_UPLOAD_TIMEOUT):  # Timeout for larger chunks
                async with self.session.get(url, headers=HEADERS) as response:
                    if response.status != HTTP_OK:
                        _LOGGER.warning("Download chunk got status %s from %s", response.status, url)
                        return 0
                    
                    # For chunked transfer encoding (Rust backend), read in chunks
                    # For regular responses (PHP backend), read all at once
                    total_bytes = 0
                    chunk_size = DOWNLOAD_CHUNK_SIZE
                    
                    async for data in response.content.iter_chunked(chunk_size):
                        total_bytes += len(data)
                    
                    return total_bytes
                    
        except asyncio.TimeoutError:
            _LOGGER.warning("Download chunk timed out from %s", url)
            return 0
        except aiohttp.ClientError as e:
            _LOGGER.warning("Download chunk HTTP error from %s: %s", url, str(e))
            return 0
        except asyncio.CancelledError:
            # Don't log cancellation as error
            raise
        except Exception as e:  # Keep broad for unexpected errors in chunks
            _LOGGER.debug("Download chunk system error from %s: %s", url, e)
            return 0
    
    async def _test_upload(self, server: dict) -> tuple[float, int]:
        """Test upload speed using LibreSpeed protocol."""
        # Build the upload URL using the server's specific endpoint
        server_url = server.get('server', '')
        if server_url.startswith("//"):
            server_url = "https:" + server_url
        elif not server_url.startswith(("http://", "https://")):
            server_url = "https://" + server_url
        
        ul_path = server.get('ulURL', 'backend/empty.php')
        base_url = f"{server_url.rstrip('/')}/{ul_path}"
        
        # Generate upload data (LibreSpeed CLI default: 1024 KiB)
        upload_size = UPLOAD_CHUNK_SIZE
        
        # Generate random data asynchronously to avoid blocking
        import os
        import asyncio
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, os.urandom, upload_size)
        
        total_bytes = 0
        start_time = time.time()
        test_duration = SPEED_TEST_DURATION
        concurrent_requests = min(3, MAX_CONCURRENT_UPLOADS)  # Limit concurrent requests
        
        _LOGGER.info("Starting upload test (15 seconds) with %d concurrent requests", concurrent_requests)
        
        active_tasks = []
        uploads_completed = 0
        
        # Create a semaphore to limit concurrent uploads
        upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
        
        async def do_upload(stream_id: int):
            """Upload function that continuously uploads until time expires."""
            nonlocal total_bytes, uploads_completed
            
            while (time.time() - start_time) < test_duration:
                async with upload_semaphore:  # Acquire semaphore before uploading
                    try:
                        bytes_sent = await self._upload_chunk(server, data)
                        
                        if bytes_sent > 0:
                            total_bytes += bytes_sent
                            uploads_completed += 1
                            
                            # Log progress periodically (less frequently for uploads)
                            if uploads_completed % UPLOAD_LOG_INTERVAL == 0:
                                elapsed = time.time() - start_time
                                if elapsed > 0:
                                    current_speed = (total_bytes * 8) / elapsed / 1_000_000
                                    _LOGGER.info("Upload progress: %.2f Mbps (%d MB in %.1fs, %d chunks)", 
                                               current_speed, total_bytes / 1_000_000, elapsed, uploads_completed)
                    except asyncio.CancelledError:
                        break
                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        _LOGGER.warning("Upload stream %d network error: %s", stream_id, e)
                        await asyncio.sleep(PING_INTERVAL)
        
        # Start concurrent upload streams with 200ms delay between each
        for i in range(concurrent_requests):
            task = asyncio.create_task(do_upload(i))
            active_tasks.append(task)
            if i < concurrent_requests - 1:
                await asyncio.sleep(STREAM_START_DELAY)  # Delay as per CLI
        
        try:
            # Let uploads run for test duration
            try:
                await asyncio.sleep(test_duration)
            except asyncio.CancelledError:
                pass
        finally:
            # Always cleanup tasks, even on exception
            for task in active_tasks:
                task.cancel()
            
            # Wait for cancellations to complete
            await asyncio.gather(*active_tasks, return_exceptions=True)
        
        elapsed = time.time() - start_time
        
        if total_bytes > 0 and elapsed > 0:
            # Calculate average speed
            speed = (total_bytes * 8) / elapsed / 1_000_000
            _LOGGER.info("Upload test complete: %.2f Mbps (%d MB in %.1f seconds)", 
                        speed, total_bytes / 1_000_000, elapsed)
        else:
            speed = 0
            _LOGGER.warning("Upload test failed: elapsed=%.1f, bytes=%d", elapsed, total_bytes)
        
        return speed, total_bytes
    
    async def _upload_chunk(self, server: dict, data: bytes) -> int:
        """Upload a chunk and return bytes sent."""
        try:
            # Build the upload URL using the server's specific endpoint
            server_url = server.get('server', '')
            if server_url.startswith("//"):
                server_url = "https:" + server_url
            elif not server_url.startswith(("http://", "https://")):
                server_url = "https://" + server_url
            
            ul_path = server.get('ulURL', 'backend/empty.php')
            upload_url = f"{server_url.rstrip('/')}/{ul_path}"
                
            async with async_timeout.timeout(CHUNK_UPLOAD_TIMEOUT):  # Increased timeout for large uploads
                async with self.session.post(
                    upload_url,
                    data=data,
                    headers={**HEADERS, "Content-Type": "application/octet-stream"},
                ) as response:
                    # Just check status, don't need to read response
                    if response.status not in (200, 201, 204):
                        _LOGGER.warning("Upload chunk got status %s to %s", response.status, upload_url)
                        return 0
                    return len(data)
        except asyncio.TimeoutError:
            _LOGGER.warning("Upload chunk timed out to %s", upload_url)
            return 0
        except aiohttp.ClientError as e:
            _LOGGER.warning("Upload chunk HTTP error to %s: %s", upload_url, str(e))
            return 0
        except asyncio.CancelledError:
            # Don't log cancellation as error
            raise
        except Exception as e:  # Keep broad for unexpected errors in chunks
            _LOGGER.debug("Upload chunk system error to %s: %s", upload_url, e)
            return 0
    
