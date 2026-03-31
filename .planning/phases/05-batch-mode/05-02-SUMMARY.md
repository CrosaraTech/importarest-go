---
phase: 05-batch-mode
plan: "02"
subsystem: api
tags: [fastapi, batch, asyncio, pydantic, supabase, jwt]

# Dependency graph
requires:
  - phase: 05-batch-mode plan 01
    provides: BatchJobManager singleton, abort_job on JobManager, batch Pydantic models
  - phase: 02-job-lifecycle
    provides: job_manager singleton, GET /jobs/{id}/status, POST /jobs/{id}/review
  - phase: 03-manual-review-gate
    provides: review gate threading pattern for both individual and batch jobs
provides:
  - POST /batch endpoint (creates batch job, fetches companies from Supabase)
  - GET /batch/{id}/status endpoint (per-company progress, ETA, review_item)
  - POST /jobs/{id}/abort endpoint (handles both individual and batch jobs)
  - POST /jobs/{id}/review now dispatches to batch_job_manager when job not in job_manager
affects: [06-frontend, lovable-spec, batch-mode-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-registry dispatch: abort and review try job_manager first, batch_job_manager second"
    - "Supabase direct query in route handler (not HTTP round-trip) for company fetch"
    - "BatchCreateRequest as Pydantic BaseModel for JSON body (not Form fields)"

key-files:
  created:
    - api/batch.py
  modified:
    - api/jobs.py
    - api/main.py
    - tests/test_batch_api.py

key-decisions:
  - "POST /batch uses UPLOAD_TEMP_DIR as job_dir base; orchestrator skips companies without XML folders (matches desktop behavior)"
  - "POST /jobs/{id}/abort uses dual-registry dispatch (job_manager then batch_job_manager) — single endpoint for both job types per CONTEXT.md locked decision"
  - "POST /jobs/{id}/review fallthrough to batch_job_manager when job_manager.get_status returns None — avoids adding a separate /batch/{id}/review endpoint"
  - "batch_dir (UPLOAD_TEMP_DIR / batch_{id}) created after create_batch_job returns the batch_id"

patterns-established:
  - "Dual-registry dispatch pattern: try individual job_manager, fallback to batch_job_manager — reusable for any cross-type operation"
  - "BatchCreateRequest as JSON body (not Form) — batch creation is not a file upload, unlike POST /jobs"

requirements-completed: [PROC-05, PROC-06]

# Metrics
duration: 32min
completed: 2026-03-31
---

# Phase 5 Plan 02: Batch HTTP Endpoints Summary

**FastAPI batch mode HTTP layer: POST /batch, GET /batch/{id}/status, POST /jobs/{id}/abort (dual-registry), and batch review dispatch via existing POST /jobs/{id}/review**

## Performance

- **Duration:** 32 min
- **Started:** 2026-03-31T17:24:52Z
- **Completed:** 2026-03-31T17:56:32Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 4

## Accomplishments

- Created `api/batch.py` with POST /batch (Supabase company fetch, 404/409 handling) and GET /batch/{id}/status (ownership check, Pydantic serialization, review_item support)
- Added POST /jobs/{id}/abort endpoint to `api/jobs.py` using dual-registry dispatch (individual then batch), with proper 403/404 handling
- Updated POST /jobs/{id}/review to fall through to `batch_job_manager` when `job_manager.get_status` returns None, enabling the same endpoint for both job types
- Wired `batch_router` into `api/main.py` via `app.include_router`
- Extended `tests/test_batch_api.py` from 11 manager-level tests to 24 tests covering all new HTTP endpoints

## Task Commits

Each task was committed atomically:

1. **Task 1: POST /batch and GET /batch/{id}/status endpoints** - `57a17e7` (feat)
2. **Task 2: POST /jobs/{id}/abort and review dispatch for batch jobs** - `99a799f` (feat)

**Plan metadata:** (docs commit follows)

_Note: Both tasks followed TDD (RED → GREEN). Tests written before implementation._

## Files Created/Modified

- `api/batch.py` — New batch router: POST /batch (company fetch from Supabase, batch job creation) and GET /batch/{id}/status (per-company progress with ETA and review_item)
- `api/jobs.py` — Added `batch_job_manager` and `AbortResponse` imports; added POST /{id}/abort endpoint; updated submit_job_review for batch fallthrough
- `api/main.py` — Added `from api.batch import router as batch_router` and `app.include_router(batch_router)`
- `tests/test_batch_api.py` — Extended from 11 to 24 tests: 7 for POST/GET batch endpoints, 6 for abort, 1 for review dispatch

## Decisions Made

- **POST /batch uses UPLOAD_TEMP_DIR as job_dir:** The batch_id is generated inside `create_batch_job` so the dir cannot be named `batch_{id}` before the call. Using `UPLOAD_TEMP_DIR` as base is clean; a `batch_{id}` subdirectory is created post-creation for staging. The orchestrator processes from `UPLOAD_TEMP_DIR` and skips companies without XML subdirectories.
- **Dual-registry dispatch for abort:** Single `POST /jobs/{id}/abort` endpoint handles both individual and batch IDs, consistent with CONTEXT.md locked decision to use the same endpoint for both types.
- **Review fallthrough pattern:** Instead of adding a new `/batch/{id}/review` route, the existing `POST /jobs/{id}/review` was extended to try `batch_job_manager` when `job_manager.get_status` returns None. Zero new routes for frontend to handle.

## Deviations from Plan

None - plan executed exactly as written. The `job_dir` pre-generation limitation was anticipated by the plan ("Claude's discretion") and resolved using `UPLOAD_TEMP_DIR` as the base directory.

## Issues Encountered

None - all tests passed on first GREEN implementation run.

## User Setup Required

None - no external service configuration required. Batch endpoints use the same Supabase admin client and JWT auth already in place.

## Next Phase Readiness

- All batch HTTP endpoints are live: POST /batch, GET /batch/{id}/status, POST /jobs/{id}/abort, POST /jobs/{id}/review (batch dispatch)
- Frontend (Phase 6 / Lovable spec Section 13) can now call these endpoints
- Batch mode is fully functional end-to-end: manager layer (Plan 01) + HTTP layer (Plan 02) + review gate reuse (Phase 3)
- No blockers — full test suite green (110 passed, 8 skipped)

---
*Phase: 05-batch-mode*
*Completed: 2026-03-31*
