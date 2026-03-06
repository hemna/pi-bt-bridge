# Implementation Plan: TNC Radio History

**Branch**: `003-tnc-radio-history` | **Date**: 2026-03-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-tnc-radio-history/spec.md`

## Summary

Add persistent TNC radio history to Pi BT Bridge, allowing users to quickly switch between previously paired TNC devices without re-scanning. The feature stores TNC metadata (MAC address, name, RFCOMM channel, friendly name, last used) in a JSON file and exposes it via the web interface and REST API.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: aiohttp (web), dataclasses (models), JSON (persistence)  
**Storage**: JSON file (`/etc/bt-bridge/tnc-history.json`)  
**Testing**: pytest, pytest-asyncio  
**Target Platform**: Raspberry Pi Zero 2 W running Raspberry Pi OS (Bookworm+)  
**Project Type**: Daemon with web interface  
**Performance Goals**: TNC switch latency <5 seconds, history load <100ms  
**Constraints**: Memory <64MB, storage minimal (history file <10KB)  
**Scale/Scope**: 10-20 TNC entries maximum per history

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Code Quality** | PASS | Feature follows existing patterns (dataclasses, type hints, docstrings) |
| **II. Testing Standards** | PASS | Will add unit tests for history model, integration tests for API endpoints |
| **III. UX Consistency** | PASS | History UI follows existing web interface patterns; connection states clearly shown |
| **IV. Performance** | PASS | JSON file load is fast; TNC switching reuses existing connection logic |

**No violations requiring justification.**

## Project Structure

### Documentation (this feature)

```text
specs/003-tnc-radio-history/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contracts)
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/
├── config.py            # MODIFY: Add history_file path config option
├── models/
│   └── tnc_history.py   # NEW: TNCDevice and TNCHistory models
├── services/
│   └── web_service.py   # MODIFY: Add history API endpoints
└── web/
    ├── models.py        # MODIFY: Add history response models if needed
    └── templates/
        └── status.html  # MODIFY: Add TNC history selection UI

tests/
├── unit/
│   └── test_tnc_history.py  # NEW: Unit tests for history model
└── integration/
    └── test_history_api.py  # NEW: Integration tests for API
```

**Structure Decision**: Extend existing single-project structure with new `src/models/tnc_history.py` for the history data model. History UI integrates into existing status page TNC Selection section.

## Complexity Tracking

> No violations requiring justification.
