"""Constants for the LibreSpeed integration."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "librespeed"
LOGGER_NAME: Final = "custom_components.librespeed"

DEFAULT_UPDATE_INTERVAL = 60

CONF_SERVER_ID = "server_id"
CONF_CUSTOM_SERVER = "custom_server"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_AUTO_UPDATE = "auto_update"
CONF_SKIP_CERT_VERIFY = "skip_cert_verify"
CONF_BACKEND_TYPE = "backend_type"
CONF_TEST_TIMEOUT = "test_timeout"

MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 1440
DEFAULT_TEST_TIMEOUT = 240  # 4 minutes
MIN_TEST_TIMEOUT = 60  # 1 minute
MAX_TEST_TIMEOUT = 600  # 10 minutes

ATTR_DOWNLOAD = "download"
ATTR_UPLOAD = "upload"
ATTR_PING = "ping"
ATTR_JITTER = "jitter"
ATTR_SERVER_NAME = "server_name"
ATTR_SERVER_LOCATION = "server_location"
ATTR_SERVER_SPONSOR = "server_sponsor"
ATTR_TIMESTAMP = "timestamp"
ATTR_BYTES_SENT = "bytes_sent"
ATTR_BYTES_RECEIVED = "bytes_received"
ATTR_LIFETIME_DOWNLOAD = "lifetime_download"
ATTR_LIFETIME_UPLOAD = "lifetime_upload"

# Speed test execution constants
SPEED_TEST_DURATION = 15  # Duration for download/upload tests in seconds (LibreSpeed default)
DEFAULT_CHUNKS = 100  # Default number of chunks for speed tests
PING_COUNT = 10  # Number of ping measurements to take
PING_INTERVAL = 0.1  # Delay between ping measurements in seconds
MAX_CONCURRENT_DOWNLOADS = 6  # Maximum concurrent download streams
MAX_CONCURRENT_UPLOADS = 3  # Maximum concurrent upload streams

# Circuit breaker thresholds
CIRCUIT_BREAKER_WARNING_THRESHOLD = 5  # Show warning repair issue after this many failures
CIRCUIT_BREAKER_OPEN_THRESHOLD = 10  # Circuit breaker opens after this many consecutive failures

# Network timeouts
SERVER_LIST_TIMEOUT = 10  # Timeout for fetching server list in seconds
PING_TIMEOUT = 2  # Timeout for individual ping tests in seconds
CHUNK_UPLOAD_TIMEOUT = 30  # Timeout for upload/download chunks in seconds
GLOBAL_TEST_LOCK_TIMEOUT = 300  # Timeout waiting for other speed test (5 minutes)

# CLI download timeouts
CLI_DOWNLOAD_TIMEOUT_TOTAL = 300  # 5 minutes total timeout for CLI download
CLI_DOWNLOAD_TIMEOUT_CONNECT = 30  # 30 seconds to establish connection
CLI_DOWNLOAD_TIMEOUT_READ = 60  # 60 seconds for socket reads

# Network connection pool settings
CONNECTION_POOL_LIMIT = 20  # Total number of connections in the pool
CONNECTION_POOL_LIMIT_PER_HOST = 15  # Max connections per host
DNS_CACHE_TTL = 300  # DNS cache time-to-live in seconds (5 minutes)
KEEPALIVE_TIMEOUT = 30  # TCP keepalive timeout in seconds
READ_BUFFER_SIZE = 262144  # Read buffer size in bytes (256KB for high-speed connections)

# HTTP session timeouts
SESSION_TIMEOUT_TOTAL = 300  # 5 minute total timeout for session
SESSION_TIMEOUT_CONNECT = 10  # 10 second connection timeout for session
SESSION_TIMEOUT_READ = 60  # 60 second read timeout for session

# Startup delays
NETWORK_STABILIZATION_DELAY = 2  # Seconds to wait for network to stabilize on startup
FIRST_TEST_DELAY = 60  # Seconds to wait before first automatic speed test

# Retry configuration
CLI_DOWNLOAD_MAX_RETRIES = 3  # Maximum retries for CLI binary download
CLI_DOWNLOAD_RETRY_DELAY = 5  # Base delay between CLI download retries in seconds
MAX_RETRIES = 3  # Maximum number of retry attempts for failed tests
RETRY_DELAY_BASE = 5  # Base delay in seconds for exponential backoff (5, 10, 20...)

# Data size thresholds
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB upload chunks
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB download chunks for streaming
RUST_BACKEND_THRESHOLD = 5_000_000  # 5MB response indicates Rust backend

# Server validation
MIN_SERVER_ID = 0
MAX_SERVER_ID = 10000

# Custom server error cooldown
CUSTOM_SERVER_ERROR_COOLDOWN = 21600  # 6 hours in seconds

# HTTP status codes
HTTP_OK = 200  # Success status code

# Process return codes  
PROCESS_SUCCESS = 0  # Successful process execution

# Timing delays
STREAM_START_DELAY = 0.2  # Delay between starting concurrent streams (200ms)

# Progress logging intervals
DOWNLOAD_LOG_INTERVAL_INITIAL = 5  # Log every 5 downloads initially
DOWNLOAD_LOG_INTERVAL_FREQUENT = 2  # Log every 2 downloads after 5 seconds
UPLOAD_LOG_INTERVAL = 50  # Log every 50 uploads

# Default timeout for speed tests
DEFAULT_SPEED_TEST_TIMEOUT = 120  # 2 minutes

# Data limits
MAX_LIFETIME_GB = 1_000_000  # Maximum lifetime data in GB (1 petabyte)

# Network validation
MAX_HOSTNAME_LENGTH = 253  # Maximum length for a hostname

# Chunk parameters
DOWNLOAD_CHUNK_PARAM = 20  # Request 20 chunks at a time (~10MB)
PHP_BACKEND_THRESHOLD = 2  # After 2 requests, assume PHP backend

# Timing thresholds
ELAPSED_TIME_THRESHOLD = 5  # Seconds before increasing log frequency