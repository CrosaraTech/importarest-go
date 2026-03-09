---
phase: 03-batch-ui-and-integration
plan: 01
subsystem: testing
tags: [tkinter, pytest, batch-panel, test-stubs, skipif, conftest]

# Dependency graph
requires:
  - phase: 02-batch-orchestrator
    provides: BatchSummary, CompanyResult dataclasses used in test_summary_lists_errors stub

provides:
  - tk_root session fixture in tests/conftest.py (shared Tk root for all batch panel tests)
  - 9 skipping test stubs in tests/test_batch_panel.py (SELEC-01..04, PROG-01..04, RESULT-02)
  - Behavior contract for PainelLote that Wave 2 must satisfy

affects: [03-batch-ui-and-integration Wave 2 — PainelLote implementation must make all 9 stubs pass]

# Tech tracking
tech-stack:
  added: [tkinter (stdlib)]
  patterns: [session-scoped tk_root fixture with withdraw()/destroy(), pytestmark skipif import guard]

key-files:
  created: [tests/test_batch_panel.py]
  modified: [tests/conftest.py]

key-decisions:
  - "tk_root fixture uses scope=session — one Tk root shared across all batch panel tests avoids multiple Tk() instantiation issues"
  - "root.withdraw() hides the window for headless test execution on Windows without blank Tk popup"
  - "pytestmark skipif (not xfail) — consistent with test_spreadsheet.py and test_batch_orchestrator.py patterns"
  - "BatchSummary/CompanyResult import wrapped in separate try/except guard — keeps file safe if run in isolation but both classes exist from Phase 2"

patterns-established:
  - "session-scoped tk_root fixture: @pytest.fixture(scope='session') with withdraw()/yield root/destroy() teardown"
  - "UI test stubs: pytestmark skipif on module-level import guard, pass body, filled in Wave 2"

requirements-completed: [SELEC-01, SELEC-02, SELEC-03, SELEC-04, PROG-01, PROG-02, PROG-03, PROG-04, RESULT-02]

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 3 Plan 01: Batch Panel Test Infrastructure Summary

**9 skipping test stubs for PainelLote UI (SELEC-01..04, PROG-01..04, RESULT-02) plus session-scoped tk_root fixture in conftest.py**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T19:25:37Z
- **Completed:** 2026-03-09T19:27:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `import tkinter as tk` and session-scoped `tk_root` fixture to `tests/conftest.py` with `withdraw()` for headless execution and `destroy()` teardown — existing fixtures unchanged
- Created `tests/test_batch_panel.py` with try/except import guard + `pytestmark skipif` pattern, 9 test stubs covering all batch panel behavior contracts
- Full test suite runs: `pytest tests/ -x -q` exits 0 with 16 passed, 9 skipped — zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add tk_root fixture to tests/conftest.py** - `d961fd7` (feat)
2. **Task 2: Create tests/test_batch_panel.py with 9 skipping stubs** - `ebfbb71` (test)

## Files Created/Modified

- `tests/conftest.py` - Added `import tkinter as tk` at top; appended `tk_root` session fixture with `withdraw()` and `destroy()`
- `tests/test_batch_panel.py` - New file: try/except import guard for `ui.batch_panel.PainelLote`, `pytestmark skipif`, 9 test stubs (pass body) for SELEC-01..04, PROG-01..04, RESULT-02

## Decisions Made

- `scope="session"` for `tk_root`: one Tk instance shared across all batch panel tests — avoids multiple Tk() instantiation issues that can cause segfaults on some platforms
- `root.withdraw()`: hides the Tk window so test suite runs headless on Windows without blank popup
- `pytestmark skipif` (not `xfail`): consistent with Phase 1 and Phase 2 test patterns — stubs skip cleanly until implementation exists
- Separate `_ORCH_OK` guard for `BatchSummary`/`CompanyResult`: keeps `test_batch_panel.py` safe if run before Phase 2 implementation exists, even though both classes already exist

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Test infrastructure for `PainelLote` is ready; Wave 2 can implement `ui/batch_panel.py` and run red-green against these 9 stubs
- `tk_root` fixture is available globally via `conftest.py` for all future UI test modules
- No blockers

---
*Phase: 03-batch-ui-and-integration*
*Completed: 2026-03-09*

## Self-Check: PASSED

- FOUND: tests/conftest.py (modified, tk_root appended)
- FOUND: tests/test_batch_panel.py (created, 9 stubs)
- FOUND: .planning/phases/03-batch-ui-and-integration/03-01-SUMMARY.md
- FOUND commit: d961fd7 (feat: tk_root fixture)
- FOUND commit: ebfbb71 (test: 9 batch panel stubs)
- pytest tests/test_batch_panel.py -x -q: 9 skipped, 0 failed, exit 0
