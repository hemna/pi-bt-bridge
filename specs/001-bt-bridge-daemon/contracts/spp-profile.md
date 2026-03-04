# Contract: Bluetooth Classic SPP Profile

**Feature**: 001-bt-bridge-daemon  
**Protocol**: Bluetooth Classic Serial Port Profile (SPP)  
**Role**: SPP Client (Initiator)

## Overview

The daemon acts as an SPP client, initiating connections to a Bluetooth Classic
TNC device (ham radio). SPP provides a virtual serial port over RFCOMM.

## Connection Parameters

### Target Device

| Parameter | Source | Description |
|-----------|--------|-------------|
| Address | Configuration | Target TNC MAC address (XX:XX:XX:XX:XX:XX) |
| PIN | Configuration | Pairing PIN, default "0000" or "1234" |
| Channel | SDP Discovery | RFCOMM channel for SPP service |

### SPP Service UUID

```
00001101-0000-1000-8000-00805F9B34FB
```

This is the standard SPP UUID. The daemon queries SDP to find which RFCOMM
channel the TNC advertises for this service.

## Connection Flow

### Initial Connection

```
1. Daemon reads target_address from configuration
2. Daemon queries SDP on target for SPP service UUID
3. SDP returns RFCOMM channel number (1-30)
4. Daemon initiates RFCOMM connection to discovered channel
5. If pairing required, daemon provides configured PIN
6. On success, bidirectional byte stream established
```

### Reconnection

```
1. Detect connection loss (read/write error, disconnect event)
2. Wait reconnect_delay (starts at 1s)
3. Attempt connection (steps 2-6 above)
4. On failure, double delay (max 30s)
5. On success, reset delay to 1s
```

## Data Transfer

### Serial Parameters

SPP emulates a serial port. While the underlying transport is packet-based,
the daemon treats it as a byte stream.

| Parameter | Value | Notes |
|-----------|-------|-------|
| Baud Rate | N/A | SPP has no baud rate; speed limited by BT throughput |
| Data Bits | 8 | Implicit |
| Stop Bits | 1 | Implicit |
| Parity | None | Implicit |
| Flow Control | None | Application-level only |

### Throughput

- **Theoretical Max**: ~3 Mbps (BT 2.0 EDR)
- **Practical Throughput**: 200-700 Kbps depending on conditions
- **Minimum Required**: 960 bytes/sec (9600 baud equivalent)

### Buffering

| Direction | Buffer Size | Overflow Behavior |
|-----------|-------------|-------------------|
| TNC → Bridge | 4KB | Drop oldest, log warning |
| Bridge → TNC | 4KB | Block sender (backpressure) |

## BlueZ D-Bus Integration

### Profile Registration

The daemon registers an SPP profile with BlueZ via D-Bus Profile1 API:

```python
# Profile registration path
PROFILE_PATH = "/org/bluez/profile/spp"

# Profile options
{
    "Name": "Serial Port",
    "Service": "00001101-0000-1000-8000-00805F9B34FB",
    "Role": "client",
    "Channel": 0,  # Auto (use SDP)
    "RequireAuthentication": True,
    "RequireAuthorization": False,
}
```

### Connection Handling

When BlueZ establishes the connection, it calls:
- `NewConnection(device_path, fd, fd_properties)`: Provides file descriptor for I/O
- `RequestDisconnection(device_path)`: Called on disconnect

The daemon wraps the file descriptor with asyncio for non-blocking I/O.

## Error Handling

### Connection Errors

| Error | Cause | Daemon Response |
|-------|-------|-----------------|
| `org.bluez.Error.Failed` | General failure | Log, retry with backoff |
| `org.bluez.Error.InProgress` | Connection already pending | Wait for completion |
| `org.bluez.Error.NotReady` | Adapter not ready | Wait for adapter, retry |
| `org.bluez.Error.AuthenticationFailed` | Wrong PIN | Log error, require config update |
| `org.bluez.Error.AuthenticationCanceled` | User canceled | Log, retry |
| `org.bluez.Error.ConnectionAttemptFailed` | Device unreachable | Retry with backoff |

### Runtime Errors

| Error | Detection | Response |
|-------|-----------|----------|
| Read timeout | No data for >60s | Keep connection (TNC may be idle) |
| Write error | `write()` returns error | Mark disconnected, reconnect |
| EOF on read | `read()` returns 0 bytes | Mark disconnected, reconnect |

## Contract Test Cases

### Test 1: Initial Connection

```
GIVEN: TNC is powered on and discoverable
AND: Configuration has correct target_address
WHEN: Daemon starts
THEN: Daemon discovers SPP channel via SDP
AND: Daemon connects to RFCOMM channel
AND: Connection state becomes CONNECTED within 10 seconds
```

### Test 2: PIN Pairing

```
GIVEN: TNC requires PIN authentication
AND: Configuration has target_pin = "1234"
WHEN: Daemon connects to TNC
THEN: Daemon provides PIN "1234" when prompted
AND: Pairing succeeds
AND: Connection established
```

### Test 3: Reconnection on Disconnect

```
GIVEN: Daemon is connected to TNC
WHEN: TNC is power-cycled
THEN: Daemon detects disconnection
AND: Daemon enters CONNECTING state
AND: Daemon attempts reconnection after 1 second
AND: Connection re-established when TNC available
```

### Test 4: Exponential Backoff

```
GIVEN: TNC is powered off
AND: Daemon is attempting to connect
WHEN: Connection fails 5 times
THEN: Delay sequence is: 1s, 2s, 4s, 8s, 16s
AND: Delay caps at 30 seconds
```

### Test 5: Data Transfer

```
GIVEN: Daemon is connected to TNC
WHEN: TNC sends bytes [0xC0, 0x00, 0x48, 0x49, 0xC0]
THEN: Daemon receives bytes in rx_queue
AND: Bytes are available for KISS parsing
```

### Test 6: SDP Discovery Failure

```
GIVEN: TNC is powered on but not advertising SPP
WHEN: Daemon attempts to connect
THEN: SDP query returns no SPP service
AND: Daemon logs error "SPP service not found"
AND: Daemon retries with backoff
```

## Sequence Diagram: Connection

```
Daemon                       BlueZ                         TNC
   │                           │                            │
   │───RegisterProfile────────►│                            │
   │◄──Profile Registered──────│                            │
   │                           │                            │
   │───Connect(target_addr)───►│                            │
   │                           │───SDP Query───────────────►│
   │                           │◄──SPP Channel=1────────────│
   │                           │                            │
   │                           │───RFCOMM Connect──────────►│
   │                           │◄──RFCOMM Accepted──────────│
   │                           │                            │
   │◄──NewConnection(fd)───────│                            │
   │                           │                            │
```

## Sequence Diagram: Data Flow

```
Daemon                       BlueZ                         TNC
   │                           │                            │
   │───write(fd, data)────────►│                            │
   │                           │───RFCOMM Data─────────────►│
   │                           │                            │
   │                           │◄──RFCOMM Data──────────────│
   │◄──read(fd) = data─────────│                            │
   │                           │                            │
```

## Configuration Example

```json
{
    "target_address": "00:11:22:33:44:55",
    "target_pin": "0000",
    "reconnect_max_delay": 30
}
```
