# Contract: BLE GATT Service (Nordic UART Service)

**Feature**: 001-bt-bridge-daemon  
**Protocol**: Bluetooth Low Energy GATT  
**Service**: Nordic UART Service (NUS)

## Service Definition

The daemon exposes a BLE GATT service that emulates a serial port using the
industry-standard Nordic UART Service (NUS) UUIDs.

### Service UUID

```
6E400001-B5A3-F393-E0A9-E50E24DCCA9E
```

### Characteristics

| Characteristic | UUID | Properties | Description |
|----------------|------|------------|-------------|
| TX | `6E400002-B5A3-F393-E0A9-E50E24DCCA9E` | Write, Write Without Response | iPhone writes data TO bridge |
| RX | `6E400003-B5A3-F393-E0A9-E50E24DCCA9E` | Read, Notify | Bridge sends data TO iPhone |

**Note**: TX/RX naming is from the central's (iPhone's) perspective.

## Characteristic Details

### TX Characteristic (Central → Peripheral)

**Direction**: iPhone → Bridge (data TO the TNC)

**Properties**:
- `Write`: Acknowledged write with response
- `Write Without Response`: Faster, unacknowledged write

**Max Length**: Negotiated MTU - 3 bytes (default: 20 bytes, max: 512 bytes)

**Behavior**:
- All received bytes are queued for KISS parsing
- Data is forwarded to Classic connection after frame completion
- If Classic connection is down, data is buffered (up to 4KB)
- Writes exceeding buffer capacity return error `ATT_INSUFFICIENT_RESOURCES`

### RX Characteristic (Peripheral → Central)

**Direction**: Bridge → iPhone (data FROM the TNC)

**Properties**:
- `Read`: On-demand read of last value (not typically used for streaming)
- `Notify`: Asynchronous push when data available

**CCCD (Client Characteristic Configuration Descriptor)**:
- UUID: `0x2902`
- iPhone must enable notifications by writing `0x0001` to CCCD

**Max Length**: Negotiated MTU - 3 bytes

**Behavior**:
- KISS frames from TNC are queued and fragmented to MTU size
- Notifications sent when data available and CCCD enabled
- If notifications disabled, data accumulates until read or overflow

## Advertising

### Advertisement Data

| Field | Value |
|-------|-------|
| Flags | `0x06` (LE General Discoverable, BR/EDR Not Supported) |
| Complete Local Name | Configurable, default "PiBTBridge" |
| Complete 128-bit Service UUIDs | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |

### Scan Response Data

| Field | Value |
|-------|-------|
| TX Power Level | Actual TX power |
| Manufacturer Specific | Optional: version, status |

### Advertising Interval

- Default: 100ms - 200ms (fast advertising for discovery)
- After connection: Advertising stops until disconnect
- Configurable for power optimization

## Connection Parameters

### Requested Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Connection Interval Min | 15ms | Low latency |
| Connection Interval Max | 30ms | Balance latency/power |
| Peripheral Latency | 0 | No skipped events |
| Supervision Timeout | 4000ms | Tolerate brief dropouts |

### MTU Negotiation

- Bridge requests maximum MTU (512 bytes) during connection
- Actual MTU determined by iOS response (typically 185-512 bytes)
- Larger MTU improves throughput by reducing fragmentation overhead

## Error Handling

### ATT Errors Returned

| Error Code | Condition |
|------------|-----------|
| `ATT_INSUFFICIENT_RESOURCES` | Buffer full, Classic connection down too long |
| `ATT_WRITE_NOT_PERMITTED` | Write to RX characteristic attempted |
| `ATT_READ_NOT_PERMITTED` | Read from TX characteristic attempted |

### Connection Errors

| Event | Bridge Behavior |
|-------|-----------------|
| Unexpected disconnect | Begin advertising within 1 second |
| Authentication failure | Log error, continue advertising |
| MTU negotiation failure | Use default 23-byte MTU |

## Contract Test Cases

### Test 1: Service Discovery

```
GIVEN: Bridge is advertising
WHEN: iPhone scans for BLE devices
THEN: Bridge appears with name "PiBTBridge" (or configured name)
AND: Service UUID 6E400001-... is in advertisement
```

### Test 2: TX Write

```
GIVEN: iPhone connected to bridge
AND: Notifications enabled on RX characteristic
WHEN: iPhone writes bytes [0xC0, 0x00, 0x41, 0xC0] to TX characteristic
THEN: Write succeeds with no error
AND: Bytes are queued for KISS parsing
```

### Test 3: RX Notification

```
GIVEN: iPhone connected to bridge
AND: Notifications enabled on RX characteristic
WHEN: KISS frame arrives from TNC
THEN: Bridge sends notification on RX characteristic
AND: Notification contains frame data (fragmented if > MTU-3)
```

### Test 4: MTU Negotiation

```
GIVEN: Bridge is advertising
WHEN: iPhone connects and requests MTU of 185
THEN: Bridge accepts MTU 185
AND: Subsequent notifications limited to 182 bytes
```

### Test 5: Buffer Overflow

```
GIVEN: iPhone connected to bridge
AND: Classic connection is DOWN
AND: Buffer has accumulated 4KB of data
WHEN: iPhone writes more data
THEN: Oldest data is dropped
AND: Warning is logged
```

## Sequence Diagram: Data Write

```
iPhone                          Bridge                      TNC
   │                              │                          │
   │─────Write TX (KISS frame)───►│                          │
   │                              │──parse KISS──►           │
   │                              │                          │
   │◄────Write Response OK────────│                          │
   │                              │───────SPP Data──────────►│
   │                              │                          │
```

## Sequence Diagram: Data Receive

```
iPhone                          Bridge                      TNC
   │                              │                          │
   │                              │◄──────SPP Data───────────│
   │                              │──parse KISS──►           │
   │                              │                          │
   │◄────Notification (RX)────────│                          │
   │                              │                          │
```
