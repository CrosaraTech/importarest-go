---
phase: 05-batch-mode
plan: "01"
subsystem: api
tags: [batch, threading, pydantic, tdd, abort, review-gate, queue]

# Dependency graph
requires:
  - phase: 03-manual-review-gate
    provides: threading.Event review gate pattern reused for batch review pausing
  - phase: 02-job-lifecycle
    provides: JobManager._analyst_jobs shared registry, WorkflowProcessor threading pattern
provides:
  - BatchJobManager class with create/abort/status/review/download methods
  - Batch Pydantic models (BatchCompanyRow, BatchCreateResponse, BatchStatusResponse, AbortResponse)
  - JobManager.abort_job() for individual job abort support
  - Shared _analyst_jobs enforcement across batch and individual jobs
affects:
  - 05-02 (batch HTTP endpoints will call BatchJobManager)
  - 05-03 (Lovable frontend polls BatchStatusResponse shape)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - BatchJobManager mirrors JobManager threading pattern with queue-based consumer loop
    - ETA calculation from avg(completed_elapsed) * remaining_count
    - Shared _analyst_jobs dict between JobManager and BatchJobManager for one-job-per-analyst
    - Review gate in batch mode: same threading.Event pattern, event.wait() OUTSIDE _lock

key-files:
  created:
    - api/batch_manager.py
    - tests/test_batch_api.py
  modified:
    - api/models.py
    - api/job_manager.py
    - api/deps.py

key-decisions:
  - "BatchJobManager takes JobManager as constructor arg to share _analyst_jobs registry (not a global)"
  - "JobManager.create_job() raises ValueError when _analyst_jobs entry exists but job NOT in _jobs (means it is a batch job in another registry)"
  - "ETA formula: avg_elapsed_per_completed * remaining_count (matches desktop batch_panel.py)"
  - "BatchOrchestrator status 'ok' normalized to 'completed' in get_batch_status() for UI consistency"
  - "api/deps.py fixed to detect JWT alg from token header before attempting ES256 network call"

patterns-established:
  - "BatchJobManager._run_batch: starts BatchOrchestrator in nested thread, consumer loop reads queue"
  - "Internal fields excluded from get_batch_status: _orchestrator, review_event, review_result, review_dados_base"
  - "clean_modules fixture must NOT clear services.batch_orchestrator to avoid monkeypatch cross-test interference"

requirements-completed: [PROC-05, PROC-06]

# Metrics
duration: 6min
completed: 2026-03-31
---

# Phase 5 Plan 01: BatchJobManager and Abort Support Summary

**BatchJobManager with queue-consumer threading, per-company progress tracking, ETA calculation, and shared _analyst_jobs conflict enforcement across batch and individual jobs**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-31T17:09:19Z
- **Completed:** 2026-03-31T17:15:19Z
- **Tasks:** 2 (RED + GREEN TDD phases)
- **Files modified:** 5

## Accomplishments

- BatchJobManager class (api/batch_manager.py, 320+ lines) with create_batch_job, abort_batch, get_batch_status, submit_review, get_company_result, and _run_batch queue consumer
- Batch Pydantic models added to api/models.py: BatchCompanyRow, BatchCreateResponse, BatchStatusResponse, AbortResponse
- JobManager.abort_job() method with review gate unblocking
- Shared _analyst_jobs enforcement: both JobManager.create_job() and BatchJobManager.create_batch_job() check the same registry; conflict works bidirectionally
- 11 TDD tests all passing; full test suite green (97 passed, 8 skipped)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED phase — failing tests** - `02641bd` (test)
2. **Task 2: GREEN phase — implementation** - `b7d411a` (feat)

## Files Created/Modified

- `api/batch_manager.py` — BatchJobManager class with full lifecycle management
- `api/models.py` — BatchCompanyRow, BatchCreateResponse, BatchStatusResponse, AbortResponse models added
- `api/job_manager.py` — abort_job() method; improved _analyst_jobs conflict check for batch/individual cross-check
- `api/deps.py` — Fixed ES256 JWT handling to read alg from token header (pre-existing deviation fix)
- `tests/test_batch_api.py` — 11 unit tests for BatchJobManager and abort logic

## Decisions Made

- BatchJobManager takes JobManager as constructor argument to share the `_analyst_jobs` dict — enables bidirectional conflict enforcement without a global
- `JobManager.create_job()` now raises ValueError when `_analyst_jobs` has an entry not found in `_jobs` (i.e., it is a batch job) — this ensures one-active-job-per-analyst works across both job types
- ETA formula: `avg_elapsed_per_completed_companies * remaining_count` — matches desktop batch_panel.py behavior
- BatchOrchestrator sends status "ok" but UI/API uses "completed" — normalized in `_handle_queue_msg`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed JobManager.create_job() not blocking when batch job is active**
- **Found during:** GREEN phase — test_create_individual_conflict_with_batch
- **Issue:** `create_job()` looked up job status in `_jobs` dict; batch jobs live in `BatchJobManager._batches`, so their IDs returned `None` status, allowing the conflict check to pass silently
- **Fix:** Changed check to raise ValueError when `existing_status is None` (entry exists in `_analyst_jobs` but not in `_jobs` = active batch job in another registry)
- **Files modified:** api/job_manager.py
- **Verification:** test_create_individual_conflict_with_batch passes; no regressions in test_jobs.py
- **Committed in:** b7d411a (GREEN phase commit)

**2. [Rule 1 - Bug] Fixed api/deps.py ES256 JWT handling causing network call on wrong-secret HS256 tokens**
- **Found during:** Full test suite verification
- **Issue:** Pre-existing modification to deps.py added ES256 fallback that unconditionally tried a network call to Supabase JWKS when HS256 decoding failed, causing test_invalid_jwt_raises_401 to fail with ConnectError in offline environments
- **Fix:** Read JWT algorithm from token header first; only attempt ES256 JWKS fetch when token is actually ES256-signed
- **Files modified:** api/deps.py
- **Verification:** test_deps.py all 6 tests pass; test_invalid_jwt_raises_401 no longer makes network call
- **Committed in:** b7d411a (GREEN phase commit)

**3. [Rule 1 - Bug] Fixed clean_modules fixture clearing services.batch_orchestrator (cross-test monkeypatch interference)**
- **Found during:** Full test suite run — test_batch_orchestrator.py::test_run_processes_all_companies failed
- **Issue:** autouse fixture removed `services.batch_orchestrator` from sys.modules after each test; when test_batch_orchestrator's `monkeypatch.setattr` ran next, it patched the newly-loaded module instance while `BatchOrchestrator` objects held references to the old module's globals — the patch didn't affect the running orchestrator
- **Fix:** Removed `services.batch_orchestrator` from the list of modules to clear in clean_modules fixture
- **Files modified:** tests/test_batch_api.py
- **Verification:** All 8 test_batch_orchestrator tests pass; all 11 test_batch_api tests pass
- **Committed in:** b7d411a (GREEN phase commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 1 test infrastructure fix)
**Impact on plan:** All fixes necessary for correctness and test reliability. No scope creep.

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

- BatchJobManager is fully implemented and tested — Plan 02 (HTTP endpoints) can call `batch_job_manager.create_batch_job()`, `abort_batch()`, `get_batch_status()`, `submit_review()`
- BatchStatusResponse Pydantic model ready for use as endpoint response type
- AbortResponse model ready for `/abort` endpoints
- No blockers for Plan 02

## Self-Check: PASSED

- FOUND: api/batch_manager.py (517 lines, exceeds 150 min_lines requirement)
- FOUND: api/models.py (BatchStatusResponse present)
- FOUND: api/job_manager.py (abort_job method present)
- FOUND: tests/test_batch_api.py (11 tests, exceeds 100 min_lines requirement)
- FOUND: .planning/phases/05-batch-mode/05-01-SUMMARY.md
- COMMIT b7d411a: feat(05-01) GREEN phase — verified
- COMMIT 02641bd: test(05-01) RED phase — verified
- All 11 batch tests pass; 97 total tests pass (8 skipped, pre-existing)

---
*Phase: 05-batch-mode*
*Completed: 2026-03-31*
