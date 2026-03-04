# Data Model: Bluetooth LE to Classic Bridge

**Feature**: 001-bt-bridge-daemon  
**Date**: 2026-03-04

## Entity Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      BridgeState                            │
│  ┌─────────────────┐         ┌───────────────────────┐     │
│  │  BLEConnection  │◄───────►│  ClassicConnection    │     │
│  │  - state        │         │  - state              │     │
│  │  - device_info  │         │  - device_info        │     │
│  │  - rx_queue     │         │  - rx_queue           │     │
│  │  - tx_queue     │         │  - tx_queue           │     │
│  └────────┬────────┘         └───────────┬───────────┘     │
│           │                              │                  │
│           └──────────┬───────────────────┘                  │
│                      ▼                                      │
│              ┌───────────────┐                              │
│              │  KISSParser   │                              │
│              │  - buffer     │                              │
│              │  - frames[]   │                              │
│              └───────────────┘                              │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
              ┌───────────────┐
              │ Configuration │
              │ - target_addr │
              │ - pin_code    │
              │ - log_level   │
              └───────────────┘
```

## Entities

### ConnectionState (Enum)

Represents the state of a Bluetooth connection.

```python
class ConnectionState(Enum):
    IDLE = "idle"              # Not connected, not attempting
    SCANNING = "scanning"      # BLE: Advertising / Classic: Discovering
    CONNECTING = "connecting"  # Connection in progress
    CONNECTED = "connected"    # Active connection
    DISCONNECTING = "disconnecting"  # Graceful disconnect in progress
    ERROR = "error"            # Connection failed, requires intervention
```

**State Transitions**:
```
IDLE ──► SCANNING ──► CONNECTING ──► CONNECTED
  ▲                        │              │
  │                        ▼              ▼
  └─────────────────── ERROR ◄──── DISCONNECTING
```

**Validation Rules**:
- Only valid forward transitions allowed
- ERROR can transition to IDLE (reset) or SCANNING (retry)
- CONNECTED can only transition to DISCONNECTING or ERROR

---

### BLEConnection

Represents the Bluetooth LE connection to an iPhone.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `state` | ConnectionState | Current connection state | Required |
| `device_address` | str \| None | Connected device BT address | MAC format when set |
| `device_name` | str \| None | Device friendly name | Optional |
| `mtu` | int | Negotiated MTU size | 23-517, default 23 |
| `connected_at` | datetime \| None | Connection timestamp | UTC |
| `rx_queue` | asyncio.Queue[bytes] | Incoming data from iPhone | Max 4KB buffer |
| `tx_queue` | asyncio.Queue[bytes] | Outgoing data to iPhone | Max 4KB buffer |
| `bytes_rx` | int | Total bytes received | Monotonic counter |
| `bytes_tx` | int | Total bytes transmitted | Monotonic counter |

**Validation Rules**:
- `device_address` must be valid MAC format (XX:XX:XX:XX:XX:XX) when set
- `mtu` must be in range 23-517 (BLE spec)
- Queues have max size to prevent memory exhaustion

---

### ClassicConnection

Represents the Bluetooth Classic connection to a TNC radio.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `state` | ConnectionState | Current connection state | Required |
| `target_address` | str | Target device BT address | MAC format, from config |
| `device_name` | str \| None | Device friendly name | Discovered during connect |
| `rfcomm_channel` | int \| None | SPP channel number | 1-30 when connected |
| `connected_at` | datetime \| None | Connection timestamp | UTC |
| `rx_queue` | asyncio.Queue[bytes] | Incoming data from TNC | Max 4KB buffer |
| `tx_queue` | asyncio.Queue[bytes] | Outgoing data to TNC | Max 4KB buffer |
| `bytes_rx` | int | Total bytes received | Monotonic counter |
| `bytes_tx` | int | Total bytes transmitted | Monotonic counter |
| `reconnect_attempts` | int | Failed reconnect count | Reset on success |
| `last_error` | str \| None | Last error message | For diagnostics |

**Validation Rules**:
- `target_address` must be valid MAC format
- `rfcomm_channel` must be 1-30 when set (SPP spec)
- `reconnect_attempts` tracked for exponential backoff

---

### KISSFrame

Represents a complete KISS protocol frame.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `port` | int | TNC port number | 0-15 |
| `command` | KISSCommand | Frame command type | Enum value |
| `data` | bytes | Frame payload | Max 1024 bytes recommended |
| `raw` | bytes | Original escaped frame | For passthrough |
| `timestamp` | datetime | Frame creation time | UTC |

**KISSCommand Enum**:
```python
class KISSCommand(Enum):
    DATA_FRAME = 0x00
    TX_DELAY = 0x01
    PERSISTENCE = 0x02
    SLOT_TIME = 0x03
    TX_TAIL = 0x04
    FULL_DUPLEX = 0x05
    SET_HARDWARE = 0x06
    RETURN = 0xFF
```

**Validation Rules**:
- `port` must be 0-15 (4-bit value)
- `command` extracted from low nibble of command byte
- `data` should not exceed TNC buffer limits (typically 1KB)

---

### KISSParser

Stateful parser for KISS frame extraction from byte stream.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `buffer` | bytearray | Accumulation buffer | Max 4KB |
| `in_frame` | bool | Currently inside a frame | State flag |
| `escape_next` | bool | Next byte is escaped | State flag |

**Methods**:
- `feed(data: bytes) -> list[KISSFrame]`: Process incoming bytes, return complete frames
- `reset() -> None`: Clear parser state (after error)

**State Machine**:
```
                    ┌──────────────────────┐
                    │     IDLE             │
                    │  (waiting for FEND)  │
                    └──────────┬───────────┘
                               │ FEND received
                               ▼
                    ┌──────────────────────┐
                    │    IN_FRAME          │◄──┐
                    │ (accumulating data)  │   │
                    └──────────┬───────────┘   │
                               │               │
              ┌────────────────┼────────────┐  │
              │                │            │  │
         FEND │           FESC │      other │  │
              ▼                ▼            │  │
     ┌────────────┐   ┌─────────────┐      │  │
     │ EMIT FRAME │   │  ESCAPE     │      │  │
     │ → IDLE     │   │  (wait next)├──────┘  │
     └────────────┘   └──────┬──────┘         │
                             │ TFEND/TFESC    │
                             └────────────────┘
```

---

### BridgeState

Top-level state container for the daemon.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `ble` | BLEConnection | BLE connection state | Required |
| `classic` | ClassicConnection | Classic connection state | Required |
| `ble_parser` | KISSParser | Parser for BLE→Classic | Required |
| `classic_parser` | KISSParser | Parser for Classic→BLE | Required |
| `started_at` | datetime | Daemon start time | UTC |
| `frames_bridged` | int | Total frames transferred | Both directions |
| `errors` | list[ErrorEvent] | Recent errors | Capped at 100 |

**Computed Properties**:
- `is_fully_connected`: Both connections in CONNECTED state
- `is_partially_connected`: One connection in CONNECTED state
- `uptime`: Time since `started_at`

---

### Configuration

Persisted daemon configuration.

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `target_address` | str | BT Classic target MAC | Required |
| `target_pin` | str | Pairing PIN if needed | "0000" |
| `device_name` | str | Advertised BLE name | "PiBTBridge" |
| `log_level` | str | Logging verbosity | "INFO" |
| `log_file` | str \| None | Log file path | None (stdout) |
| `buffer_size` | int | Queue buffer size bytes | 4096 |
| `reconnect_max_delay` | int | Max reconnect wait (sec) | 30 |
| `status_socket` | str | Unix socket for status | "/var/run/bt-bridge.sock" |

**Validation Rules**:
- `target_address` must be valid MAC format
- `log_level` must be DEBUG, INFO, WARNING, ERROR
- `buffer_size` must be 1024-65536
- `reconnect_max_delay` must be 5-300

**Persistence**: JSON file at `/etc/bt-bridge/config.json`

---

### ErrorEvent

Structured error for logging and status reporting.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | datetime | When error occurred |
| `source` | str | Component (ble, classic, bridge, config) |
| `error_type` | str | Error classification |
| `message` | str | Human-readable description |
| `remediation` | str \| None | Suggested fix |

---

## Relationships

```
Configuration (1) ──────────► BridgeState (1)
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            BLEConnection   ClassicConnection   ErrorEvent[]
                    │               │
                    │               │
                    ▼               ▼
               KISSParser      KISSParser
                    │               │
                    ▼               ▼
               KISSFrame[]     KISSFrame[]
```

## Data Flow

```
iPhone ──BLE──► BLEConnection.rx_queue ──► KISSParser ──► KISSFrame[]
                                                              │
                                                              ▼
                                               ClassicConnection.tx_queue ──► TNC

TNC ──SPP──► ClassicConnection.rx_queue ──► KISSParser ──► KISSFrame[]
                                                              │
                                                              ▼
                                                  BLEConnection.tx_queue ──► iPhone
```
