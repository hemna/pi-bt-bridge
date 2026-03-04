# Research: Bluetooth LE to Classic Bridge Daemon

**Feature**: 001-bt-bridge-daemon  
**Date**: 2026-03-04  
**Status**: Complete

## 1. Bluetooth Stack for Raspberry Pi Zero 2 W

### Decision: Python with `bless` (BLE GATT) + `dbus-python` (BT Classic SPP)

### Rationale

1. **Bless** is the only actively maintained Python library for BLE GATT server (peripheral mode). It uses BlueZ D-Bus API and complements Bleak.
2. **PyBluez is deprecated** - GitHub repo explicitly states "not under development".
3. For BT Classic SPP, `dbus-python` with BlueZ Profile1 API is the most reliable approach.
4. Python is suitable for <100ms latency - Bluetooth radio latency dominates (15-50ms per operation), not CPU overhead.

### Alternatives Considered

| Library | BLE Peripheral | BT Classic SPP | Status | Verdict |
|---------|----------------|----------------|--------|---------|
| Bleak | No (client only) | No | Active | Rejected - no server support |
| Bless | **Yes** | No | Active | **Selected for BLE** |
| PyBluez | No | Yes (RFCOMM) | Deprecated | Rejected - unmaintained |
| dbus-python | Yes | **Yes** | Active | **Selected for SPP** |
| BlueR (Rust) | Yes | Yes | Active | Rejected - higher dev cost |

### Key Technical Details

- **Pi Zero 2 W Hardware**: BCM43436S supports Bluetooth 4.2 (BLE + BR/EDR dual mode)
- **BlueZ Config**: `ControllerMode=dual` enables simultaneous BLE + Classic (default)
- **Concurrent Connections**: Practical limit ~5-7, sufficient for 1 iPhone + 1 TNC
- **BLE MTU**: Default 20 bytes (BLE 4.x), up to 512 bytes with MTU negotiation

---

## 2. BLE Serial Service UUIDs

### Decision: Use Nordic UART Service (NUS)

### UUIDs

```
Service:        6E400001-B5A3-F393-E0A9-E50E24DCCA9E
TX Characteristic: 6E400002-B5A3-F393-E0A9-E50E24DCCA9E  (Write/WriteNoResponse)
RX Characteristic: 6E400003-B5A3-F393-E0A9-E50E24DCCA9E  (Read/Notify)
```

### Rationale

1. **Industry standard** for BLE serial communication (de-facto, no official BLE serial profile)
2. **iOS app compatibility**: Recognized by nRF Connect, LightBlue, Bluefruit LE Connect
3. **128-bit vendor UUID**: Won't conflict with Bluetooth SIG reserved range

### Alternatives Considered

- Custom UUIDs: Rejected - would require iOS app modification
- Standard GATT services: No serial equivalent exists in Bluetooth SIG specs

---

## 3. KISS TNC Protocol

### Protocol Summary

**Frame Format**: `[FEND] [Command Byte] [Data...] [FEND]`

| Byte | Name | Description |
|------|------|-------------|
| `0xC0` | FEND | Frame delimiter (start/end) |
| `0xDB` | FESC | Escape character |
| `0xDC` | TFEND | Escaped FEND (0xDB 0xDC → 0xC0) |
| `0xDD` | TFESC | Escaped FESC (0xDB 0xDD → 0xDB) |

**Command Bytes** (low nibble = command, high nibble = port 0-15):

| Command | Name | Description |
|---------|------|-------------|
| `0x00` | Data Frame | Payload to transmit |
| `0x01` | TX Delay | Keyup delay (10ms units) |
| `0x02` | Persistence | CSMA P value |
| `0x03` | Slot Time | CSMA slot interval |
| `0xFF` | Return | Exit KISS mode |

### Implementation Notes

1. **Back-to-back FENDs**: Discard all but last (not empty frames)
2. **Invalid escapes**: Ignore bad byte after FESC, continue assembly
3. **Maximum frame size**: No protocol limit; recommend 1024 bytes minimum buffer
4. **No CRC on KISS link**: HDLC CRC handled at RF layer

### Existing Libraries

- **kiss3** (recommended): Active, Python 3.6+, pip installable
- **kiss**: Original library, archived 2024

### Test Vectors

```python
# Basic data frame
b'\xC0\x00TEST\xC0'  # Send "TEST" on port 0

# Escaped FEND in data
b'\xC0\x00\xDB\xDC\xC0'  # Data contains 0xC0

# Multiple FENDs (synchronization)
b'\xC0\xC0\xC0\x00TEST\xC0'  # Produces single "TEST" frame
```

---

## 4. Language and Runtime

### Decision: Python 3.11+ with asyncio

### Rationale

1. **Latency analysis**:
   - BLE GATT operation: 15-50ms (radio-dominated)
   - Python overhead: <2ms
   - Total well under 100ms requirement

2. **asyncio benefits**:
   - Bless uses asyncio natively
   - Non-blocking I/O for both connections
   - Simpler concurrency than threads

3. **Development velocity**: Faster prototyping, better debugging

### Alternatives Considered

- **Rust (BlueR)**: Better performance but 3-4x development time
- **C (BlueZ API)**: Maximum performance but high complexity
- **Go**: Limited Bluetooth library support

---

## 5. Architecture Decision

### Selected Architecture

```
┌─────────────────────────────────────────────────┐
│              Python Daemon (asyncio)            │
├─────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌───────────────────┐  │
│  │  BLEService     │    │  ClassicService   │  │
│  │  (bless)        │    │  (dbus-python)    │  │
│  │  - GATT Server  │    │  - SPP Profile    │  │
│  │  - NUS UUIDs    │    │  - RFCOMM         │  │
│  └────────┬────────┘    └─────────┬─────────┘  │
│           │                       │             │
│           └───────────┬───────────┘             │
│                       │                         │
│              ┌────────▼────────┐               │
│              │  KISSBridge     │               │
│              │  - Frame parse  │               │
│              │  - Bidirectional│               │
│              └────────┬────────┘               │
│                       │                         │
│              ┌────────▼────────┐               │
│              │  BlueZ D-Bus    │               │
│              └─────────────────┘               │
└─────────────────────────────────────────────────┘
```

---

## 6. Dependencies

### Required Packages

```
# Python packages (pip)
bless>=0.3.0         # BLE GATT server
dbus-python>=1.3.2   # D-Bus bindings for SPP
PyGObject>=3.42.0    # GLib main loop integration

# System packages (apt)
bluez>=5.55          # BlueZ stack
python3-dbus         # D-Bus bindings
python3-gi           # GObject introspection
```

### Optional

```
kiss3>=8.0.0         # KISS frame handling (or implement minimal parser)
```

---

## 7. Platform Configuration

### BlueZ Configuration (`/etc/bluetooth/main.conf`)

```ini
[General]
ControllerMode=dual      # BLE + Classic (default)
Name=PiBTBridge
DiscoverableTimeout=0    # Always discoverable for pairing

[Policy]
AutoEnable=true
```

### Systemd Service

```ini
[Unit]
Description=Bluetooth KISS Bridge Daemon
After=bluetooth.target
Requires=bluetooth.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/bt-bridge/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Summary of Decisions

| Aspect | Decision |
|--------|----------|
| Language | Python 3.11+ with asyncio |
| BLE Library | bless (GATT server) |
| Classic Library | dbus-python (Profile1 API) |
| BLE Service | Nordic UART Service UUIDs |
| KISS Handling | Custom parser or kiss3 library |
| Configuration | JSON file in /etc/bt-bridge/ |
| Service Manager | systemd |
