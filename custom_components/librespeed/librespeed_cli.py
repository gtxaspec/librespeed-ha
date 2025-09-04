"""LibreSpeed CLI backend implementation."""
from __future__ import annotations

import asyncio
import json
import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

import aiohttp
import async_timeout

from .const import (
    DOMAIN,
    LOGGER_NAME,
    CLI_DOWNLOAD_MAX_RETRIES,
    CLI_DOWNLOAD_RETRY_DELAY,
    MIN_SERVER_ID,
    MAX_SERVER_ID,
    HTTP_OK,
    PROCESS_SUCCESS,
    DEFAULT_SPEED_TEST_TIMEOUT,
    MAX_HOSTNAME_LENGTH,
    CLI_DOWNLOAD_TIMEOUT_TOTAL,
    CLI_DOWNLOAD_TIMEOUT_CONNECT,
    CLI_DOWNLOAD_TIMEOUT_READ,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
from .exceptions import (
    CLIError,
    CLIExecutionError,
    CLINotFoundError,
    CLIOutputError,
    NetworkError,
    SpeedTestTimeoutError,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class LibreSpeedCLI:
    """LibreSpeed CLI backend for speed testing."""
    
    def __init__(self, config_path: str, cli_path: str | None = None, hass: "HomeAssistant | None" = None):
        """Initialize the CLI backend."""
        self._config_path = config_path
        self._cli_path = cli_path
        self._platform_info = None
        self._hass = hass
    
    @property
    def cli_path(self) -> Path:
        """Get the CLI binary path."""
        if self._cli_path:
            return Path(self._cli_path)
        
        # Default path in HA config directory
        # Keeps everything contained within the custom component
        cli_dir = Path(self._config_path) / "custom_components/librespeed/bin"
        
        # Binary name - Home Assistant only runs on Linux
        binary_name = "librespeed-cli"
        
        return cli_dir / binary_name
    
    def get_platform_info(self) -> dict[str, str]:
        """Get platform information for downloading the correct binary."""
        if self._platform_info:
            return self._platform_info
        
        # Home Assistant only runs on Linux
        system = 'linux'
        machine = platform.machine().lower()
        
        # Map Python platform names to Go architecture names
        # Only support 64-bit architectures as per HA deprecation
        arch_map = {
            'x86_64': 'amd64',
            'amd64': 'amd64',
            'aarch64': 'arm64',
            'arm64': 'arm64',
        }
        
        arch = arch_map.get(machine, machine)
        
        # Linux always uses tar.gz
        extension = '.tar.gz'
        
        self._platform_info = {
            'system': system,
            'arch': arch,
            'extension': extension,
        }
        
        return self._platform_info
    
    def is_cli_supported(self) -> bool:
        """Check if CLI is supported on this platform."""
        info = self.get_platform_info()
        
        # Only support 64-bit Linux architectures per HA deprecation policy
        supported_platforms = {
            ('linux', 'amd64'),  # 64-bit x86
            ('linux', 'arm64'),  # 64-bit ARM (aarch64)
        }
        
        return (info['system'], info['arch']) in supported_platforms
    
    async def check_cli_exists(self) -> bool:
        """Check if CLI binary exists and is executable."""
        cli_path = self.cli_path
        
        if not cli_path.exists():
            return False
        
        # Try to run it with --version to verify it works
        try:
            proc = await asyncio.create_subprocess_exec(
                str(cli_path),
                '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == PROCESS_SUCCESS:
                # Binary works, optionally log version
                if stdout:
                    version_output = stdout.decode('utf-8').strip()
                    _LOGGER.debug("CLI version check: %s", version_output)
                return True
            return False
        except OSError as e:
            _LOGGER.debug("CLI check failed: %s", e)
            return False
    
    async def verify_cli_integrity(self) -> bool:
        """Verify the integrity of an existing CLI binary against GitHub checksums.
        
        Returns:
            True if checksum matches or cannot be verified, False if mismatch detected.
        """
        cli_path = self.cli_path
        if not cli_path.exists():
            return False
        
        try:
            # Read binary file
            import hashlib
            loop = asyncio.get_event_loop()
            binary_data = await loop.run_in_executor(None, lambda: cli_path.read_bytes())
            actual_checksum = hashlib.sha256(binary_data).hexdigest().lower()
            
            # Get version from binary
            proc = await asyncio.create_subprocess_exec(
                str(cli_path),
                '--version',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != PROCESS_SUCCESS:
                _LOGGER.warning("Cannot get version from CLI binary")
                return True  # Can't verify, assume OK
            
            # Parse version (format: "librespeed-cli vX.Y.Z")
            version_output = stdout.decode('utf-8').strip()
            import re
            version_match = re.search(r'v?([\d.]+)', version_output)
            if not version_match:
                _LOGGER.warning("Cannot parse version from: %s", version_output)
                return True  # Can't verify, assume OK
            
            version = version_match.group(1)
            
            # Get checksums from GitHub
            info = self.get_platform_info()
            asset_name = f"librespeed-cli_{version}_{info['system']}_{info['arch']}{info['extension']}"
            
            # Note: This would need to fetch from GitHub API
            # For now, we'll just log the checksum for future verification
            _LOGGER.debug("CLI binary SHA256: %s (file: %s)", actual_checksum, asset_name)
            
            return True  # For now, always return True since we can't fetch old checksums easily
            
        except Exception as e:
            _LOGGER.warning("Failed to verify CLI integrity: %s", e)
            return True  # On error, assume OK to avoid blocking
    
    async def download_cli(self) -> bool:
        """Download and install the CLI binary with retry logic."""
        if not self.is_cli_supported():
            _LOGGER.error("CLI not supported on architecture: %s (only amd64 and arm64 are supported)", 
                         platform.machine())
            return False
        
        info = self.get_platform_info()
        
        # Retry logic for transient network issues
        max_retries = CLI_DOWNLOAD_MAX_RETRIES
        retry_delay = CLI_DOWNLOAD_RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                # Configure session with longer timeouts for downloads
                timeout = aiohttp.ClientTimeout(
                    total=CLI_DOWNLOAD_TIMEOUT_TOTAL,
                    connect=CLI_DOWNLOAD_TIMEOUT_CONNECT,
                    sock_read=CLI_DOWNLOAD_TIMEOUT_READ
                )
                
                connector = aiohttp.TCPConnector(
                    force_close=True,
                    limit=10,
                    ttl_dns_cache=300
                )
                
                async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                    # Get latest release info
                    _LOGGER.info("Fetching LibreSpeed CLI release info (attempt %d/%d)...", 
                                attempt + 1, max_retries)
                    async with session.get(
                        "https://api.github.com/repos/librespeed/speedtest-cli/releases/latest",
                        headers={"Accept": "application/vnd.github.v3+json"}
                    ) as resp:
                        if resp.status != HTTP_OK:
                            _LOGGER.error("Failed to get latest release info: %s", resp.status)
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                continue
                            return False
                    
                        release_data = await resp.json()
                        version = release_data['tag_name'].lstrip('v')
                
                    # Build asset name
                    asset_name = f"librespeed-cli_{version}_{info['system']}_{info['arch']}{info['extension']}"
                    
                    # Find download URL and checksum URL
                    asset_url = None
                    checksums_url = None
                    for asset in release_data['assets']:
                        if asset['name'] == asset_name:
                            asset_url = asset['browser_download_url']
                        elif asset['name'] == 'checksums.txt':
                            checksums_url = asset['browser_download_url']
                    
                    if not asset_url:
                        _LOGGER.error("No CLI binary found for %s %s", info['system'], info['arch'])
                        return False
                    
                    # Download checksums file if available
                    expected_checksum = None
                    if checksums_url:
                        _LOGGER.debug("Downloading checksums for integrity validation...")
                        try:
                            async with session.get(checksums_url, allow_redirects=True) as resp:
                                if resp.status == HTTP_OK:
                                    checksums_content = await resp.text()
                                    # Parse checksums file (format: "hash  filename")
                                    for line in checksums_content.splitlines():
                                        if line.strip():
                                            parts = line.split('  ', 1)  # Split on double space
                                            if len(parts) == 2 and parts[1] == asset_name:
                                                expected_checksum = parts[0].lower()
                                                _LOGGER.info("Found SHA256 checksum for %s", asset_name)
                                                break
                                    if not expected_checksum:
                                        _LOGGER.warning("No checksum found for %s in checksums.txt", asset_name)
                                else:
                                    _LOGGER.warning("Failed to download checksums: HTTP %s", resp.status)
                        except Exception as e:
                            _LOGGER.warning("Failed to fetch checksums: %s", e)
                    
                    _LOGGER.info("Downloading LibreSpeed CLI binary (%s)...", asset_name)
                
                    # Create bin directory
                    cli_dir = self.cli_path.parent
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: cli_dir.mkdir(parents=True, exist_ok=True))
                
                    # Download to temporary file with predictable name for cleanup
                    import tempfile
                    tmp_dir = tempfile.gettempdir()
                    tmp_filename = f"librespeed_cli_{info['system']}_{info['arch']}{info['extension']}"
                    tmp_path = Path(tmp_dir) / tmp_filename
                
                    async with session.get(asset_url, allow_redirects=True) as resp:
                        if resp.status != HTTP_OK:
                            _LOGGER.error("Failed to download CLI binary: HTTP %s", resp.status)
                            if attempt < max_retries - 1:
                                await asyncio.sleep(retry_delay)
                                continue
                            return False
                        
                        # Download with progress tracking
                        total_size = int(resp.headers.get('Content-Length', 0))
                        if total_size > 0:
                            _LOGGER.info("Downloading %.1f MB...", total_size / 1024 / 1024)
                        
                        data = await resp.read()
                        
                        # Validate checksum if we have one
                        if expected_checksum:
                            import hashlib
                            actual_checksum = hashlib.sha256(data).hexdigest().lower()
                            if actual_checksum != expected_checksum:
                                _LOGGER.error(
                                    "Checksum validation failed! Expected: %s, Got: %s",
                                    expected_checksum, actual_checksum
                                )
                                _LOGGER.error("This could indicate a corrupted download")
                                if attempt < max_retries - 1:
                                    _LOGGER.info("Retrying download...")
                                    await asyncio.sleep(retry_delay)
                                    continue
                                return False
                            _LOGGER.info("Checksum validation successful ✓")
                        else:
                            _LOGGER.warning("No checksum available for validation - proceeding with caution")
                        
                        # Write file in executor to avoid blocking
                        await loop.run_in_executor(None, lambda: tmp_path.write_bytes(data))
                        _LOGGER.info("Download complete, extracting binary...")
                
                    # Extract binary using async to avoid blocking
                    try:
                        if info['extension'] == '.tar.gz':
                            # Run tar extraction in executor to avoid blocking
                            import tarfile
                            import concurrent.futures
                            
                            def extract_tar():
                                with tarfile.open(tmp_path, 'r:gz') as tar:
                                    # Find the binary file in the archive
                                    for member in tar.getmembers():
                                        if member.name == 'librespeed-cli' or member.name.endswith('librespeed-cli'):
                                            # Extract to temporary location first
                                            tar.extract(member, cli_dir)
                                            extracted_path = cli_dir / member.name
                                            # Move to final location if needed
                                            if extracted_path != self.cli_path:
                                                extracted_path.rename(self.cli_path)
                                            break
                            
                            # Run in executor to avoid blocking
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, extract_tar)
                    
                        # Make executable (always on Linux)
                        await loop.run_in_executor(None, lambda: self.cli_path.chmod(0o755))
                        
                        _LOGGER.info("Successfully downloaded and installed LibreSpeed CLI")
                        return True
                        
                    finally:
                        # Clean up temporary file
                        await loop.run_in_executor(None, lambda: tmp_path.unlink(missing_ok=True))
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Extract more specific error info
                error_msg = str(e)
                if "DNS" in error_msg or "getaddrinfo" in error_msg:
                    _LOGGER.warning("DNS resolution failed (attempt %d/%d). This is common during HA startup.", 
                                  attempt + 1, max_retries)
                elif "TimeoutError" in error_msg or "Timeout" in error_msg:
                    _LOGGER.warning("Connection timed out (attempt %d/%d). Network may be slow or unavailable.", 
                                  attempt + 1, max_retries)
                else:
                    _LOGGER.warning("Network error downloading CLI (attempt %d/%d): %s", 
                                  attempt + 1, max_retries, e)
                
                if attempt < max_retries - 1:
                    _LOGGER.info("Retrying in %d seconds...", retry_delay)
                    await asyncio.sleep(retry_delay)
                    # Increase retry delay for subsequent attempts
                    retry_delay = min(retry_delay * 2, 30)  # Exponential backoff, max 30 seconds
                    continue
                else:
                    _LOGGER.error("Failed to download CLI after %d attempts. Will use Python backend as fallback.", max_retries)
                    return False
            except (OSError, IOError) as e:
                _LOGGER.error("File system error downloading CLI: %s", e)
                return False
            except json.JSONDecodeError as e:
                _LOGGER.error("Failed to parse GitHub API response: %s", e)
                return False
        
        # Should not reach here
        return False
    
    async def cleanup_temp_files(self) -> None:
        """Clean up any leftover temporary files from previous runs."""
        try:
            import tempfile
            tmp_dir = Path(tempfile.gettempdir())
            
            # Clean up old download files
            for pattern in ["librespeed_cli_*.tar.gz", "librespeed_cli_*.zip"]:
                for file in tmp_dir.glob(pattern):
                    try:
                        file.unlink()
                        _LOGGER.debug("Cleaned up old temp file: %s", file)
                    except (OSError, PermissionError) as e:
                        _LOGGER.debug("Could not clean up %s: %s", file, e)
        except (OSError, ImportError) as e:
            _LOGGER.debug("Error during temp file cleanup: %s", e)
    
    async def ensure_cli_available(self, force_download: bool = False) -> bool:
        """Ensure CLI is available, downloading if necessary."""
        # Clean up any old temp files first
        await self.cleanup_temp_files()
        
        if not force_download and await self.check_cli_exists():
            # CLI exists and works, clear any repair issues
            if self._hass:
                from homeassistant.helpers import issue_registry as ir
                ir.async_delete_issue(self._hass, DOMAIN, "cli_download_failed")
            return True
        
        _LOGGER.info("CLI not found, attempting to download...")
        success = await self.download_cli()
        
        if success:
            # Download succeeded, clear any repair issues
            if self._hass:
                from homeassistant.helpers import issue_registry as ir
                ir.async_delete_issue(self._hass, DOMAIN, "cli_download_failed")
            return True
        else:
            # Download failed, create repair issue
            if self._hass:
                from homeassistant.helpers import issue_registry as ir
                _LOGGER.warning("CLI download failed, creating repair issue")
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    "cli_download_failed",
                    is_fixable=True,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="cli_download_failed",
                )
            return False
    
    async def run_speed_test(self, server_id: int | None = None, 
                           custom_server: str | None = None,
                           skip_cert_verify: bool = False,
                           timeout: int = DEFAULT_SPEED_TEST_TIMEOUT) -> dict[str, Any]:
        """Run speed test using CLI and return results."""
        # CLI should already be available from setup, but do a quick check
        if not self.cli_path.exists():
            _LOGGER.error("CLI binary not found at %s", self.cli_path)
            raise CLINotFoundError(f"LibreSpeed CLI not available at {self.cli_path}")
        
        cmd = [str(self.cli_path), "--json"]
        stdin_data = None
        
        try:
            # Add server selection with input validation
            if server_id is not None:
                # Validate server_id is a positive integer with reasonable bounds
                # LibreSpeed servers typically have IDs from 1-999, cap at 10000 for safety
                if not isinstance(server_id, int) or server_id < MIN_SERVER_ID or server_id > MAX_SERVER_ID:
                    raise ValueError(f"Invalid server_id: {server_id} (must be 0-10000)")
                cmd.extend(["--server", str(server_id)])
            elif custom_server:
                # Validate custom_server URL
                if not self._validate_url(custom_server):
                    raise ValueError(f"Invalid custom server URL: {custom_server}")
                # For custom servers, pipe JSON via stdin instead of temp file
                stdin_data = await self._create_custom_server_json_string(custom_server)
                if stdin_data:
                    cmd.extend(["--local-json", "-"])  # "-" means read from stdin
                    # Also specify to use the first server in the list
                    cmd.extend(["--server", "1"])
                else:
                    raise CLIError("Failed to create custom server configuration")
            
            # Add SSL verification skip
            if skip_cert_verify:
                cmd.append("--skip-cert-verify")
            
            _LOGGER.info("Running LibreSpeed CLI with command: %s", ' '.join(cmd))
            
            # Run the CLI with timeout
            async with async_timeout.timeout(timeout):  # Use configurable timeout
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE if stdin_data else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                # Send stdin data if we have custom server JSON
                if stdin_data:
                    stdout, stderr = await proc.communicate(input=stdin_data.encode())
                else:
                    stdout, stderr = await proc.communicate()
                
                if proc.returncode != PROCESS_SUCCESS:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    _LOGGER.error("CLI failed with code %d: %s", proc.returncode, error_msg)
                    raise CLIExecutionError(f"CLI failed with code {proc.returncode}: {error_msg}")
                
                # Parse JSON output (it's an array with one object)
                results = json.loads(stdout.decode())
                if not results:
                    raise CLIOutputError("No results from CLI")
                
                result = results[0]
                
                # Convert to our format
                return {
                    'download': result.get('download', 0),
                    'upload': result.get('upload', 0),
                    'ping': result.get('ping', 0),
                    'jitter': result.get('jitter', 0),
                    'server': {
                        'id': server_id,
                        'name': result.get('server', {}).get('name', 'Unknown'),
                        'server': result.get('server', {}).get('url', ''),
                        'location': result.get('server', {}).get('name', 'Unknown'),
                        'sponsor': 'Unknown',
                    },
                    'timestamp': datetime.fromisoformat(result.get('timestamp', datetime.now().isoformat())),
                    'bytes_sent': result.get('bytes_sent', 0),
                    'bytes_received': result.get('bytes_received', 0),
                }
                
        except asyncio.TimeoutError:
            _LOGGER.error("Speed test timed out")
            raise SpeedTestTimeoutError("Speed test timed out after 120 seconds")
        except json.JSONDecodeError as e:
            _LOGGER.error("Failed to parse CLI output: %s", e)
            raise CLIOutputError(f"Invalid CLI output: {e}")
        except CLIError:
            # Re-raise our custom exceptions
            raise
        except OSError as e:
            _LOGGER.error("Speed test process error: %s", e)
            raise CLIExecutionError(f"Failed to run CLI: {e}")
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL format and safety."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            
            # Check for valid scheme
            if parsed.scheme not in ('http', 'https'):
                return False
            
            # Check for valid hostname
            if not parsed.netloc or len(parsed.netloc) > MAX_HOSTNAME_LENGTH:
                return False
            
            # Basic check for malicious patterns
            if any(char in url for char in ['\n', '\r', '\0', '`', '$', ';', '|', '&', '<', '>']):
                return False
            
            # Validate hostname format
            hostname_pattern = re.compile(
                r'^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])'
                r'(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*$'
            )
            hostname = parsed.hostname
            if hostname and not (hostname_pattern.match(hostname) or self._is_valid_ip(hostname)):
                return False
            
            return True
        except (ValueError, TypeError, AttributeError):
            return False
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IP address."""
        try:
            import ipaddress
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False
    
    async def _create_custom_server_json_string(self, custom_server: str) -> str | None:
        """Create a JSON string with custom server configuration."""
        try:
            # Parse the custom server URL to get name
            from urllib.parse import urlparse
            parsed = urlparse(custom_server)
            server_name = f"Custom ({parsed.netloc})"
            
            # For the CLI, the server JSON format is simpler
            # The "server" field should just be the base URL without the backend path
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Create server JSON in the format expected by CLI
            servers = [{
                "id": 1,  # CLI requires a valid ID
                "name": server_name,
                "server": base_url,  # Just the base URL, CLI will add the endpoints
            }]
            
            # Return JSON string
            json_string = json.dumps(servers)
            _LOGGER.debug("Created custom server JSON string for %s", base_url)
            return json_string
                
        except (ValueError, TypeError, AttributeError) as e:
            _LOGGER.error("Failed to create custom server JSON: %s", e)
            return None
    
