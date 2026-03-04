# Feature Specification: Bluetooth LE to Classic Bridge Daemon

**Feature Branch**: `001-bt-bridge-daemon`  
**Created**: 2026-03-04  
**Status**: Draft  
**Input**: User description: "Create a daemon/app that will operate as a Bluetooth LE to Bluetooth Classic bridge for the Raspberry Pi zero 2 w. The daemon will have to manage pairing to both an iPhone over BTLE and a ham radio over BT Classic. The app will then bridge all serial KISS traffic from one end to the other so an iPhone can have serial KISS TNC Device support for iOS apps."

## User Scenarios & Testing

### User Story 1 - Initial Bridge Setup and Pairing (Priority: P1)

As a ham radio operator, I want to pair my iPhone with the Pi bridge over BLE and pair the bridge with my Bluetooth-enabled TNC radio so that I can establish a communication path between my iPhone apps and the radio.

**Why this priority**: This is the foundational capability - without successful pairing on both ends, no data can flow. This must work first.

**Independent Test**: Can be tested by running the daemon, pairing an iPhone via BLE, pairing a BT Classic device (TNC or simulator), and verifying both connections show "connected" status.

**Acceptance Scenarios**:

1. **Given** the daemon is running and advertising BLE, **When** an iPhone initiates BLE pairing, **Then** the daemon accepts the pairing and establishes a BLE connection with GATT serial service.
2. **Given** the daemon is running, **When** configured with a target BT Classic device address, **Then** the daemon connects to the ham radio TNC via SPP profile.
3. **Given** both BLE and Classic connections are established, **When** the user queries status, **Then** both connections show "connected" state with device identifiers.

---

### User Story 2 - KISS Frame Bridging (Priority: P1)

As a ham radio operator using an iOS packet radio app, I want KISS frames sent from my iPhone to be transparently forwarded to the TNC and KISS frames from the TNC to be forwarded to my iPhone so that my iOS app can communicate with the radio as if directly connected.

**Why this priority**: This is the core value proposition - actual data transfer. Without this, the bridge has no utility.

**Independent Test**: Can be tested by sending KISS frames from a mock BLE client, verifying they arrive at a mock SPP endpoint, and vice versa.

**Acceptance Scenarios**:

1. **Given** both connections are established, **When** the iPhone sends a KISS frame over BLE, **Then** the daemon forwards the complete frame to the BT Classic TNC within 100ms.
2. **Given** both connections are established, **When** the TNC sends a KISS frame over BT Classic, **Then** the daemon forwards the complete frame to the iPhone over BLE within 100ms.
3. **Given** a partial KISS frame is received, **When** more data arrives completing the frame, **Then** only the complete frame is forwarded (no partial frame transmission).
4. **Given** multiple KISS frames arrive in a single BLE packet, **When** processing occurs, **Then** each frame is individually forwarded maintaining frame boundaries.

---

### User Story 3 - Connection Recovery and Resilience (Priority: P2)

As a ham radio operator in the field, I want the bridge to automatically attempt reconnection if either Bluetooth link drops so that I don't have to manually restart the daemon during temporary signal loss.

**Why this priority**: Field conditions are unreliable. Auto-recovery significantly improves usability but requires basic connectivity (P1) first.

**Independent Test**: Can be tested by simulating a BLE disconnect, verifying reconnection attempts, and confirming data flow resumes after reconnection.

**Acceptance Scenarios**:

1. **Given** the BLE connection drops unexpectedly, **When** the iPhone is still in range, **Then** the daemon re-advertises and accepts reconnection within 10 seconds.
2. **Given** the BT Classic connection drops, **When** the TNC is still available, **Then** the daemon attempts reconnection with exponential backoff (1s, 2s, 4s, max 30s).
3. **Given** one link is down, **When** data arrives on the active link, **Then** data is buffered (up to 4KB) until the other link recovers or buffer is full.
4. **Given** buffer is full and link is still down, **When** more data arrives, **Then** oldest data is dropped and warning is logged.

---

### User Story 4 - Status Monitoring and Logging (Priority: P2)

As a ham radio operator, I want to monitor the bridge status and view logs so that I can diagnose connection issues and verify the bridge is operating correctly.

**Why this priority**: Essential for troubleshooting but not required for basic operation.

**Independent Test**: Can be tested by querying the daemon's status interface and verifying accurate reflection of connection states and statistics.

**Acceptance Scenarios**:

1. **Given** the daemon is running, **When** queried via status command/API, **Then** response includes: BLE state, Classic state, bytes transferred, uptime, error counts.
2. **Given** logging is enabled, **When** a KISS frame is bridged, **Then** log entry includes timestamp, direction, frame size (not content for privacy).
3. **Given** an error occurs, **When** logged, **Then** log includes error type, affected connection, and suggested remediation.

---

### User Story 5 - Daemon Lifecycle Management (Priority: P3)

As a system administrator, I want to run the bridge as a systemd service that starts on boot and can be controlled via standard service commands so that the bridge operates reliably as infrastructure.

**Why this priority**: Important for production deployment but can be manually started during development.

**Independent Test**: Can be tested by installing the systemd unit, rebooting, and verifying the daemon starts and accepts connections.

**Acceptance Scenarios**:

1. **Given** the daemon is installed, **When** systemctl start is executed, **Then** daemon starts within 5 seconds and begins advertising.
2. **Given** the daemon is running, **When** systemctl stop is executed, **Then** daemon gracefully disconnects both links and exits cleanly.
3. **Given** the Pi reboots, **When** boot completes, **Then** daemon auto-starts if enabled.
4. **Given** the daemon crashes, **When** systemd detects exit, **Then** daemon is restarted automatically after 5 second delay.

---

### Edge Cases

- What happens when iPhone disconnects during active KISS frame transmission? (Discard incomplete, log warning)
- How does the system handle malformed KISS frames? (Pass through transparently - TNC will reject)
- What if two iPhones try to connect simultaneously? (Accept first, reject second with busy status)
- What happens if BT Classic device requires PIN pairing? (Support configurable PIN, default 0000/1234)
- How to handle BLE MTU negotiation? (Request max MTU, handle fragmentation transparently)

## Requirements

### Functional Requirements

- **FR-001**: System MUST advertise a BLE GATT service that emulates a serial port (Nordic UART Service or custom UUID).
- **FR-002**: System MUST connect to a BT Classic device using SPP (Serial Port Profile).
- **FR-003**: System MUST parse KISS frame boundaries correctly (FEND framing, escape sequences).
- **FR-004**: System MUST bridge data bidirectionally between BLE and Classic connections.
- **FR-005**: System MUST persist configuration (target BT Classic address, PIN, logging level) across restarts.
- **FR-006**: System MUST provide connection status via queryable interface (D-Bus, socket, or file).
- **FR-007**: System MUST run as a systemd-compatible daemon on Raspberry Pi OS.
- **FR-008**: System MUST handle concurrent read/write operations without data corruption.

### Non-Functional Requirements

- **NFR-001**: Latency MUST NOT exceed 100ms for frames under 256 bytes.
- **NFR-002**: Memory footprint MUST NOT exceed 64MB.
- **NFR-003**: Daemon MUST be ready to accept connections within 5 seconds of start.
- **NFR-004**: System MUST support 9600 baud equivalent throughput (960 bytes/sec minimum).

### Key Entities

- **BLEConnection**: Represents the BLE link to iPhone (state, MTU, GATT handles, rx/tx queues)
- **ClassicConnection**: Represents the BT Classic link to TNC (state, SPP channel, rx/tx queues)
- **KISSFrame**: A complete KISS protocol frame with command byte and data payload
- **BridgeState**: Overall daemon state (idle, partial, connected, error) with both connection refs
- **Configuration**: Persisted settings (target address, PIN, log level, buffer sizes)

## Success Criteria

### Measurable Outcomes

- **SC-001**: iPhone can pair and establish BLE connection within 10 seconds of initiating pairing.
- **SC-002**: Bridge sustains 1000 bytes/second throughput for 1 hour without frame loss or corruption.
- **SC-003**: End-to-end latency for 100-byte KISS frame is under 50ms (p95) under normal conditions.
- **SC-004**: Daemon recovers from single-link failure within 30 seconds when device returns to range.
- **SC-005**: Memory usage remains under 32MB during normal operation (50% of 64MB limit).
- **SC-006**: Daemon passes all contract tests for KISS framing, BLE GATT service, and SPP profile.
