# Roadmap: ImportaREST GO — Processamento em Lote

## Overview

This roadmap adds batch NFS-e processing to the existing ImportaREST GO desktop application. The work proceeds in three phases that follow strict dependency order: first build the spreadsheet reader (zero UI dependencies, fully testable in isolation), then build the batch orchestrator (worker logic, threading, error handling — before any UI exists), then build and integrate the full batch UI panel (all user-visible controls, progress display, and Notebook tab integration). The existing individual workflow is never touched.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Spreadsheet reader and config constants — isolated, testable, no UI dependencies (completed 2026-03-09)
- [ ] **Phase 2: Batch Orchestrator** - Worker loop, thread-safe manual review dialogs, abort/error handling
- [ ] **Phase 3: Batch UI and Integration** - Full batch panel with progress controls, app.py Notebook tab

## Phase Details

### Phase 1: Foundation
**Goal**: The spreadsheet can be read reliably — analysts can be listed, their companies enumerated, and failures reported clearly
**Depends on**: Nothing (first phase)
**Requirements**: PLAN-01, PLAN-02, PLAN-03, PLAN-04, PLAN-05
**Success Criteria** (what must be TRUE):
  1. App reads the spreadsheet from the fixed path and returns a list of analyst names with no manual configuration needed
  2. Only companies with GOIANIA in the MUNICIPIO column are returned — companies from other cities do not appear
  3. If the spreadsheet is locked by another user, missing from drive G:, or has an invalid format, the app displays a specific plain-language error message naming the cause
  4. If the spreadsheet columns COD (A) or ANALISTA (D) are not found in row 1, the app rejects the file before attempting to process any data
  5. After an analyst is selected, the app displays the exact count of GOIANIA companies assigned to that analyst
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — Config constants + test infrastructure (Wave 1)
- [ ] 01-02-PLAN.md — Implement services/spreadsheet.py TDD red-green (Wave 2)

### Phase 2: Batch Orchestrator
**Goal**: The batch worker can process all companies sequentially, pause correctly for manual review dialogs, and handle errors and aborts without crashing or leaving the analyst uninformed
**Depends on**: Phase 1
**Requirements**: PROC-01, PROC-02, PROC-03, PROC-04
**Success Criteria** (what must be TRUE):
  1. All companies for the selected analyst are processed one at a time in sequence — the next company only starts after the previous one fully completes
  2. When a note requires manual review during a batch run, the review dialog appears normally and the batch pauses until the analyst responds — after responding, the batch resumes automatically
  3. When a company fails, the error is recorded and the orchestrator moves on to the next company without crashing or requiring analyst action
  4. When the analyst clicks Abort, the current company finishes its full processing cycle before the batch stops — no company is abandoned mid-process
  5. On abort or completion, a partial or full summary is always generated listing which companies succeeded, failed, or were not reached
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — Test stubs: 8 failing tests for PROC-01..04 (Wave 1)
- [ ] 02-02-PLAN.md — Implement services/batch_orchestrator.py TDD green (Wave 2)

**Implementation note (PROC-03):** The manual review dialog must work normally in batch mode — it is NOT suppressed. The worker thread signals the main thread via `queue.Queue`; the main thread opens the dialog via `after()` and passes the analyst's response back to the worker via `threading.Event`. This is the prescribed thread-safe pattern and is a hard requirement.

### Phase 3: Batch UI and Integration
**Goal**: The analyst can configure and run a full batch from the application's batch tab, see real-time progress, and receive a clear summary when the batch ends — without disrupting the existing individual workflow
**Depends on**: Phase 2
**Requirements**: SELEC-01, SELEC-02, SELEC-03, SELEC-04, PROG-01, PROG-02, PROG-03, PROG-04, RESULT-01, RESULT-02
**Success Criteria** (what must be TRUE):
  1. Analyst can open the batch tab, select their name from a list, enter a competencia, choose a destination folder, and click Start — the existing Individual tab remains unchanged and functional
  2. The Start button is disabled until analyst, competencia, and destination folder are all filled in — clicking Start with any field missing is not possible
  3. During the batch run, the UI shows a progress bar with X/Y company count, the name of the company currently being processed, an estimated time remaining (visible after the first company completes), and a scrollable log of results per company
  4. At the end of the batch (whether completed or aborted), the UI shows a summary: total companies processed, number of successes, number of errors, and number skipped
  5. If any companies failed, the summary prominently lists each failed company by code and name so the analyst knows exactly what needs manual follow-up
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete   | 2026-03-09 |
| 2. Batch Orchestrator | 0/2 | Not started | - |
| 3. Batch UI and Integration | 0/TBD | Not started | - |
