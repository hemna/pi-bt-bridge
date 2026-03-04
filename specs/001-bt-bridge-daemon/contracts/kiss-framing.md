# Contract: KISS TNC Protocol Framing

**Feature**: 001-bt-bridge-daemon  
**Protocol**: KISS TNC (Keep It Simple, Stupid)  
**Reference**: ARRL/TAPR AX.25 Link-Layer Protocol Specification

## Overview

KISS is a host-to-TNC protocol that frames data for transmission over amateur
radio links. The bridge transparently forwards KISS frames between the iPhone
(BLE) and TNC (Classic) without interpreting the payload.

## Frame Format

```
┌──────┬─────────────┬────────────────┬──────┐
│ FEND │ Command Byte│     Data       │ FEND │
│ 0xC0 │   1 byte    │  0-N bytes     │ 0xC0 │
└──────┴─────────────┴────────────────┴──────┘
```

### Special Characters

| Byte | Name | Description |
|------|------|-------------|
| `0xC0` | FEND | Frame End - marks start AND end of frame |
| `0xDB` | FESC | Frame Escape - escapes special characters in data |
| `0xDC` | TFEND | Transposed Frame End - represents 0xC0 in data |
| `0xDD` | TFESC | Transposed Frame Escape - represents 0xDB in data |

### Escape Sequences

To transmit a special character within frame data:

| To Send | Transmit | Description |
|---------|----------|-------------|
| `0xC0` | `0xDB 0xDC` | FESC + TFEND |
| `0xDB` | `0xDB 0xDD` | FESC + TFESC |

### Command Byte

```
┌───────────┬───────────┐
│ Port (4b) │ Cmd (4b)  │
│  High     │  Low      │
└───────────┴───────────┘
```

| Command | Value | Direction | Description |
|---------|-------|-----------|-------------|
| Data Frame | `0x00` | Both | AX.25 frame data |
| TX Delay | `0x01` | To TNC | Keyup delay (10ms units) |
| Persistence | `0x02` | To TNC | CSMA P value (0-255) |
| Slot Time | `0x03` | To TNC | CSMA slot interval (10ms units) |
| TX Tail | `0x04` | To TNC | Hold TX after frame (10ms units) |
| Full Duplex | `0x05` | To TNC | 0=half, non-zero=full |
| Set Hardware | `0x06` | To TNC | TNC-specific config |
| Return | `0xFF` | To TNC | Exit KISS mode |

**Port Number**: High nibble allows addressing multi-port TNCs (0-15).

## Parsing Rules

### Frame Boundary Detection

1. Leading FEND (`0xC0`) marks frame start
2. Trailing FEND (`0xC0`) marks frame end
3. Multiple consecutive FENDs do NOT produce empty frames
4. Leading FENDs flush garbage from previous errors

### Escape Handling

1. When FESC (`0xDB`) is received, enter escape mode
2. In escape mode:
   - TFEND (`0xDC`) → emit `0xC0`, exit escape mode
   - TFESC (`0xDD`) → emit `0xDB`, exit escape mode
   - Any other byte → protocol error, discard byte, exit escape mode
3. Two consecutive FESCs indicate abort; discard frame

### Maximum Frame Size

- **Protocol Limit**: None (limited by TNC memory)
- **Recommended Minimum Buffer**: 1024 bytes
- **AX.25 Typical Max**: 330 bytes (256 data + headers)
- **Bridge Buffer**: 4096 bytes (handles oversized frames)

## Bridge Behavior

### Transparent Forwarding

The bridge does NOT interpret KISS frame contents. It:

1. Parses frame boundaries (FEND delimiters)
2. Handles escape sequences
3. Forwards complete frames to the other connection
4. Preserves command bytes and port numbers

### Incomplete Frame Handling

| Condition | Behavior |
|-----------|----------|
| Partial frame at disconnect | Discard, log warning |
| Frame exceeds buffer | Discard, log error |
| Invalid escape sequence | Discard bad byte, continue parsing |
| Multiple FENDs | Treat as single delimiter |

### Timing

| Metric | Requirement |
|--------|-------------|
| Frame forwarding latency | <100ms (end-to-end) |
| Parse time per frame | <1ms |
| Inter-frame gap | None required |

## Contract Test Cases

### Test 1: Simple Data Frame

```
INPUT:  0xC0 0x00 0x48 0x45 0x4C 0x4C 0x4F 0xC0
EXPECT: Frame with port=0, cmd=DATA_FRAME, data="HELLO"
```

### Test 2: Escaped FEND in Data

```
INPUT:  0xC0 0x00 0x41 0xDB 0xDC 0x42 0xC0
EXPECT: Frame with data = [0x41, 0xC0, 0x42] ("A" + FEND + "B")
```

### Test 3: Escaped FESC in Data

```
INPUT:  0xC0 0x00 0xDB 0xDD 0xC0
EXPECT: Frame with data = [0xDB]
```

### Test 4: Multiple FENDs (Sync)

```
INPUT:  0xC0 0xC0 0xC0 0x00 0x41 0xC0
EXPECT: Single frame with data = [0x41] ("A")
```

### Test 5: Port Number Extraction

```
INPUT:  0xC0 0x50 0x44 0x41 0x54 0x41 0xC0
EXPECT: Frame with port=5, cmd=DATA_FRAME, data="DATA"
        (0x50 = 0101 0000, high nibble=5, low nibble=0)
```

### Test 6: TX Delay Command

```
INPUT:  0xC0 0x01 0x1E 0xC0
EXPECT: Frame with port=0, cmd=TX_DELAY, data=[0x1E] (30 * 10ms = 300ms)
```

### Test 7: Return Command (Exit KISS)

```
INPUT:  0xC0 0xFF 0xC0
EXPECT: Frame with cmd=RETURN, data=[]
NOTE:   Bridge forwards without interpretation
```

### Test 8: Invalid Escape Sequence

```
INPUT:  0xC0 0x00 0x41 0xDB 0x42 0x43 0xC0
EXPECT: Frame with data = [0x41, 0x43] (0x42 discarded as invalid escape)
        Log warning about invalid escape sequence
```

### Test 9: Back-to-Back Frames

```
INPUT:  0xC0 0x00 0x41 0xC0 0xC0 0x00 0x42 0xC0
EXPECT: Two frames:
        Frame 1: data = [0x41] ("A")
        Frame 2: data = [0x42] ("B")
```

### Test 10: Frame Too Large

```
INPUT:  0xC0 0x00 [5000 bytes] 0xC0
EXPECT: Frame discarded
        Log error "Frame exceeds maximum size (5000 > 4096)"
```

## Encoding (Bridge → Output)

When forwarding a frame, the bridge re-encodes:

```python
def encode_frame(frame: KISSFrame) -> bytes:
    output = bytearray([FEND])
    
    # Command byte: (port << 4) | command
    cmd_byte = (frame.port << 4) | frame.command.value
    output.append(cmd_byte)
    
    # Escape data
    for byte in frame.data:
        if byte == FEND:
            output.extend([FESC, TFEND])
        elif byte == FESC:
            output.extend([FESC, TFESC])
        else:
            output.append(byte)
    
    output.append(FEND)
    return bytes(output)
```

## Sequence Diagram: Frame Flow

```
iPhone App          Bridge              TNC Radio
    │                 │                    │
    │──KISS Frame────►│                    │
    │  (BLE Write)    │                    │
    │                 │──parse──►          │
    │                 │                    │
    │                 │───KISS Frame──────►│
    │                 │   (SPP Write)      │
    │                 │                    │
    │                 │◄──KISS Frame───────│
    │                 │   (SPP Read)       │
    │                 │                    │
    │                 │──parse──►          │
    │                 │                    │
    │◄──KISS Frame────│                    │
    │  (BLE Notify)   │                    │
    │                 │                    │
```

## Constants Reference

```python
# Frame delimiters
FEND  = 0xC0
FESC  = 0xDB
TFEND = 0xDC
TFESC = 0xDD

# Commands
DATA_FRAME  = 0x00
TX_DELAY    = 0x01
PERSISTENCE = 0x02
SLOT_TIME   = 0x03
TX_TAIL     = 0x04
FULL_DUPLEX = 0x05
SET_HARDWARE = 0x06
RETURN      = 0xFF

# Limits
MAX_FRAME_SIZE = 4096
MAX_PORT = 15
```
