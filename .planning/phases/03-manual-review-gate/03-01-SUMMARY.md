---
phase: 03-manual-review-gate
plan: "01"
subsystem: api
tags: [threading, review-gate, fastapi, pydantic, tdd]

# Dependency graph
requires:
  - phase: 02-job-lifecycle
    provides: JobManager singleton, _run_job worker thread, abrir_tela_manual_fn stub
provides:
  - ReviewItem, ReviewSubmission, ReviewResponse Pydantic models in api/models.py
  - JobStatusResponse extended with review_item: ReviewItem | None field
  - threading.Event review gate in job_manager blocking on event.wait(timeout=300)
  - POST /jobs/{id}/review endpoint with auth, 404/403/409/422 checks
  - JobManager.submit_review() method to wake blocked worker
  - get_status() excludes review_event, review_result, review_dados_base
affects:
  - 03-manual-review-gate (frontend review form uses review_item shape and POST /review)
  - Phase 4 download endpoint (no changes, but job lifecycle is now extended)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - threading.Event + result_holder[0] pattern for blocking worker gate
    - Import montar_linha_txt inside submit_review() (not at module top) to stay G-drive import linter safe
    - get_status() exclusion filter pattern: exclude internal/heavy keys from serialized copy

key-files:
  created:
    - tests/test_review_gate.py
  modified:
    - api/models.py
    - api/job_manager.py
    - api/jobs.py
    - tests/test_jobs.py

key-decisions:
  - "event.wait(timeout=300) called OUTSIDE _lock to prevent deadlock — worker releases lock before blocking"
  - "status='running' is set by the worker after event.wait() returns, NOT by submit_review() — avoids race"
  - "montar_linha_txt / montar_linha_txt_n8n called inside submit_review() with stored dados_base — frontend sends raw item_lc/ddd only"
  - "_extract_descricao and _extract_municipio are module-level helpers; no services.ibge import in API layer"

patterns-established:
  - "Review gate: store review_item (public) + review_event/review_result/review_dados_base (internal, excluded from get_status)"
  - "Timeout auto-accepts AI suggestion and logs 'Auto-aceito por timeout: {chave_nfse}' to recent_logs"

requirements-completed: [PROC-03, PROC-04]

# Metrics
duration: 6min
completed: 2026-03-30
---

# Phase 3 Plan 01: Manual Review Gate Summary

**threading.Event review gate replacing auto-accept stub: job pauses at review_needed, analyst submits Item LC via POST /review, worker resumes — with 5-minute timeout auto-accepting AI suggestion**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-30T19:31:29Z
- **Completed:** 2026-03-30T19:37:00Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 4 modified, 1 created

## Accomplishments
- ReviewItem, ReviewSubmission, ReviewResponse Pydantic models added to api/models.py
- JobStatusResponse extended with `review_item: ReviewItem | None = None`
- Real blocking review gate implemented in `abrir_tela_manual_fn` with `threading.Event.wait(timeout=300)`
- `JobManager.submit_review()` wakes blocked worker, builds TXT line server-side with stored dados_base
- `POST /jobs/{id}/review` endpoint with proper auth (404/403/409/422)
- `get_status()` updated to exclude internal threading objects from serialized response
- 12 new review gate tests (all passing) + 1 new test in test_jobs.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic models and review gate tests (RED)** - `4205f78` (test)
2. **Task 2: Review gate implementation and review endpoint (GREEN)** - `2dbcfe1` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD tasks have two commits: test (RED) then feat (GREEN)_

## Files Created/Modified
- `api/models.py` - Added ReviewItem, ReviewSubmission, ReviewResponse; extended JobStatusResponse with review_item field
- `api/job_manager.py` - Added _extract_descricao/_extract_municipio helpers; replaced auto-accept stub with real gate; added submit_review(); updated get_status() exclusion filter
- `api/jobs.py` - Added POST /jobs/{id}/review endpoint; updated get_job_status to pass review_item through
- `tests/test_review_gate.py` - 12 tests covering full review gate lifecycle
- `tests/test_jobs.py` - Added test_get_status_review_item_null_when_running

## Decisions Made
- `event.wait(timeout=300)` called outside `_lock` to prevent deadlock — workers must not hold the lock while blocking
- `status="running"` is set by the worker after `event.wait()` returns, NOT by `submit_review()` — this avoids a race condition where the endpoint could mark the job running before the worker cleans up
- `montar_linha_txt` / `montar_linha_txt_n8n` called inside `submit_review()` with the stored `dados_base` — frontend only sends raw `item_lc` and `ddd` values
- `_extract_descricao` and `_extract_municipio` are module-level helpers that do NOT call `services.ibge` — keeps the API layer side-effect-free

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test patch target for montar_linha_txt**
- **Found during:** Task 2 (GREEN phase, running test_submit_review_gate_resumes)
- **Issue:** Test used `patch("api.job_manager.montar_linha_txt")` but the function is imported dynamically inside submit_review(), so the patch target was the source module
- **Fix:** Changed patch to `patch("core.txt_builder.montar_linha_txt")`
- **Files modified:** tests/test_review_gate.py
- **Verification:** Test passes after fix
- **Committed in:** `2dbcfe1` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug in test patch target)
**Impact on plan:** Trivial fix, no scope change.

## Issues Encountered
- `test_deps.py::test_invalid_jwt_raises_401` and `test_deps.py::test_expired_jwt_raises_401` fail due to pre-existing network unavailability (`test.supabase.co` DNS resolution fails in this environment). Confirmed pre-existing by checking git stash. Not caused by this plan's changes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Review gate backend is complete and tested
- Phase 3 Plan 02 (frontend review form) can use the `review_item` field shape from `GET /jobs/{id}/status` and `POST /jobs/{id}/review` endpoint contract
- `review_item` fields: `chave_nfse`, `descricao`, `municipio`, `item_lc_original`, `from_n8n`, `suggested_item_lc`, `timeout_at`

---
*Phase: 03-manual-review-gate*
*Completed: 2026-03-30*
