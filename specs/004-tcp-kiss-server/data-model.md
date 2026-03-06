# Data Model: TCP KISS Server

**Feature**: 004-tcp-kiss-server  
**Date**: 2026-03-06

## New Entities

### TcpKissConnection

Represents a single connected TCP KISS client. Follows the same pattern as `BLEConnection` and `ClassicConnection`.

**Location**: `src/models/connection.py`

```python
@dataclass
class TcpKissConnection:
    """State for a single TCP KISS client connection."""
    remote_address: str = ""         # IP:port of the connected client
    connected_at: datetime | None = None  # When the client connected (UTC)
    bytes_rx: int = 0                # Bytes received from this client
    bytes_tx: int = 0                # Bytes sent to this client
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `remote_address` | `str` | `""` | Remote IP:port (e.g., "192.168.1.100:54321") |
| `connected_at` | `datetime \| None` | `None` | UTC timestamp of connection establishment |
| `bytes_rx` | `int` | `0` | Total bytes received from this client |
| `bytes_tx` | `int` | `0` | Total bytes sent to this client |

**Relationships**: Managed as a list within `BridgeState.tcp_clients`.

---

## Modified Entities

### BridgeState (modification)

**Location**: `src/models/state.py`

**Added fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tcp_clients` | `list[TcpKissConnection]` | `field(default_factory=list)` | Currently connected TCP KISS clients |

**Modified methods**:

- `to_status_dict()` → Add `tcp_clients` section with client count and per-client details

---

### Configuration (modification)

**Location**: `src/config.py`

**Added fields**:

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `tcp_kiss_enabled` | `bool` | `True` | N/A | Enable TCP KISS server |
| `tcp_kiss_port` | `int` | `8001` | 1024-65535 | TCP listen port |
| `tcp_kiss_host` | `str` | `"0.0.0.0"` | Valid IP | TCP bind address |
| `tcp_kiss_max_clients` | `int` | `5` | 1-20 | Maximum simultaneous TCP clients |

---

### Web Models (modification)

**Location**: `src/web/models.py`

**New class**:

```python
@dataclass
class TcpKissClientStatus:
    """Status of a single TCP KISS client for web display."""
    remote_address: str
    connected_at: str | None  # ISO format string
    bytes_rx: int
    bytes_tx: int

@dataclass
class TcpKissStatus:
    """TCP KISS server status for web display."""
    enabled: bool
    listening: bool
    port: int
    client_count: int
    max_clients: int
    clients: list[TcpKissClientStatus]
```

**Modified class**:

- `BridgeStatus` → Add `tcp_kiss: TcpKissStatus` field

---

## State Transitions

### TCP Client Lifecycle

```
NEW CONNECTION
    │
    ▼
[max_clients check] ──exceeded──▶ REJECT (close socket, log warning)
    │
    │ accepted
    ▼
CONNECTED
    │
    ├── receives data ──▶ KISSParser.feed() ──▶ complete frames ──▶ bridge._forward_to_classic()
    │
    ├── bridge broadcasts RX ──▶ StreamWriter.write(data)
    │
    ├── write error ──▶ DISCONNECTED (remove from list)
    │
    └── client closes ──▶ DISCONNECTED (remove from list)
```

No complex state machine needed (unlike BLE/Classic which have connecting/reconnecting states). TCP clients are either connected or not.

## Data Flow Diagram

```
                    ┌─────────────────┐
                    │   BLE Client    │
                    │ (iOS APRS Chat) │
                    └────────┬────────┘
                             │ BLE GATT NUS
                    ┌────────┴────────┐
                    │   BLEService    │
                    │  send_data()    │
                    └────────┬────────┘
                             │
    ┌────────────┐  ┌────────┴────────┐  ┌────────────────┐
    │ TCP Client │  │                 │  │                │
    │ (APRSIS32) ├──┤  BridgeService  ├──┤ ClassicService │──── TNC Radio
    │            │  │                 │  │                │     (SPP/RFCOMM)
    └────────────┘  │  _forward_to_  │  └────────────────┘
    ┌────────────┐  │   clients()    │
    │ TCP Client │  │                │
    │ (Xastir)   ├──┤  _forward_to_  │
    │            │  │   classic()    │
    └────────────┘  └────────────────┘
                    TcpKissService
                     broadcast()
```
