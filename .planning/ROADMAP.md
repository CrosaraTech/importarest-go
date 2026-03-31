# Roadmap: ImportaREST GO Web

## Overview

This project migrates the ImportaREST GO desktop app to a web service. The strategy is wrap-not-rewrite: the existing ~3500 lines of Python processing logic are placed behind a FastAPI HTTP layer and exposed through a Lovable-generated React frontend backed by Supabase Auth. Phases 1-3 are strict sequential dependencies. Phases 4-6 unlock after Phase 3 but can overlap. The highest-risk phase is Phase 3 (manual review gate), which introduces the threading.Event suspend/resume pattern.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Config isolation, Supabase setup, company data migration, and analyst auth (completed 2026-03-26)
- [ ] **Phase 2: Job Lifecycle** - File upload, job creation, WorkflowProcessor wrapping, progress polling
- [ ] **Phase 3: Manual Review Gate** - Job suspend on low-confidence, inline review form, worker resume
- [x] **Phase 4: Output Delivery** - Byte-perfect TXT/CSV download and per-vigencia split files (completed 2026-03-31)
- [ ] **Phase 5: Batch Mode** - Multi-company batch jobs, per-company progress, job abort
- [ ] **Phase 6: n8n Compatibility and Hardening** - Classification proxy endpoint, rate limiting, operational verification

## Phase Details

### Phase 1: Foundation
**Goal**: Analysts can authenticate and the server starts cleanly without G: drive dependencies; company data is in Supabase
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, INFR-03, INFR-04, AUTH-01, AUTH-02, AUTH-03, DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):
  1. Analyst can sign up and log in with email and password, and session persists across browser refresh
  2. Multiple analysts can be logged in concurrently without interference
  3. FastAPI server starts and responds to GET /health without any G: drive path access
  4. Company registry data loaded from RELACAO_EMPRESAS XLSX is queryable in Supabase; analyst can filter by analyst name and municipality
  5. FastAPI reads company data from Supabase and returns a filtered list via GET /companies
**Plans:** 3/3 plans complete

Plans:
- [x] 01-01-PLAN.md — Config isolation, FastAPI scaffold, health endpoint, Redis Docker
- [x] 01-02-PLAN.md — Supabase auth dependency (JWT verification), migration script
- [x] 01-03-PLAN.md — GET /companies endpoint with filtering, end-of-phase verification

### Phase 2: Job Lifecycle
**Goal**: Analysts can upload NFS-e XML or ZIP files, trigger processing, and watch real-time progress
**Depends on**: Phase 1
**Requirements**: FILE-01, FILE-02, FILE-03, FILE-04, PROC-01, PROC-02, PROC-07, FRNT-01, FRNT-02
**Success Criteria** (what must be TRUE):
  1. Analyst can upload one or more XML files or a ZIP file, with company code, vigencia, and MEI toggle, and receive a job_id immediately
  2. Files are validated for type and non-empty content before the job is created; invalid uploads receive a clear error
  3. Analyst can poll job progress and see "X of N notes processed" and current status updating in real time
  4. When processing errors occur, analyst sees per-note error messages matching desktop app error detail
  5. WorkflowProcessor runs in a dedicated thread (not FastAPI threadpool) and produces the same output as the desktop app
**Plans:** 1/2 plans executed

Plans:
- [ ] 02-01-PLAN.md — Job models, manager with processor thread wrapper, upload and poll endpoints
- [ ] 02-02-PLAN.md — Lovable frontend specification and end-to-end verification

### Phase 3: Manual Review Gate
**Goal**: When AI flags a low-confidence classification, the job pauses and the analyst corrects the record inline; processing then resumes
**Depends on**: Phase 2
**Requirements**: PROC-03, PROC-04, FRNT-03
**Success Criteria** (what must be TRUE):
  1. When a low-confidence record is encountered, the job pauses and the poll response includes a review_item with service description, suggested Item LC, and editable fields
  2. Analyst submits a correction via the inline review form and the job resumes processing the remaining notes
  3. If the analyst closes the browser without reviewing, the job times out the review gate, marks the note as skipped, and continues automatically
**Plans:** 2 plans

Plans:
- [ ] 03-01-PLAN.md — Review gate backend: models, threading.Event gate, POST /review endpoint, tests
- [ ] 03-02-PLAN.md — Lovable spec addendum for review form and end-of-phase verification

### Phase 4: Output Delivery
**Goal**: Analysts can download the TXT REST and CSV audit files, with correct byte formatting and per-vigencia splits when applicable
**Depends on**: Phase 3
**Requirements**: OUTP-01, OUTP-02, OUTP-03, FRNT-04
**Success Criteria** (what must be TRUE):
  1. Analyst can download the TXT REST file and a byte-level diff against desktop-generated output for all 4 municipalities (Goiania, Aparecida, Anapolis, Brasilia) shows zero differences
  2. Analyst can download the CSV audit report with per-note processing details
  3. When notes fall outside the target vigencia, separate TXT files are generated per period and each is individually downloadable
  4. Results page shows download buttons for TXT and CSV immediately after job completion
**Plans:** 2/2 plans complete

Plans:
- [x] 04-01-PLAN.md — Download endpoints (TXT, CSV, split TXT, file metadata) with TDD unit tests
- [ ] 04-02-PLAN.md — Byte-fidelity test scaffold, Lovable spec results section, end-of-phase verification

### Phase 5: Batch Mode
**Goal**: Analysts can select an analyst name and vigencia to trigger a batch job that processes all companies, with per-company progress and job abort
**Depends on**: Phase 2 (job lifecycle) and Phase 1 (company data)
**Requirements**: PROC-05, PROC-06, FRNT-05
**Success Criteria** (what must be TRUE):
  1. Analyst can select an analyst name and vigencia, see the list of matching companies, and trigger a batch job that processes all of them
  2. Batch progress dashboard shows per-company status and note counts updating in real time
  3. Analyst can abort a running job mid-processing; the job stops within the current note and marks remaining notes as aborted
**Plans:** 2/3 plans executed

Plans:
- [ ] 05-01-PLAN.md — BatchJobManager class, batch models, abort support, TDD tests
- [ ] 05-02-PLAN.md — Batch endpoints (POST /batch, GET /batch/{id}/status), abort endpoint, review dispatch, router wiring
- [ ] 05-03-PLAN.md — Lovable spec batch dashboard section, end-of-phase verification

### Phase 6: n8n Compatibility and Hardening
**Goal**: The classification endpoint preserves existing n8n workflow compatibility; operational pitfalls (timeouts, CORS, rate limiting) are verified and mitigated
**Depends on**: Phase 4 (system functionally complete)
**Requirements**: INFR-02
**Success Criteria** (what must be TRUE):
  1. POST /classify passes a request through to the n8n webhook and returns the classification response; existing n8n workflows call it without modification
  2. n8n calls with a 90-second timeout and one retry on failure; a Cloudflare 524 or ReadTimeout falls back to a manual review item rather than crashing the job
  3. A verification checklist passes: byte diff clean, job ownership 403 confirmed, RLS confirmed in Supabase SQL editor, CORS confirmed in browser DevTools with no wildcard credentials
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete   | 2026-03-26 |
| 2. Job Lifecycle | 1/2 | In Progress|  |
| 3. Manual Review Gate | 1/2 | In Progress | - |
| 4. Output Delivery | 2/2 | Complete   | 2026-03-31 |
| 5. Batch Mode | 2/3 | In Progress|  |
| 6. n8n Compatibility and Hardening | 0/TBD | Not started | - |
