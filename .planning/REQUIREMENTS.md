# Requirements: ImportaREST GO Web

**Defined:** 2026-03-26
**Core Value:** Analysts can upload NFS-e XMLs and download byte-perfect REST TXT files for ISS.NET import, with AI-assisted classification and inline manual review.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Authentication

- [x] **AUTH-01**: Analyst can sign up and log in with email and password via Supabase Auth
- [x] **AUTH-02**: Analyst session persists across browser refresh
- [x] **AUTH-03**: Multiple analysts can use the system concurrently without interfering with each other's jobs

### Data Management

- [x] **DATA-01**: Company registry data is imported from RELACAO_EMPRESAS XLSX into Supabase (one-time migration)
- [x] **DATA-02**: Analyst can view and filter companies by analyst name and municipality
- [x] **DATA-03**: FastAPI reads company data from Supabase instead of XLSX file

### File Handling

- [x] **FILE-01**: Analyst can upload one or more XML files for a given company code and vigencia
- [x] **FILE-02**: Analyst can upload a ZIP file containing multiple XMLs
- [x] **FILE-03**: Analyst can specify company code, vigencia (MM/YYYY), and MEI toggle before processing
- [x] **FILE-04**: Uploaded files are validated (file type, non-empty) before job creation

### Processing

- [x] **PROC-01**: Analyst can trigger a single-company processing job that wraps the existing WorkflowProcessor
- [x] **PROC-02**: Analyst can poll job progress in real-time (X of N notes processed, current status)
- [x] **PROC-03**: When AI flags a low-confidence record, the job pauses and the analyst sees an inline review form with service description, suggested Item LC, and editable fields
- [x] **PROC-04**: After analyst submits a correction on the review form, the job resumes processing
- [ ] **PROC-05**: Analyst can trigger a batch job selecting an analyst name and vigencia to process all companies for that analyst
- [ ] **PROC-06**: Analyst can abort a running job mid-processing
- [x] **PROC-07**: Processing errors are displayed per-note with reason (parity with desktop error messages)

### Output

- [x] **OUTP-01**: Analyst can download the generated TXT REST file in byte-perfect ISS.NET format (20 fields, semicolon delimiter, exact header)
- [x] **OUTP-02**: Analyst can download the CSV audit report with per-note processing details
- [x] **OUTP-03**: When notes fall outside the target vigencia, separate TXT files are generated and downloadable per period

### Infrastructure

- [x] **INFR-01**: FastAPI backend runs on a local office server with single-worker uvicorn
- [ ] **INFR-02**: n8n webhook compatibility is preserved — FastAPI exposes the same classification endpoint interface
- [x] **INFR-03**: G: drive paths in config.py are replaced with configurable environment variables
- [x] **INFR-04**: Redis runs in Docker on the office server for job queue (arq)

### Frontend

- [ ] **FRNT-01**: Lovable-generated React frontend with file upload form, company/vigencia inputs, and MEI toggle
- [ ] **FRNT-02**: Processing progress dashboard showing job status, note count, and log messages
- [ ] **FRNT-03**: Inline manual review form that appears when a job pauses for review
- [x] **FRNT-04**: Results page with download buttons for TXT and CSV files
- [ ] **FRNT-05**: Batch processing view with analyst selector, company list, and per-company progress

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Access Control

- **ACCS-01**: Analyst sees only their own companies and jobs (Supabase RLS policies)
- **ACCS-02**: Admin role can view all analysts' jobs

### Quality of Life

- **QLTY-01**: Job history with ability to re-download previous results (24h+ retention)
- **QLTY-02**: Persistent job log stored in Supabase for debugging
- **QLTY-03**: Browser notification when background job completes
- **QLTY-04**: Review queue visibility showing count of pending reviews before starting

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Rewriting Python XML parsing | Core logic is battle-tested; wrapping is the strategy |
| WebSocket real-time push | Polling at 1-2s is sufficient; adds complexity for minimal UX gain |
| In-app company registry editor | Companies change rarely; use Supabase Table Editor |
| Scheduled/recurring batch runs | No reliable input source; XMLs arrive irregularly |
| Mobile-native app | Web-first; responsive design sufficient |
| Email notifications | Batch jobs complete in <5 min; analysts watch progress |
| Real-time collaboration on reviews | Blocking review is inherently single-reviewer |
| Drag-and-drop folder upload | ZIP upload already solves multi-file case |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Complete |
| AUTH-02 | Phase 1 | Complete |
| AUTH-03 | Phase 1 | Complete |
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| FILE-01 | Phase 2 | Complete |
| FILE-02 | Phase 2 | Complete |
| FILE-03 | Phase 2 | Complete |
| FILE-04 | Phase 2 | Complete |
| PROC-01 | Phase 2 | Complete |
| PROC-02 | Phase 2 | Complete |
| PROC-03 | Phase 3 | Complete |
| PROC-04 | Phase 3 | Complete |
| PROC-05 | Phase 5 | Pending |
| PROC-06 | Phase 5 | Pending |
| PROC-07 | Phase 2 | Complete |
| OUTP-01 | Phase 4 | Complete |
| OUTP-02 | Phase 4 | Complete |
| OUTP-03 | Phase 4 | Complete |
| INFR-01 | Phase 1 | Complete |
| INFR-02 | Phase 6 | Pending |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 1 | Complete |
| FRNT-01 | Phase 2 | Pending |
| FRNT-02 | Phase 2 | Pending |
| FRNT-03 | Phase 3 | Pending |
| FRNT-04 | Phase 4 | Complete |
| FRNT-05 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 29 total
- Mapped to phases: 29
- Unmapped: 0

---
*Requirements defined: 2026-03-26*
*Last updated: 2026-03-26 after roadmap creation — all 29 requirements mapped*
