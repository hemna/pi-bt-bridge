# Feature Specification: TNC Radio History

**Feature Branch**: `003-tnc-radio-history`  
**Created**: 2026-03-06  
**Status**: Draft  
**Input**: User description: "Keep history for the BT paired TNC Radios, so I can switch back and forth. I will typically have the same phone, but different radios that I'd like to use."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Quick Switch Between Known TNCs (Priority: P1)

As a ham radio operator with multiple TNC radios (e.g., TH-D74, Mobilinkd TNC3), I want to quickly switch between previously paired TNCs without re-scanning and re-pairing each time, so I can efficiently use different radios depending on my operating situation.

**Why this priority**: This is the core value proposition - eliminating repetitive pairing workflows when switching between radios the user already owns and has paired before.

**Independent Test**: Can be fully tested by pairing two TNC devices, switching between them via the web interface, and verifying the bridge connects to the selected TNC without requiring a new scan or pairing process.

**Acceptance Scenarios**:

1. **Given** I have previously paired TNC "TH-D74" and "Mobilinkd TNC3", **When** I open the TNC Selection on the web interface, **Then** I see a list of my previously used TNCs with their names and MAC addresses.
2. **Given** I am currently connected to "TH-D74", **When** I select "Mobilinkd TNC3" from my TNC history, **Then** the bridge disconnects from TH-D74 and connects to Mobilinkd TNC3.
3. **Given** I select a TNC from history, **When** the connection is established, **Then** the selected TNC becomes the new "current" target and the bridge is ready to forward packets.

---

### User Story 2 - Persist TNC History Across Restarts (Priority: P1)

As a user, I want my TNC history to persist across daemon restarts and reboots, so I don't lose my list of known radios.

**Why this priority**: Without persistence, the history feature would be useless after a reboot, which is common for Raspberry Pi deployments.

**Independent Test**: Pair a TNC, restart the daemon, and verify the TNC still appears in history.

**Acceptance Scenarios**:

1. **Given** I have 3 TNCs in my history, **When** I restart the bt-bridge daemon, **Then** all 3 TNCs still appear in my history list.
2. **Given** I have TNCs in history, **When** the Raspberry Pi reboots, **Then** my TNC history is preserved.

---

### User Story 3 - Add Friendly Names to TNCs (Priority: P2)

As a user with multiple similar radios, I want to assign friendly names to my TNCs (e.g., "Mobile TNC", "Base Station TNC"), so I can easily identify which radio is which.

**Why this priority**: Improves usability but not essential for core functionality. MAC addresses and device names from Bluetooth may be sufficient for some users.

**Independent Test**: Add a TNC to history, assign a custom name, and verify the custom name displays in the list.

**Acceptance Scenarios**:

1. **Given** I have a TNC in my history, **When** I edit its friendly name to "Mobile Rig", **Then** the list shows "Mobile Rig" as the display name.
2. **Given** I have not set a friendly name, **When** viewing the TNC in history, **Then** the Bluetooth device name is shown (or MAC address if no name).

---

### User Story 4 - Remove TNCs from History (Priority: P2)

As a user, I want to remove TNCs I no longer use from my history, so my list stays clean and manageable.

**Why this priority**: Nice-to-have for list management, not critical for switching functionality.

**Independent Test**: Add a TNC, remove it from history, verify it no longer appears.

**Acceptance Scenarios**:

1. **Given** I have a TNC "Old Radio" in my history, **When** I click remove/delete, **Then** "Old Radio" is removed from the history list.
2. **Given** I remove a TNC from history, **When** I scan for devices, **Then** that TNC can still be discovered and re-added.

---

### User Story 5 - Show Connection Status in History (Priority: P3)

As a user, I want to see which TNC is currently active and the last connection time for each TNC in history, so I have visibility into my usage patterns.

**Why this priority**: Informational enhancement, not required for core switching functionality.

**Independent Test**: Connect to a TNC, view history, verify "active" indicator and last-used timestamp.

**Acceptance Scenarios**:

1. **Given** I am connected to "TH-D74", **When** I view TNC history, **Then** "TH-D74" shows as "Active" or "Connected".
2. **Given** I have multiple TNCs in history, **When** I view the list, **Then** each shows "Last used: [timestamp]" or "Never connected".

---

### Edge Cases

- What happens when a TNC in history is no longer paired at the Bluetooth level? (Show warning, offer to re-pair)
- What happens when selecting a TNC that is powered off or out of range? (Connection fails gracefully, show error, keep in history)
- What is the maximum number of TNCs in history? (Reasonable limit, e.g., 10-20)
- What happens if the history file is corrupted? (Fall back to empty history, log warning)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a persistent list of previously used TNC devices
- **FR-002**: System MUST store for each TNC: MAC address, Bluetooth device name, RFCOMM channel, optional friendly name, last used timestamp
- **FR-003**: System MUST allow users to select a TNC from history to connect to
- **FR-004**: System MUST allow users to assign/edit friendly names for TNCs in history
- **FR-005**: System MUST allow users to remove TNCs from history
- **FR-006**: System MUST persist history across daemon restarts
- **FR-007**: System MUST show current connection status for each TNC in history
- **FR-008**: System MUST automatically add newly paired TNCs to history when used
- **FR-009**: Web interface MUST display TNC history in a selectable list format
- **FR-010**: API MUST provide endpoints for listing, selecting, updating, and removing TNC history entries

### Key Entities

- **TNCDevice**: Represents a known TNC radio with address, name, friendly_name, rfcomm_channel, last_used, paired status
- **TNCHistory**: Collection of TNCDevice entries, persisted to storage

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can switch between 2+ previously paired TNCs in under 5 seconds (no re-scanning required)
- **SC-002**: TNC history persists across daemon restarts with 100% reliability
- **SC-003**: Users can identify TNCs by friendly name or Bluetooth name in the selection list
- **SC-004**: Web interface shows TNC history list without requiring manual scan
