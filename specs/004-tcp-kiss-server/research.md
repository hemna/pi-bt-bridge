# Research: TCP KISS Server

**Feature**: 004-tcp-kiss-server  
**Date**: 2026-03-06

## Research Topics

### 1. KISS-over-TCP Protocol Convention

**Decision**: Use raw TCP with KISS framing (0xC0 delimiters), no additional framing layer.

**Rationale**: KISS-over-TCP is a de facto standard in ham radio software. The protocol is simply KISS frames (with standard 0xC0 FEND delimiters) sent as a raw TCP byte stream. There is no additional length prefix, header, or handshake. This is how APRSIS32, Xastir, Direwolf, and virtually all APRS/packet software implement KISS TCP. The default port convention is 8001 (used by Direwolf, KISSUtil, and others).

**Alternatives considered**:
- **AGW/AGWPE protocol**: More complex, proprietary framing. Rejected - KISS is simpler and more widely supported.
- **AX.25-over-TCP (port 93)**: Would require AX.25 extraction from KISS. Rejected - adds complexity, KISS is the standard for TNC bridging.
- **WebSocket KISS**: Would allow browser-based clients. Rejected for now - no existing ham software uses this. Could be added later.

### 2. asyncio TCP Server Approach

**Decision**: Use `asyncio.start_server()` with per-client coroutine handlers.

**Rationale**: The existing codebase is fully async (asyncio event loop). `asyncio.start_server()` is the standard asyncio pattern for TCP servers, handles backpressure via `StreamWriter.drain()`, and integrates naturally with the existing event loop. Each client gets a dedicated `_handle_client()` coroutine that reads from `StreamReader` and forwards complete KISS frames to the bridge.

**Alternatives considered**:
- **socket + asyncio.open_connection**: Lower level, more manual buffering. Rejected - `start_server` handles this.
- **aiohttp WebSocket**: Would require clients to use WebSocket. Rejected - standard KISS clients expect raw TCP.
- **Separate thread pool**: Would complicate thread safety. Rejected - asyncio is already the concurrency model.

### 3. Fan-Out Architecture (Multi-Client Broadcast)

**Decision**: Modify `BridgeService` to accept a list of "data sinks" for RX frames, rather than hardcoding BLE as the only destination.

**Rationale**: Currently `_forward_to_ble_kiss()` sends only to BLE. For multi-client support, the bridge needs to fan out to BLE + all TCP clients. The cleanest approach is:

1. `TcpKissService` registers a data callback on `BridgeService` (same pattern as BLE/Classic)
2. `BridgeService._forward_to_ble_kiss()` is renamed/extended to `_forward_to_clients()` which calls both `self._ble.send_data()` and `self._tcp.broadcast()` if available
3. `TcpKissService.broadcast(data)` iterates over connected clients and writes to each

This preserves the existing callback architecture and keeps the TCP service decoupled from BLE.

**Alternatives considered**:
- **Pub/sub event bus**: Too complex for 2-3 subscribers. Rejected.
- **TCP service polls bridge for data**: Violates push model. Rejected.
- **TCP service wraps BLE service**: Creates tight coupling. Rejected.

### 4. KISS Frame Reassembly on TCP

**Decision**: Use the existing `KISSParser` class for TCP frame reassembly.

**Rationale**: TCP is a stream protocol, so KISS frames may arrive fragmented across multiple `read()` calls or multiple frames may arrive in a single `read()`. The existing `KISSParser` already handles this exact problem - it's a byte-by-byte state machine that accumulates bytes between 0xC0 delimiters and returns complete `KISSFrame` objects. Each TCP client gets its own `KISSParser` instance.

**Alternatives considered**:
- **Custom TCP KISS parser**: Unnecessary duplication. Rejected.
- **Assume one frame per read**: Incorrect for TCP streams. Rejected.

### 5. Client Connection Limits and Backpressure

**Decision**: Hard limit of configurable max clients (default 5), per-client write with asyncio backpressure via `drain()`, drop-on-error for unresponsive clients.

**Rationale**: Pi Zero 2 W has 512MB RAM and limited CPU. Each TCP client adds a coroutine, StreamReader/Writer buffers (~64KB each), and a KISSParser instance. With 5 clients that's ~1-2MB overhead, well within budget. For slow clients, `StreamWriter.write()` + `drain()` provides natural backpressure. If a client's write raises an exception (broken pipe, timeout), that client is disconnected without affecting others.

**Alternatives considered**:
- **Unlimited clients**: Risk OOM on Pi Zero. Rejected.
- **Queued broadcast with drop policy**: Over-engineered for 5 clients. Rejected.

### 6. TCP Client State in BridgeState

**Decision**: Add `tcp_clients: list[TcpKissConnection]` to `BridgeState` and a `TcpKissConnection` dataclass to track per-client state.

**Rationale**: Follows the existing pattern where `BLEConnection` and `ClassicConnection` are dataclasses stored on `BridgeState`. The web service reads these for status display. `TcpKissConnection` tracks: remote address (ip:port), connected_at timestamp, bytes_rx, bytes_tx.

**Alternatives considered**:
- **Single aggregate counter**: Loses per-client visibility. Rejected.
- **Separate TCP state object**: Inconsistent with existing BLE/Classic pattern. Rejected.

## Resolved Clarifications

All technical context items were clear from the feature spec and existing codebase analysis. No NEEDS CLARIFICATION items were identified.

| Item | Resolution |
|------|-----------|
| Default port | 8001 (Direwolf/KISS convention) |
| Authentication | None needed (standard for LAN KISS servers) |
| Max clients | 5 (configurable), suitable for Pi Zero 2 W resource constraints |
| Protocol | Raw KISS over TCP (no additional framing) |
| BLE coexistence | BLE and TCP are equal peers; both receive all RX, both can TX |
| HDLC support | TCP clients always use KISS framing; HDLC translation happens at the Classic/TNC edge only |
