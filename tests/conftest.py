"""Shared pytest fixtures for BT bridge daemon tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Configuration
from src.models.kiss import KISSCommand, KISSFrame, KISSParser
from src.models.state import ConnectionState

# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def valid_config() -> Configuration:
    """Provide a valid configuration for testing."""
    return Configuration(
        target_address="00:11:22:33:44:55",
        target_pin="1234",
        device_name="TestBridge",
        log_level="DEBUG",
        buffer_size=4096,
        reconnect_max_delay=30,
        status_socket="/tmp/test-bt-bridge.sock",
    )


@pytest.fixture
def config_dict() -> dict[str, object]:
    """Provide a valid configuration dictionary."""
    return {
        "target_address": "00:11:22:33:44:55",
        "target_pin": "1234",
        "device_name": "TestBridge",
        "log_level": "DEBUG",
        "buffer_size": 4096,
        "reconnect_max_delay": 30,
        "status_socket": "/tmp/test-bt-bridge.sock",
    }


# =============================================================================
# KISS Frame Fixtures
# =============================================================================


@pytest.fixture
def sample_kiss_frame() -> KISSFrame:
    """Provide a sample KISS data frame."""
    return KISSFrame(
        port=0,
        command=KISSCommand.DATA_FRAME,
        data=b"HELLO",
    )


@pytest.fixture
def sample_kiss_bytes() -> bytes:
    """Provide sample KISS frame as wire bytes."""
    # FEND + DATA_FRAME(0x00) + "HELLO" + FEND
    return bytes([0xC0, 0x00, 0x48, 0x45, 0x4C, 0x4C, 0x4F, 0xC0])


@pytest.fixture
def kiss_frame_with_escapes() -> bytes:
    """Provide KISS frame with escaped characters."""
    # FEND + DATA_FRAME + "A" + escaped_FEND + "B" + FEND
    # Data should be: A + 0xC0 + B
    return bytes([0xC0, 0x00, 0x41, 0xDB, 0xDC, 0x42, 0xC0])


@pytest.fixture
def multiple_kiss_frames() -> bytes:
    """Provide multiple back-to-back KISS frames."""
    # Two frames: "A" and "B"
    return bytes([0xC0, 0x00, 0x41, 0xC0, 0xC0, 0x00, 0x42, 0xC0])


@pytest.fixture
def kiss_parser() -> KISSParser:
    """Provide a fresh KISS parser instance."""
    return KISSParser()


# =============================================================================
# Mock BLE Adapter Fixtures
# =============================================================================


@pytest.fixture
def mock_ble_adapter() -> Generator[MagicMock, None, None]:
    """Provide a mock BLE adapter for testing."""
    with patch("bless.BlessServer") as mock:
        adapter = MagicMock()
        adapter.is_advertising = False
        adapter.is_connected = False
        adapter.mtu = 23

        # Mock async methods
        adapter.start = AsyncMock()
        adapter.stop = AsyncMock()
        adapter.add_new_service = AsyncMock()
        adapter.add_new_characteristic = AsyncMock()

        mock.return_value = adapter
        yield adapter


@pytest.fixture
def mock_ble_connection() -> MagicMock:
    """Provide a mock BLE connection state."""
    conn = MagicMock()
    conn.state = ConnectionState.IDLE
    conn.device_address = None
    conn.device_name = None
    conn.mtu = 23
    conn.connected_at = None
    conn.rx_queue = asyncio.Queue()
    conn.tx_queue = asyncio.Queue()
    conn.bytes_rx = 0
    conn.bytes_tx = 0
    return conn


# =============================================================================
# Mock SPP/Classic Fixtures
# =============================================================================


@pytest.fixture
def mock_dbus_connection() -> Generator[MagicMock, None, None]:
    """Provide a mock D-Bus connection for SPP testing."""
    with patch("dbus.SystemBus") as mock_bus:
        bus = MagicMock()
        mock_bus.return_value = bus
        yield bus


@pytest.fixture
def mock_spp_socket() -> MagicMock:
    """Provide a mock SPP socket/file descriptor."""
    sock = MagicMock()
    sock.fileno.return_value = 42
    sock.read = AsyncMock(return_value=b"")
    sock.write = AsyncMock()
    sock.close = MagicMock()
    return sock


@pytest.fixture
def mock_classic_connection() -> MagicMock:
    """Provide a mock Classic connection state."""
    conn = MagicMock()
    conn.state = ConnectionState.IDLE
    conn.target_address = "00:11:22:33:44:55"
    conn.device_name = None
    conn.rfcomm_channel = None
    conn.connected_at = None
    conn.rx_queue = asyncio.Queue()
    conn.tx_queue = asyncio.Queue()
    conn.bytes_rx = 0
    conn.bytes_tx = 0
    conn.reconnect_attempts = 0
    conn.last_error = None
    return conn


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
async def event_loop() -> AsyncGenerator[asyncio.AbstractEventLoop, None]:
    """Provide an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_bridge_state(
    mock_ble_connection: MagicMock,
    mock_classic_connection: MagicMock,
    kiss_parser: KISSParser,
) -> MagicMock:
    """Provide a mock bridge state for testing."""
    state = MagicMock()
    state.ble = mock_ble_connection
    state.classic = mock_classic_connection
    state.ble_parser = kiss_parser
    state.classic_parser = KISSParser()
    state.started_at = datetime.now(UTC)
    state.frames_bridged = 0
    state.errors = []
    state.is_fully_connected = False
    state.is_partially_connected = False
    return state


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def temp_config_file(tmp_path: pytest.TempPathFactory) -> Generator[str, None, None]:
    """Provide a temporary configuration file path."""
    config_file = tmp_path / "config.json"  # type: ignore[operator]
    yield str(config_file)


@pytest.fixture
def unix_socket_path(tmp_path: pytest.TempPathFactory) -> str:
    """Provide a temporary Unix socket path."""
    return str(tmp_path / "test.sock")  # type: ignore[operator]
