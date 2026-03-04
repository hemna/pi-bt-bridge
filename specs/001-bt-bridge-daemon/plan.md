# Implementation Plan: Bluetooth LE to Classic Bridge Daemon

**Branch**: `001-bt-bridge-daemon` | **Date**: 2026-03-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-bt-bridge-daemon/spec.md`

## Summary

Build a Python daemon for Raspberry Pi Zero 2 W that bridges Bluetooth LE (iPhone) to 
Bluetooth Classic (ham radio TNC) connections, transparently forwarding KISS TNC frames
bidirectionally. Uses `bless` for BLE GATT server with Nordic UART Service and 
`dbus-python` for BT Classic SPP via BlueZ D-Bus API.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: bless (BLE GATT), dbus-python (SPP), PyGObject (GLib loop)  
**Storage**: JSON configuration file in /etc/bt-bridge/config.json  
**Testing**: pytest with mock Bluetooth adapters, hardware integration tests  
**Target Platform**: Raspberry Pi Zero 2 W, Raspberry Pi OS (Bookworm) with BlueZ 5.55+  
**Project Type**: Daemon/system service  
**Performance Goals**: <100ms end-to-end latency, >=960 bytes/sec throughput  
**Constraints**: <64MB memory, <5s startup time, dual BLE+Classic concurrent operation  
**Scale/Scope**: Single iPhone + single TNC connection, ~1000 bytes/sec sustained

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Plan Compliance | Status |
|-----------|-------------|-----------------|--------|
| **I. Code Quality** | Type annotations on public APIs | All public interfaces will have type hints | ✅ PASS |
| | Functions <50 lines | Design for small, focused functions | ✅ PASS |
| | Explicit error handling for BT/serial | All BLE/Classic/KISS operations wrapped with try/except | ✅ PASS |
| | Docstrings on public APIs | All public classes/methods documented | ✅ PASS |
| | Linting passes | Configure ruff/mypy, enforce in CI | ✅ PASS |
| **II. Testing Standards** | 80% unit test coverage | Mock BLE/Classic adapters for unit tests | ✅ PASS |
| | Integration tests for BT flows | Hardware simulator tests for pairing/bridging | ✅ PASS |
| | Contract tests for protocols | KISS framing, NUS GATT, SPP profile contracts | ✅ PASS |
| | Test independence | No shared state between tests | ✅ PASS |
| **III. UX Consistency** | Connection state communication | Status API exposes BLE/Classic states | ✅ PASS |
| | Actionable error messages | Structured errors with remediation hints | ✅ PASS |
| | Graceful degradation | Single-link failures don't crash daemon | ✅ PASS |
| | Configuration persistence | JSON config survives restarts | ✅ PASS |
| | Feedback <200ms | Not applicable (daemon, no interactive UI) | ✅ N/A |
| **IV. Performance** | Latency <100ms | BLE ~50ms + overhead well under limit | ✅ PASS |
| | Throughput >=960 B/s | BLE MTU negotiation + async I/O | ✅ PASS |
| | Memory <64MB | Python baseline ~20MB, plenty of headroom | ✅ PASS |
| | Startup <5s | Minimal initialization, lazy BT discovery | ✅ PASS |

**Gate Status**: ✅ ALL PRINCIPLES SATISFIED

## Project Structure

### Documentation (this feature)

```text
specs/001-bt-bridge-daemon/
├── plan.md              # This file
├── research.md          # Phase 0 output (complete)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── ble-gatt.md      # NUS GATT service contract
│   ├── spp-profile.md   # BT Classic SPP contract
│   └── kiss-framing.md  # KISS protocol contract
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── __init__.py
├── main.py              # Entry point, daemon lifecycle
├── config.py            # Configuration loading/persistence
├── models/
│   ├── __init__.py
│   ├── connection.py    # BLEConnection, ClassicConnection
│   ├── kiss.py          # KISSFrame, KISSParser
│   └── state.py         # BridgeState, ConnectionState enum
├── services/
│   ├── __init__.py
│   ├── ble_service.py   # BLE GATT server (bless)
│   ├── classic_service.py  # BT Classic SPP (dbus)
│   └── bridge.py        # Bidirectional bridging logic
└── util/
    ├── __init__.py
    └── logging.py       # Structured logging setup

tests/
├── __init__.py
├── conftest.py          # Shared fixtures, mock adapters
├── contract/
│   ├── test_kiss_framing.py
│   ├── test_ble_gatt.py
│   └── test_spp_profile.py
├── integration/
│   ├── test_bridge_flow.py
│   └── test_reconnection.py
└── unit/
    ├── test_kiss_parser.py
    ├── test_config.py
    └── test_state_machine.py
```

**Structure Decision**: Single project layout. Daemon runs as a system service; no
frontend/backend split. Tests organized by type (contract, integration, unit) per
constitution requirements.

## Complexity Tracking

> No Constitution Check violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |
