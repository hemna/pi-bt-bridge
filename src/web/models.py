"""Data models for the web interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ConnectionState(StrEnum):
    """State of a Bluetooth connection."""

    IDLE = "idle"  # Not attempting connection
    SCANNING = "scanning"  # Scanning for devices (BLE advertising / Classic discovery)
    CONNECTING = "connecting"  # Connection in progress
    CONNECTED = "connected"  # Active connection
    DISCONNECTED = "disconnected"  # Was connected, now disconnected
    ERROR = "error"  # Connection failed


class PairingState(StrEnum):
    """State of pairing process."""

    IDLE = "idle"
    SCANNING = "scanning"
    SCAN_COMPLETE = "scan_complete"
    PAIRING = "pairing"
    PIN_REQUIRED = "pin_required"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class BLEStatus:
    """BLE connection status."""

    state: ConnectionState = ConnectionState.IDLE
    device_name: str | None = None  # Connected device name (if known)
    device_address: str | None = None  # Connected device MAC
    connected_at: datetime | None = None
    advertising: bool = False  # Currently advertising

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "device_name": self.device_name,
            "device_address": self.device_address,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "advertising": self.advertising,
        }


@dataclass
class ClassicStatus:
    """Bluetooth Classic connection status."""

    state: ConnectionState = ConnectionState.IDLE
    target_address: str = ""  # Configured target MAC
    target_name: str | None = None  # Resolved device name
    connected_at: datetime | None = None
    rfcomm_channel: int = 2

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "target_address": self.target_address,
            "target_name": self.target_name,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "rfcomm_channel": self.rfcomm_channel,
        }


@dataclass
class BridgeStatus:
    """Overall bridge status."""

    ble: BLEStatus
    classic: ClassicStatus
    started_at: datetime
    version: str = "1.0.0"

    @property
    def uptime_seconds(self) -> float:
        """Calculate uptime in seconds."""
        return (datetime.now() - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ble": self.ble.to_dict(),
            "classic": self.classic.to_dict(),
            "uptime_seconds": self.uptime_seconds,
            "started_at": self.started_at.isoformat(),
            "version": self.version,
        }


@dataclass
class PacketStatistics:
    """Bridge traffic statistics."""

    packets_tx: int = 0  # Packets sent to TNC
    packets_rx: int = 0  # Packets received from TNC
    bytes_tx: int = 0  # Bytes sent to TNC
    bytes_rx: int = 0  # Bytes received from TNC
    errors: int = 0  # Error count
    last_tx_at: datetime | None = None
    last_rx_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "packets_tx": self.packets_tx,
            "packets_rx": self.packets_rx,
            "bytes_tx": self.bytes_tx,
            "bytes_rx": self.bytes_rx,
            "errors": self.errors,
            "last_tx_at": self.last_tx_at.isoformat() if self.last_tx_at else None,
            "last_rx_at": self.last_rx_at.isoformat() if self.last_rx_at else None,
        }

    def record_tx(self, byte_count: int) -> None:
        """Record a transmitted packet."""
        self.packets_tx += 1
        self.bytes_tx += byte_count
        self.last_tx_at = datetime.now()

    def record_rx(self, byte_count: int) -> None:
        """Record a received packet."""
        self.packets_rx += 1
        self.bytes_rx += byte_count
        self.last_rx_at = datetime.now()

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1


@dataclass
class DiscoveredDevice:
    """Discovered Bluetooth device."""

    address: str  # MAC address
    name: str | None = None  # Device name (may be None)
    rssi: int | None = None  # Signal strength (dBm)
    device_class: int | None = None  # Bluetooth device class
    paired: bool = False  # Already paired
    trusted: bool = False  # Marked as trusted
    has_spp: bool = False  # Has Serial Port Profile

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "address": self.address,
            "name": self.name or "Unknown",
            "rssi": self.rssi,
            "device_class": self.device_class,
            "paired": self.paired,
            "trusted": self.trusted,
            "has_spp": self.has_spp,
        }


@dataclass
class PairingSession:
    """Active pairing session."""

    state: PairingState = PairingState.IDLE
    target_address: str | None = None
    target_name: str | None = None
    pin_required: bool = False
    error_message: str | None = None
    discovered_devices: list[DiscoveredDevice] = field(default_factory=list)
    started_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "state": self.state.value,
            "target_address": self.target_address,
            "target_name": self.target_name,
            "pin_required": self.pin_required,
            "error_message": self.error_message,
            "discovered_devices": [d.to_dict() for d in self.discovered_devices],
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }

    def reset(self) -> None:
        """Reset the pairing session to idle state."""
        self.state = PairingState.IDLE
        self.target_address = None
        self.target_name = None
        self.pin_required = False
        self.error_message = None
        self.discovered_devices = []
        self.started_at = None
