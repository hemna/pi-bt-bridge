# Tasks: TNC Radio History

**Feature**: 003-tnc-radio-history  
**Branch**: `003-tnc-radio-history`  
**Date**: 2026-03-06

**Input**: Design documents from `/specs/003-tnc-radio-history/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Tests**: Included per Constitution Testing Standards (80% coverage required)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create new files and project structure for TNC history feature

- [ ] T001 Create TNCDevice and TNCHistory models in src/models/tnc_history.py
- [ ] T002 [P] Add history_file config option to src/config.py
- [ ] T003 [P] Create unit test file tests/unit/test_tnc_history.py with test structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core TNCHistory class with persistence - MUST be complete before any user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Implement TNCDevice dataclass with validation in src/models/tnc_history.py
- [ ] T005 Implement TNCHistory._load() method for JSON file reading in src/models/tnc_history.py
- [ ] T006 Implement TNCHistory._save() method for JSON file writing in src/models/tnc_history.py
- [ ] T007 Implement TNCHistory.add() method in src/models/tnc_history.py
- [ ] T008 Implement TNCHistory.get() method in src/models/tnc_history.py
- [ ] T009 Implement TNCHistory.list_all() method with sorting in src/models/tnc_history.py
- [ ] T010 Implement TNCHistory.remove() method in src/models/tnc_history.py
- [ ] T011 Add TNCDevice.to_dict() and from_dict() serialization methods in src/models/tnc_history.py
- [ ] T012 [P] Write unit tests for TNCDevice validation in tests/unit/test_tnc_history.py
- [ ] T013 [P] Write unit tests for TNCHistory CRUD operations in tests/unit/test_tnc_history.py
- [ ] T014 [P] Write unit tests for JSON persistence in tests/unit/test_tnc_history.py

**Checkpoint**: TNCHistory model complete with persistence - API implementation can begin

---

## Phase 3: User Story 1 - Quick Switch Between Known TNCs (Priority: P1) 🎯 MVP

**Goal**: Users can see list of previously used TNCs and select one to connect to

**Independent Test**: Pair two TNC devices, view history list in web UI, select one, verify bridge connects without re-scanning

### Tests for User Story 1

- [ ] T015 [P] [US1] Write integration test for GET /api/tnc-history endpoint in tests/integration/test_history_api.py
- [ ] T016 [P] [US1] Write integration test for POST /api/tnc-history/{address}/select endpoint in tests/integration/test_history_api.py

### Implementation for User Story 1

- [ ] T017 [US1] Add TNCHistory instance initialization in src/services/web_service.py
- [ ] T018 [US1] Implement GET /api/tnc-history endpoint in src/services/web_service.py
- [ ] T019 [US1] Implement GET /api/tnc-history/{address} endpoint in src/services/web_service.py
- [ ] T020 [US1] Implement POST /api/tnc-history/{address}/select endpoint in src/services/web_service.py
- [ ] T021 [US1] Add is_paired check by querying BlueZ paired devices in src/services/web_service.py
- [ ] T022 [US1] Add is_current check comparing to config.target_address in src/services/web_service.py
- [ ] T023 [US1] Update TNC Selection section in src/web/templates/status.html to show history list
- [ ] T024 [US1] Add JavaScript to fetch and render TNC history list in src/web/templates/status.html
- [ ] T025 [US1] Add "Select" button for each TNC in history list in src/web/templates/status.html
- [ ] T026 [US1] Add JavaScript handler for TNC selection (calls /select endpoint) in src/web/templates/status.html
- [ ] T027 [US1] Auto-add TNC to history when connection succeeds in src/services/web_service.py

**Checkpoint**: User Story 1 complete - users can view and switch between TNCs in history

---

## Phase 4: User Story 2 - Persist TNC History Across Restarts (Priority: P1)

**Goal**: TNC history survives daemon restarts and reboots

**Independent Test**: Add TNCs to history, restart daemon, verify history is preserved

### Tests for User Story 2

- [ ] T028 [P] [US2] Write unit test for history file creation on first write in tests/unit/test_tnc_history.py
- [ ] T029 [P] [US2] Write unit test for history reload after simulated restart in tests/unit/test_tnc_history.py

### Implementation for User Story 2

- [ ] T030 [US2] Ensure TNCHistory loads from file on WebService startup in src/services/web_service.py
- [ ] T031 [US2] Handle missing history file gracefully (create empty) in src/models/tnc_history.py
- [ ] T032 [US2] Handle corrupted history file gracefully (log warning, use empty) in src/models/tnc_history.py
- [ ] T033 [US2] Add version field to history JSON format for future migrations in src/models/tnc_history.py

**Checkpoint**: User Story 2 complete - history persists across restarts

---

## Phase 5: User Story 3 - Add Friendly Names to TNCs (Priority: P2)

**Goal**: Users can assign custom names to TNCs for easy identification

**Independent Test**: Add TNC to history, edit friendly name, verify display name updates

### Tests for User Story 3

- [ ] T034 [P] [US3] Write integration test for PUT /api/tnc-history/{address} endpoint in tests/integration/test_history_api.py

### Implementation for User Story 3

- [ ] T035 [US3] Implement PUT /api/tnc-history/{address} endpoint in src/services/web_service.py
- [ ] T036 [US3] Add display_name property to TNCDevice (friendly_name or bluetooth_name) in src/models/tnc_history.py
- [ ] T037 [US3] Add "Edit" button for each TNC in history list in src/web/templates/status.html
- [ ] T038 [US3] Add inline edit form for friendly name in src/web/templates/status.html
- [ ] T039 [US3] Add JavaScript handler to save friendly name via PUT endpoint in src/web/templates/status.html
- [ ] T040 [US3] Validate friendly_name length (1-50 chars) in src/services/web_service.py

**Checkpoint**: User Story 3 complete - users can customize TNC display names

---

## Phase 6: User Story 4 - Remove TNCs from History (Priority: P2)

**Goal**: Users can remove unused TNCs from history list

**Independent Test**: Add TNC to history, remove it, verify it no longer appears

### Tests for User Story 4

- [ ] T041 [P] [US4] Write integration test for DELETE /api/tnc-history/{address} endpoint in tests/integration/test_history_api.py
- [ ] T042 [P] [US4] Write integration test for delete prevention of current target in tests/integration/test_history_api.py

### Implementation for User Story 4

- [ ] T043 [US4] Implement DELETE /api/tnc-history/{address} endpoint in src/services/web_service.py
- [ ] T044 [US4] Prevent deletion of currently active TNC (return 409 Conflict) in src/services/web_service.py
- [ ] T045 [US4] Add "Remove" button for each TNC in history list in src/web/templates/status.html
- [ ] T046 [US4] Add confirmation dialog before removal in src/web/templates/status.html
- [ ] T047 [US4] Add JavaScript handler to remove TNC via DELETE endpoint in src/web/templates/status.html

**Checkpoint**: User Story 4 complete - users can manage history list

---

## Phase 7: User Story 5 - Show Connection Status in History (Priority: P3)

**Goal**: Users can see which TNC is active and when each was last used

**Independent Test**: Connect to TNC, view history, verify "Active" indicator and timestamp

### Tests for User Story 5

- [ ] T048 [P] [US5] Write unit test for last_used timestamp update on selection in tests/unit/test_tnc_history.py

### Implementation for User Story 5

- [ ] T049 [US5] Update last_used timestamp when TNC is selected in src/services/web_service.py
- [ ] T050 [US5] Add "Active" badge styling for current TNC in src/web/templates/status.html
- [ ] T051 [US5] Add "Last used: [timestamp]" display for each TNC in src/web/templates/status.html
- [ ] T052 [US5] Add "Not paired" warning badge for unpaired TNCs in src/web/templates/status.html
- [ ] T053 [US5] Format timestamps in user-friendly relative format (e.g., "2 hours ago") in src/web/templates/status.html

**Checkpoint**: User Story 5 complete - full status visibility in history

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup and documentation

- [ ] T054 [P] Implement POST /api/tnc-history endpoint for manual TNC addition in src/services/web_service.py
- [ ] T055 [P] Add TNC history API documentation to docs/api.md
- [ ] T056 [P] Add TNC history section to docs/web-interface.md
- [ ] T057 Run ruff check and fix any linting issues in src/models/tnc_history.py
- [ ] T058 Run mypy type check on src/models/tnc_history.py
- [ ] T059 Run pytest with coverage, ensure >80% for new code
- [ ] T060 Manual end-to-end test: pair 2 TNCs, switch between them, restart daemon, verify history
- [ ] T061 Update docs/configuration.md with history_file option

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - Core MVP functionality
- **User Story 2 (Phase 4)**: Depends on Foundational - Can parallel with US1
- **User Story 3 (Phase 5)**: Depends on Foundational - Can parallel with US1/US2
- **User Story 4 (Phase 6)**: Depends on Foundational - Can parallel with US1/US2/US3
- **User Story 5 (Phase 7)**: Depends on Foundational - Can parallel with others
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

| Story | Priority | Can Start After | Dependencies on Other Stories |
|-------|----------|-----------------|------------------------------|
| US1 - Quick Switch | P1 | Phase 2 | None - MVP |
| US2 - Persistence | P1 | Phase 2 | None - independent |
| US3 - Friendly Names | P2 | Phase 2 | None - independent |
| US4 - Remove TNCs | P2 | Phase 2 | None - independent |
| US5 - Status Display | P3 | Phase 2 | None - independent |

### Within Each User Story

1. Tests written first (if included)
2. Backend API implementation
3. Frontend UI implementation
4. Integration and validation

### Parallel Opportunities

**Phase 1 (Setup)**:
- T002 and T003 can run in parallel

**Phase 2 (Foundational)**:
- T012, T013, T014 (unit tests) can run in parallel after models complete

**After Phase 2 completes**:
- All user stories (US1-US5) can be worked on in parallel by different developers
- Within each story, tests marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch tests in parallel:
Task: "Write integration test for GET /api/tnc-history in tests/integration/test_history_api.py"
Task: "Write integration test for POST /api/tnc-history/{address}/select in tests/integration/test_history_api.py"

# Then implement sequentially:
# Backend first → Frontend second
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (TNCHistory model with persistence)
3. Complete Phase 3: User Story 1 (Quick Switch)
4. Complete Phase 4: User Story 2 (Persistence)
5. **STOP and VALIDATE**: Test switching between TNCs, restart daemon
6. Deploy MVP

### Incremental Delivery

1. MVP (US1 + US2) → Core switching functionality
2. Add US3 → Friendly names for better UX
3. Add US4 → History management
4. Add US5 → Status visibility
5. Polish → Documentation and cleanup

---

## Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 - Setup | T001-T003 | Create files and structure |
| 2 - Foundational | T004-T014 | TNCHistory model with CRUD and tests |
| 3 - US1 Quick Switch | T015-T027 | Core switching functionality (MVP) |
| 4 - US2 Persistence | T028-T033 | Survive restarts |
| 5 - US3 Friendly Names | T034-T040 | Custom naming |
| 6 - US4 Remove TNCs | T041-T047 | History management |
| 7 - US5 Status Display | T048-T053 | Status visibility |
| 8 - Polish | T054-T061 | Documentation and cleanup |

**Total Tasks**: 61
**MVP Tasks (US1 + US2)**: 33 tasks (Phases 1-4)
