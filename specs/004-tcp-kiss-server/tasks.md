# Tasks: TCP KISS Server

**Input**: Design documents from `/specs/004-tcp-kiss-server/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required per constitution (80% coverage, unit + integration + contract tests).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US1, US2, US3, US4)
- Exact file paths included in descriptions

---

## Phase 1: Setup

**Purpose**: Shared data model and infrastructure needed before any user story

- [x] T001 [P] Add `TcpKissConnection` dataclass to src/models/connection.py per data-model.md (fields: remote_address, connected_at, bytes_rx, bytes_tx)
- [x] T002 [P] Add `tcp_clients: list[TcpKissConnection]` field to `BridgeState` in src/models/state.py and update `to_status_dict()` to include tcp_clients section

**Checkpoint**: Shared models ready. User stories can begin.

---

## Phase 2: User Story 1 - Connect a KISS-over-TCP Client (Priority: P1) 🎯 MVP

**Goal**: A standard KISS-over-TCP client can connect to the bridge, send KISS frames to the TNC, and receive KISS frames from the TNC.

**Independent Test**: `printf '\xc0\x00test\xc0' | nc pi-sugar.hemna.com 8001` sends a KISS frame to the TNC; received TNC packets appear on the TCP connection.

### Tests for User Story 1

> **Write tests FIRST, ensure they FAIL before implementation**

- [x] T003 [P] [US1] Contract tests for KISS-over-TCP frame integrity and reassembly (CT-001, CT-002, CT-003) in tests/contract/test_tcp_kiss_framing.py
- [x] T004 [P] [US1] Unit tests for TcpKissService: start/stop, accept client, receive data, send data, disconnect handling in tests/unit/test_tcp_kiss_service.py
- [x] T005 [P] [US1] Integration tests for TCP→Classic and Classic→TCP bridge flow in tests/integration/test_tcp_bridge.py

### Implementation for User Story 1

- [x] T006 [US1] Implement `TcpKissService` in src/services/tcp_kiss_service.py: asyncio TCP server with `start()`, `stop()`, `_handle_client()` coroutine, per-client `KISSParser`, `set_data_callback()` for forwarding parsed frames, `broadcast(data)` for sending to all clients, `send_data(data)` alias, client tracking via `TcpKissConnection` on `BridgeState.tcp_clients`
- [x] T007 [US1] Modify `BridgeService` in src/services/bridge.py: accept optional `tcp_service: TcpKissService` parameter, register `_handle_tcp_data()` callback for TCP→Classic path, extend `_forward_to_ble_kiss()` to also call `tcp_service.broadcast()` for Classic→TCP path (rename to `_forward_to_clients()`)
- [x] T008 [US1] Wire up `TcpKissService` in src/main.py: create service if enabled (hardcode enabled=True, port=8001 for now), pass to `BridgeService`, add to start/stop lifecycle
- [x] T009 [US1] Verify all US1 tests pass: run `pytest tests/unit/test_tcp_kiss_service.py tests/contract/test_tcp_kiss_framing.py tests/integration/test_tcp_bridge.py -v`

**Checkpoint**: Single TCP client can connect and exchange KISS frames with the TNC. MVP is functional.

---

## Phase 3: User Story 2 - Multi-Client Fan-Out (Priority: P1)

**Goal**: Multiple clients (BLE + TCP, or multiple TCP) all receive TNC packets simultaneously. TX from any client reaches the TNC.

**Independent Test**: Connect two TCP clients and one BLE client. Transmit from another radio. All three clients receive the KISS frame.

### Tests for User Story 2

- [ ] T010 [P] [US2] Contract tests for multi-client broadcast (CT-004) and client isolation (CT-005) in tests/contract/test_tcp_kiss_framing.py (append to existing file)
- [ ] T011 [P] [US2] Integration tests for multi-client scenarios: 2 TCP clients, BLE+TCP, disconnect one client doesn't affect others, in tests/integration/test_tcp_bridge.py (append to existing file)

### Implementation for User Story 2

- [ ] T012 [US2] Ensure `TcpKissService.broadcast()` in src/services/tcp_kiss_service.py writes to ALL connected clients, handles per-client write errors without affecting other clients, and updates per-client bytes_tx counters
- [ ] T013 [US2] Ensure `BridgeService._forward_to_clients()` in src/services/bridge.py sends to BOTH BLE and all TCP clients (handle errors independently for each destination)
- [ ] T014 [US2] Verify all US2 tests pass: run `pytest tests/ --ignore=tests/integration/test_bridge_flow.py -v`

**Checkpoint**: Multi-client fan-out works. BLE and TCP clients are equal peers.

---

## Phase 4: User Story 3 - TCP KISS Configuration (Priority: P2)

**Goal**: TCP KISS server is configurable via config.json: enable/disable, port, host, max clients.

**Independent Test**: Set `tcp_kiss_port: 9001` in config.json, restart, verify server listens on 9001. Set `tcp_kiss_enabled: false`, restart, verify no TCP server.

### Tests for User Story 3

- [ ] T015 [P] [US3] Unit tests for Configuration TCP fields (defaults, validation, from_dict/to_dict) in tests/unit/test_config.py (append to existing file)
- [ ] T016 [P] [US3] Contract test for connection limit enforcement (CT-006): max_clients reached → reject, client disconnects → accept again, in tests/contract/test_tcp_kiss_framing.py (append)

### Implementation for User Story 3

- [ ] T017 [US3] Add TCP KISS configuration fields to `Configuration` dataclass in src/config.py: `tcp_kiss_enabled: bool = True`, `tcp_kiss_port: int = 8001`, `tcp_kiss_host: str = "0.0.0.0"`, `tcp_kiss_max_clients: int = 5` with validation (port 1024-65535, max_clients 1-20)
- [ ] T018 [US3] Update `TcpKissService` in src/services/tcp_kiss_service.py to accept `host`, `port`, `max_clients` parameters and enforce connection limit (reject with log warning when exceeded)
- [ ] T019 [US3] Update src/main.py to read TCP config from `Configuration` and conditionally create `TcpKissService` only if `tcp_kiss_enabled` is True, passing configured port/host/max_clients
- [ ] T020 [US3] Verify all US3 tests pass: run `pytest tests/unit/test_config.py tests/contract/test_tcp_kiss_framing.py -v`

**Checkpoint**: TCP KISS is fully configurable. Disabled by config → no server started.

---

## Phase 5: User Story 4 - TCP Client Visibility in Web UI (Priority: P3)

**Goal**: Status page shows TCP KISS server state and connected clients. SSE updates include TCP info.

**Independent Test**: Connect a TCP client, view status page, see client IP in TCP section.

### Tests for User Story 4

- [ ] T021 [P] [US4] Add `TcpKissClientStatus` and `TcpKissStatus` dataclass tests in tests/unit/test_tcp_kiss_service.py (append: verify web model serialization)
- [ ] T022 [P] [US4] Integration test for `/api/status` response including `tcp_kiss` object (CT-API-001) in tests/integration/test_tcp_bridge.py (append)

### Implementation for User Story 4

- [ ] T023 [P] [US4] Add `TcpKissClientStatus` and `TcpKissStatus` dataclasses to src/web/models.py and add `tcp_kiss: TcpKissStatus` field to `BridgeStatus`
- [ ] T024 [US4] Update `_get_bridge_status()` in src/services/web_service.py to include `TcpKissStatus` built from `BridgeState.tcp_clients` and config (enabled, port, max_clients, client list)
- [ ] T025 [US4] Add TCP KISS clients section to src/web/templates/status.html: show "TCP KISS: Listening on port N (X clients)" with per-client IP/duration, update via SSE `updateStatusUI()` function
- [ ] T026 [US4] Verify all US4 tests pass and full test suite passes: run `pytest tests/ --ignore=tests/integration/test_bridge_flow.py -v`

**Checkpoint**: TCP KISS status visible in web UI and SSE updates.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, cleanup, deployment

- [ ] T027 Run ruff linting on all changed files: `ruff check src/ tests/`
- [ ] T028 Verify full test suite passes with >=80% coverage on new code: `pytest tests/ --ignore=tests/integration/test_bridge_flow.py --cov=src/services/tcp_kiss_service -v`
- [ ] T029 Deploy to Pi and test with real TNC: `rsync` + restart service, verify TCP connection with `nc pi-sugar.hemna.com 8001`
- [ ] T030 Run quickstart.md validation: connect with netcat, verify KISS frame exchange

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - start immediately
- **Phase 2 (US1)**: Depends on Phase 1 completion
- **Phase 3 (US2)**: Depends on Phase 2 (US1) - extends multi-client behavior
- **Phase 4 (US3)**: Depends on Phase 2 (US1) - adds config to existing service. Can run in parallel with Phase 3.
- **Phase 5 (US4)**: Depends on Phase 2 (US1) - adds web UI for existing service. Can run in parallel with Phase 3/4.
- **Phase 6 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 1 setup only. Core MVP.
- **US2 (P1)**: Depends on US1 (extends broadcast behavior). Most of US2 is built into US1's broadcast() implementation.
- **US3 (P2)**: Depends on US1 (adds config to service). Can start in parallel with US2.
- **US4 (P3)**: Depends on US1 (adds web display). Can start in parallel with US2/US3.

### Within Each User Story

- Tests written FIRST and verified to FAIL
- Models before services
- Services before endpoints/UI
- Run story tests at checkpoint

### Parallel Opportunities

- T001 and T002 (Phase 1 models) in parallel
- T003, T004, T005 (US1 tests) all in parallel
- T010 and T011 (US2 tests) in parallel
- T015 and T016 (US3 tests) in parallel
- T021 and T022 (US4 tests) in parallel
- T023 can run in parallel with T021/T022 (different files)
- US3 and US4 can run in parallel with each other (after US1)

---

## Parallel Example: User Story 1

```bash
# Phase 1 - Launch both model tasks together:
Task: "Add TcpKissConnection to src/models/connection.py"
Task: "Add tcp_clients to BridgeState in src/models/state.py"

# US1 Tests - Launch all three test files together:
Task: "Contract tests in tests/contract/test_tcp_kiss_framing.py"
Task: "Unit tests in tests/unit/test_tcp_kiss_service.py"
Task: "Integration tests in tests/integration/test_tcp_bridge.py"
```

## Parallel Example: Post-US1

```bash
# US3 and US4 can run in parallel after US1 completes:
Task: "US3 - Add config fields to src/config.py"
Task: "US4 - Add web models to src/web/models.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: US1 tests + implementation (T003-T009)
3. **STOP and VALIDATE**: Deploy to Pi, test with `nc` and real TNC
4. Single TCP client can exchange KISS frames - MVP complete

### Incremental Delivery

1. Setup + US1 → Test independently → Deploy (MVP!)
2. Add US2 → Verify multi-client broadcast → Deploy
3. Add US3 → Verify config knobs → Deploy
4. Add US4 → Verify web UI shows TCP clients → Deploy
5. Polish → Lint, coverage, quickstart validation → Final deploy
