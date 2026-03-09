---
phase: 01-foundation
plan: 02
subsystem: spreadsheet
tags: [openpyxl, xlsx, tdd, spreadsheet, data-access, exceptions]

# Dependency graph
requires:
  - phase: 01-foundation/01-01
    provides: "pytest infrastructure, conftest.py tmp_xlsx fixture, 8 test stubs, config.py spreadsheet constants"
provides:
  - "services/spreadsheet.py with load_analysts(), get_companies_for_analyst(), SpreadsheetError, SpreadsheetAccessError, SpreadsheetFormatError"
  - "Complete XLSX reader isolated from UI, threads, and network — suitable as data source for Phase 2 and 3"
affects: [02-individual, 03-batch, services/spreadsheet]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD green phase: implement minimal code to make 8 pre-existing stubs pass"
    - "Private helper _load_goiania_rows() opens/closes workbook fresh per call — avoids iter_rows exhaustion"
    - "Module-level import of PLANILHA_EMPRESAS enables monkeypatch.setattr in tests"
    - "Exception hierarchy: SpreadsheetError base, SpreadsheetAccessError (I/O), SpreadsheetFormatError (format)"

key-files:
  created:
    - services/spreadsheet.py
  modified: []

key-decisions:
  - "MUNICIPIO column position discovered dynamically via header_map (not hardcoded) — accepts accent variant MUNICÍPIO as fallback"
  - "GOIÂNIA filter uses str(municipio).strip().upper() == 'GOIÂNIA' — accent preserved, GOIANIA without accent does NOT match"
  - "COD type safety: str(cod).strip() always — Excel stores numeric cells as int which would cause key errors"
  - "wb.close() placed in finally block — workbook closed even on exception, prevents file handle leaks"

patterns-established:
  - "services/*.py: module-level functions (not classes), no tkinter/threading imports, from config import at top"
  - "Error messages in Portuguese naming the cause clearly with path, enabling user action"

requirements-completed: [PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05]

# Metrics
duration: 2min
completed: 2026-03-09
---

# Phase 1 Plan 02: Spreadsheet Service Summary

**openpyxl-based XLSX reader with header validation, GOIÂNIA filter, and Portuguese error messages — 8/8 tests green**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-09T18:31:38Z
- **Completed:** 2026-03-09T18:33:18Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments
- Implemented services/spreadsheet.py with load_analysts() and get_companies_for_analyst() as module-level functions
- All 8 test stubs from Plan 01 turned GREEN (was 8 skipped, now 8 passed)
- Header validation checks COD at index 0 (column A) and ANALISTA at index 3 (column D) per config constants
- MUNICIPIO column discovered dynamically — accepts accent variant MUNICÍPIO as fallback
- Three-tier exception hierarchy (SpreadsheetError > SpreadsheetAccessError / SpreadsheetFormatError) with Portuguese messages
- wb.close() in finally block — no file handle leaks even on exception

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement services/spreadsheet.py (TDD GREEN)** - `3139b14` (feat)

**Plan metadata:** (docs commit follows)

_Note: Plan is TDD — Task 1 is the GREEN phase turning 8 pre-existing stubs to passing_

## Files Created/Modified
- `services/spreadsheet.py` - XLSX reader with exceptions, header validation, GOIÂNIA filter, 173 lines

## Decisions Made
- MUNICIPIO column discovered dynamically via header_map (not hardcoded to index 2) so column order changes do not break the service. Fallback to "MUNICÍPIO" (with accent) via `header_map.get("MUNICIPIO") or header_map.get("MUNICÍPIO")`.
- GOIÂNIA comparison: `str(municipio).strip().upper() == "GOIÂNIA"` — accent required. "GOIANIA" without accent will not match (matches PLAN-02 truth).
- `str(cod).strip()` always applied — openpyxl returns numeric cells as int, not str.
- PermissionError caught as plain Python built-in before openpyxl's exception clause, since the OS raises it before openpyxl can wrap it.

## Deviations from Plan

None - plan executed exactly as written. All implementation decisions were specified in the plan's `<implementation>` block.

## Issues Encountered
None — all tests passed on first run.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- services/spreadsheet.py complete and tested in isolation
- All 5 requirements (PLAN-01 through PLAN-05) covered by 8 passing tests
- Phase 1 Foundation is now complete — both plans executed
- Phase 2 (individual processing) can use load_analysts() and get_companies_for_analyst() directly
- No blockers for Phase 2

---
*Phase: 01-foundation*
*Completed: 2026-03-09*

## Self-Check: PASSED

- FOUND: services/spreadsheet.py
- FOUND: .planning/phases/01-foundation/01-02-SUMMARY.md
- FOUND: commit 3139b14 (feat(01-02): implement services/spreadsheet.py)
- VERIFIED: 8/8 tests passing in tests/test_spreadsheet.py
- VERIFIED: All required exports present (load_analysts, get_companies_for_analyst, SpreadsheetError, SpreadsheetAccessError, SpreadsheetFormatError)
- VERIFIED: wb.close() in finally block, read_only=True, data_only=True, no tkinter/threading imports
