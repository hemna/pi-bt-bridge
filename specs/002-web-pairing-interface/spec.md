# Feature Specification: Web Pairing Interface

**Feature Branch**: `002-web-pairing-interface`  
**Created**: 2026-03-05  
**Status**: Draft  
**Input**: User description: "the daemon should show a web interface that can walk the user through pairing to both sides of the bridge."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Bridge Status (Priority: P1)

As a user, I want to see the current status of both Bluetooth connections (BLE to phone and Classic to TNC) on a web dashboard so I can quickly understand if the bridge is working.

**Why this priority**: Without status visibility, users cannot troubleshoot connection issues. This is the foundation for all other features.

**Independent Test**: Can be tested by opening browser to Pi's IP address and seeing real-time connection states. Delivers immediate value by showing if bridge is operational.

**Acceptance Scenarios**:

1. **Given** the bridge daemon is running, **When** I navigate to http://pi-address:8080, **Then** I see a dashboard showing BLE connection state and Classic connection state
2. **Given** the TH-D74 is connected, **When** I view the dashboard, **Then** I see "Classic: Connected to 24:71:89:8D:26:EF"
3. **Given** no iPhone is connected, **When** I view the dashboard, **Then** I see "BLE: Waiting for connection"

---

### User Story 2 - Pair with Bluetooth Classic TNC (Priority: P2)

As a user, I want the web interface to help me pair the Pi with my Bluetooth TNC (TH-D74) by scanning for devices and guiding me through the pairing process.

**Why this priority**: New users need to set up the Classic Bluetooth side before the bridge can function. Manual command-line pairing is error-prone.

**Independent Test**: Can be tested by clicking "Scan for TNCs", selecting a device, and completing pairing. Delivers value by enabling first-time setup without SSH.

**Acceptance Scenarios**:

1. **Given** no TNC is paired, **When** I click "Scan for Bluetooth devices", **Then** I see a list of discoverable Bluetooth Classic devices
2. **Given** I see a list of devices, **When** I select my TH-D74 and click "Pair", **Then** the system initiates pairing and shows progress
3. **Given** pairing requires a PIN, **When** the TNC shows a PIN, **Then** I can enter it in the web interface to complete pairing
4. **Given** pairing succeeds, **When** the process completes, **Then** the device is saved as the target TNC in configuration

---

### User Story 3 - Configure Bridge Settings (Priority: P3)

As a user, I want to configure bridge settings (device name, target MAC, RFCOMM channel) through the web interface so I don't need to edit config files manually.

**Why this priority**: After initial pairing works, users may need to adjust settings. Web UI is more user-friendly than JSON config files.

**Independent Test**: Can be tested by changing the BLE device name in the web UI and verifying it takes effect. Delivers value by simplifying configuration.

**Acceptance Scenarios**:

1. **Given** I am on the settings page, **When** I change the BLE device name to "MyBridge", **Then** the change is saved to /etc/bt-bridge/config.json
2. **Given** I change settings, **When** I click "Apply", **Then** the bridge restarts with new settings
3. **Given** I enter an invalid MAC address, **When** I try to save, **Then** I see a validation error

---

### User Story 4 - View Packet Statistics (Priority: P4)

As a user, I want to see packet statistics (packets sent/received, bytes transferred, errors) so I can monitor bridge health.

**Why this priority**: Nice-to-have for debugging but not essential for basic operation.

**Independent Test**: Can be tested by sending packets through the bridge and seeing counters increment. Delivers value for troubleshooting.

**Acceptance Scenarios**:

1. **Given** packets are flowing through the bridge, **When** I view the stats page, **Then** I see packet counts and byte totals
2. **Given** errors occur, **When** I view stats, **Then** I see error counts and recent error messages

---

### Edge Cases

- What happens when Bluetooth adapter is not available? Show clear error message.
- What happens when user tries to pair while bridge is already connected? Warn and require confirmation.
- How does system handle web interface access while pairing is in progress? Show pairing progress, disable other actions.
- What happens if the Pi has no network connection? Web interface is inaccessible; this is acceptable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST serve a web interface on a configurable HTTP port (default: 8080)
- **FR-002**: Web interface MUST display real-time BLE connection status (idle, advertising, connected, device name)
- **FR-003**: Web interface MUST display real-time Classic connection status (disconnected, connecting, connected, target MAC)
- **FR-004**: System MUST provide endpoint to scan for discoverable Bluetooth Classic devices
- **FR-005**: System MUST provide endpoint to initiate pairing with a selected Bluetooth Classic device
- **FR-006**: System MUST support PIN entry during pairing process
- **FR-007**: System MUST allow configuration of: device_name, target_address, rfcomm_channel, log_level
- **FR-008**: Configuration changes MUST be persisted to /etc/bt-bridge/config.json
- **FR-009**: System MUST provide statistics: packets_tx, packets_rx, bytes_tx, bytes_rx, errors, uptime
- **FR-010**: Web interface MUST work without JavaScript for basic status viewing (progressive enhancement)
- **FR-011**: Web interface MUST be responsive and usable on mobile devices

### Key Entities

- **BridgeStatus**: Current state of both connections, uptime, last activity timestamps
- **BluetoothDevice**: Discovered device with MAC address, name, device class, signal strength
- **PairingSession**: In-progress pairing with state, PIN requirement, timeout
- **Configuration**: User-configurable settings (target_address, device_name, rfcomm_channel, etc.)
- **Statistics**: Packet/byte counters, error counts, connection history

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can view bridge status within 2 seconds of page load
- **SC-002**: Bluetooth scan completes and displays results within 15 seconds
- **SC-003**: Successful pairing workflow completes in under 60 seconds (excluding user input time)
- **SC-004**: Configuration changes take effect within 10 seconds of applying
- **SC-005**: Web interface memory overhead does not exceed 16MB additional RAM
- **SC-006**: Web server startup adds less than 2 seconds to daemon startup time
