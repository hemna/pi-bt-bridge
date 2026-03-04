# Tasks: Bluetooth LE to Classic Bridge Daemon

**Input**: Design documents from `/specs/001-bt-bridge-daemon/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Constitution requires 80% unit test coverage, integration tests for BT flows, and contract tests for protocols. Tests are included.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create project directory structure per plan.md in src/ and tests/
- [x] T002 Initialize Python project with pyproject.toml (Python 3.11+, bless, dbus-python, PyGObject dependencies)
- [x] T003 [P] Configure ruff linter and mypy type checker in pyproject.toml
- [x] T004 [P] Create pytest configuration in pyproject.toml with asyncio mode
- [x] T005 [P] Create .gitignore for Python project (venv, __pycache__, .mypy_cache)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Create ConnectionState enum in src/models/state.py with IDLE, SCANNING, CONNECTING, CONNECTED, DISCONNECTING, ERROR states
- [x] T007 Create KISSCommand enum in src/models/kiss.py with DATA_FRAME, TX_DELAY, PERSISTENCE, SLOT_TIME, TX_TAIL, FULL_DUPLEX, SET_HARDWARE, RETURN values
- [x] T008 [P] Create KISSFrame dataclass in src/models/kiss.py with port, command, data, raw, timestamp fields
- [x] T009 [P] Create KISSParser class in src/models/kiss.py with feed() and reset() methods implementing FEND/FESC state machine
- [x] T010 [P] Create ErrorEvent dataclass in src/models/state.py with timestamp, source, error_type, message, remediation fields
- [x] T011 Create Configuration dataclass in src/config.py with target_address, target_pin, device_name, log_level, buffer_size, reconnect_max_delay, status_socket fields
- [x] T012 Implement configuration load/save from JSON file in src/config.py with validation
- [x] T013 [P] Create structured logging setup in src/util/logging.py with configurable log level and file output
- [x] T014 Create tests/conftest.py with shared pytest fixtures for mock BLE adapter, mock SPP socket, sample KISS frames

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Initial Bridge Setup and Pairing (Priority: P1) 🎯 MVP

**Goal**: Pair iPhone with Pi bridge over BLE and pair bridge with TNC over BT Classic

**Independent Test**: Run daemon, pair iPhone via BLE, pair TNC via Classic, verify both show "connected" status

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T015 [P] [US1] Contract test for BLE GATT NUS service discovery in tests/contract/test_ble_gatt.py
- [x] T016 [P] [US1] Contract test for BLE TX/RX characteristic properties in tests/contract/test_ble_gatt.py
- [x] T017 [P] [US1] Contract test for SPP profile registration in tests/contract/test_spp_profile.py
- [x] T018 [P] [US1] Contract test for SPP connection flow in tests/contract/test_spp_profile.py
- [x] T019 [P] [US1] Unit test for BLEConnection state transitions in tests/unit/test_state_machine.py
- [x] T020 [P] [US1] Unit test for ClassicConnection state transitions in tests/unit/test_state_machine.py
- [x] T021 [P] [US1] Integration test for BLE pairing flow in tests/integration/test_bridge_flow.py

### Implementation for User Story 1

- [x] T022 [P] [US1] Create BLEConnection dataclass in src/models/connection.py with state, device_address, device_name, mtu, connected_at, rx_queue, tx_queue, bytes_rx, bytes_tx fields
- [x] T023 [P] [US1] Create ClassicConnection dataclass in src/models/connection.py with state, target_address, device_name, rfcomm_channel, connected_at, rx_queue, tx_queue, bytes_rx, bytes_tx, reconnect_attempts, last_error fields
- [x] T024 [US1] Implement BLEService class in src/services/ble_service.py with bless GATT server setup
- [x] T025 [US1] Add Nordic UART Service (NUS) UUID definitions and characteristic setup in src/services/ble_service.py
- [x] T026 [US1] Implement BLE advertising start/stop in src/services/ble_service.py
- [x] T027 [US1] Implement BLE connection accept and MTU negotiation callbacks in src/services/ble_service.py
- [x] T028 [US1] Implement ClassicService class in src/services/classic_service.py with dbus-python SPP profile registration
- [x] T029 [US1] Implement SPP connection initiation to target address in src/services/classic_service.py
- [x] T030 [US1] Implement NewConnection/RequestDisconnection D-Bus handlers in src/services/classic_service.py
- [x] T031 [US1] Add connection state change logging in both services

**Checkpoint**: User Story 1 complete - BLE and Classic pairing works independently

---

## Phase 4: User Story 2 - KISS Frame Bridging (Priority: P1) 🎯 MVP

**Goal**: Transparently forward KISS frames bidirectionally between BLE and Classic connections

**Independent Test**: Send KISS frames from mock BLE client, verify arrival at mock SPP endpoint, and vice versa

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T032 [P] [US2] Contract test for KISS frame parsing (simple frame) in tests/contract/test_kiss_framing.py
- [x] T033 [P] [US2] Contract test for KISS escape sequences (FEND/FESC in data) in tests/contract/test_kiss_framing.py
- [x] T034 [P] [US2] Contract test for KISS multiple FENDs and back-to-back frames in tests/contract/test_kiss_framing.py
- [x] T035 [P] [US2] Contract test for KISS port number extraction in tests/contract/test_kiss_framing.py
- [x] T036 [P] [US2] Unit test for KISSParser.feed() with various inputs in tests/unit/test_kiss_parser.py
- [x] T037 [P] [US2] Unit test for KISS frame encoding in tests/unit/test_kiss_parser.py
- [x] T038 [P] [US2] Integration test for BLE→Classic frame bridging in tests/integration/test_bridge_flow.py
- [x] T039 [P] [US2] Integration test for Classic→BLE frame bridging in tests/integration/test_bridge_flow.py

### Implementation for User Story 2

- [x] T040 [US2] Create BridgeState dataclass in src/models/state.py with ble, classic, ble_parser, classic_parser, started_at, frames_bridged, errors fields
- [x] T041 [US2] Add computed properties is_fully_connected, is_partially_connected, uptime to BridgeState in src/models/state.py
- [x] T042 [US2] Implement BridgeService class in src/services/bridge.py with asyncio event loop
- [x] T043 [US2] Implement BLE RX handler: read from BLEConnection.rx_queue, feed to KISSParser in src/services/bridge.py
- [x] T044 [US2] Implement Classic TX handler: forward parsed KISSFrames to ClassicConnection.tx_queue in src/services/bridge.py
- [x] T045 [US2] Implement Classic RX handler: read from ClassicConnection.rx_queue, feed to KISSParser in src/services/bridge.py
- [x] T046 [US2] Implement BLE TX handler: forward parsed KISSFrames to BLEConnection.tx_queue in src/services/bridge.py
- [x] T047 [US2] Add latency tracking and frames_bridged counter in src/services/bridge.py
- [x] T048 [US2] Implement frame size validation (max 4096 bytes) with error logging in src/services/bridge.py

**Checkpoint**: User Stories 1 AND 2 complete - Full MVP with pairing and frame bridging

---

## Phase 5: User Story 3 - Connection Recovery and Resilience (Priority: P2)

**Goal**: Automatically attempt reconnection if either Bluetooth link drops

**Independent Test**: Simulate BLE disconnect, verify reconnection attempts, confirm data flow resumes

### Tests for User Story 3

- [x] T049 [P] [US3] Unit test for exponential backoff timing in tests/unit/test_state_machine.py
- [x] T050 [P] [US3] Integration test for BLE disconnect/reconnect in tests/integration/test_reconnection.py
- [x] T051 [P] [US3] Integration test for Classic disconnect/reconnect in tests/integration/test_reconnection.py
- [x] T052 [P] [US3] Integration test for data buffering during link down in tests/integration/test_reconnection.py

### Implementation for User Story 3

- [x] T053 [US3] Add BLE disconnect detection callback in src/services/ble_service.py
- [x] T054 [US3] Implement BLE re-advertising on unexpected disconnect in src/services/ble_service.py
- [x] T055 [US3] Add Classic disconnect detection in src/services/classic_service.py
- [x] T056 [US3] Implement exponential backoff reconnection logic (1s, 2s, 4s, max 30s) in src/services/classic_service.py
- [x] T057 [US3] Add data buffering in BridgeService when one link is down in src/services/bridge.py
- [x] T058 [US3] Implement buffer overflow handling (drop oldest, log warning) in src/services/bridge.py
- [x] T059 [US3] Add reconnect_attempts tracking and reset on success in src/models/connection.py

**Checkpoint**: User Story 3 complete - Bridge recovers from link failures

---

## Phase 6: User Story 4 - Status Monitoring and Logging (Priority: P2)

**Goal**: Monitor bridge status and view logs for diagnostics

**Independent Test**: Query daemon's status interface, verify accurate reflection of connection states and statistics

### Tests for User Story 4

- [x] T060 [P] [US4] Unit test for status JSON serialization in tests/unit/test_config.py
- [x] T061 [P] [US4] Integration test for Unix socket status query in tests/integration/test_bridge_flow.py

### Implementation for User Story 4

- [x] T062 [US4] Create status response schema with ble_state, classic_state, bytes_transferred, uptime, error_counts in src/models/state.py
- [x] T063 [US4] Implement Unix socket server for status queries in src/services/bridge.py
- [x] T064 [US4] Add JSON status response handler in src/services/bridge.py
- [x] T065 [US4] Implement frame bridging log entries (timestamp, direction, size) in src/services/bridge.py
- [x] T066 [US4] Add structured error logging with remediation hints in src/util/logging.py

**Checkpoint**: User Story 4 complete - Status monitoring available

---

## Phase 7: User Story 5 - Daemon Lifecycle Management (Priority: P3)

**Goal**: Run bridge as systemd service that starts on boot

**Independent Test**: Install systemd unit, reboot, verify daemon starts and accepts connections

### Tests for User Story 5

- [x] T067 [P] [US5] Unit test for graceful shutdown signal handling in tests/unit/test_state_machine.py

### Implementation for User Story 5

- [x] T068 [US5] Create daemon entry point in src/main.py with asyncio.run() and signal handlers
- [x] T069 [US5] Implement graceful shutdown (disconnect both links, close sockets) in src/main.py
- [x] T070 [US5] Add startup validation (config exists, bluetooth adapter available) in src/main.py
- [x] T071 [US5] Create systemd service unit file in systemd/bt-bridge.service with restart policy
- [x] T072 [US5] Add installation script for systemd service in scripts/install.sh

**Checkpoint**: User Story 5 complete - Daemon runs as system service

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements across all stories

- [x] T073 [P] Create requirements.txt from pyproject.toml dependencies
- [x] T074 [P] Create example configuration file in config.example.json
- [x] T075 [P] Add type annotations to all public interfaces (mypy strict compliance)
- [x] T076 Run ruff linter and fix any warnings across all src/ files
- [ ] T077 Run mypy type checker and fix any errors across all src/ files (requires: pip install mypy)
- [ ] T078 Run full test suite and verify 80% coverage threshold (requires: pip install -e .[dev])
- [ ] T079 Validate quickstart.md steps work end-to-end
- [ ] T080 Performance test: verify <100ms latency for 256-byte frames

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on Foundational phase completion (can run in parallel with US1, but US2 needs US1 connections to bridge)
- **User Story 3 (Phase 5)**: Depends on US1 and US2 completion (recovery requires working connections and bridging)
- **User Story 4 (Phase 6)**: Depends on US1 and US2 completion (status reports on active bridge)
- **User Story 5 (Phase 7)**: Depends on US1 and US2 completion (daemon needs core functionality)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - Uses connections from US1 but tests independently with mocks
- **User Story 3 (P2)**: Requires US1+US2 - Adds recovery to existing connections
- **User Story 4 (P2)**: Requires US1+US2 - Reports on existing bridge state
- **User Story 5 (P3)**: Requires US1+US2 - Wraps core functionality in daemon

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models/dataclasses before services
- Services before integration logic
- Core implementation before error handling
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T003, T004, T005)
- All Foundational tasks marked [P] can run in parallel (T008, T009, T010, T013)
- All tests for a user story marked [P] can run in parallel
- Models within US1 marked [P] can run in parallel (T022, T023)
- US1 and US2 can start in parallel after Foundational

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Contract test for BLE GATT NUS service discovery in tests/contract/test_ble_gatt.py"
Task: "Contract test for BLE TX/RX characteristic properties in tests/contract/test_ble_gatt.py"
Task: "Contract test for SPP profile registration in tests/contract/test_spp_profile.py"
Task: "Contract test for SPP connection flow in tests/contract/test_spp_profile.py"
Task: "Unit test for BLEConnection state transitions in tests/unit/test_state_machine.py"
Task: "Unit test for ClassicConnection state transitions in tests/unit/test_state_machine.py"
```

## Parallel Example: User Story 2 Tests

```bash
# Launch all US2 tests together:
Task: "Contract test for KISS frame parsing (simple frame) in tests/contract/test_kiss_framing.py"
Task: "Contract test for KISS escape sequences in tests/contract/test_kiss_framing.py"
Task: "Contract test for KISS multiple FENDs in tests/contract/test_kiss_framing.py"
Task: "Unit test for KISSParser.feed() in tests/unit/test_kiss_parser.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (BLE + Classic pairing)
4. Complete Phase 4: User Story 2 (KISS frame bridging)
5. **STOP and VALIDATE**: Test bridging works end-to-end
6. Deploy/demo if ready - this is the minimum viable product

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 + 2 → Test bridging → Deploy/Demo (MVP!)
3. Add User Story 3 → Test reconnection → Deploy/Demo
4. Add User Story 4 → Test status monitoring → Deploy/Demo
5. Add User Story 5 → Test systemd service → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (connections)
   - Developer B: User Story 2 (bridging logic, mocked connections)
3. After US1+US2 merge:
   - Developer A: User Story 3 (recovery)
   - Developer B: User Story 4 (monitoring)
4. Finally: User Story 5 (systemd integration)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution requires: 80% coverage, <100ms latency, <64MB memory
