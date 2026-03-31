---
phase: 04-output-delivery
plan: "01"
subsystem: api
tags: [fastapi, download, csv, txt, encoding, tdd, pydantic]

requires:
  - phase: 03-manual-review-gate
    provides: "completed job state with ProcessorResult stored in job_manager"
  - phase: 02-job-lifecycle
    provides: "job_manager.get_status() and get_result() API, JobManager singleton"

provides:
  - "GET /jobs/{id}/download/txt — UTF-8 (no BOM) main TXT download endpoint"
  - "GET /jobs/{id}/download/csv — UTF-8-BOM semicolon CSV relatorio download endpoint"
  - "GET /jobs/{id}/download/txt/{vigencia} — per-vigencia split TXT with montar_cabecalho header"
  - "GET /jobs/{id}/files — JSON metadata listing all available downloads with summary stats"
  - "FileEntry, JobSummary, JobFilesResponse Pydantic models in api/models.py"

affects: [05-ui-frontend, 06-deployment]

tech-stack:
  added: []
  patterns:
    - "_get_completed_job_or_raise() helper: shared 404/403/409 auth guard for all download routes"
    - "_CSV_CABECALHO constant in api/jobs.py: avoids importing services.report (G-drive linter safe)"
    - "utf-8 (no BOM) for TXT, utf-8-sig (BOM) for CSV — enforced via encode() call"
    - "Split TXT vigencia key format: MMYYYY (e.g. '122024') converted to ISO date for montar_cabecalho"

key-files:
  created:
    - tests/test_download.py
  modified:
    - api/jobs.py
    - api/models.py

key-decisions:
  - "_CSV_CABECALHO defined as module-level constant in api/jobs.py rather than importing from services.report to avoid G-drive config.py load in api/ modules"
  - "Routes declared in order: /files, /download/txt, /download/csv, /download/txt/{vigencia} — exact-match before parameterized to prevent FastAPI path ambiguity"
  - "emp_cod and vigencia read from job_state (job_manager.get_status()) NOT from ProcessorResult — ProcessorResult lacks those fields"
  - "errors count in JobSummary uses row[4] != 'OK' (Status column index 4 per _CABECALHO)"

patterns-established:
  - "Download routes: _get_completed_job_or_raise() centralises access control — all 4 routes use it"
  - "TDD: RED commit (failing tests) then GREEN commit (implementation) per plan TDD task type"

requirements-completed: [OUTP-01, OUTP-02, OUTP-03, FRNT-04]

duration: 46min
completed: 2026-03-31
---

# Phase 4 Plan 01: Download Endpoints Summary

**Four download endpoints + file metadata route delivering UTF-8 TXT, UTF-8-BOM CSV, and per-vigencia split TXT files from completed ISS.NET processing jobs**

## Performance

- **Duration:** 46 min
- **Started:** 2026-03-31T12:59:17Z
- **Completed:** 2026-03-31T13:45:27Z
- **Tasks:** 2 (TDD — RED then GREEN)
- **Files modified:** 3 (api/jobs.py modified, tests/test_download.py created, api/models.py already had models)

## Accomplishments
- 13 new unit tests covering all 4 endpoints with auth checks (404/403/409), encoding verification, and header validation
- `GET /jobs/{id}/files` returns JSON metadata with job summary stats and full file list
- `GET /jobs/{id}/download/txt` returns UTF-8 (no BOM) byte stream with correct Content-Disposition
- `GET /jobs/{id}/download/csv` returns UTF-8-BOM encoded CSV with semicolon delimiter and 10-column header
- `GET /jobs/{id}/download/txt/{vigencia}` returns per-vigencia split TXT with `montar_cabecalho` as first line
- Zero regressions across full test suite (87 passing tests excluding 2 pre-existing failures unrelated to this plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing tests for download endpoints (RED)** - `4c27b79` (test)
2. **Task 2: Implement download endpoints (GREEN)** - `93f10d9` (feat)

**Plan metadata:** (added with this summary commit)

_Note: TDD tasks have separate test (RED) and implementation (GREEN) commits_

## Files Created/Modified
- `tests/test_download.py` — 13 tests for all 4 download endpoints with mock ProcessorResult
- `api/jobs.py` — 4 new routes, helper function, CSV header constant, updated imports
- `api/models.py` — FileEntry, JobSummary, JobFilesResponse models (already present from prior state)

## Decisions Made
- `_CSV_CABECALHO` defined as constant in `api/jobs.py` instead of importing from `services.report` — avoids G-drive config.py import in api/ modules (pre-existing project constraint)
- Route ordering: `/files` and `/download/txt` declared before `/download/txt/{vigencia}` to prevent FastAPI path ambiguity
- `emp_cod` and `vigencia` sourced from `job_state` (not `ProcessorResult`) — ProcessorResult contains only processing output, not job metadata
- errors count: rows where `row[4] != "OK"` (Status is the 5th column per `_CABECALHO`)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Two pre-existing test failures in `tests/test_spreadsheet.py::test_filters_goiania_only` and `tests/test_deps.py::test_invalid_jwt_raises_401` — confirmed pre-existing (failed before our changes) and unrelated to download functionality. Not fixed (out of scope per boundary rules).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 download endpoints are operational and tested
- Frontend (Phase 5) can consume: `GET /jobs/{id}/files` for file listing, then individual download URLs
- CSV encoding (UTF-8-BOM) ensures Excel opens correctly without manual encoding selection
- Split TXT files available for ISS.NET import of prior-period corrections

## Self-Check: PASSED

- FOUND: tests/test_download.py
- FOUND: api/jobs.py
- FOUND: .planning/phases/04-output-delivery/04-01-SUMMARY.md
- FOUND commit: 4c27b79 (RED phase)
- FOUND commit: 93f10d9 (GREEN phase)

---
*Phase: 04-output-delivery*
*Completed: 2026-03-31*
