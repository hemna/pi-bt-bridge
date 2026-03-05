# Implementation Tasks: Web Pairing Interface

**Feature**: 002-web-pairing-interface  
**Date**: 2026-03-05  
**Branch**: `002-web-pairing-interface`

## Overview

Implementation tasks for adding a web interface to the pi-bt-bridge daemon. Tasks are ordered by dependency and priority.

---

## Phase 1: Foundation (P1 - Status Dashboard)

### Task 1.1: Add Web Dependencies
**Priority**: P1  
**Estimate**: 15 min  
**Files**: `requirements.txt`, `pyproject.toml`

- Add `aiohttp>=3.9.0`
- Add `aiohttp-jinja2>=1.6.0`
- Update requirements.txt

**Acceptance**: Dependencies installable with `pip install -r requirements.txt`

---

### Task 1.2: Extend Configuration for Web
**Priority**: P1  
**Estimate**: 30 min  
**Files**: `src/config.py`

- Add `web_port: int = 8080` field
- Add `web_enabled: bool = True` field
- Add validation for port range (1024-65535)
- Update `config.example.json`

**Acceptance**: Config loads with new fields, validation works

**Test**: Unit test for new config fields

---

### Task 1.3: Create Web Data Models
**Priority**: P1  
**Estimate**: 45 min  
**Files**: `src/web/__init__.py`, `src/web/models.py`

- Create `ConnectionState` enum
- Create `BLEStatus`, `ClassicStatus`, `BridgeStatus` dataclasses
- Create `PacketStatistics` dataclass
- Add `to_dict()` methods for JSON serialization

**Acceptance**: Models can be instantiated and serialized to JSON

**Test**: Unit tests for all model serialization

---

### Task 1.4: Create Web Service Skeleton
**Priority**: P1  
**Estimate**: 1 hour  
**Files**: `src/services/web_service.py`

- Create `WebService` class with aiohttp Application
- Implement `start()` and `stop()` methods
- Add basic route registration
- Add Jinja2 template setup

**Acceptance**: Web server starts and responds to requests

**Test**: Integration test for server start/stop

---

### Task 1.5: Create Base Template
**Priority**: P1  
**Estimate**: 30 min  
**Files**: `src/web/templates/base.html`, `src/web/static/style.css`

- Create HTML5 base template with:
  - Header with bridge name
  - Navigation (Status, Pairing, Settings, Stats)
  - Main content block
  - Footer with version
- Create minimal CSS for responsive layout
- Mobile-first design

**Acceptance**: Base template renders correctly on desktop and mobile

---

### Task 1.6: Implement Status Dashboard
**Priority**: P1  
**Estimate**: 1.5 hours  
**Files**: `src/web/handlers.py`, `src/web/templates/status.html`

- Create `GET /` handler returning status page
- Create `GET /api/status` handler returning JSON
- Display BLE connection state
- Display Classic connection state
- Display uptime

**Acceptance**: Dashboard shows real-time connection states

**Test**: Unit test for status handler, integration test for page load

---

### Task 1.7: Implement SSE Status Stream
**Priority**: P1  
**Estimate**: 1 hour  
**Files**: `src/web/handlers.py`

- Create `GET /api/status/stream` SSE endpoint
- Push status updates on state change
- Send ping every 30 seconds
- Limit concurrent connections to 5

**Acceptance**: Browser receives real-time updates via EventSource

**Test**: Integration test for SSE stream

---

### Task 1.8: Integrate Web Service with Main
**Priority**: P1  
**Estimate**: 30 min  
**Files**: `src/main.py`

- Create WebService in `run_daemon()`
- Start web server alongside bridge
- Pass bridge state to web service
- Graceful shutdown of web server

**Acceptance**: Daemon starts with web server, both shut down cleanly

**Test**: Integration test for full daemon startup

---

## Phase 2: Pairing Workflow (P2)

### Task 2.1: Create Bluetooth Scanner Service
**Priority**: P2  
**Estimate**: 2 hours  
**Files**: `src/services/scanner_service.py`

- Create `ScannerService` class using D-Bus BlueZ API
- Implement `start_scan()` - initiates Classic discovery
- Implement `get_devices()` - returns discovered devices
- Implement `stop_scan()` - stops discovery
- Filter devices for SPP profile

**Acceptance**: Scan finds Bluetooth Classic devices with SPP

**Test**: Unit test with mocked D-Bus, integration test on Pi

---

### Task 2.2: Create Pairing Session Manager
**Priority**: P2  
**Estimate**: 1.5 hours  
**Files**: `src/web/models.py`, `src/services/pairing_manager.py`

- Create `PairingSession` model
- Create `PairingManager` class
- Implement session state machine (idle -> scanning -> pairing -> success/failed)
- Handle PIN callback from BlueZ agent

**Acceptance**: Pairing state machine works correctly

**Test**: Unit test for state transitions

---

### Task 2.3: Extend Pairing Agent for Web
**Priority**: P2  
**Estimate**: 1 hour  
**Files**: `src/services/pairing_agent.py`

- Add callback hook for PIN requests
- Add method to submit PIN from web
- Add method to initiate outbound pairing

**Acceptance**: Agent can initiate pairing and relay PIN requests

**Test**: Unit test with mocked D-Bus

---

### Task 2.4: Implement Pairing API Endpoints
**Priority**: P2  
**Estimate**: 1.5 hours  
**Files**: `src/web/handlers.py`

- `POST /api/pairing/scan` - start scan
- `GET /api/pairing/devices` - get discovered devices
- `POST /api/pairing/pair` - initiate pairing
- `POST /api/pairing/pin` - submit PIN
- `GET /api/pairing/status` - get pairing status

**Acceptance**: All pairing endpoints work correctly

**Test**: Unit tests for each endpoint

---

### Task 2.5: Create Pairing Page Template
**Priority**: P2  
**Estimate**: 1 hour  
**Files**: `src/web/templates/pairing.html`

- Scan button and device list
- Device selection UI
- PIN entry dialog (shown when needed)
- Progress indicator
- Success/error messages

**Acceptance**: Full pairing workflow works in browser

**Test**: Manual testing on Pi with TH-D74

---

## Phase 3: Settings (P3)

### Task 3.1: Implement Settings API
**Priority**: P3  
**Estimate**: 1 hour  
**Files**: `src/web/handlers.py`

- `GET /api/settings` - get current config
- `POST /api/settings` - update config
- Validation with detailed error messages
- Save to `/etc/bt-bridge/config.json`

**Acceptance**: Settings can be read and updated via API

**Test**: Unit tests for validation and persistence

---

### Task 3.2: Create Settings Page Template
**Priority**: P3  
**Estimate**: 45 min  
**Files**: `src/web/templates/settings.html`

- Form with all editable fields
- Client-side validation
- Save button with confirmation
- Restart button (with warning)

**Acceptance**: Settings page allows configuration changes

**Test**: Manual testing

---

### Task 3.3: Implement Restart Endpoint
**Priority**: P3  
**Estimate**: 30 min  
**Files**: `src/web/handlers.py`

- `POST /api/restart` - trigger daemon restart
- Send response before restart
- Use systemd restart if available

**Acceptance**: Daemon restarts when endpoint called

**Test**: Integration test

---

## Phase 4: Statistics (P4)

### Task 4.1: Add Statistics Tracking
**Priority**: P4  
**Estimate**: 1 hour  
**Files**: `src/models/state.py`, `src/services/bridge.py`

- Add `PacketStatistics` to bridge state
- Increment counters on packet TX/RX
- Track error counts
- Track timestamps

**Acceptance**: Statistics accumulate during operation

**Test**: Unit test for counter increments

---

### Task 4.2: Implement Statistics Endpoints
**Priority**: P4  
**Estimate**: 30 min  
**Files**: `src/web/handlers.py`

- `GET /api/stats` - return statistics JSON

**Acceptance**: Stats endpoint returns correct data

**Test**: Unit test

---

### Task 4.3: Create Statistics Page Template
**Priority**: P4  
**Estimate**: 30 min  
**Files**: `src/web/templates/stats.html`

- Display packet counts
- Display byte counts
- Display error count
- Display last activity times

**Acceptance**: Stats page shows all metrics

---

## Phase 5: Testing & Polish

### Task 5.1: Write Contract Tests
**Priority**: P2  
**Estimate**: 2 hours  
**Files**: `tests/contract/test_web_api.py`

- Test all API endpoints against contract
- Test error responses
- Test SSE stream format

**Acceptance**: All contract tests pass

---

### Task 5.2: Write Integration Tests
**Priority**: P2  
**Estimate**: 2 hours  
**Files**: `tests/integration/test_web_integration.py`

- Test full status flow
- Test pairing flow (mocked)
- Test settings flow

**Acceptance**: All integration tests pass

---

### Task 5.3: Add Progressive Enhancement JS
**Priority**: P4  
**Estimate**: 1 hour  
**Files**: `src/web/static/main.js`

- Auto-refresh status via SSE
- Form validation
- Pairing workflow UX improvements

**Acceptance**: JS enhances experience but not required

---

### Task 5.4: Documentation
**Priority**: P3  
**Estimate**: 30 min  
**Files**: `README.md`

- Document web interface
- Document API endpoints
- Document firewall recommendations

**Acceptance**: User can set up web interface from docs

---

## Task Dependencies

```
1.1 ─┬─> 1.2 ─┬─> 1.4 ─> 1.8
     │        │
     └─> 1.3 ─┘
              │
         1.5 ─┴─> 1.6 ─> 1.7

2.1 ─┬─> 2.2 ─> 2.4 ─> 2.5
     │
2.3 ─┘

3.1 ─> 3.2 ─> 3.3

4.1 ─> 4.2 ─> 4.3

5.1, 5.2, 5.3, 5.4 (parallel after phases 1-2)
```

## Estimated Total Time

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Phase 1 (P1) | 8 tasks | ~6.5 hours |
| Phase 2 (P2) | 5 tasks | ~7 hours |
| Phase 3 (P3) | 3 tasks | ~2.25 hours |
| Phase 4 (P4) | 3 tasks | ~2 hours |
| Phase 5 | 4 tasks | ~5.5 hours |
| **Total** | **23 tasks** | **~23 hours** |

## Definition of Done

- [ ] All P1 tasks complete (status dashboard works)
- [ ] All P2 tasks complete (pairing workflow works)
- [ ] Test coverage >= 80% for web module
- [ ] No linting errors
- [ ] Documentation updated
- [ ] Deployed and tested on Pi
