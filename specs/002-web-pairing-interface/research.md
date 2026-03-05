# Research: Web Pairing Interface

**Feature**: 002-web-pairing-interface  
**Date**: 2026-03-05  
**Status**: Complete

## Executive Summary

This research document covers the technical approach for adding a web interface to the pi-bt-bridge daemon. The key decisions are:

1. **Web Framework**: Use `aiohttp` - lightweight, async-native, integrates naturally with the existing asyncio-based daemon
2. **Templates**: Use `Jinja2` for server-rendered HTML with progressive enhancement
3. **Real-time Updates**: Use Server-Sent Events (SSE) for live status updates (simpler than WebSocket)
4. **Bluetooth Scanning**: Use D-Bus BlueZ API via existing `dbus-python` dependency
5. **Pairing Flow**: Extend existing `PairingAgent` to handle web-initiated pairing

## Research Topics

### 1. Web Framework Selection

**Options Evaluated**:
- **aiohttp**: Pure async, lightweight (~700KB), native asyncio support
- **FastAPI**: More features, but heavier (~2MB with dependencies), overkill for this use case
- **Flask**: Synchronous, would require threading to integrate with asyncio event loop

**Decision**: `aiohttp`

**Rationale**:
- Already using asyncio for BLE (bless) and RFCOMM operations
- Minimal memory footprint aligns with <16MB constraint
- Built-in support for SSE (Server-Sent Events) for real-time updates
- No ASGI server needed - embeds directly in daemon

### 2. Template Engine

**Decision**: `Jinja2`

**Rationale**:
- Industry standard, well-documented
- aiohttp has built-in Jinja2 integration via `aiohttp_jinja2`
- Supports template inheritance for consistent layouts
- Works with progressive enhancement (no JS required for basic views)

### 3. Real-time Status Updates

**Options Evaluated**:
- **Polling**: Simple but increases latency and server load
- **WebSocket**: Full-duplex, but more complex than needed
- **Server-Sent Events (SSE)**: Server-to-client only, perfect for status updates

**Decision**: SSE (Server-Sent Events)

**Rationale**:
- Status updates are server-initiated (connection state changes)
- Simpler implementation than WebSocket
- Automatic reconnection built into browser EventSource API
- Falls back gracefully to polling for non-JS browsers

### 4. Bluetooth Device Scanning (Classic)

**Current State**: The bridge already uses D-Bus for BLE via `bless`, and has `dbus-python` installed.

**BlueZ D-Bus API for Discovery**:
```python
# Start discovery
adapter = bus.get('org.bluez', '/org/bluez/hci0')
adapter.StartDiscovery()

# Get discovered devices
om = bus.get('org.bluez', '/')
for path, interfaces in om.GetManagedObjects().items():
    if 'org.bluez.Device1' in interfaces:
        device = interfaces['org.bluez.Device1']
        # device['Address'], device['Name'], device['RSSI']
```

**Key Finding**: Need to filter for Bluetooth Classic devices (not BLE-only). Check `UUIDs` property for SPP profile (00001101-0000-1000-8000-00805F9B34FB).

### 5. Pairing Flow via Web Interface

**Current State**: `PairingAgent` in `src/services/pairing_agent.py` already handles:
- Auto-accepting incoming pairing requests
- Providing PIN when requested

**Extension Needed**:
- Initiate pairing to a device (not just accept)
- Web UI for PIN entry when TNC displays PIN
- Report pairing progress/result back to web UI

**BlueZ Pairing API**:
```python
device = bus.get('org.bluez', f'/org/bluez/hci0/dev_{mac.replace(":", "_")}')
device.Pair()  # Async - agent callback handles PIN
device.Trust() # Mark as trusted after pairing
```

### 6. Integration with Existing Daemon

**Current Architecture** (from `src/main.py`):
```
main() -> asyncio.run(run_daemon(config))
  -> bridge.start()
  -> await shutdown_event.wait()
```

**Web Server Integration**:
```python
async def run_daemon(config):
    # ... existing setup ...
    
    # Create web service
    web_service = WebService(
        host="0.0.0.0",
        port=config.web_port,  # New config field
        bridge_state=state,
        config=config,
    )
    
    # Start bridge and web server concurrently
    await asyncio.gather(
        bridge.start(),
        web_service.start(),
    )
```

### 7. Configuration Extensions

**New Fields for `Configuration`**:
```python
web_port: int = 8080  # HTTP port
web_enabled: bool = True  # Allow disabling web UI
```

### 8. Memory Budget Analysis

**Constraint**: <16MB additional RAM

**Estimates**:
- aiohttp: ~5MB (Python + dependencies)
- Jinja2: ~2MB
- HTML templates: ~0.5MB
- Active connections: ~0.5MB per client
- **Total**: ~8-10MB typical usage

**Conclusion**: Within budget with margin.

## API Design Preview

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Dashboard (status overview) |
| GET | `/status` | JSON status API |
| GET | `/status/stream` | SSE status stream |
| GET | `/pairing` | Pairing page |
| POST | `/pairing/scan` | Start BT Classic scan |
| GET | `/pairing/devices` | List discovered devices |
| POST | `/pairing/pair` | Initiate pairing |
| POST | `/pairing/pin` | Submit PIN |
| GET | `/settings` | Settings page |
| POST | `/settings` | Update settings |
| GET | `/stats` | Statistics page |

### Status Response Schema

```json
{
  "ble": {
    "state": "connected",
    "device_name": "iPhone",
    "connected_at": "2026-03-05T10:30:00Z"
  },
  "classic": {
    "state": "connected",
    "target_address": "24:71:89:8D:26:EF",
    "connected_at": "2026-03-05T10:25:00Z"
  },
  "uptime_seconds": 3600,
  "packets": {
    "tx": 150,
    "rx": 145,
    "errors": 0
  }
}
```

## Dependencies

**New Dependencies**:
```
aiohttp>=3.9.0
aiohttp-jinja2>=1.6.0
```

**Existing Dependencies** (no changes):
- bless (BLE GATT)
- dbus-python (D-Bus/BlueZ)
- PyGObject (GLib)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| BlueZ scan conflicts with BLE advertising | Pause BLE advertising during Classic scan |
| Pairing blocks event loop | Run pairing in executor thread |
| Memory growth with SSE clients | Limit concurrent SSE connections to 5 |
| Security - no auth | Bind to localhost by default, document firewall rules |

## Open Questions (Resolved)

1. **Q: Use WebSocket or SSE?** A: SSE - simpler, sufficient for this use case
2. **Q: Full SPA or server-rendered?** A: Server-rendered with progressive enhancement
3. **Q: Separate process or embedded?** A: Embedded in daemon for simplicity

## Next Steps

1. Create data-model.md defining status/config/stats models
2. Create API contracts in contracts/ directory
3. Generate tasks.md with implementation plan
