# API Contract: TNC History

**Feature**: 003-tnc-radio-history  
**Date**: 2026-03-06  
**Base URL**: `http://<pi-ip>:8080`

## Endpoints

### GET /api/tnc-history

List all TNC devices in history.

**Response (200 OK)**:

```json
{
  "devices": [
    {
      "address": "00:1A:7D:DA:71:13",
      "bluetooth_name": "TH-D74",
      "friendly_name": "Mobile Rig",
      "display_name": "Mobile Rig",
      "rfcomm_channel": 2,
      "last_used": "2026-03-06T10:30:00Z",
      "added_at": "2026-03-01T14:00:00Z",
      "is_current": true,
      "is_paired": true
    },
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "bluetooth_name": "Mobilinkd TNC3",
      "friendly_name": null,
      "display_name": "Mobilinkd TNC3",
      "rfcomm_channel": 1,
      "last_used": "2026-03-05T08:15:00Z",
      "added_at": "2026-03-02T09:00:00Z",
      "is_current": false,
      "is_paired": true
    }
  ],
  "count": 2,
  "current_address": "00:1A:7D:DA:71:13"
}
```

**Notes**:
- Devices sorted by `last_used` descending (most recent first)
- `display_name` is computed: `friendly_name` if set, else `bluetooth_name`
- `is_current` is true if this device matches current `target_address` in config
- `is_paired` indicates Bluetooth pairing status (may be false if unpaired)

---

### GET /api/tnc-history/{address}

Get a single TNC device by MAC address.

**Path Parameters**:
- `address`: MAC address (URL-encoded if needed)

**Response (200 OK)**:

```json
{
  "address": "00:1A:7D:DA:71:13",
  "bluetooth_name": "TH-D74",
  "friendly_name": "Mobile Rig",
  "display_name": "Mobile Rig",
  "rfcomm_channel": 2,
  "last_used": "2026-03-06T10:30:00Z",
  "added_at": "2026-03-01T14:00:00Z",
  "is_current": true,
  "is_paired": true
}
```

**Response (404 Not Found)**:

```json
{
  "success": false,
  "message": "TNC not found in history",
  "address": "00:1A:7D:DA:71:13"
}
```

---

### POST /api/tnc-history

Add a TNC device to history (or update if exists).

**Request Body**:

```json
{
  "address": "00:1A:7D:DA:71:13",
  "bluetooth_name": "TH-D74",
  "friendly_name": "Mobile Rig",
  "rfcomm_channel": 2
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `address` | Yes | MAC address |
| `bluetooth_name` | Yes | Device name from Bluetooth |
| `friendly_name` | No | User-assigned name |
| `rfcomm_channel` | Yes | RFCOMM channel (1-30) |

**Response (201 Created)** - New entry:

```json
{
  "success": true,
  "message": "TNC added to history",
  "device": { ... }
}
```

**Response (200 OK)** - Updated existing:

```json
{
  "success": true,
  "message": "TNC updated in history",
  "device": { ... }
}
```

**Response (400 Bad Request)** - Validation error:

```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "address": "Invalid MAC address format",
    "rfcomm_channel": "Must be 1-30"
  }
}
```

---

### PUT /api/tnc-history/{address}

Update a TNC device (primarily for friendly name).

**Path Parameters**:
- `address`: MAC address

**Request Body**:

```json
{
  "friendly_name": "Base Station"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `friendly_name` | No | New friendly name (null to clear) |
| `rfcomm_channel` | No | Updated RFCOMM channel |

**Response (200 OK)**:

```json
{
  "success": true,
  "message": "TNC updated",
  "device": { ... }
}
```

**Response (404 Not Found)**:

```json
{
  "success": false,
  "message": "TNC not found in history"
}
```

---

### DELETE /api/tnc-history/{address}

Remove a TNC device from history.

**Path Parameters**:
- `address`: MAC address

**Response (200 OK)**:

```json
{
  "success": true,
  "message": "TNC removed from history"
}
```

**Response (404 Not Found)**:

```json
{
  "success": false,
  "message": "TNC not found in history"
}
```

**Response (409 Conflict)** - Cannot remove current target:

```json
{
  "success": false,
  "message": "Cannot remove currently active TNC. Select a different TNC first."
}
```

---

### POST /api/tnc-history/{address}/select

Select a TNC from history as the active target.

**Path Parameters**:
- `address`: MAC address

**Response (200 OK)**:

```json
{
  "success": true,
  "message": "TNC selected as active target",
  "device": { ... },
  "connecting": true
}
```

**Behavior**:
1. Updates `target_address` and `rfcomm_channel` in config
2. Saves config to file
3. Updates `last_used` timestamp in history
4. Initiates connection to new target (if bridge is running)
5. Returns immediately (connection happens asynchronously)

**Response (404 Not Found)**:

```json
{
  "success": false,
  "message": "TNC not found in history"
}
```

**Response (400 Bad Request)** - Device not paired:

```json
{
  "success": false,
  "message": "TNC is not paired. Please pair the device first.",
  "is_paired": false
}
```

---

## Error Response Format

All error responses follow this format:

```json
{
  "success": false,
  "message": "Human-readable error message",
  "errors": { }  // Optional: field-specific errors
}
```

## Data Types

### MAC Address

- Format: `XX:XX:XX:XX:XX:XX`
- Case-insensitive (normalized to uppercase on storage)
- Used in URL paths (no encoding needed for colons)

### Timestamps

- Format: ISO 8601 with UTC timezone
- Example: `"2026-03-06T10:30:00Z"`
- `null` if never used

### RFCOMM Channel

- Integer 1-30
- Common values: 1 (Mobilinkd), 2 (TH-D74)
