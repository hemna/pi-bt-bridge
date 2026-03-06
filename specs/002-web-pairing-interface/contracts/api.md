# API Contracts: Web Pairing Interface

**Feature**: 002-web-pairing-interface  
**Date**: 2026-03-05

## Base URL

`http://<pi-address>:8080`

## Authentication

None (local network only). Document firewall recommendations.

---

## Endpoints

### GET /

**Description**: Dashboard page (HTML)

**Response**: HTML page showing bridge status

---

### GET /api/status

**Description**: Get current bridge status

**Response** (200 OK):
```json
{
  "ble": {
    "state": "connected",
    "device_name": "iPhone",
    "device_address": "AA:BB:CC:DD:EE:FF",
    "connected_at": "2026-03-05T10:30:00Z",
    "advertising": false
  },
  "classic": {
    "state": "connected",
    "target_address": "24:71:89:8D:26:EF",
    "target_name": "TH-D74",
    "connected_at": "2026-03-05T10:25:00Z",
    "rfcomm_channel": 2
  },
  "uptime_seconds": 3600.5,
  "started_at": "2026-03-05T09:30:00Z",
  "version": "1.0.0"
}
```

---

### GET /api/status/stream

**Description**: Server-Sent Events stream for real-time status updates

**Response**: `text/event-stream`

```
event: status
data: {"ble":{"state":"connected",...},"classic":{...}}

event: status
data: {"ble":{"state":"disconnected",...},"classic":{...}}
```

**Events**:
- `status`: Full status update (sent on change)
- `ping`: Keepalive (every 30 seconds)

---

### GET /api/stats

**Description**: Get packet statistics

**Response** (200 OK):
```json
{
  "packets_tx": 150,
  "packets_rx": 145,
  "bytes_tx": 12500,
  "bytes_rx": 11800,
  "errors": 0,
  "last_tx_at": "2026-03-05T10:35:00Z",
  "last_rx_at": "2026-03-05T10:35:01Z"
}
```

---

### GET /pairing

**Description**: Pairing page (HTML)

**Response**: HTML page for BT Classic pairing workflow

---

### POST /api/pairing/scan

**Description**: Start Bluetooth Classic device scan

**Request**: None (empty body)

**Response** (202 Accepted):
```json
{
  "status": "scanning",
  "message": "Scan started, results in 10-15 seconds"
}
```

**Response** (409 Conflict):
```json
{
  "error": "Scan already in progress"
}
```

---

### GET /api/pairing/devices

**Description**: Get list of discovered devices

**Response** (200 OK):
```json
{
  "state": "scan_complete",
  "devices": [
    {
      "address": "24:71:89:8D:26:EF",
      "name": "TH-D74",
      "rssi": -65,
      "device_class": 1028,
      "paired": false,
      "trusted": false,
      "has_spp": true
    },
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "name": "Other Device",
      "rssi": -80,
      "device_class": 2048,
      "paired": false,
      "trusted": false,
      "has_spp": false
    }
  ]
}
```

**Response** (425 Too Early) - Scan not complete:
```json
{
  "state": "scanning",
  "devices": [],
  "message": "Scan in progress"
}
```

---

### POST /api/pairing/pair

**Description**: Initiate pairing with a device

**Request**:
```json
{
  "address": "24:71:89:8D:26:EF"
}
```

**Response** (202 Accepted):
```json
{
  "status": "pairing",
  "message": "Pairing initiated with 24:71:89:8D:26:EF"
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Invalid MAC address format"
}
```

**Response** (409 Conflict):
```json
{
  "error": "Pairing already in progress"
}
```

---

### POST /api/pairing/pin

**Description**: Submit PIN for pairing

**Request**:
```json
{
  "pin": "0000"
}
```

**Response** (200 OK):
```json
{
  "status": "success",
  "message": "Pairing complete"
}
```

**Response** (400 Bad Request):
```json
{
  "error": "No PIN requested"
}
```

**Response** (401 Unauthorized):
```json
{
  "error": "Invalid PIN"
}
```

---

### GET /api/pairing/status

**Description**: Get current pairing session status

**Response** (200 OK):
```json
{
  "state": "pin_required",
  "target_address": "24:71:89:8D:26:EF",
  "target_name": "TH-D74",
  "pin_required": true,
  "error_message": null
}
```

---

### GET /settings

**Description**: Settings page (HTML)

**Response**: HTML page for configuration

---

### GET /api/settings

**Description**: Get current configuration

**Response** (200 OK):
```json
{
  "device_name": "PiBTBridge",
  "target_address": "24:71:89:8D:26:EF",
  "rfcomm_channel": 2,
  "log_level": "INFO",
  "web_port": 8080
}
```

---

### POST /api/settings

**Description**: Update configuration

**Request**:
```json
{
  "device_name": "MyBridge",
  "target_address": "24:71:89:8D:26:EF",
  "rfcomm_channel": 2,
  "log_level": "DEBUG"
}
```

**Response** (200 OK):
```json
{
  "status": "saved",
  "message": "Configuration saved. Restart required for some changes.",
  "restart_required": true
}
```

**Response** (400 Bad Request):
```json
{
  "error": "Validation failed",
  "details": {
    "target_address": "Invalid MAC address format"
  }
}
```

---

### POST /api/restart

**Description**: Restart the bridge daemon

**Request**: None

**Response** (202 Accepted):
```json
{
  "status": "restarting",
  "message": "Bridge will restart in 2 seconds"
}
```

---

## Error Response Format

All errors follow this format:

```json
{
  "error": "Human readable error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

**Common Error Codes**:
- `VALIDATION_ERROR`: Request validation failed
- `NOT_FOUND`: Resource not found
- `CONFLICT`: Operation conflicts with current state
- `INTERNAL_ERROR`: Unexpected server error

---

## Rate Limiting

No rate limiting implemented (single user expected).

---

## CORS

Not required (same-origin requests only).
