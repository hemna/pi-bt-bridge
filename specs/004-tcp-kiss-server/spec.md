# Feature Specification: TCP KISS Server

**Feature Branch**: `004-tcp-kiss-server`  
**Created**: 2026-03-06  
**Status**: Draft  
**Input**: User description: "Add a TCP KISS server to pi-bt-bridge that allows traditional KISS-over-TCP clients (APRSIS32, Xastir, PinPoint APRS, etc.) to connect to the bridge alongside the existing BLE connection. All clients share the same TNC radio - RX frames from the TNC are broadcast to all connected clients (BLE + TCP), and TX frames from any client are forwarded to the TNC."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect a KISS-over-TCP Client to the Bridge (Priority: P1)

As a ham radio operator running APRSIS32, Xastir, or PinPoint APRS on a laptop/desktop on my LAN, I want to connect to the Pi bridge via TCP KISS so I can use my TNC radio without a direct Bluetooth connection from my computer.

**Why this priority**: This is the core value proposition - enabling any KISS-over-TCP capable application to use the bridge, not just BLE-capable iOS apps.

**Independent Test**: Start the bridge with a TNC connected, connect a KISS-over-TCP client (e.g., using `nc` or a real APRS app) to port 8001, send a KISS frame, and verify it reaches the TNC. Receive a frame from the TNC and verify it arrives at the TCP client.

**Acceptance Scenarios**:

1. **Given** the bridge is running with TCP KISS enabled on port 8001, **When** a KISS-over-TCP client connects, **Then** the connection is accepted and logged.
2. **Given** a TCP client is connected, **When** the TNC radio receives a packet, **Then** the KISS frame is delivered to the TCP client.
3. **Given** a TCP client is connected, **When** the client sends a KISS frame, **Then** the frame is forwarded to the TNC radio via Classic Bluetooth SPP.
4. **Given** a TCP client disconnects, **When** the connection closes, **Then** the bridge logs the disconnection and continues operating normally.

---

### User Story 2 - Multi-Client Fan-Out (Priority: P1)

As a ham radio operator, I want multiple clients (BLE phone + TCP laptop, or multiple TCP clients) to all receive packets from the TNC simultaneously, so I can run different APRS applications concurrently.

**Why this priority**: Multi-client support is fundamental to the value of a shared bridge. Without it, the TCP server would just be a 1:1 replacement for BLE.

**Independent Test**: Connect an iOS app via BLE and a laptop via TCP KISS simultaneously. Send a packet from a nearby radio. Verify both clients receive the KISS frame.

**Acceptance Scenarios**:

1. **Given** a BLE client and a TCP client are both connected, **When** the TNC receives a packet, **Then** both clients receive the KISS frame.
2. **Given** two TCP clients are connected, **When** the TNC receives a packet, **Then** both TCP clients receive the KISS frame.
3. **Given** multiple clients are connected, **When** any client sends a KISS frame, **Then** it is forwarded to the TNC.
4. **Given** one TCP client disconnects, **When** the TNC receives a packet, **Then** remaining clients still receive frames normally.

---

### User Story 3 - TCP KISS Configuration (Priority: P2)

As a system administrator, I want to configure the TCP KISS server port, enable/disable it, and set a maximum client limit, so I can control resource usage on the Pi Zero 2 W.

**Why this priority**: Configurability is important for deployment flexibility but has sensible defaults that work out of the box.

**Independent Test**: Set `tcp_kiss_port` to 9001 in config.json, restart, and verify the server listens on port 9001.

**Acceptance Scenarios**:

1. **Given** `tcp_kiss_enabled` is true in config, **When** the daemon starts, **Then** the TCP KISS server listens on the configured port.
2. **Given** `tcp_kiss_enabled` is false in config, **When** the daemon starts, **Then** no TCP server is started.
3. **Given** `tcp_kiss_max_clients` is 3, **When** a 4th client tries to connect, **Then** the connection is rejected with a log message.
4. **Given** default config (no TCP settings), **When** the daemon starts, **Then** TCP KISS is enabled on port 8001 with max 5 clients.

---

### User Story 4 - TCP Client Visibility in Web UI (Priority: P3)

As a user, I want to see connected TCP KISS clients in the web status page, so I know who is using the bridge.

**Why this priority**: Informational enhancement for operational awareness, not required for core TCP functionality.

**Independent Test**: Connect a TCP client, view the status page, verify the client appears with its IP address.

**Acceptance Scenarios**:

1. **Given** two TCP clients are connected, **When** I view the status page, **Then** I see a TCP KISS section showing "2 clients connected" with their IP addresses.
2. **Given** no TCP clients are connected, **When** I view the status page, **Then** I see "TCP KISS: Listening on port 8001 (0 clients)".
3. **Given** TCP KISS is disabled in config, **When** I view the status page, **Then** the TCP section shows "Disabled" or is hidden.

---

### Edge Cases

- What happens when a TCP client sends malformed (non-KISS) data? (Discard invalid bytes, log warning, do not disconnect)
- What happens when the TNC disconnects while TCP clients are connected? (TCP clients stay connected, frames are queued or dropped with warning)
- What happens when the Pi runs out of memory with many clients? (Max client limit prevents this)
- What happens with very slow TCP clients that can't keep up with RX rate? (Per-client send buffer with backpressure, drop frames if buffer full)
- What happens when the bridge restarts? (TCP clients disconnect, can reconnect automatically if their apps support it)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a TCP server that accepts KISS-over-TCP connections on a configurable port (default 8001)
- **FR-002**: System MUST support multiple simultaneous TCP KISS clients (configurable max, default 5)
- **FR-003**: System MUST parse KISS frames from TCP clients and forward them to the TNC via Classic Bluetooth SPP
- **FR-004**: System MUST broadcast KISS frames received from the TNC to ALL connected clients (BLE + TCP)
- **FR-005**: System MUST accept TX frames from ANY connected client (BLE or TCP) and forward to TNC
- **FR-006**: System MUST track per-client statistics: remote address, connection time, bytes TX/RX
- **FR-007**: System MUST gracefully handle client connect/disconnect without affecting other clients
- **FR-008**: System MUST be configurable via `config.json` (enabled, port, max clients)
- **FR-009**: Web status page MUST show TCP KISS server status and connected clients
- **FR-010**: System MUST log all TCP client connections and disconnections

### Key Entities

- **TcpKissConnection**: Represents a single connected TCP KISS client with address, connection time, bytes transferred
- **TcpKissService**: Async TCP server managing client connections, KISS parsing, and data broadcast

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A standard KISS-over-TCP client can connect and exchange KISS frames with the TNC within 1 second
- **SC-002**: Multiple clients (BLE + TCP) simultaneously receive all RX frames from the TNC with no data loss
- **SC-003**: TCP KISS server adds less than 5MB memory overhead on Pi Zero 2 W
- **SC-004**: End-to-end latency for TCP→TNC→TCP round trip is under 100ms on LAN
- **SC-005**: Bridge continues operating normally when TCP clients connect/disconnect
