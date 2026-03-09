---
phase: 02-batch-orchestrator
plan: 01
subsystem: testing
tags: [pytest, unittest.mock, threading, queue, tdd]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: tests/conftest.py with tmp_xlsx fixture and test_spreadsheet.py pattern to mirror
provides:
  - tests/test_batch_orchestrator.py with 8 test stubs covering PROC-01 through PROC-04
affects: [02-02, 03-batch-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - try/except import guard + pytestmark skipif allows pytest collection before implementation exists
    - FakeProcessor inner class injects behaviour into WorkflowProcessor constructor callbacks
    - threading.Thread + queue.Queue in test_manual_review_queue_event_protocol drives the event protocol without blocking the test thread

key-files:
  created:
    - tests/test_batch_orchestrator.py
  modified: []

key-decisions:
  - "Test stubs use pytestmark skipif (not xfail) — matches test_spreadsheet.py pattern established in Phase 1"
  - "FakeProcessor preferred over unittest.mock.patch for PROC-03 test — inner class gives direct access to abrir_tela_manual_fn callback captured at __init__"
  - "test_abort_stops_after_current_company calls abort() BEFORE run() — simplest deterministic approach; avoids threading races in stub phase"
  - "monkeypatch.setattr on services.batch_orchestrator.montar_cabecalho used in overflow test — isolates TXT file save from core.txt_builder dependency"

patterns-established:
  - "Pattern 1: FakeProcessor inner class — captures constructor callbacks for fine-grained control without unittest.mock complexity"
  - "Pattern 2: _drain_queue helper — collect all queue messages after synchronous run for assertion"
  - "Pattern 3: background threading.Thread in PROC-03 test — allows event.wait() to block worker while test thread drives queue interaction"

requirements-completed: [PROC-01, PROC-02, PROC-03, PROC-04]

# Metrics
duration: 1min
completed: 2026-03-09
---

# Phase 2 Plan 01: Batch Orchestrator Test Stubs Summary

**8 pytest stubs covering BatchOrchestrator's queue+Event threading contract (PROC-01 through PROC-04) using try/except import guard so collection passes before services/batch_orchestrator.py exists**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-09T19:03:21Z
- **Completed:** 2026-03-09T19:04:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created tests/test_batch_orchestrator.py with 8 test stubs
- All 8 tests collected by pytest without ImportError or SyntaxError
- All 8 tests reported as SKIPPED (import guard active; module not yet implemented)
- Existing 8 tests in test_spreadsheet.py remain green (no regression)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write test_batch_orchestrator.py with 8 failing stubs** - `9e94e5f` (test)

## Files Created/Modified

- `tests/test_batch_orchestrator.py` - 8 test stubs for BatchOrchestrator: PROC-01 (sequential processing), PROC-02 (error continues loop + None=skipped), PROC-03 (queue+Event manual review protocol), PROC-04 (abort before run), and 3 supporting correctness tests (TXT save, overflow TXT, BatchSummary counts)

## Decisions Made

- Used pytestmark skipif (not xfail) to match the exact pattern established in test_spreadsheet.py (Phase 1)
- Used FakeProcessor inner class instead of unittest.mock.patch for most tests — captures abrir_tela_manual_fn at __init__ directly, making the PROC-03 threading test straightforward
- test_abort_stops_after_current_company calls abort() before run() — deterministic, race-condition-free approach matching the plan's "recommended approach" note
- monkeypatch.setattr on services.batch_orchestrator.montar_cabecalho in overflow test to isolate from core.txt_builder

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- tests/test_batch_orchestrator.py is the complete executable specification for Plan 02
- Plan 02 must create services/batch_orchestrator.py implementing BatchOrchestrator, BatchSummary, and CompanyResult
- When services/batch_orchestrator.py is created, all 8 tests should transition from SKIPPED to PASSED (or FAILED if implementation is wrong)
- Blocker (from Phase 1): Thread-safe manual review dialog (PROC-03) requires careful queue.Queue + threading.Event coordination

---
*Phase: 02-batch-orchestrator*
*Completed: 2026-03-09*
