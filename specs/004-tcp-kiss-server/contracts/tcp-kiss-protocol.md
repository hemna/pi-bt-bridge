# Contract: TCP KISS Protocol

**Feature**: 004-tcp-kiss-server  
**Type**: Network protocol (TCP)

## Overview

The TCP KISS server exposes a standard KISS-over-TCP interface on a configurable port (default 8001). This is a de facto industry standard used by Direwolf, APRSIS32, Xastir, PinPoint APRS, and other ham radio software.

## Protocol Specification

### Transport

- **Protocol**: TCP
- **Default Port**: 8001
- **Bind Address**: 0.0.0.0 (configurable)
- **Encoding**: Raw binary (no text encoding)
- **Framing**: KISS protocol (0xC0 delimiters)
- **Handshake**: None (connect and immediately send/receive KISS frames)
- **Authentication**: None

### KISS Frame Format (per AX.25 KISS TNC spec)

```
┌──────┬──────────┬─────────────────┬──────┐
│ FEND │ CMD_BYTE │    DATA ...     │ FEND │
│ 0xC0 │ port|cmd │ (0-256+ bytes)  │ 0xC0 │
└──────┴──────────┴─────────────────┴──────┘
```

- **FEND** (0xC0): Frame delimiter
- **CMD_BYTE**: Upper nibble = port (0-15), lower nibble = command (0=data, 1-6=TNC params)
- **DATA**: AX.25 frame payload (for data frames) or parameter value
- **KISS escaping**: 0xC0 in data → 0xDB 0xDC, 0xDB in data → 0xDB 0xDD

### Connection Lifecycle

```
Client                          Server
  │                               │
  │──── TCP SYN ─────────────────▶│  Connection attempt
  │◀─── TCP SYN-ACK ─────────────│
  │──── TCP ACK ─────────────────▶│  Connected (logged)
  │                               │
  │◀─── KISS frame (RX from TNC) │  Server pushes received frames
  │──── KISS frame (TX to TNC) ──▶│  Client sends frames to transmit
  │     ...                       │
  │                               │
  │──── TCP FIN ─────────────────▶│  Client disconnect (logged)
  │◀─── TCP FIN-ACK ─────────────│
```

### Rejection (max clients exceeded)

```
Client                          Server
  │                               │
  │──── TCP SYN ─────────────────▶│
  │◀─── TCP SYN-ACK ─────────────│
  │──── TCP ACK ─────────────────▶│  Connected
  │◀─── TCP FIN ──────────────────│  Immediately closed (logged as rejected)
```

## Contract Tests

The following properties MUST be verified by contract tests:

### CT-001: Frame Integrity
- A complete KISS frame sent by a TCP client MUST arrive at the bridge as an identical `KISSFrame` object
- A KISS frame from the TNC MUST arrive at the TCP client as identical bytes

### CT-002: Frame Reassembly
- A KISS frame split across multiple TCP segments MUST be reassembled correctly
- Multiple KISS frames in a single TCP segment MUST be parsed as separate frames

### CT-003: KISS Escaping
- 0xC0 bytes within frame data MUST be escaped as 0xDB 0xDC
- 0xDB bytes within frame data MUST be escaped as 0xDB 0xDD
- Escaped sequences MUST be unescaped correctly on receive

### CT-004: Multi-Client Broadcast
- A KISS frame from the TNC MUST be delivered to ALL connected TCP clients
- A KISS frame from the TNC MUST also be delivered to the BLE client (if connected)

### CT-005: Client Isolation
- One client disconnecting MUST NOT affect other clients
- One client sending invalid data MUST NOT affect other clients
- Data from one TCP client MUST NOT be echoed back to that client (only forwarded to TNC)

### CT-006: Connection Limit
- When `max_clients` is reached, new connections MUST be rejected
- After a client disconnects, a new client MUST be able to connect
