# Data Model: TNC Radio History

**Feature**: 003-tnc-radio-history  
**Date**: 2026-03-06

## Entities

### TNCDevice

Represents a known TNC radio device that has been paired and used.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | `str` | Yes | Bluetooth MAC address (primary identifier, format: `XX:XX:XX:XX:XX:XX`) |
| `bluetooth_name` | `str` | Yes | Device name from Bluetooth discovery |
| `friendly_name` | `str \| None` | No | User-assigned display name |
| `rfcomm_channel` | `int` | Yes | RFCOMM channel for SPP connection (1-30) |
| `last_used` | `datetime \| None` | No | Timestamp of last successful connection |
| `added_at` | `datetime` | Yes | Timestamp when added to history |

**Validation Rules**:
- `address`: Must match MAC pattern `^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$`
- `rfcomm_channel`: Must be integer 1-30
- `bluetooth_name`: Non-empty string
- `friendly_name`: If provided, must be 1-50 characters

**Display Name Logic**:
```
display_name = friendly_name if friendly_name else bluetooth_name
```

### TNCHistory

Collection of TNCDevice entries with persistence.

| Field | Type | Description |
|-------|------|-------------|
| `devices` | `dict[str, TNCDevice]` | Map of MAC address to TNCDevice |
| `path` | `Path` | File path for persistence |

**Operations**:

| Operation | Description |
|-----------|-------------|
| `add(device)` | Add or update device in history |
| `remove(address)` | Remove device from history |
| `get(address)` | Get device by MAC address |
| `list_all()` | Get all devices sorted by last_used (most recent first) |
| `select(address)` | Mark device as selected and update config |

**Invariants**:
- Maximum 20 devices (soft limit, oldest by `last_used` can be evicted if needed)
- Address is unique (adding duplicate updates existing entry)
- File is written after each modification

## State Transitions

### TNC Selection Flow

```
┌─────────────┐     select(addr)    ┌──────────────┐
│  History    │ ──────────────────► │  Connecting  │
│  (idle)     │                     │  to TNC      │
└─────────────┘                     └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │  Connected   │
                                    │  (update     │
                                    │  last_used)  │
                                    └──────────────┘
```

### History Entry Lifecycle

```
┌─────────────┐     pair + use     ┌──────────────┐
│  Unknown    │ ─────────────────► │  In History  │
│  Device     │                    │  (added_at   │
└─────────────┘                    │   set)       │
                                   └──────────────┘
                                          │
                                          │ each use
                                          ▼
                                   ┌──────────────┐
                                   │  In History  │
                                   │  (last_used  │
                                   │   updated)   │
                                   └──────────────┘
                                          │
                                          │ user delete
                                          ▼
                                   ┌──────────────┐
                                   │  Removed     │
                                   │  (can re-add │
                                   │   via scan)  │
                                   └──────────────┘
```

## Persistence Format

**File**: `/etc/bt-bridge/tnc-history.json`

```json
{
  "version": 1,
  "devices": [
    {
      "address": "00:1A:7D:DA:71:13",
      "bluetooth_name": "TH-D74",
      "friendly_name": "Mobile Rig",
      "rfcomm_channel": 2,
      "last_used": "2026-03-06T10:30:00Z",
      "added_at": "2026-03-01T14:00:00Z"
    },
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "bluetooth_name": "Mobilinkd TNC3",
      "friendly_name": null,
      "rfcomm_channel": 1,
      "last_used": "2026-03-05T08:15:00Z",
      "added_at": "2026-03-02T09:00:00Z"
    }
  ]
}
```

**Version Field**: Allows future schema migrations if needed.

## Relationships

```
┌─────────────────┐
│  Configuration  │
│  (config.json)  │
├─────────────────┤
│ target_address  │◄──────────┐
│ rfcomm_channel  │           │
└─────────────────┘           │
                              │ select() copies
┌─────────────────┐           │ address + channel
│   TNCHistory    │           │
│ (tnc-history.   │           │
│     json)       │           │
├─────────────────┤           │
│ devices[]       │───────────┘
└─────────────────┘
        │
        │ contains
        ▼
┌─────────────────┐
│   TNCDevice     │
├─────────────────┤
│ address         │
│ bluetooth_name  │
│ friendly_name   │
│ rfcomm_channel  │
│ last_used       │
│ added_at        │
└─────────────────┘
```

## API Response Models

### TNCDeviceResponse

Response model for API endpoints:

```python
@dataclass
class TNCDeviceResponse:
    address: str
    bluetooth_name: str
    friendly_name: str | None
    display_name: str          # Computed: friendly_name or bluetooth_name
    rfcomm_channel: int
    last_used: str | None      # ISO 8601 timestamp
    added_at: str              # ISO 8601 timestamp
    is_current: bool           # True if this is the current target
    is_paired: bool            # True if still paired at Bluetooth level
```

### TNCHistoryResponse

```python
@dataclass
class TNCHistoryResponse:
    devices: list[TNCDeviceResponse]
    count: int
    current_address: str | None  # Currently active TNC address
```
