---
phase: 01-foundation
plan: 01
subsystem: testing
tags: [pytest, openpyxl, config, spreadsheet, tdd]

# Dependency graph
requires: []
provides:
  - "config.py spreadsheet constants (PLANILHA_EMPRESAS, PLANILHA_COL_COD, PLANILHA_COL_ANALISTA)"
  - "tests/ Python package with conftest.py tmp_xlsx fixture"
  - "8 test stubs for services/spreadsheet.py covering PLAN-01 through PLAN-05"
affects: [01-02, services/spreadsheet]

# Tech tracking
tech-stack:
  added: [pytest 9.0.2]
  patterns: [TDD red-phase stubs with try/except import guard + pytestmark skipif for clean collection]

key-files:
  created:
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_spreadsheet.py
  modified:
    - config.py

key-decisions:
  - "Import guard uses try/except + pytestmark skipif instead of bare import to allow pytest collection before services/spreadsheet.py exists"
  - "8 test functions total (plan says 7 behaviors but test_missing_analista_header_raises_format_error is included as additional PLAN-03 coverage)"

patterns-established:
  - "TDD stub pattern: try/except import with pytestmark skipif keeps tests collectable in RED phase"
  - "conftest.py factory fixture pattern: tmp_xlsx(rows, headers=None) returns Path to in-memory XLSX"

requirements-completed: [PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05]

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 1 Plan 01: Test Infrastructure and Config Constants Summary

**pytest test infrastructure for spreadsheet service with 8 collected stubs, openpyxl tmp_xlsx fixture, and 3 config constants added to config.py**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T18:26:07Z
- **Completed:** 2026-03-09T18:28:33Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added PLANILHA_EMPRESAS (Path), PLANILHA_COL_COD (int 0), PLANILHA_COL_ANALISTA (int 3) constants to config.py PATHS section
- Installed pytest 9.0.2 (openpyxl was already present)
- Created tests/ package with __init__.py, conftest.py factory fixture using openpyxl Workbook(), and 8 test stubs for spreadsheet service
- All 8 tests are collected by pytest and correctly skip (RED phase) until Plan 02 implements services/spreadsheet.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Add spreadsheet constants to config.py and install pytest** - `6a6e09a` (feat)
2. **Task 2: Create test infrastructure — tests/__init__.py, conftest.py, test_spreadsheet.py stubs** - `18990a7` (test)

**Plan metadata:** (docs commit follows)

_Note: Task 2 is the TDD RED phase — tests are collected and skipped until services/spreadsheet.py is implemented in Plan 02_

## Files Created/Modified
- `config.py` - Added PLANILHA_EMPRESAS, PLANILHA_COL_COD, PLANILHA_COL_ANALISTA after RELATORIO_CSV in PATHS section
- `tests/__init__.py` - Empty file making tests/ a Python package
- `tests/conftest.py` - tmp_xlsx factory fixture using openpyxl Workbook() for in-memory XLSX creation
- `tests/test_spreadsheet.py` - 8 test stubs covering PLAN-01 through PLAN-05 with try/except import guard

## Decisions Made
- Import guard uses try/except + pytestmark skipif instead of bare import to allow pytest collection before services/spreadsheet.py exists. The bare import caused "ERROR collecting" which blocked pytest from listing test names. The skipif approach allows `--collect-only` to show all 8 test names.
- 8 test functions total: plan behavior section lists 7 but the actual code spec includes `test_missing_analista_header_raises_format_error` as additional PLAN-03 coverage for both COD and ANALISTA header validation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added try/except import guard with pytestmark skipif**
- **Found during:** Task 2 (test infrastructure creation)
- **Issue:** Bare `from services.spreadsheet import ...` at module level caused `ERROR collecting tests/test_spreadsheet.py` — pytest could not list test items at all. The plan says "if collection fails entirely, wrap the import" as an explicit fallback.
- **Fix:** Wrapped import in try/except, set `_SPREADSHEET_AVAILABLE` flag, added `pytestmark = pytest.mark.skipif(...)` so all 8 tests are collected and marked skip
- **Files modified:** tests/test_spreadsheet.py
- **Verification:** `pytest tests/test_spreadsheet.py --collect-only -q` shows 8 test items collected; `pytest tests/test_spreadsheet.py -v` shows 8 skipped
- **Committed in:** 18990a7 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix was explicitly anticipated in plan instructions ("if collection fails entirely, wrap the import"). No scope creep.

## Issues Encountered
- Initial bare import caused collection failure (exit code 2, 0 tests collected). Fixed per plan's explicit fallback instructions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- config.py constants ready for use in services/spreadsheet.py
- Test contract fully defined: 8 test functions covering all 5 requirements
- pytest infrastructure in place — Plan 02 can immediately implement services/spreadsheet.py and turn the 8 skipped tests green
- No blockers for Plan 02 execution

---
*Phase: 01-foundation*
*Completed: 2026-03-09*

## Self-Check: PASSED

- FOUND: config.py
- FOUND: tests/__init__.py
- FOUND: tests/conftest.py
- FOUND: tests/test_spreadsheet.py
- FOUND: .planning/phases/01-foundation/01-01-SUMMARY.md
- FOUND: commit 6a6e09a (feat: config constants + pytest install)
- FOUND: commit 18990a7 (test: test infrastructure RED phase)
