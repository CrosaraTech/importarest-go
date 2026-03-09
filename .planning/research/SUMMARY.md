# Project Research Summary

**Project:** ImportaREST GO — Batch NFS-e Processing
**Domain:** Python/ttkbootstrap desktop app — batch XLSX-driven fiscal document processing via N8N
**Researched:** 2026-03-09
**Confidence:** HIGH

## Executive Summary

This project adds a batch processing tab to an existing NFS-e import desktop application. The core workflow is well-defined: read a shared XLSX spreadsheet to enumerate companies assigned to a given analyst, then invoke the existing `WorkflowProcessor` sequentially for each company, collecting results and displaying real-time progress in a new UI panel. The recommended approach is additive — zero changes to existing `processor.py` or `dialogs.py`, with three new files (`batch_orchestrator.py`, `batch_panel.py`, `spreadsheet.py`) and minimal surgery on `app.py` to add a Notebook tab.

The single biggest architectural decision is the threading model. The existing app already violates Tkinter thread safety (`janela.update()` from a background thread), which is tolerable for single-company runs but will cause intermittent crashes under batch load. The correct pattern — `queue.Queue` + `after()` polling — is well-documented and must be applied consistently: the worker thread never touches any widget directly. Every UI update flows through the queue and is applied in the main thread's `after()` callback. This is non-negotiable for a stable batch mode.

The key risk is not technical complexity — the stack is stdlib-only (plus `openpyxl`) and the architecture is a straightforward callback substitution. The risk is correctness under failure: Tkinter dialogs opened from worker threads, unhandled spreadsheet lock errors, N8N timeouts accumulating across companies, and abort leaving partial output without a summary. All of these are identified with concrete prevention strategies and must be addressed in implementation order before integration testing.

---

## Key Findings

### Recommended Stack

The stack requires only one new dependency (`openpyxl 3.1.x`) on top of existing Python stdlib. All threading primitives needed — `queue.Queue`, `threading.Event`, `threading.Thread`, and `after()` — are already present in the Python runtime used by the app.

**Core technologies:**
- `openpyxl 3.1.x`: Read columns A (COD) and D (ANALISTA) from the shared XLSX — lightweight, no NumPy/pandas chain, already mandated by PROJECT.md
- `queue.Queue` (stdlib): Thread-safe message channel from worker to UI — only mechanism that avoids Tkinter re-entrancy
- `threading.Event` (stdlib): Zero-CPU pause/abort signal — worker blocks on `wait()` until UI resolves error dialog
- `tkinter.after()` (stdlib): Schedules UI updates on the main thread — mandatory replacement for `janela.update()` in batch context
- `ttk.Progressbar` (mode="determinate"): Outer company progress; driven by queue messages

**Avoid:** `pandas` (30 MB compiled dependencies for 2-column read), `xlrd` (dropped XLSX support in 2020), `janela.update()` from worker thread, `messagebox` from background thread, `multiprocessing` (N8N prohibits parallelism, startup overhead unnecessary).

### Expected Features

**Must have (table stakes):**
- Outer progress bar with company X/Y count and current company name displayed
- Real-time scrollable log per company (success/error/skipped), updated via queue
- ETA estimate displayed after first company completes (rolling average)
- Error pause dialog (Skip / Abort) — blocks batch when company fails; analyst decides explicitly
- Post-run summary: totals and list of failed companies
- Manual review suppression — `abrir_tela_manual_fn` replaced with no-op that returns `None`; batch continues
- Pre-run validation: analyst selected, competencia valid, destination folder chosen; Start disabled until all three are set
- Company count preview after analyst selection
- Abort button available during run; cancels after current company finishes

**Should have (differentiators):**
- Auto-open destination folder in Explorer on successful completion
- Batch audit CSV (company, result, note count, errors) in addition to individual TXTs
- Remaining time estimate after first company
- Per-company timer in UI (helps detect stuck N8N requests)

**Defer to v2+:**
- Per-company competencia override (out of scope)
- Parallel company processing (prohibited by PROJECT.md; N8N cost; error handling complexity)
- IBGE cache pre-warm (minor startup latency, not a failure mode)

### Architecture Approach

The architecture is strictly additive. `WorkflowProcessor` already accepts behavior via 4 constructor callbacks (`log_fn`, `progress_fn`, `contador_fn`, `abrir_tela_manual_fn`). The batch orchestrator constructs a fresh `WorkflowProcessor` per company with batch-aware callbacks — no modifications to `processor.py`. The new `ttk.Notebook` in `app.py` hosts the existing individual tab unchanged plus the new `PainelLote` tab.

**Major components:**
1. `services/spreadsheet.py` (new) — reads XLSX via openpyxl, validates headers, returns `[(cod, analista)]`; raises typed exceptions for lock/missing file
2. `services/batch_orchestrator.py` (new) — sequential company loop, error handling, threading.Event pause/abort, result accumulation, TXT saving
3. `ui/batch_panel.py` (new) — all batch widgets; owns queue polling via `after(100, _poll_queue)`; opens error dialogs from main thread only
4. `ui/app.py` (modified minimally) — wrap existing content in Notebook "Individual" tab; add "Lote" tab with `PainelLote`
5. `services/processor.py` (no changes) — existing pipeline reused as-is via callback injection

Data flow: `PainelLote` spawns daemon thread → `BatchOrchestrator.run()` → for each company: `WorkflowProcessor.processar(cod, vigencia)` with batch callbacks → results flow back via `queue.Queue` → `after()` drains queue → widgets updated in main thread.

### Critical Pitfalls

1. **Tkinter widgets created from worker thread (CRITICAL)** — `processor.py` calls `_abrir_tela_manual()` from background thread; in batch mode this opens `Toplevel` + `wait_window()` off-main-thread → intermittent Windows crashes. Prevention: replace `abrir_tela_manual_fn` with a no-op returning `None` before any batch integration; all dialogs flow through queue to main thread.

2. **`janela.update()` from worker thread (HIGH)** — existing `app.py` line 148 calls this inside `log()`, which is invoked from worker. Single-company runs tolerate it; batch loops pump the Tk event loop from off-thread → button clicks can fire mid-processing. Prevention: batch callbacks must never call `janela.update()`; use `after(0, fn)` for all widget updates.

3. **N8N timeout accumulation (HIGH)** — current `n8n_client.py` timeout is 150s per call. 30 companies × 150s = 75-minute worst-case timeout accumulation with no UI indication. Prevention: reduce batch timeout to 60s; show per-company elapsed timer; treat `requests.Timeout` as company error (pause dialog), not crash.

4. **Shared spreadsheet locked by Excel on drive G: (HIGH)** — `openpyxl` raises `PermissionError` or `zipfile.BadZipFile` when another user has the file open. Prevention: always open with `read_only=True`; catch `PermissionError`, `BadZipFile`, `FileNotFoundError`; display user-facing message naming the cause; validate on tab activation, not only at Start click.

5. **Column position access breaks silently on spreadsheet reorganization (MEDIUM)** — accessing `row[0]` and `row[3]` by index processes wrong companies without any error if columns shift. Prevention: validate row 1 headers contain "COD" in column A and "ANALISTA" in column D before processing.

6. **Pause dialog blocks indefinitely if analyst leaves desk (MEDIUM)** — worker blocks on `threading.Event.wait()` with no timeout. Prevention: add 5-minute auto-skip with countdown timer in the dialog; or offer "auto-skip on error" toggle before batch starts.

7. **Abort leaves partial output without summary (MEDIUM)** — analyst cannot determine which companies completed. Prevention: always generate partial summary on abort, listing successes, errors, skipped, and not-started companies.

---

## Implications for Roadmap

Based on combined research, the implementation has four natural phases driven by dependency order: infrastructure that everything else builds on must come first, worker logic before UI, UI integration last to avoid breaking the existing flow during development.

### Phase 1: Foundation — Config and Spreadsheet Reader

**Rationale:** `spreadsheet.py` has zero UI dependencies; it can be built and tested in isolation before any threading or widget code exists. Getting header validation and error handling right here prevents Pitfall 4 (lock errors) and Pitfall 5 (silent column mismatch) from surfacing later.

**Delivers:** `services/spreadsheet.py` with header validation, `config.py` constants (`PLANILHA_EMPRESAS`, column indices), typed exceptions for lock/missing file scenarios.

**Addresses:** Pre-run validation feature; company count preview (requires reading spreadsheet at tab activation).

**Avoids:** Pitfall 4 (spreadsheet lock), Pitfall 5 (column position fragility).

### Phase 2: Batch Orchestrator — Worker Logic

**Rationale:** `batch_orchestrator.py` contains all the sequential loop logic, threading.Event pause/abort, WorkflowProcessor callback wiring, and result accumulation. It must be correct before any UI is wired to it. The no-op `abrir_tela_manual_fn` must be established here — this is the Pitfall 1 (CRITICAL) prevention.

**Delivers:** `services/batch_orchestrator.py` — sequential company loop, callback injection into WorkflowProcessor, error pause/abort via threading.Event, TXT saving, partial summary on abort.

**Uses:** `queue.Queue` for event passing, `threading.Event` for pause/abort, `openpyxl` via spreadsheet.py.

**Implements:** BatchOrchestrator component; WorkflowProcessor reuse via callback substitution.

**Avoids:** Pitfall 1 (Tkinter from worker), Pitfall 2 (`janela.update()` from worker), Pitfall 3 (N8N timeout), Pitfall 6 (dialog blocks indefinitely), Pitfall 7 (abort without summary), Pitfall 8 (partial note failure masked as OK).

### Phase 3: Batch UI Panel

**Rationale:** `batch_panel.py` is built after the orchestrator so the queue message contract is already defined. The UI consumes — never produces — business logic. All widget updates use `after()` exclusively; all dialogs are opened from main thread in response to queue messages.

**Delivers:** `ui/batch_panel.py` — analyst selector, competencia input, destination folder picker, progress bar, ETA display, scrollable log, Start/Abort controls, error dialog handler, post-run summary, optional "open folder" button.

**Uses:** `queue.Queue` + `after(100, _poll_queue)` pattern; `ttk.Progressbar` (determinate); `tk.Text` + `ttk.Scrollbar` (not `ScrolledText`) for log.

**Implements:** PainelLote component.

**Avoids:** Pitfall 2 (no `janela.update()` from batch callbacks).

### Phase 4: App Integration — Notebook Tab

**Rationale:** App.py is modified last to prevent breaking the existing individual workflow during development of phases 1-3. The Notebook wraps existing content unchanged; the new tab just instantiates PainelLote.

**Delivers:** `ui/app.py` refactored with `ttk.Notebook`; window size expanded to accommodate batch log; "Individual" tab preserves all existing behavior without modification.

**Avoids:** Regression in existing single-company workflow.

### Phase Ordering Rationale

- Spreadsheet before orchestrator: orchestrator imports `SpreadsheetReader`; testable in isolation first
- Orchestrator before UI: queue message schema defined by orchestrator; UI just consumes it
- UI before app integration: PainelLote can be tested as a standalone window before embedding in Notebook
- App integration last: surgical change to working code; done last to minimize regression window
- No phase requires changes to `processor.py` or `dialogs.py` — this constraint is maintained throughout

### Research Flags

Phases with well-documented patterns (no additional research needed):
- **Phase 1 (Spreadsheet):** openpyxl read_only pattern is standard; header validation is straightforward
- **Phase 2 (Orchestrator):** queue.Queue + threading.Event is stdlib-prescribed pattern; no unknowns
- **Phase 3 (Batch UI):** after() polling pattern is Python FAQ-documented for Tkinter
- **Phase 4 (Notebook):** ttk.Notebook tab addition is standard Tkinter; minimal code change

No phase requires `/gsd:research-phase` — research is complete and specific enough to implement directly.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | openpyxl mandated in PROJECT.md; threading pattern prescribed in Python FAQ; stdlib-only additions |
| Features | HIGH | Derived directly from existing app behavior and analyst workflow; error scenarios enumerated from actual code paths |
| Architecture | HIGH | Based on direct reading of `processor.py` and `app.py`; callback contract confirmed at source lines 298-304 |
| Pitfalls | HIGH | Identified from actual code (not speculation); severities assigned based on Windows Tkinter behavior under thread stress |

**Overall confidence:** HIGH

### Gaps to Address

- **Window resize dimensions:** The batch log requires a taller window; exact new size (currently 420x580) should be determined during Phase 3 implementation based on actual widget layout, not prescribed in advance.
- **N8N timeout value for batch:** Research recommends reducing from 150s to 60s for batch mode; the exact value should be validated against observed N8N response times in production before hardcoding.
- **Auto-skip timeout duration:** Research suggests 5 minutes for the pause dialog auto-skip; this should be confirmed with the analyst as a UX preference before implementation.
- **Audit CSV format:** Schema (columns, encoding, delimiter) for the optional batch CSV report should be confirmed with the analyst who will consume it before Phase 3 implementation.

---

## Sources

### Primary (HIGH confidence)
- Direct codebase reading (`services/processor.py`, `ui/app.py`) — WorkflowProcessor callback contract, existing threading pattern, `janela.update()` location
- Python stdlib documentation — `queue.Queue`, `threading.Event`, `after()` Tkinter threading FAQ
- openpyxl 3.1.x documentation — `read_only=True`, `iter_rows()`, `BadZipFile` exception handling

### Secondary (MEDIUM confidence)
- PROJECT.md — mandates openpyxl, prohibits parallel processing, defines spreadsheet path and column layout
- ttkbootstrap documentation — `ttk.Progressbar`, `tk.Text` + `ttk.Scrollbar` construction guidance

### Tertiary (LOW confidence)
- N8N timeout behavior under batch load — estimated from `n8n_client.py` timeout value; actual behavior under concurrent company processing not directly measured

---

*Research completed: 2026-03-09*
*Ready for roadmap: yes*
