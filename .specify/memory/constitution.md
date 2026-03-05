<!--
================================================================================
SYNC IMPACT REPORT
================================================================================
Version Change: N/A (initial) → 1.0.0
Bump Rationale: Initial constitution adoption - MAJOR version 1.0.0

Modified Principles: N/A (initial adoption)

Added Sections:
  - Core Principles (4 principles: Code Quality, Testing Standards, UX Consistency, Performance)
  - Development Workflow
  - Quality Gates
  - Governance

Removed Sections: N/A (initial adoption)

Templates Requiring Updates:
  - .specify/templates/plan-template.md: ✅ Compatible (Constitution Check section exists)
  - .specify/templates/spec-template.md: ✅ Compatible (Success Criteria aligns with principles)
  - .specify/templates/tasks-template.md: ✅ Compatible (Test phases align with Testing principle)

Deferred Items: None
================================================================================
-->

# Pi-BT-Bridge Constitution

## Core Principles

### I. Code Quality

All code MUST meet the following quality standards:

- **Readability**: Code MUST be self-documenting with clear variable/function names.
  Functions exceeding 50 lines MUST be refactored or justified in code comments.
- **Type Safety**: All public interfaces MUST have explicit type annotations.
  Dynamic typing is permitted only in internal implementation details.
- **Error Handling**: All external interfaces (Bluetooth, serial, network) MUST have
  explicit error handling. Silent failures are prohibited.
- **Documentation**: All public APIs MUST have docstrings describing purpose,
  parameters, return values, and potential exceptions.
- **Linting**: Code MUST pass configured linting rules with zero warnings before merge.

**Rationale**: Bluetooth bridging involves complex state management across multiple
protocols. Clear, well-documented code prevents protocol mismatches and simplifies
debugging of hardware interactions.

### II. Testing Standards

Testing is MANDATORY for all functional code:

- **Unit Tests**: All service/business logic MUST have unit tests with minimum 80%
  line coverage. Hardware abstraction layers MUST be mockable.
- **Integration Tests**: Bluetooth pairing flows, serial communication paths, and
  bridge handoff scenarios MUST have integration tests using hardware simulators
  or mock devices.
- **Contract Tests**: Protocol boundaries (BLE GATT services, Classic SPP profiles,
  KISS framing) MUST have contract tests verifying spec compliance.
- **Test Independence**: Each test MUST be independently runnable without relying
  on test execution order or shared mutable state.
- **Regression Prevention**: Every bug fix MUST include a test that would have caught
  the bug.

**Rationale**: Ham radio communication relies on precise protocol adherence. Untested
code risks data corruption or connection failures that could interrupt emergency
communications.

### III. User Experience Consistency

User-facing behavior MUST be predictable and consistent:

- **Connection States**: All Bluetooth connection states MUST be clearly communicated
  to the user (scanning, connecting, connected, disconnected, error).
- **Error Messages**: Error conditions MUST produce actionable messages indicating
  what failed and suggested remediation steps.
- **Graceful Degradation**: Partial failures (e.g., one Bluetooth link active)
  MUST NOT crash the application. Degraded modes MUST be communicated clearly.
- **Configuration**: User-configurable settings MUST persist across restarts.
  Defaults MUST be sensible for common ham radio KISS TNC configurations.
- **Feedback Latency**: User actions MUST produce visible feedback within 200ms.
  Long operations MUST show progress indication.

**Rationale**: Ham radio operators often use this bridge in field conditions where
debugging is difficult. Consistent, informative UX reduces operator frustration
and speeds troubleshooting.

### IV. Performance Requirements

The bridge MUST meet these performance targets:

- **Latency**: End-to-end packet latency (BLE to Classic) MUST NOT exceed 100ms
  for packets under 256 bytes under normal conditions.
- **Throughput**: Bridge MUST sustain minimum 9600 baud equivalent throughput
  (960 bytes/second) to support standard KISS TNC speeds.
- **Memory**: Application memory footprint MUST NOT exceed 64MB on target
  Raspberry Pi hardware.
- **Startup Time**: Application MUST be ready to accept connections within 5 seconds
  of launch on target hardware.
- **Battery Impact**: When running on battery-powered Pi, idle power consumption
  MUST be optimized (BLE advertising intervals, sleep states).

**Rationale**: Ham radio packet operations have timing constraints. Excessive latency
causes protocol timeouts; insufficient throughput creates bottlenecks for standard
1200/9600 baud packet operations.

## Development Workflow

All development MUST follow this workflow:

1. **Branch Strategy**: Feature branches MUST be created from main. Branch names
   MUST follow pattern: `[issue-number]-short-description`.
2. **Commit Standards**: Commits MUST be atomic and focused. Commit messages MUST
   follow conventional commits format (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).
3. **Code Review**: All changes MUST be reviewed before merge. Reviews MUST verify
   compliance with all four Core Principles.
4. **CI/CD Gates**: All tests MUST pass. Linting MUST pass. Coverage MUST NOT
   decrease without justification.

## Quality Gates

Before any release, the following gates MUST pass:

| Gate | Requirement | Measured By |
|------|-------------|-------------|
| Unit Tests | 100% pass, >=80% coverage | CI test runner |
| Integration Tests | 100% pass | CI test runner |
| Linting | Zero warnings | Linter output |
| Performance | Latency <100ms, throughput >=960 B/s | Benchmark suite |
| Documentation | All public APIs documented | Doc coverage tool |

## Governance

This constitution supersedes all other development practices for the Pi-BT-Bridge
project.

### Amendment Process

1. Proposed amendments MUST be documented in a pull request with rationale.
2. Amendments MUST include a migration plan for existing code if principles change.
3. Version number MUST be updated according to semantic versioning:
   - **MAJOR**: Removal or incompatible redefinition of principles
   - **MINOR**: New principles added or material expansion of guidance
   - **PATCH**: Clarifications, wording improvements, non-semantic changes

### Compliance Review

- All pull requests MUST include a Constitution Compliance statement.
- Complexity that violates principles MUST be explicitly justified in the PR.
- Quarterly reviews SHOULD assess overall codebase compliance.

### Runtime Guidance

For day-to-day development decisions not covered by this constitution, consult
project documentation in `docs/` and established patterns in the existing codebase.

**Version**: 1.0.0 | **Ratified**: 2026-03-04 | **Last Amended**: 2026-03-04
