# Data Model: Web Pairing Interface

**Feature**: 002-web-pairing-interface  
**Date**: 2026-03-05

## Overview

This document defines the data models for the web interface feature. These models represent the state exposed via the web API and used by templates.

## Models

### 1. ConnectionState (Enum)

Represents the state of a Bluetooth connection.

```python
class ConnectionState(str, Enum):
    """State of a Bluetooth connection."""
    IDLE = "idle"              # Not attempting connection
    SCANNING = "scanning"      # Scanning for devices (BLE advertising / Classic discovery)
    CONNECTING = "connecting"  # Connection in progress
    CONNECTED = "connected"    # Active connection
    DISCONNECTED = "disconnected"  # Was connected, now disconnected
    ERROR = "error"            # Connection failed
```

### 2. BLEStatus

Status of the BLE (phone) side of the bridge.

```python
@dataclass
class BLEStatus:
    """BLE connection status."""
    state: ConnectionState
    device_name: str | None = None      # Connected device name (if known)
    device_address: str | None = None   # Connected device MAC
    connected_at: datetime | None = None
    advertising: bool = False           # Currently advertising
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "device_name": self.device_name,
            "device_address": self.device_address,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "advertising": self.advertising,
        }
```

### 3. ClassicStatus

Status of the Bluetooth Classic (TNC) side of the bridge.

```python
@dataclass
class ClassicStatus:
    """Bluetooth Classic connection status."""
    state: ConnectionState
    target_address: str                 # Configured target MAC
    target_name: str | None = None      # Resolved device name
    connected_at: datetime | None = None
    rfcomm_channel: int = 2
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "target_address": self.target_address,
            "target_name": self.target_name,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "rfcomm_channel": self.rfcomm_channel,
        }
```

### 4. BridgeStatus

Combined status of the entire bridge.

```python
@dataclass
class BridgeStatus:
    """Overall bridge status."""
    ble: BLEStatus
    classic: ClassicStatus
    uptime_seconds: float
    started_at: datetime
    version: str = "1.0.0"
    
    def to_dict(self) -> dict:
        return {
            "ble": self.ble.to_dict(),
            "classic": self.classic.to_dict(),
            "uptime_seconds": self.uptime_seconds,
            "started_at": self.started_at.isoformat(),
            "version": self.version,
        }
```

### 5. PacketStatistics

Packet and byte counters for monitoring.

```python
@dataclass
class PacketStatistics:
    """Bridge traffic statistics."""
    packets_tx: int = 0         # Packets sent to TNC
    packets_rx: int = 0         # Packets received from TNC
    bytes_tx: int = 0           # Bytes sent to TNC
    bytes_rx: int = 0           # Bytes received from TNC
    errors: int = 0             # Error count
    last_tx_at: datetime | None = None
    last_rx_at: datetime | None = None
    
    def to_dict(self) -> dict:
        return {
            "packets_tx": self.packets_tx,
            "packets_rx": self.packets_rx,
            "bytes_tx": self.bytes_tx,
            "bytes_rx": self.bytes_rx,
            "errors": self.errors,
            "last_tx_at": self.last_tx_at.isoformat() if self.last_tx_at else None,
            "last_rx_at": self.last_rx_at.isoformat() if self.last_rx_at else None,
        }
```

### 6. DiscoveredDevice

A Bluetooth device found during scanning.

```python
@dataclass
class DiscoveredDevice:
    """Discovered Bluetooth device."""
    address: str                # MAC address
    name: str | None            # Device name (may be None)
    rssi: int | None            # Signal strength (dBm)
    device_class: int | None    # Bluetooth device class
    paired: bool = False        # Already paired
    trusted: bool = False       # Marked as trusted
    has_spp: bool = False       # Has Serial Port Profile
    
    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "name": self.name or "Unknown",
            "rssi": self.rssi,
            "device_class": self.device_class,
            "paired": self.paired,
            "trusted": self.trusted,
            "has_spp": self.has_spp,
        }
```

### 7. PairingState (Enum)

State of an active pairing session.

```python
class PairingState(str, Enum):
    """State of pairing process."""
    IDLE = "idle"
    SCANNING = "scanning"
    SCAN_COMPLETE = "scan_complete"
    PAIRING = "pairing"
    PIN_REQUIRED = "pin_required"
    SUCCESS = "success"
    FAILED = "failed"
```

### 8. PairingSession

Active pairing session state.

```python
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
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "target_address": self.target_address,
            "target_name": self.target_name,
            "pin_required": self.pin_required,
            "error_message": self.error_message,
            "discovered_devices": [d.to_dict() for d in self.discovered_devices],
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }
```

### 9. WebConfiguration

Web-editable configuration subset.

```python
@dataclass
class WebConfiguration:
    """User-editable configuration via web UI."""
    device_name: str = "PiBTBridge"
    target_address: str = ""
    rfcomm_channel: int = 2
    log_level: str = "INFO"
    web_port: int = 8080
    
    def to_dict(self) -> dict:
        return {
            "device_name": self.device_name,
            "target_address": self.target_address,
            "rfcomm_channel": self.rfcomm_channel,
            "log_level": self.log_level,
            "web_port": self.web_port,
        }
    
    @classmethod
    def from_config(cls, config: Configuration) -> "WebConfiguration":
        """Extract web-editable fields from full config."""
        return cls(
            device_name=config.device_name,
            target_address=config.target_address,
            rfcomm_channel=config.rfcomm_channel,
            log_level=config.log_level,
            web_port=getattr(config, 'web_port', 8080),
        )
```

## Model Relationships

```
BridgeStatus
├── BLEStatus (1:1)
└── ClassicStatus (1:1)

PairingSession
└── DiscoveredDevice (1:N)

WebConfiguration <-> Configuration (subset mapping)
```

## Storage

- **BridgeStatus**: In-memory only, derived from runtime state
- **PacketStatistics**: In-memory counters, reset on restart
- **PairingSession**: In-memory, single active session
- **WebConfiguration**: Persisted to `/etc/bt-bridge/config.json`

## Validation Rules

| Field | Rule |
|-------|------|
| `target_address` | Must match MAC pattern `XX:XX:XX:XX:XX:XX` |
| `rfcomm_channel` | Must be 1-30 |
| `log_level` | Must be DEBUG, INFO, WARNING, or ERROR |
| `web_port` | Must be 1024-65535 |
| `device_name` | Must be 1-20 characters, alphanumeric + hyphen |
