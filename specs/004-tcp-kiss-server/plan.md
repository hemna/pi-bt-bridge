# Implementation Plan: TCP KISS Server

**Branch**: `004-tcp-kiss-server` | **Date**: 2026-03-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-tcp-kiss-server/spec.md`

## Summary

Add a TCP KISS server to the pi-bt-bridge daemon that allows standard KISS-over-TCP clients (APRSIS32, Xastir, PinPoint APRS, etc.) to connect alongside BLE clients. The server uses Python's `asyncio.start_server()` to accept multiple simultaneous TCP connections. RX frames from the TNC are broadcast to ALL connected clients (BLE + TCP), and TX frames from ANY client are forwarded to the TNC. This transforms the bridge from a 1:1 BLE-to-Classic relay into a multi-client KISS hub.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing codebase)
**Primary Dependencies**: asyncio (stdlib, TCP server), existing KISSParser for frame parsing
**Storage**: N/A (no persistence needed; config via existing `config.json`)
**Testing**: pytest + pytest-asyncio (existing test infrastructure)
**Target Platform**: Raspberry Pi Zero 2 W (Debian Bookworm, armhf, 512MB RAM)
**Project Type**: Daemon/service (extension of existing bt-bridge daemon)
**Performance Goals**: <100ms end-to-end latency, >=960 B/s throughput (per constitution)
**Constraints**: <5MB additional memory, max 5 concurrent TCP clients (configurable), must not degrade BLE path performance
**Scale/Scope**: 1-5 simultaneous TCP clients on local LAN

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status | Notes |
|-----------|-------------|--------|-------|
| I. Code Quality - Readability | Functions <=50 lines, self-documenting | PASS | TCP service follows existing service patterns |
| I. Code Quality - Type Safety | All public interfaces have type annotations | PASS | All public methods will be typed |
| I. Code Quality - Error Handling | All external interfaces have explicit error handling | PASS | TCP socket operations wrapped in try/except |
| I. Code Quality - Documentation | All public APIs have docstrings | PASS | Will follow existing docstring patterns |
| I. Code Quality - Linting | Zero ruff warnings | PASS | Will run ruff before merge |
| II. Testing - Unit Tests | >=80% coverage, mockable | PASS | TCP server is fully testable with asyncio test infrastructure |
| II. Testing - Integration Tests | Bridge paths tested | PASS | TCP→TNC and TNC→TCP integration tests planned |
| II. Testing - Contract Tests | Protocol boundaries tested | PASS | KISS framing over TCP contract tests |
| II. Testing - Independence | Tests independently runnable | PASS | No shared state |
| III. UX - Connection States | States clearly communicated | PASS | TCP client states shown in web UI and SSE |
| III. UX - Error Messages | Actionable errors | PASS | Connection rejection, malformed data logged |
| III. UX - Graceful Degradation | Partial failures don't crash | PASS | Client disconnect doesn't affect others |
| III. UX - Configuration | Settings persist, sensible defaults | PASS | Defaults: enabled, port 8001, max 5 clients |
| IV. Performance - Latency | <100ms end-to-end | PASS | TCP on LAN adds <1ms vs BLE's ~10ms |
| IV. Performance - Throughput | >=960 B/s | PASS | TCP easily exceeds this |
| IV. Performance - Memory | <64MB total | PASS | TCP adds ~2-5MB for buffers + asyncio overhead |
| IV. Performance - Startup | <5s ready | PASS | `asyncio.start_server()` is near-instant |

**Gate Result**: PASS - No violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/004-tcp-kiss-server/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── config.py                    # MODIFY: Add tcp_kiss_enabled, tcp_kiss_port, tcp_kiss_max_clients
├── main.py                      # MODIFY: Wire up TcpKissService lifecycle
├── models/
│   ├── connection.py            # MODIFY: Add TcpKissConnection dataclass
│   └── state.py                 # MODIFY: Add tcp_clients to BridgeState
├── services/
│   ├── bridge.py                # MODIFY: Fan-out RX to TCP, accept TCP TX
│   ├── tcp_kiss_service.py      # NEW: TCP KISS server
│   └── web_service.py           # MODIFY: TCP status in API + SSE
└── web/
    ├── models.py                # MODIFY: Add TcpKissStatus web model
    └── templates/
        └── status.html          # MODIFY: TCP clients section

tests/
├── contract/
│   └── test_tcp_kiss_framing.py # NEW: KISS-over-TCP protocol compliance
├── integration/
│   └── test_tcp_bridge.py       # NEW: TCP↔TNC bridge flow tests
└── unit/
    └── test_tcp_kiss_service.py # NEW: TCP server unit tests
```

**Structure Decision**: Single project, extending existing `src/services/` and `src/models/` patterns. One new service file, modifications to existing bridge and config. Three new test files.
