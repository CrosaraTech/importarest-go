---
phase: 04-output-delivery
plan: 02
subsystem: testing-and-frontend-spec
tags: [byte-fidelity, pytest, lovable-spec, download-ui, frnt-04, outp-01]
dependency_graph:
  requires: [04-01]
  provides: [byte-fidelity-scaffold, lovable-download-spec]
  affects: [frontend-generation, regression-testing]
tech_stack:
  added: []
  patterns: [parametrized-pytest-skip, fixture-directory-convention, authenticated-blob-download]
key_files:
  created:
    - tests/test_byte_fidelity.py
    - tests/fixtures/README.md
    - tests/fixtures/goiania/input/
    - tests/fixtures/goiania/expected/
    - tests/fixtures/aparecida/input/
    - tests/fixtures/aparecida/expected/
    - tests/fixtures/anapolis/input/
    - tests/fixtures/anapolis/expected/
    - tests/fixtures/brasilia/input/
    - tests/fixtures/brasilia/expected/
  modified:
    - .planning/phases/02-job-lifecycle/lovable-spec.md
decisions:
  - "Byte-fidelity tests use pytest.skip (not xfail) so they appear as SKIPPED not FAILED in CI until fixtures arrive"
  - "Download buttons use fetch+blob+createObjectURL pattern (not plain <a href>) to support JWT Authorization header"
  - "ResultsSection renders inline on same /jobs/:jobId page — no navigation to separate results route"
metrics:
  duration: "13 min"
  completed_date: "2026-03-31"
  tasks_completed: 2
  tasks_total: 3
  files_created: 11
  files_modified: 1
  checkpoint_at: "Task 3 — end-of-phase human verification"
---

# Phase 4 Plan 2: Byte-Fidelity Scaffold and Lovable Spec Update Summary

Parametrized byte-fidelity test scaffold for 4 municipalities (skip until fixtures arrive) plus Lovable spec Section 12 with authenticated download buttons and ResultsSection component spec.

## What Was Built

### Task 1 — Byte-Fidelity Test Scaffold

Created `tests/test_byte_fidelity.py` with 8 parametrized tests (4 municipalities x TXT + CSV). Tests use `pytest.skip` when no fixture files are present, so the suite stays green with an empty fixtures directory.

Created `tests/fixtures/{municipality}/{input,expected}/` directory structure for all 4 municipalities: goiania, aparecida, anapolis, brasilia.

Created `tests/fixtures/README.md` documenting filename conventions and the TODO implementation path for when the user provides reference files.

**Verification:** `pytest tests/test_byte_fidelity.py -v` — 8 skipped, 0 failed.

### Task 2 — Lovable Spec Results/Download Section

Added Section 12 "Results and Download Section — Phase 4 Addition (FRNT-04)" to `.planning/phases/02-job-lifecycle/lovable-spec.md`.

Key spec decisions included:

- **State transition (12.1):** TanStack Query second query for `GET /jobs/{id}/files`, enabled only when `result_ready=true`, `staleTime: Infinity` since file list is stable.
- **Summary card (12.3):** Green/red card showing total/errors/skipped/processing_seconds; errors count in destructive red when > 0.
- **Download buttons (12.4):** Primary blue for main TXT, outline for CSV, conditional split-files subsection. All downloads use `fetch+blob+createObjectURL` pattern with `apiRequest()` for JWT support (plain `<a href>` can't send Authorization header).
- **"Novo Job" button (12.5):** Calls `navigate('/upload')` to reset page state.
- **API contract (12.7):** Full `GET /jobs/{id}/files` response example with split file entry.
- **Component checklist (12.8):** `ResultsSection`, `DownloadButton` new components; `JobProgress` update to wire the new query.

**Verification:** `grep -c "download\|ResultsSection\|Start New Job\|Novo Job" lovable-spec.md` → 31 matches.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | dcab1a4 | feat(04-02): add byte-fidelity test scaffold and fixture directories |
| 2 | 641a2bb | feat(04-02): add results/download section to Lovable spec (FRNT-04) |

## Deviations from Plan

None — plan executed exactly as written.

## Auth Gates

None.

## Checkpoint Reached

Task 3 is a `checkpoint:human-verify` gate. Execution paused here for end-of-phase verification.

**What to verify:**
1. `python -m pytest tests/ -x -q --ignore=tests/test_deps.py --ignore=tests/test_spreadsheet.py` — all tests pass (byte-fidelity tests will be skipped)
2. `python -m pytest tests/test_download.py -v` — all 13 download tests green
3. Review `lovable-spec.md` Section 12 — confirm download UI matches vision
4. Check `tests/fixtures/` directory structure exists for all 4 municipalities
5. When ready to add byte-fidelity test data, provide desktop-generated TXT+CSV files in the expected/ directories

## Self-Check: PASSED

- tests/test_byte_fidelity.py — FOUND
- tests/fixtures/README.md — FOUND
- tests/fixtures/goiania/expected — FOUND
- tests/fixtures/brasilia/expected — FOUND
- Commit dcab1a4 — FOUND
- Commit 641a2bb — FOUND
