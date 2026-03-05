# Implementation Plan: Web Pairing Interface

**Branch**: `002-web-pairing-interface` | **Date**: 2026-03-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-web-pairing-interface/spec.md`

## Summary

Add a web interface to the pi-bt-bridge daemon that allows users to view bridge status, pair with Bluetooth Classic TNCs, configure settings, and monitor packet statistics. The interface will be embedded in the existing Python daemon using aiohttp for async HTTP serving, with server-rendered HTML templates for progressive enhancement.

## Technical Context

**Language/Version**: Python 3.11+ (targeting 3.13 on Raspbian Trixie)  
**Primary Dependencies**: aiohttp (async web server), Jinja2 (templates), existing bless/dbus-python  
**Storage**: JSON file at /etc/bt-bridge/config.json (existing)  
**Testing**: pytest with pytest-aiohttp for async HTTP testing  
**Target Platform**: Raspberry Pi Zero 2 W, Raspbian Trixie, ARM64  
**Project Type**: Daemon with embedded web service  
**Performance Goals**: <2s page load, <15s Bluetooth scan  
**Constraints**: <16MB additional memory, works without JavaScript for basic viewing  
**Scale/Scope**: Single user, single bridge instance

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Compliance Strategy |
|-----------|-------------|---------------------|
| I. Code Quality | Type annotations, docstrings, <50 line functions | All web handlers will have type hints and docstrings |
| II. Testing Standards | 80% coverage, integration tests | pytest-aiohttp for HTTP tests, mock Bluetooth for pairing tests |
| III. UX Consistency | Clear connection states, actionable errors, <200ms feedback | Real-time status via WebSocket/SSE, clear error messages |
| IV. Performance | <100ms latency, <64MB memory | Lightweight aiohttp, minimal dependencies, no SPA bloat |

**Gate Status**: ✅ PASS - All principles can be satisfied with proposed approach.

## Project Structure

### Documentation (this feature)

```text
specs/002-web-pairing-interface/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contracts)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── models/              # Existing models
├── services/
│   ├── ble_service.py   # Existing BLE GATT server
│   ├── classic_service.py # Existing RFCOMM service
│   └── web_service.py   # NEW: Web interface service
├── web/                 # NEW: Web interface module
│   ├── __init__.py
│   ├── handlers.py      # HTTP request handlers
│   ├── templates/       # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── status.html
│   │   ├── pairing.html
│   │   ├── settings.html
│   │   └── stats.html
│   └── static/          # CSS, minimal JS
│       └── style.css
├── config.py            # Existing - add web port config
└── main.py              # Existing - integrate web service

tests/
├── contract/            # API contract tests
├── integration/         # Full workflow tests
└── unit/
    └── web/             # Web handler unit tests
```

**Structure Decision**: Extend existing single-project structure with new `src/web/` module for web interface code. Templates and static files live under `src/web/` to keep deployment simple.

## Complexity Tracking

No constitution violations anticipated. The design uses:
- Single additional dependency (aiohttp) - minimal complexity
- Server-rendered HTML - avoids SPA complexity
- Integration with existing GLib main loop via aiohttp's asyncio support
