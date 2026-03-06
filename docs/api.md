# REST API Reference

Pi BT Bridge provides a REST API for programmatic access to status, configuration, and pairing functionality.

## Overview

The API is served by the same HTTP server as the web interface. All endpoints return JSON responses.

## Base URL

```
http://<pi-ip-address>:8080
```

Default port is `8080`. See [Configuration](configuration.md) to change it.

## Authentication

**None.** The API is intended for use on a trusted local network. Do not expose to the internet.

## Content Types

- **Requests**: `application/json` for POST requests with body
- **Responses**: `application/json` for all endpoints

---

## Status APIs

### GET /api/status

Get the current bridge status.

**Response:**

```json
{
  "ble": {
    "state": "connected",
    "device_name": "iPhone",
    "device_address": "A1:B2:C3:D4:E5:F6",
    "connected_at": "2024-01-15T10:30:00Z",
    "advertising": false,
    "advertised_name": "PiBTBridge"
  },
  "classic": {
    "state": "connected",
    "target_name": "TH-D74",
    "target_address": "00:1A:7D:DA:71:13",
    "rfcomm_channel": 2,
    "connected_at": "2024-01-15T10:29:55Z"
  },
  "tcp_kiss": {
    "enabled": true,
    "listening": true,
    "port": 8001,
    "host": "0.0.0.0",
    "client_count": 2,
    "max_clients": 5,
    "clients": [
      {
        "remote_address": "192.168.1.50:49271",
        "connected_at": "2024-01-15T10:31:00Z",
        "bytes_rx": 1234,
        "bytes_tx": 5678
      },
      {
        "remote_address": "192.168.1.75:52340",
        "connected_at": "2024-01-15T10:32:15Z",
        "bytes_rx": 456,
        "bytes_tx": 789
      }
    ]
  },
  "uptime_seconds": 3600,
  "start_time": "2024-01-15T09:30:00Z",
  "version": "1.0.0"
}
```

**Connection States:**

| State | Description |
|-------|-------------|
| `idle` | Not connected, not attempting |
| `scanning` | BLE advertising / Classic discovering |
| `connecting` | Connection attempt in progress |
| `connected` | Active connection established |
| `disconnected` | Was connected, now disconnected |
| `error` | Connection failed |

---

### GET /api/status/stream

Server-Sent Events (SSE) stream for real-time status updates.

**Usage:**

```javascript
const eventSource = new EventSource('/api/status/stream');

eventSource.addEventListener('status', (event) => {
  const status = JSON.parse(event.data);
  console.log('Status update:', status);
});

eventSource.addEventListener('ping', (event) => {
  console.log('Keep-alive ping');
});
```

**Events:**

| Event | Description |
|-------|-------------|
| `status` | Status update (same format as GET /api/status) |
| `ping` | Keep-alive ping (every 30 seconds) |

**Limitations:**

- Maximum 5 concurrent clients
- Returns HTTP 503 if limit exceeded

**Error Response (503):**

```json
{
  "error": "Too many SSE clients"
}
```

---

### GET /api/stats

Get packet statistics.

**Response:**

```json
{
  "frames_bridged": 1234,
  "bytes_to_tnc": 56789,
  "bytes_from_tnc": 43210,
  "errors": 0,
  "ble_state": "connected",
  "classic_state": "connected",
  "uptime_seconds": 3600,
  "start_time": "2024-01-15T09:30:00Z"
}
```

---

## Settings APIs

### GET /api/settings

Get current configuration.

**Response:**

```json
{
  "target_address": "00:1A:7D:DA:71:13",
  "target_pin": "0000",
  "rfcomm_channel": 2,
  "device_name": "PiBTBridge",
  "log_level": "INFO",
  "log_file": null,
  "buffer_size": 4096,
  "reconnect_max_delay": 30,
  "status_socket": "/var/run/bt-bridge.sock",
  "web_enabled": true,
  "web_port": 8080,
  "web_host": "0.0.0.0",
  "tcp_kiss_enabled": true,
  "tcp_kiss_port": 8001,
  "tcp_kiss_host": "0.0.0.0",
  "tcp_kiss_max_clients": 5
}
```

---

### POST /api/settings

Update configuration settings.

**Request Body:**

Only include fields you want to change:

```json
{
  "device_name": "MyBridge",
  "log_level": "DEBUG",
  "web_port": 9000,
  "tcp_kiss_enabled": true,
  "tcp_kiss_port": 8001,
  "tcp_kiss_max_clients": 10
}
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Settings saved",
  "restart_required": true
}
```

**Validation Error Response (400):**

```json
{
  "success": false,
  "message": "Validation failed",
  "errors": {
    "web_port": "web_port must be 1024-65535, got: 80",
    "target_address": "target_address must be valid MAC format"
  }
}
```

**Field Validation:**

| Field | Validation |
|-------|------------|
| `target_address` | Valid MAC format (XX:XX:XX:XX:XX:XX) |
| `rfcomm_channel` | Integer 1-30 |
| `log_level` | One of: DEBUG, INFO, WARNING, ERROR |
| `buffer_size` | Integer 1024-65536 |
| `reconnect_max_delay` | Integer 5-300 |
| `web_port` | Integer 1024-65535 |
| `tcp_kiss_enabled` | Boolean (true/false) |
| `tcp_kiss_port` | Integer 1024-65535 |
| `tcp_kiss_host` | Non-empty string |
| `tcp_kiss_max_clients` | Integer 1-20 |

---

### POST /api/restart

Restart the daemon.

**Request Body:** None required

**Response:**

```json
{
  "success": true,
  "message": "Restarting..."
}
```

The daemon will terminate and systemd will restart it automatically.

**Note:** The HTTP connection will be closed as the server shuts down.

---

## Pairing APIs

### POST /api/pairing/scan

Start scanning for Bluetooth Classic devices.

**Request Body:** None required

**Response:**

```json
{
  "success": true,
  "message": "Scan started"
}
```

Scanning takes approximately 10-15 seconds. Poll `/api/pairing/devices` to get results.

**Error Response (409 - Scan already in progress):**

```json
{
  "success": false,
  "message": "Scan already in progress"
}
```

---

### GET /api/pairing/devices

Get discovered devices and scan status.

**Response (while scanning):**

```json
{
  "state": "scanning",
  "devices": []
}
```

**Response (scan complete):**

```json
{
  "state": "scan_complete",
  "devices": [
    {
      "address": "00:1A:7D:DA:71:13",
      "name": "TH-D74",
      "rssi": -45,
      "paired": false,
      "has_spp": true
    },
    {
      "address": "AA:BB:CC:DD:EE:FF",
      "name": "Unknown Device",
      "rssi": -72,
      "paired": true,
      "has_spp": false
    }
  ]
}
```

**Device Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Bluetooth MAC address |
| `name` | string | Device name (or "Unknown Device") |
| `rssi` | integer | Signal strength in dBm (closer to 0 = stronger) |
| `paired` | boolean | Whether device is already paired |
| `has_spp` | boolean | Whether device supports Serial Port Profile |

---

### POST /api/pairing/pair

Initiate pairing with a device.

**Request Body:**

```json
{
  "address": "00:1A:7D:DA:71:13"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Pairing started"
}
```

Poll `/api/pairing/status` to monitor pairing progress.

**Error Response (400):**

```json
{
  "success": false,
  "message": "Address is required"
}
```

---

### POST /api/pairing/pin

Submit PIN code during pairing.

**Request Body:**

```json
{
  "pin": "0000"
}
```

**Response:**

```json
{
  "success": true,
  "message": "PIN submitted"
}
```

**Error Response (400 - No PIN requested):**

```json
{
  "success": false,
  "message": "No PIN entry in progress"
}
```

---

### GET /api/pairing/status

Get current pairing session status.

**Response (idle):**

```json
{
  "state": "idle",
  "address": null,
  "device_name": null,
  "error": null
}
```

**Response (pairing in progress):**

```json
{
  "state": "pairing",
  "address": "00:1A:7D:DA:71:13",
  "device_name": "TH-D74",
  "error": null
}
```

**Response (PIN required):**

```json
{
  "state": "pin_required",
  "address": "00:1A:7D:DA:71:13",
  "device_name": "TH-D74",
  "error": null
}
```

**Response (success):**

```json
{
  "state": "success",
  "address": "00:1A:7D:DA:71:13",
  "device_name": "TH-D74",
  "error": null
}
```

**Response (failed):**

```json
{
  "state": "failed",
  "address": "00:1A:7D:DA:71:13",
  "device_name": "TH-D74",
  "error": "Device rejected pairing"
}
```

**Pairing States:**

| State | Description |
|-------|-------------|
| `idle` | No pairing in progress |
| `scanning` | Scanning for devices |
| `scan_complete` | Scan finished, devices available |
| `pairing` | Pairing attempt in progress |
| `pin_required` | Waiting for PIN entry |
| `success` | Pairing completed successfully |
| `failed` | Pairing failed (see error field) |

---

### POST /api/pairing/use

Set a paired device as the target TNC.

**Request Body:**

```json
{
  "address": "00:1A:7D:DA:71:13",
  "name": "TH-D74"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Target TNC updated to TH-D74 (00:1A:7D:DA:71:13)"
}
```

This updates `target_address` in the configuration and saves to file. The device is also automatically added to TNC history for quick switching later.

**Error Response (400):**

```json
{
  "success": false,
  "message": "Address is required"
}
```

---

## TNC History APIs

The TNC history API allows managing a list of previously paired TNC devices for quick switching without re-scanning.

### GET /api/tnc-history

List all TNC devices in history, sorted by most recently used first.

**Response (200 OK):**

```json
{
  "devices": [
    {
      "address": "00:1A:7D:DA:71:13",
      "bluetooth_name": "TH-D74",
      "friendly_name": "Mobile Rig",
      "display_name": "Mobile Rig",
      "rfcomm_channel": 2,
      "last_used": "2026-03-06T10:30:00",
      "added_at": "2026-03-01T14:00:00",
      "is_current": true,
      "is_paired": true
    }
  ],
  "count": 1,
  "current_address": "00:1A:7D:DA:71:13"
}
```

**Fields:**

| Field | Description |
|-------|-------------|
| `display_name` | `friendly_name` if set, otherwise `bluetooth_name` |
| `is_current` | True if this device matches the current `target_address` |
| `is_paired` | True if the device is currently Bluetooth paired |

---

### GET /api/tnc-history/{address}

Get a single TNC device by MAC address.

**Response (200 OK):**

```json
{
  "address": "00:1A:7D:DA:71:13",
  "bluetooth_name": "TH-D74",
  "friendly_name": "Mobile Rig",
  "display_name": "Mobile Rig",
  "rfcomm_channel": 2,
  "last_used": "2026-03-06T10:30:00",
  "added_at": "2026-03-01T14:00:00",
  "is_current": true,
  "is_paired": true
}
```

**Response (404 Not Found):**

```json
{
  "success": false,
  "message": "TNC not found in history",
  "address": "00:1A:7D:DA:71:13"
}
```

---

### POST /api/tnc-history

Add a TNC device to history (or update if it already exists).

**Request Body:**

```json
{
  "address": "00:1A:7D:DA:71:13",
  "bluetooth_name": "TH-D74",
  "friendly_name": "Mobile Rig",
  "rfcomm_channel": 2
}
```

| Field | Required | Validation |
|-------|----------|------------|
| `address` | Yes | Valid MAC format (XX:XX:XX:XX:XX:XX) |
| `bluetooth_name` | Yes | Non-empty string |
| `friendly_name` | No | 1-50 characters or null |
| `rfcomm_channel` | Yes | Integer 1-30 |

**Response (201 Created)** - New device:

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

**Response (400 Bad Request):**

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

Update a TNC device (friendly name or RFCOMM channel).

**Request Body:**

```json
{
  "friendly_name": "Base Station"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `friendly_name` | No | New name (1-50 chars), or `null` to clear |
| `rfcomm_channel` | No | Updated RFCOMM channel (1-30) |

**Response (200 OK):**

```json
{
  "success": true,
  "message": "TNC updated",
  "device": { ... }
}
```

**Response (404 Not Found):**

```json
{
  "success": false,
  "message": "TNC not found in history"
}
```

---

### DELETE /api/tnc-history/{address}

Remove a TNC device from history.

**Response (200 OK):**

```json
{
  "success": true,
  "message": "TNC removed from history"
}
```

**Response (404 Not Found):**

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

**Behavior:**

1. Updates `target_address` and `rfcomm_channel` in configuration
2. Saves configuration to file
3. Updates `last_used` timestamp in history
4. Returns immediately (connection happens asynchronously)

**Response (200 OK):**

```json
{
  "success": true,
  "message": "TNC selected as active target",
  "device": { ... },
  "connecting": true
}
```

**Response (404 Not Found):**

```json
{
  "success": false,
  "message": "TNC not found in history"
}
```

**Response (400 Bad Request)** - Not paired:

```json
{
  "success": false,
  "message": "TNC is not paired. Please pair the device first.",
  "is_paired": false
}
```

---

## Error Responses

All endpoints may return these error responses:

### 400 Bad Request

Invalid request data:

```json
{
  "success": false,
  "message": "Description of the error",
  "errors": { }
}
```

### 404 Not Found

Endpoint doesn't exist:

```json
{
  "error": "Not Found"
}
```

### 500 Internal Server Error

Server-side error:

```json
{
  "success": false,
  "message": "Internal server error",
  "error": "Exception details"
}
```

### 503 Service Unavailable

Resource limit reached (e.g., SSE clients):

```json
{
  "error": "Too many SSE clients"
}
```

---

## Data Models

### ConnectionState

Enum representing connection states:

```
idle | scanning | connecting | connected | disconnected | error
```

### PairingState

Enum representing pairing workflow states:

```
idle | scanning | scan_complete | pairing | pin_required | success | failed
```

---

## Examples

### cURL Examples

**Get status:**

```bash
curl http://raspberrypi.local:8080/api/status
```

**Update settings:**

```bash
curl -X POST http://raspberrypi.local:8080/api/settings \
  -H "Content-Type: application/json" \
  -d '{"device_name": "MyBridge", "log_level": "DEBUG"}'
```

**Start scan:**

```bash
curl -X POST http://raspberrypi.local:8080/api/pairing/scan
```

**Get devices:**

```bash
curl http://raspberrypi.local:8080/api/pairing/devices
```

**Pair with device:**

```bash
curl -X POST http://raspberrypi.local:8080/api/pairing/pair \
  -H "Content-Type: application/json" \
  -d '{"address": "00:1A:7D:DA:71:13"}'
```

**Submit PIN:**

```bash
curl -X POST http://raspberrypi.local:8080/api/pairing/pin \
  -H "Content-Type: application/json" \
  -d '{"pin": "0000"}'
```

**Set as target TNC:**

```bash
curl -X POST http://raspberrypi.local:8080/api/pairing/use \
  -H "Content-Type: application/json" \
  -d '{"address": "00:1A:7D:DA:71:13", "name": "TH-D74"}'
```

**Restart daemon:**

```bash
curl -X POST http://raspberrypi.local:8080/api/restart
```

**List TNC history:**

```bash
curl http://raspberrypi.local:8080/api/tnc-history
```

**Add TNC to history:**

```bash
curl -X POST http://raspberrypi.local:8080/api/tnc-history \
  -H "Content-Type: application/json" \
  -d '{"address": "00:1A:7D:DA:71:13", "bluetooth_name": "TH-D74", "rfcomm_channel": 2}'
```

**Update TNC friendly name:**

```bash
curl -X PUT http://raspberrypi.local:8080/api/tnc-history/00:1A:7D:DA:71:13 \
  -H "Content-Type: application/json" \
  -d '{"friendly_name": "Mobile Rig"}'
```

**Select TNC as active:**

```bash
curl -X POST http://raspberrypi.local:8080/api/tnc-history/00:1A:7D:DA:71:13/select
```

**Remove TNC from history:**

```bash
curl -X DELETE http://raspberrypi.local:8080/api/tnc-history/AA:BB:CC:DD:EE:FF
```

### Python Example

```python
import requests

BASE_URL = "http://raspberrypi.local:8080"

# Get status
response = requests.get(f"{BASE_URL}/api/status")
status = response.json()
print(f"BLE: {status['ble']['state']}, Classic: {status['classic']['state']}")

# Update settings
response = requests.post(
    f"{BASE_URL}/api/settings",
    json={"device_name": "MyBridge"}
)
result = response.json()
if result["success"]:
    print("Settings saved!")
else:
    print(f"Error: {result['message']}")

# Scan for devices
requests.post(f"{BASE_URL}/api/pairing/scan")

# Wait and get devices
import time
time.sleep(15)
response = requests.get(f"{BASE_URL}/api/pairing/devices")
devices = response.json()
for device in devices["devices"]:
    print(f"{device['name']} ({device['address']}) - RSSI: {device['rssi']}")
```

### JavaScript Example (Browser)

```javascript
// Get status
fetch('/api/status')
  .then(response => response.json())
  .then(status => {
    console.log(`BLE: ${status.ble.state}, Classic: ${status.classic.state}`);
  });

// Update settings
fetch('/api/settings', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ device_name: 'MyBridge' })
})
  .then(response => response.json())
  .then(result => {
    if (result.success) {
      console.log('Settings saved!');
    } else {
      console.error('Error:', result.message);
    }
  });

// Real-time status updates via SSE
const eventSource = new EventSource('/api/status/stream');
eventSource.addEventListener('status', (event) => {
  const status = JSON.parse(event.data);
  updateUI(status);
});
```

---

## See Also

- [Web Interface Guide](web-interface.md) - Using the web UI
- [Configuration Reference](configuration.md) - All configuration options
- [Installation Guide](installation.md) - Setup instructions
