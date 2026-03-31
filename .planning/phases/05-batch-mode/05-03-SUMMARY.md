---
phase: 05-batch-mode
plan: "03"
subsystem: ui
tags: [react, lovable, batch, frontend-spec, tanstack-query, supabase]

# Dependency graph
requires:
  - phase: 02-job-lifecycle
    provides: lovable-spec.md base spec (Phases 2-4 already appended)
  - phase: 03-manual-review-gate
    provides: ReviewCard component (reused as-is for batch review)
  - phase: 04-output-delivery
    provides: downloadWithAuth pattern (reused for per-company batch downloads)
  - phase: 05-batch-mode (plans 01-02)
    provides: BatchJobManager, POST /batch, GET /batch/{id}/status, POST /jobs/{id}/abort
provides:
  - "Lovable spec Section 13: complete batch processing dashboard specification"
  - "BatchDashboard component spec (creation form with analyst selector + company preview)"
  - "BatchProgress component spec (per-company table, ETA, abort, summary)"
  - "Phase 5 API contracts documented for Lovable frontend generation"
affects: [lovable-generated frontend, 05-batch-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Phase 5 frontend spec follows same addendum pattern as Phases 3 and 4"
    - "ReviewCard reuse in batch context: same component, different queryClient cache key"
    - "downloadWithAuth pattern extended to per-company batch downloads"

key-files:
  created: []
  modified:
    - .planning/phases/02-job-lifecycle/lovable-spec.md

key-decisions:
  - "Phase 5 spec is a self-contained addendum (Section 13) — no modifications to Sections 1-12"
  - "ReviewCard reused as-is; only queryKey changes from ['job-status', jobId] to ['batch-status', batchId]"
  - "Per-company download endpoints use /batch/{id}/company/{cod}/download/{type} path pattern"
  - "BatchProgress stops polling on both 'completed' and 'aborted' status"
  - "Individual upload form shows disabled state with message when analyst has active batch"

patterns-established:
  - "Batch component spec pattern: creation form (BatchDashboard) + progress view (BatchProgress) as two separate routes"
  - "Company-level status badge distinct from job-level status badge (CompanyStatusBadge vs StatusBadge)"

requirements-completed: [FRNT-05]

# Metrics
duration: 2min
completed: 2026-03-31
---

# Phase 5 Plan 03: Batch Processing Lovable Spec Summary

**Lovable spec extended with Section 13 covering BatchDashboard + BatchProgress components, per-company table with status/ETA/abort/review-reuse, and all Phase 5 API contracts**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-31T17:09:34Z
- **Completed:** 2026-03-31T17:11:57Z
- **Tasks:** 1 of 2 (Task 2 is human verification checkpoint)
- **Files modified:** 1

## Accomplishments
- Appended Phase 5 batch processing section (Section 13) to lovable-spec.md — 422 lines added
- BatchDashboard: analyst selector (from GET /companies unique analista values), vigencia, MEI, company preview list, Iniciar Lote button with 404/409 error handling
- BatchProgress: per-company progress table with 6 status badge variants, ETA footer (calc from eta_seconds), abort button with confirmation dialog, summary section with per-company download buttons
- Review gate reuse: Phase 3 ReviewCard embedded in BatchProgress when review_item is non-null, with correct cache invalidation for batch-status query key
- All API contracts documented inline: POST /batch, GET /batch/{id}/status, POST /jobs/{id}/abort, POST /jobs/{id}/review (reused)
- Updated type unions: JobStatus adds "aborted"; CompanyStatus and BatchStatus type unions defined

## Task Commits

1. **Task 1: Add batch processing section to Lovable spec** - `2d0c34e` (feat)

## Files Created/Modified
- `.planning/phases/02-job-lifecycle/lovable-spec.md` — Phase 5 addendum (Section 13): BatchDashboard, BatchProgress, API contracts, component checklist

## Decisions Made
- Section 13 follows same addendum pattern as Sections 11 (Phase 3) and 12 (Phase 4) — clearly marked "PHASE 5 ADDITION" in HTML comment header
- ReviewCard reused without modification; only the queryClient invalidation key changes (batch-status vs job-status)
- Per-company downloads use dedicated `/batch/{id}/company/{cod}/download/{type}` paths, with disabled+tooltip fallback if endpoints not yet deployed
- Abort button hidden on terminal states (completed/aborted); confirmation dialog prevents accidental abort

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — the spec was appended cleanly after the existing Section 12 (Phase 4). The lovable-spec.md file is gitignored but tracked via `git add -f`, consistent with prior Phase 4 commit (641a2bb).

## User Setup Required

None — this is a documentation/spec update only. No new environment variables or external services required.

## Next Phase Readiness

- Lovable spec complete with all 5 phases (Phase 2 base + Phase 3 review + Phase 4 downloads + Phase 5 batch)
- Ready for human verification (Task 2 checkpoint): run tests, review spec, optionally test API manually
- After human approval, Phase 5 is complete

---

## Self-Check

### Files Verified
- `.planning/phases/02-job-lifecycle/lovable-spec.md` — FOUND (confirmed by grep)
  - BatchDashboard mentions: 4
  - BatchProgress mentions: present
  - PHASE 5 ADDITION comment: present

### Commits Verified
- `2d0c34e` — FOUND (feat(05-03): add batch processing dashboard section to Lovable spec)

## Self-Check: PASSED

---
*Phase: 05-batch-mode*
*Completed: 2026-03-31*
