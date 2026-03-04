"""State management models for the BT bridge daemon."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.connection import BLEConnection, ClassicConnection
    from src.models.kiss import KISSParser


class ConnectionState(Enum):
    """
    Represents the state of a Bluetooth connection.

    State transitions:
        IDLE -> SCANNING -> CONNECTING -> CONNECTED
        CONNECTED -> DISCONNECTING -> IDLE
        Any state -> ERROR -> IDLE or SCANNING (retry)
    """

    IDLE = "idle"
    """Not connected, not attempting to connect."""

    SCANNING = "scanning"
    """BLE: Advertising / Classic: Discovering target device."""

    CONNECTING = "connecting"
    """Connection attempt in progress."""

    CONNECTED = "connected"
    """Active connection established."""

    DISCONNECTING = "disconnecting"
    """Graceful disconnect in progress."""

    ERROR = "error"
    """Connection failed, requires intervention or retry."""


@dataclass
class ErrorEvent:
    """
    Structured error event for logging and status reporting.

    Attributes:
        timestamp: When the error occurred (UTC).
        source: Component that raised the error (ble, classic, bridge, config).
        error_type: Classification of the error.
        message: Human-readable description.
        remediation: Suggested fix, if available.
    """

    timestamp: datetime
    source: str
    error_type: str
    message: str
    remediation: str | None = None

    @classmethod
    def create(
        cls,
        source: str,
        error_type: str,
        message: str,
        remediation: str | None = None,
    ) -> ErrorEvent:
        """Create an ErrorEvent with current timestamp."""
        return cls(
            timestamp=datetime.now(UTC),
            source=source,
            error_type=error_type,
            message=message,
            remediation=remediation,
        )

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "error_type": self.error_type,
            "message": self.message,
            "remediation": self.remediation,
        }


@dataclass
class BridgeState:
    """
    Top-level state container for the daemon.

    Attributes:
        ble: BLE connection state.
        classic: Classic connection state.
        ble_parser: KISS parser for BLE -> Classic direction.
        classic_parser: KISS parser for Classic -> BLE direction.
        started_at: Daemon start time (UTC).
        frames_bridged: Total frames transferred in both directions.
        errors: Recent error events (capped at 100).
    """

    ble: BLEConnection
    classic: ClassicConnection
    ble_parser: KISSParser
    classic_parser: KISSParser
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    frames_bridged: int = 0
    errors: list[ErrorEvent] = field(default_factory=list)

    MAX_ERRORS: int = field(default=100, repr=False)

    @property
    def is_fully_connected(self) -> bool:
        """Check if both connections are in CONNECTED state."""
        return (
            self.ble.state == ConnectionState.CONNECTED
            and self.classic.state == ConnectionState.CONNECTED
        )

    @property
    def is_partially_connected(self) -> bool:
        """Check if exactly one connection is in CONNECTED state."""
        ble_connected = self.ble.state == ConnectionState.CONNECTED
        classic_connected = self.classic.state == ConnectionState.CONNECTED
        return ble_connected != classic_connected

    @property
    def uptime(self) -> float:
        """Get daemon uptime in seconds."""
        return (datetime.now(UTC) - self.started_at).total_seconds()

    def add_error(self, error: ErrorEvent) -> None:
        """Add an error event, maintaining max size limit."""
        self.errors.append(error)
        if len(self.errors) > self.MAX_ERRORS:
            self.errors = self.errors[-self.MAX_ERRORS :]

    def to_status_dict(self) -> dict[str, object]:
        """Convert to status dictionary for JSON serialization."""
        return {
            "ble_state": self.ble.state.value,
            "classic_state": self.classic.state.value,
            "bytes_transferred": {
                "ble_rx": self.ble.bytes_rx,
                "ble_tx": self.ble.bytes_tx,
                "classic_rx": self.classic.bytes_rx,
                "classic_tx": self.classic.bytes_tx,
            },
            "frames_bridged": self.frames_bridged,
            "uptime_seconds": self.uptime,
            "error_count": len(self.errors),
            "is_fully_connected": self.is_fully_connected,
        }
