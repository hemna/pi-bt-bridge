"""Bluetooth connection models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from src.models.state import ConnectionState

# Default values
DEFAULT_MTU: Final[int] = 23  # BLE 4.x default ATT_MTU
MAX_MTU: Final[int] = 512  # BLE 5.x maximum
DEFAULT_BUFFER_SIZE: Final[int] = 4096  # 4KB buffer


@dataclass
class BLEConnection:
    """
    Represents the Bluetooth LE connection to an iPhone.

    Attributes:
        state: Current connection state.
        device_address: Connected device BT address (MAC format).
        device_name: Device friendly name (optional).
        mtu: Negotiated MTU size (23-512).
        connected_at: Connection timestamp (UTC).
        rx_queue: Incoming data from iPhone.
        tx_queue: Outgoing data to iPhone.
        bytes_rx: Total bytes received.
        bytes_tx: Total bytes transmitted.
    """

    state: ConnectionState = ConnectionState.IDLE
    device_address: str | None = None
    device_name: str | None = None
    mtu: int = DEFAULT_MTU
    connected_at: datetime | None = None
    rx_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    tx_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    bytes_rx: int = 0
    bytes_tx: int = 0

    def __post_init__(self) -> None:
        """Validate connection fields."""
        if not DEFAULT_MTU <= self.mtu <= MAX_MTU:
            raise ValueError(f"MTU must be {DEFAULT_MTU}-{MAX_MTU}, got {self.mtu}")

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self.state == ConnectionState.CONNECTED

    @property
    def payload_size(self) -> int:
        """Get maximum payload size (MTU - 3 for ATT header)."""
        return self.mtu - 3

    def set_connected(self, device_address: str, device_name: str | None = None) -> None:
        """
        Mark connection as established.

        Args:
            device_address: Connected device MAC address.
            device_name: Device friendly name (optional).
        """
        self.state = ConnectionState.CONNECTED
        self.device_address = device_address
        self.device_name = device_name
        self.connected_at = datetime.now(UTC)

    def set_disconnected(self) -> None:
        """Mark connection as disconnected and reset state."""
        self.state = ConnectionState.IDLE
        self.device_address = None
        self.device_name = None
        self.mtu = DEFAULT_MTU
        self.connected_at = None

    def update_mtu(self, new_mtu: int) -> None:
        """
        Update MTU after negotiation.

        Args:
            new_mtu: Negotiated MTU value.
        """
        if not DEFAULT_MTU <= new_mtu <= MAX_MTU:
            raise ValueError(f"MTU must be {DEFAULT_MTU}-{MAX_MTU}, got {new_mtu}")
        self.mtu = new_mtu

    def record_rx(self, size: int) -> None:
        """Record received bytes."""
        self.bytes_rx += size

    def record_tx(self, size: int) -> None:
        """Record transmitted bytes."""
        self.bytes_tx += size


@dataclass
class ClassicConnection:
    """
    Represents the Bluetooth Classic connection to a TNC radio.

    Attributes:
        state: Current connection state.
        target_address: Target device BT address (from config).
        device_name: Device friendly name (discovered).
        rfcomm_channel: SPP channel number (1-30).
        connected_at: Connection timestamp (UTC).
        rx_queue: Incoming data from TNC.
        tx_queue: Outgoing data to TNC.
        bytes_rx: Total bytes received.
        bytes_tx: Total bytes transmitted.
        reconnect_attempts: Failed reconnect count.
        last_error: Last error message for diagnostics.
    """

    target_address: str
    state: ConnectionState = ConnectionState.IDLE
    device_name: str | None = None
    rfcomm_channel: int | None = None
    connected_at: datetime | None = None
    rx_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    tx_queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    bytes_rx: int = 0
    bytes_tx: int = 0
    reconnect_attempts: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        """Validate connection fields."""
        if self.rfcomm_channel is not None and not 1 <= self.rfcomm_channel <= 30:
            raise ValueError(f"RFCOMM channel must be 1-30, got {self.rfcomm_channel}")

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self.state == ConnectionState.CONNECTED

    def set_connected(
        self,
        rfcomm_channel: int,
        device_name: str | None = None,
    ) -> None:
        """
        Mark connection as established.

        Args:
            rfcomm_channel: SPP channel number.
            device_name: Device friendly name (optional).
        """
        if not 1 <= rfcomm_channel <= 30:
            raise ValueError(f"RFCOMM channel must be 1-30, got {rfcomm_channel}")

        self.state = ConnectionState.CONNECTED
        self.rfcomm_channel = rfcomm_channel
        self.device_name = device_name
        self.connected_at = datetime.now(UTC)
        self.reconnect_attempts = 0  # Reset on success

    def set_disconnected(self, error: str | None = None) -> None:
        """
        Mark connection as disconnected.

        Args:
            error: Error message if disconnect was unexpected.
        """
        self.state = ConnectionState.IDLE
        self.rfcomm_channel = None
        self.connected_at = None
        if error:
            self.last_error = error

    def record_reconnect_attempt(self) -> None:
        """Increment reconnect attempt counter."""
        self.reconnect_attempts += 1

    def get_backoff_delay(self, max_delay: int = 30) -> float:
        """
        Calculate exponential backoff delay for reconnection.

        Args:
            max_delay: Maximum delay in seconds.

        Returns:
            Delay in seconds before next reconnection attempt.
        """
        delay = min(2**self.reconnect_attempts, max_delay)
        return float(delay)

    def record_rx(self, size: int) -> None:
        """Record received bytes."""
        self.bytes_rx += size

    def record_tx(self, size: int) -> None:
        """Record transmitted bytes."""
        self.bytes_tx += size
