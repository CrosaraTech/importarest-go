# Phase 3: Batch UI and Integration - Research

**Researched:** 2026-03-09
**Domain:** Python/Tkinter desktop UI — queue-driven batch panel, ttk.Notebook integration, after() polling
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SELEC-01 | Analyst selects name from ttk.Combobox populated by `load_analysts()` | `spreadsheet.load_analysts()` returns `list[str]`; Combobox binding triggers `get_companies_for_analyst()` |
| SELEC-02 | Analyst enters competencia (MMYYYY) via Entry | Plain `tk.Entry`; same style as existing `ent_vigencia` in app.py |
| SELEC-03 | Analyst picks destination folder via `filedialog.askdirectory()` | `ui/app.py` already imports `filedialog`; same pattern as existing save dialog |
| SELEC-04 | Start button disabled until all three fields are filled | `StringVar`/`BooleanVar` trace callbacks calling `_update_start_state()` |
| PROG-01 | Progress bar shows X/Y companies | `ttk.Progressbar(mode="determinate")` driven by `company_start` queue message |
| PROG-02 | Current company code displayed | `tk.Label` updated on `company_start` queue message |
| PROG-03 | ETA displayed after first company completes | Elapsed time from `company_done` elapsed_seconds field; rolling average |
| PROG-04 | Scrollable log with per-company result | `tk.Text` + `ttk.Scrollbar`; colored tags for ok/error/skipped entries |
| RESULT-01 | Post-run summary: totals, successes, errors, skipped | `BatchSummary` dataclass from `batch_done` queue message |
| RESULT-02 | If failures, summary highlights each failed company | `BatchSummary.company_results` filtered by `status == "error"` |
</phase_requirements>

---

## Summary

Phase 3 delivers two interconnected artifacts: `ui/batch_panel.py` (the `PainelLote` class — all batch widgets and queue-poll loop) and a minimal surgical modification to `ui/app.py` (wrapping the existing individual workflow in a `ttk.Notebook` and adding the Lote tab). Both Phases 1 and 2 are fully complete, so all upstream contracts are fixed and verified.

The queue message schema is completely defined by `services/batch_orchestrator.py` (Phase 2 deliverable, 130 lines, all 8 tests green). The UI panel is a pure consumer: it reads queue messages, updates widgets on the main thread via `after()`, and delegates one action back to the orchestrator (`abort()`). The PROC-03 manual-review protocol requires the panel to open `abrir_tela_manual_itemlc()` via `after(0, ...)` when a `manual_review` message arrives, populate `result_holder[0]`, then call `event.set()` — this is the only complex interaction pattern.

The app.py integration is the smallest-risk task: wrap the existing `_construir_ui()` output in a `Notebook` tab called "Individual", add a second "Lote" tab instantiating `PainelLote`. The existing window size is 420x580 (`self.janela.geometry("420x580")`); the batch tab needs extra vertical space for the log widget. Window width must be increased to at least 700px to accommodate the wider batch layout, and height to at least 640px. `resizable(False, False)` must change to `resizable(True, True)` or a fixed larger geometry must be chosen — research recommends a fixed `900x660` to avoid layout shifts.

**Primary recommendation:** Build `ui/batch_panel.py` as a standalone `tk.Frame` subclass with its own `after()` poll loop, then integrate into `app.py` via `ttk.Notebook` as a single final step. Never modify `processor.py` or `dialogs.py`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tkinter` + `ttkbootstrap` | stdlib / project-current | All widgets — Notebook, Combobox, Progressbar, Text, Scrollbar | Already the app's UI toolkit; ttkbootstrap is already the main window |
| `ttk.Notebook` | stdlib ttk | Tab container for Individual + Lote | Project decision: "Modo lote como aba separada (Notebook)" |
| `ttk.Progressbar` | stdlib ttk | Determinate progress bar for X/Y companies | Prescribed in SUMMARY.md; simpler than CircularProgress for batch |
| `tk.Text` + `ttk.Scrollbar` | stdlib | Scrollable log | Explicitly prescribed: NOT `ScrolledText` |
| `ttk.Combobox` | stdlib ttk | Analyst name selector | Standard single-choice dropdown; `state="readonly"` prevents free-form typing |
| `tkinter.filedialog` | stdlib | Destination folder picker | Already imported in `app.py`; `askdirectory()` is the standard call |
| `queue.Queue` | stdlib | Inter-thread message bus (Phase 2 defines messages) | Fixed contract from `batch_orchestrator.py` |
| `services.spreadsheet` | Phase 1 | `load_analysts()` / `get_companies_for_analyst()` | Complete, tested, raises typed exceptions |
| `services.batch_orchestrator` | Phase 2 | `BatchOrchestrator`, `BatchSummary`, `CompanyResult` | Complete, all 8 tests green |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `threading.Thread` | stdlib | Daemon thread that runs `BatchOrchestrator.run()` | Spawned when analyst clicks Start |
| `tkinter.messagebox` | stdlib | Post-run summary dialog (RESULT-01, RESULT-02) | Called from main thread only, in `_poll_queue` handler for `batch_done` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ttk.Progressbar` | `CircularProgress` (existing component) | CircularProgress is PIL-based and requires `__setitem__`; fine for single note count; `ttk.Progressbar` is simpler for integer company index and has native determinate mode |
| `messagebox` for summary | Inline panel (`tk.Frame`) | Messagebox is simpler; inline avoids dismissal friction; project has precedent for messagebox summaries; choose messagebox |
| `ttk.Notebook` tabs | Separate `tk.Toplevel` window | Notebook is the project decision (STATE.md); Toplevel would break window management |
| `scrolledtext.ScrolledText` | `tk.Text` + `ttk.Scrollbar` | ScrolledText is explicitly forbidden in critical constraints |

**Installation:** No new packages. All stdlib + `ttkbootstrap` (already present) + `openpyxl` (Phase 1 already installed).

---

## Architecture Patterns

### Recommended Project Structure

```
ui/
├── app.py          # MODIFIED — wrap in Notebook; add PainelLote tab
├── batch_panel.py  # NEW — PainelLote class (all batch widgets + queue poll)
├── components.py   # unchanged
└── dialogs.py      # unchanged
```

### Pattern 1: Queue Poll Loop via `after()`

**What:** `PainelLote` calls `self.after(100, self._poll_queue)` in its `__init__` and re-schedules itself at the end of each poll tick. The loop runs for the lifetime of the panel.

**When to use:** Whenever a background thread must communicate to the UI thread without blocking it.

**Example:**
```python
# Source: Python stdlib Tkinter threading FAQ + project SUMMARY.md prescription
def _poll_queue(self):
    try:
        while True:
            msg = self._q.get_nowait()
            self._dispatch(msg)
    except queue.Empty:
        pass
    self.after(100, self._poll_queue)

def _dispatch(self, msg):
    kind = msg[0]
    if kind == "company_start":
        _, cod, i, total = msg
        self._on_company_start(cod, i, total)
    elif kind == "log":
        _, cod, text = msg
        self._log(f"[{cod}] {text}")
    elif kind == "counter":
        _, cod, atual, total = msg
        # update note counter label (optional detail display)
        pass
    elif kind == "manual_review":
        _, dados_base, chave_nfse, from_n8n, event, result_holder = msg
        self.after(0, lambda: self._handle_manual_review(
            dados_base, chave_nfse, from_n8n, event, result_holder))
    elif kind == "company_done":
        _, cod, status, notes, elapsed, detail = msg
        self._on_company_done(cod, status, notes, elapsed, detail)
    elif kind == "batch_done":
        _, summary = msg
        self._on_batch_done(summary)
```

### Pattern 2: PROC-03 Manual Review from Main Thread

**What:** When `manual_review` arrives, the main thread calls `abrir_tela_manual_itemlc()`, populates `result_holder[0]`, then calls `event.set()` to unblock the worker.

**Critical:** `event.set()` must be called even if the analyst cancels (so `result_holder[0]` stays `None`). The worker's `_make_manual_callback` returns `result_holder[0]`, which `processor.py` handles when `None` (note skipped or filled with fallback).

**Example:**
```python
# Source: batch_orchestrator.py lines 92-99 + critical architectural constraint
def _handle_manual_review(self, dados_base, chave_nfse, from_n8n, event, result_holder):
    # Called via after(0, ...) — guaranteed to run on main thread
    result = abrir_tela_manual_itemlc(
        self.winfo_toplevel(),   # parent_window
        dados_base,
        chave_nfse,
        from_n8n
    )
    result_holder[0] = result   # None if cancelled, string if confirmed
    event.set()                  # ALWAYS set — never leave worker blocked
```

### Pattern 3: Analyst Selection with Live Company Count (SELEC-01, SELEC-04)

**What:** `ttk.Combobox` bound to `<<ComboboxSelected>>`. On selection, call `get_companies_for_analyst()`, update a count label, and call `_update_start_state()`.

**Example:**
```python
# Source: services/spreadsheet.py public API
def _on_analyst_selected(self, event=None):
    name = self._var_analyst.get()
    try:
        companies = get_companies_for_analyst(name)
        self._companies = companies
        self._lbl_count.configure(
            text=f"{len(companies)} empresa(s) encontrada(s)"
        )
    except SpreadsheetError as e:
        messagebox.showerror("Erro na planilha", str(e))
        self._companies = []
    self._update_start_state()

def _update_start_state(self, *_):
    ok = (
        bool(self._var_analyst.get()) and
        bool(self._var_vigencia.get().strip()) and
        bool(self._var_dest.get().strip())
    )
    self._btn_start.configure(state="normal" if ok else "disabled")
```

### Pattern 4: ETA Estimation (PROG-03)

**What:** After first `company_done` message, record elapsed time. Each subsequent `company_done` updates a rolling average. ETA = average_per_company * remaining_companies.

**Example:**
```python
# Source: project SUMMARY.md + REQUIREMENTS.md PROG-03
def _on_company_done(self, cod, status, notes, elapsed, detail):
    self._elapsed_times.append(elapsed)
    avg = sum(self._elapsed_times) / len(self._elapsed_times)
    remaining = self._total_companies - len(self._elapsed_times)
    eta_seconds = avg * remaining
    if remaining > 0:
        mins, secs = divmod(int(eta_seconds), 60)
        self._lbl_eta.configure(text=f"ETA: ~{mins}m {secs}s")
    else:
        self._lbl_eta.configure(text="")
```

### Pattern 5: `tk.Text` Scrollable Log (PROG-04)

**What:** `tk.Text` in read-only state with named color tags. Lines are appended at `tk.END`. Auto-scroll via `see(tk.END)`.

**Example:**
```python
# Source: Python Tkinter docs + project SUMMARY.md prescription
frame_log = tk.Frame(self, bg=COR_BG)
frame_log.pack(fill="both", expand=True, padx=8, pady=(4, 8))

self._txt_log = tk.Text(
    frame_log,
    height=12,
    font=("Segoe UI", 8),
    bg=COR_CARD,
    fg=COR_TEXTO,
    relief="flat",
    state="disabled",
    wrap="word",
)
sb = ttk.Scrollbar(frame_log, orient="vertical", command=self._txt_log.yview)
self._txt_log.configure(yscrollcommand=sb.set)
sb.pack(side="right", fill="y")
self._txt_log.pack(side="left", fill="both", expand=True)

# Tag colors
self._txt_log.tag_configure("ok",      foreground="#1B8A1B")
self._txt_log.tag_configure("error",   foreground="#C0392B")
self._txt_log.tag_configure("skipped", foreground="#B8860B")
self._txt_log.tag_configure("info",    foreground=COR_SUBTEXTO)

def _log(self, msg: str, tag: str = "info"):
    self._txt_log.configure(state="normal")
    self._txt_log.insert(tk.END, msg + "\n", tag)
    self._txt_log.see(tk.END)
    self._txt_log.configure(state="disabled")
```

### Pattern 6: Notebook Integration in app.py

**What:** Wrap the existing `_construir_ui()` body in a `ttk.Frame` that becomes the "Individual" tab. Add a "Lote" tab with `PainelLote`. The existing `JanelaCrosara` window is enlarged to fit both tabs.

**Key constraint:** The current `_construir_ui()` packs directly to `self.janela`. After wrapping, it must pack to a `tab_individual` Frame. All `self.janela.X` widget packs become `tab_individual.X` packs. Alternatively, `_construir_ui()` receives a `parent` parameter.

**Example structure:**
```python
def _construir_ui(self):
    nb = ttk.Notebook(self.janela)
    nb.pack(fill="both", expand=True)

    tab_individual = tk.Frame(nb, bg=COR_BG)
    nb.add(tab_individual, text="Individual")

    tab_lote = tk.Frame(nb, bg=COR_BG)
    nb.add(tab_lote, text="Lote")

    self._construir_aba_individual(tab_individual)
    PainelLote(tab_lote).pack(fill="both", expand=True)

def _construir_aba_individual(self, parent):
    # Exact copy of existing _construir_ui() body
    # with self.janela replaced by parent in all pack() calls
    self._exibir_logo(parent)
    ...
```

**Window geometry:** Current `"420x580"`, `resizable(False, False)`. Change to `"900x660"` and `resizable(False, False)` (fixed wider layout for batch tab; Individual tab content unchanged inside its tab frame).

### Anti-Patterns to Avoid

- **`janela.update()` from worker thread:** The existing `app.py` `log()` method (line 148) calls `self.janela.update()`. Batch callbacks must never call this — use `after(0, fn)` instead. The `log_fn` passed to `WorkflowProcessor` in batch mode is `lambda msg: self._q.put(("log", cod, msg))`, never touching Tkinter.
- **Opening Tkinter dialogs from worker thread:** `abrir_tela_manual_itemlc()` is called only from the main-thread handler. Never put it directly in a lambda that runs in the worker thread.
- **`ScrolledText` widget:** Forbidden by project constraint. Use `tk.Text` + `ttk.Scrollbar`.
- **Blocking the poll loop:** `_dispatch()` must return quickly. For `manual_review`, use `after(0, ...)` to schedule the dialog open so the poll loop continues (the worker is already blocked on `event.wait()`; no UI polling is needed while blocked).
- **Modifying `processor.py` or `dialogs.py`:** Zero changes to these files. `PainelLote` imports `abrir_tela_manual_itemlc` from `ui.dialogs` and calls it from the main thread.
- **Spawning batch thread with `daemon=False`:** If the user closes the window, a non-daemon thread will keep the process alive. Always `daemon=True`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe message passing | Custom shared-memory state or locks | `queue.Queue` (Phase 2 already defines schema) | Queue is already in use; adding state bypasses the thread-safe design |
| Analyst name picker | Custom listbox dialog | `ttk.Combobox(state="readonly")` | Native dropdown; focus/tab/keyboard navigation is free |
| Folder picking | Custom path entry | `filedialog.askdirectory()` | Stdlib; already imported in app.py |
| Post-run summary dialog | Custom Toplevel with tables | `messagebox.showinfo()` / `messagebox.showwarning()` | Sufficient for text summary; complexity not warranted for v1 |
| Color-coded log | Canvas-based text renderer | `tk.Text` with named tags | Tags provide per-run coloring with zero reimplementation |
| ETA calculation | External time library | `time.monotonic()` diff from `company_done.elapsed_seconds` | `elapsed_seconds` is already computed and included in every `company_done` message |

**Key insight:** Every non-trivial problem in this phase is already solved upstream (queue contract, spreadsheet reader, orchestrator, dialogs). Phase 3 is exclusively widget wiring and event routing.

---

## Common Pitfalls

### Pitfall 1: `event.set()` Not Called on Dialog Cancel
**What goes wrong:** Analyst dismisses the manual review dialog (closes it or clicks a cancel button that doesn't exist in `abrir_tela_manual_itemlc`). If `event.set()` is not called, the worker thread blocks on `event.wait()` forever — the batch hangs with no feedback.
**Why it happens:** Tkinter `wait_window()` returns `None` on destroy; the calling code assumes the return value implies completion.
**How to avoid:** Wrap the dialog call in try/finally: `finally: event.set()`. The worker receives `result_holder[0] == None` and the note is skipped (existing processor behavior).
**Warning signs:** Batch log stops updating; Abort button appears unresponsive; last log line was a `manual_review` emission.

### Pitfall 2: Re-scheduling Poll Loop After `batch_done`
**What goes wrong:** `_poll_queue` keeps calling `self.after(100, self._poll_queue)` after `batch_done` is received, wasting cycles and potentially calling `_dispatch` on stale messages if a new batch is started.
**Why it happens:** Simple re-schedule at end of poll without a stop flag.
**How to avoid:** Add `self._running = False` when `batch_done` is processed. At the top of `_poll_queue`, check `if not self._running: return` before rescheduling. Reset `self._running = True` at batch start.
**Warning signs:** CPU usage stays elevated after batch finishes; second batch run sees messages from first run.

### Pitfall 3: Window Geometry Conflicts Between Tabs
**What goes wrong:** The Individual tab content was designed for a 420×580 window with `pack(fill="x")`. After wrapping in a Notebook that is itself in a 900×660 window, the Individual tab content may stretch horizontally into an ugly wide layout.
**Why it happens:** `pack(fill="x")` in the individual tab will expand to the full 900px width.
**How to avoid:** Give the Individual tab a fixed-width container frame (420px) centered in the tab, or use a column layout. Simplest: put all individual tab content in a frame with `padx` to constrain width to ~420px. Do not change any existing Individual tab widget creation logic — only change the parent frame.

### Pitfall 4: Combobox Populated Before Spreadsheet Is Loaded
**What goes wrong:** `PainelLote.__init__` calls `load_analysts()` synchronously during panel construction. If the G: drive is unavailable, the `SpreadsheetAccessError` crashes the entire app startup.
**Why it happens:** Eager loading during `__init__`.
**How to avoid:** Load the analyst list lazily — on tab focus (`<<NotebookTabChanged>>` event) or on a "Carregar" button click. Display "Carregando..." until load completes. Catch `SpreadsheetError` and display an error label with the message.

### Pitfall 5: Start Button Trace Not Fired for Combobox
**What goes wrong:** `StringVar.trace()` works for `Entry` widgets automatically, but `ttk.Combobox` selection does not update the `StringVar` until focus leaves. The Start button stays disabled even after analyst is selected.
**Why it happens:** Combobox does not fire `StringVar` write trace on `<<ComboboxSelected>>`.
**How to avoid:** Bind `<<ComboboxSelected>>` explicitly and call `_update_start_state()` from that binding — do not rely on the StringVar trace alone for the Combobox.

### Pitfall 6: Folder Path StringVar Trace Not Triggered After `askdirectory()`
**What goes wrong:** `filedialog.askdirectory()` returns a string. If the caller sets `self._var_dest.set(path)`, the StringVar trace fires and `_update_start_state()` is called. But if the path is set via a direct Entry update without going through the StringVar, the Start button stays disabled.
**Why it happens:** Direct widget set bypasses StringVar.
**How to avoid:** Always use `self._var_dest.set(path)` after `askdirectory()` returns, never set the Entry widget directly.

### Pitfall 7: `PainelLote` Holding Reference to `BatchOrchestrator` After Batch Ends
**What goes wrong:** If the user starts a second batch, a new `BatchOrchestrator` is created but the old one's queue messages arrive in the new poll loop, corrupting counts and logs.
**Why it happens:** Old thread still alive if not joined; old queue still being written to.
**How to avoid:** Create a fresh `queue.Queue()` per batch run (not per panel). Store `self._q = queue.Queue()` at the top of `_start_batch()`, not in `__init__`. The old queue is garbage-collected after the old thread ends.

---

## Code Examples

Verified patterns from official sources and Phase 2 codebase:

### Queue Message Schema (Complete — from batch_orchestrator.py lines 59, 69-71, 79, 85, 89, 96-97, 63)

```python
# Source: services/batch_orchestrator.py Phase 2 deliverable

# 1. company_start — emitted before processing each company
("company_start", cod: str, i: int, total: int)
# i = 0-based index; total = len(companies)

# 2. log — forwarded from WorkflowProcessor.log_fn
("log", cod: str, msg: str)
# msg is the same string that app.py's self.log() receives in individual mode

# 3. counter — forwarded from WorkflowProcessor.contador_fn
("counter", cod: str, atual: int, total: int)
# atual=0 means "reset"; total=N means N notes total for this company

# 4. manual_review — worker blocks until event.set() is called
("manual_review", dados_base: dict, chave_nfse: str, from_n8n: bool,
 event: threading.Event, result_holder: list)
# result_holder is [None]; caller sets result_holder[0] = str|None, then event.set()

# 5. company_done — emitted after each company finishes (ok, error, or skipped)
("company_done", cod: str, status: str, notes_count: int,
 elapsed_seconds: float, detail: str)
# status in ("ok", "error", "skipped")
# detail is "" for ok, exception str for error, "Pasta não encontrada" for skipped

# 6. batch_done — final message; payload is BatchSummary dataclass
("batch_done", summary: BatchSummary)
# summary.total, .successes, .errors, .skipped, .aborted, .company_results, .elapsed_total_seconds
```

### `abrir_tela_manual_itemlc` Signature (from dialogs.py lines 106-107)

```python
# Source: ui/dialogs.py
def abrir_tela_manual_itemlc(
    parent_window,          # tk.Widget — the parent window (use winfo_toplevel())
    dados_base: dict,       # dict from queue message — contains "descricao", "municipio", etc.
    chave_nfse: str,        # filename-like key shown in dialog title
    from_n8n: bool = False  # changes dialog size and field layout
) -> str | None:
    # Returns: the assembled TXT line string, or None if analyst cancelled
```

**Important:** The function calls `parent_window.wait_window(janela_manual)` internally (line 264), so it blocks the main thread until the dialog is closed. It must be called from the main thread only.

### `BatchSummary` Dataclass (from batch_orchestrator.py lines 29-37)

```python
# Source: services/batch_orchestrator.py
@dataclass
class BatchSummary:
    total: int
    successes: int
    errors: int
    skipped: int
    aborted: bool
    company_results: list       # list[CompanyResult]
    elapsed_total_seconds: float = 0.0

@dataclass
class CompanyResult:
    cod: str
    status: str                 # "ok" | "error" | "skipped"
    notes_count: int
    elapsed_seconds: float
    error_detail: str
```

### Post-Run Summary Format (RESULT-01 + RESULT-02)

```python
# Source: derived from REQUIREMENTS.md RESULT-01 and RESULT-02
def _on_batch_done(self, summary: BatchSummary):
    self._running = False
    self._btn_start.configure(state="normal")
    self._btn_abort.configure(state="disabled")

    lines = [
        f"Lote {'interrompido' if summary.aborted else 'concluido'}.",
        f"Total: {summary.total}  |  Sucesso: {summary.successes}  |  "
        f"Erro: {summary.errors}  |  Puladas: {summary.skipped}",
    ]
    if summary.errors > 0:
        failed = [r for r in summary.company_results if r.status == "error"]
        lines.append("\nEmpresas com erro:")
        for r in failed:
            lines.append(f"  • {r.cod} — {r.error_detail}")
        messagebox.showwarning("Resumo do Lote", "\n".join(lines))
    else:
        messagebox.showinfo("Resumo do Lote", "\n".join(lines))
```

### `BatchOrchestrator.run()` Signature (from batch_orchestrator.py line 51)

```python
# Source: services/batch_orchestrator.py
def run(
    self,
    companies: list[dict],  # each dict has at minimum {"cod": str}
    vigencia: str,          # MMYYYY format, e.g. "012025"
    dest_folder: Path,      # pathlib.Path to destination directory
    gerar_mei: bool = False # passed through to WorkflowProcessor
) -> None:
    # Runs synchronously — call in a daemon thread
```

### Starting the Batch Thread (Phase 3 responsibility per SUMMARY.md)

```python
# Source: Phase 2 SUMMARY.md "Next Phase Readiness" section
def _start_batch(self):
    self._q = queue.Queue()           # fresh queue per batch
    self._orc = BatchOrchestrator(self._q)
    self._running = True
    self._elapsed_times = []          # for ETA tracking

    companies = self._companies       # populated by _on_analyst_selected
    vigencia  = self._var_vigencia.get().strip()
    dest      = Path(self._var_dest.get().strip())

    t = threading.Thread(
        target=self._orc.run,
        args=(companies, vigencia, dest),
        daemon=True,                  # daemon=True is Phase 3's responsibility
    )
    t.start()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `janela.update()` from worker thread | `after(100, _poll_queue)` + queue | This phase (Phase 3) | Eliminates thread-safety violation in batch mode; individual mode retains the old pattern (acceptable) |
| Single-window flat UI | `ttk.Notebook` with Individual + Lote tabs | This phase | Additive; existing workflow untouched |

**Deprecated/outdated:**
- `ScrolledText`: Forbidden. Use `tk.Text` + `ttk.Scrollbar` as prescribed.
- `janela.update()` in batch callbacks: The existing individual workflow uses it (app.py line 148); batch callbacks must never use it.

---

## Open Questions

1. **Window geometry for combined Individual + Lote tabs**
   - What we know: Current window is `420x580`, `resizable(False, False)`. Batch log needs ~12 text lines (~200px) plus controls.
   - What's unclear: Whether to use a fixed larger size or allow resizing. The `resizable(False, False)` currently prevents accidental layout breaks.
   - Recommendation: Use `"900x660"`, keep `resizable(False, False)`. Individual tab content constrained inside a ~420px-wide inner Frame with centering padding so it visually matches the current layout.

2. **When to load analyst list from spreadsheet**
   - What we know: `load_analysts()` can raise `SpreadsheetAccessError` if G: drive unavailable. Calling it in `__init__` will break app startup if drive is down.
   - What's unclear: Whether to load at tab activation or at panel init.
   - Recommendation: Load on `<<NotebookTabChanged>>` event when Lote tab is selected, or provide an explicit "Carregar lista" button that the analyst clicks. Display a descriptive error label (not a crash) if load fails.

3. **`gerar_mei` flag in batch mode**
   - What we know: `BatchOrchestrator.run()` accepts `gerar_mei: bool = False`. The individual tab has a MEI checkbox.
   - What's unclear: Requirements do not mention a MEI checkbox for the batch tab.
   - Recommendation: Default `gerar_mei=False` in batch mode. Do not add a MEI checkbox unless explicitly required. Out of scope for v1 per REQUIREMENTS.md.

---

## Validation Architecture

`nyquist_validation` is enabled (`config.json` line 11: `"nyquist_validation": true`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (current — confirmed by `tests/` directory with `conftest.py`) |
| Config file | none detected — pytest discovers via `tests/` directory convention |
| Quick run command | `pytest tests/test_batch_panel.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SELEC-01 | `load_analysts()` result populates Combobox values | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_analyst_list_populated -x` | Wave 0 |
| SELEC-02 | Vigencia StringVar accepts MMYYYY string | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_vigencia_input -x` | Wave 0 |
| SELEC-03 | Dest folder StringVar set after `askdirectory()` | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_dest_folder_set -x` | Wave 0 |
| SELEC-04 | Start button disabled when any field is empty | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_start_disabled_until_all_fields -x` | Wave 0 |
| PROG-01 | Progressbar maximum and value updated by `company_start` | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_progress_bar_updates -x` | Wave 0 |
| PROG-02 | Current company label text updated by `company_start` | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_current_company_label -x` | Wave 0 |
| PROG-03 | ETA label updated after first `company_done` | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_eta_after_first_done -x` | Wave 0 |
| PROG-04 | Log text widget contains company entry after `company_done` | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_log_entry_appended -x` | Wave 0 |
| RESULT-01 | `batch_done` triggers summary messagebox with totals | manual-only | manual | N/A |
| RESULT-02 | Summary lists failed companies when errors > 0 | unit (no Tkinter) | `pytest tests/test_batch_panel.py::test_summary_lists_errors -x` | Wave 0 |

**Note on Tkinter unit tests:** `PainelLote` is a `tk.Frame` subclass. Unit tests that do not open a real Tk window must test the business logic methods (`_update_start_state`, `_on_company_start`, `_on_company_done`, `_on_batch_done`) in isolation by constructing a `PainelLote` against a real hidden `tk.Tk()` root (created and destroyed per test, or per module via a session-scoped fixture). This is the standard approach for Tkinter unit testing — create a root with `tk.Tk()`, call `root.withdraw()` to hide it, run tests, destroy at teardown.

RESULT-01 is marked manual-only because `messagebox.showinfo` cannot be easily asserted without a real display interaction in the test environment (Windows messageboxes require a real event loop response).

### Sampling Rate

- **Per task commit:** `pytest tests/test_batch_panel.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_batch_panel.py` — covers SELEC-01 through PROG-04, RESULT-02 (8 stubs)
- [ ] Shared Tkinter root fixture in `tests/conftest.py` — add `tk_root` session-scoped fixture that creates `tk.Tk()`, calls `withdraw()`, and yields; teardown calls `destroy()`

Existing `tests/conftest.py` has `tmp_xlsx` fixture only — needs the `tk_root` fixture added.

---

## Sources

### Primary (HIGH confidence)

- `services/batch_orchestrator.py` (Phase 2 deliverable, direct read) — complete queue message schema, all 6 message types, exact tuple positions, `BatchSummary` and `CompanyResult` dataclasses
- `ui/app.py` (direct read) — current window geometry `420x580`, `resizable(False, False)`, all widget structure, existing `log()` threading violation at line 148, `_abrir_tela_manual_wrapper` pattern
- `ui/dialogs.py` (direct read) — `abrir_tela_manual_itemlc` full signature, `parent_window.wait_window()` pattern (line 264), dialog geometry `"540x560"` / `"540x520"`
- `services/spreadsheet.py` (Phase 1 deliverable, direct read) — `load_analysts()` and `get_companies_for_analyst()` API, typed exceptions `SpreadsheetAccessError` / `SpreadsheetFormatError`
- `config.py` (direct read) — all color constants; `PLANILHA_EMPRESAS`, `PLANILHA_COL_COD`, `PLANILHA_COL_ANALISTA`
- `ui/components.py` (direct read) — `criar_botao`, `criar_entry`, `CircularProgress` interfaces
- `.planning/phases/02-batch-orchestrator/02-02-SUMMARY.md` — Phase 3 responsibilities stated explicitly
- `.planning/research/SUMMARY.md` — architecture prescriptions, widget prescriptions (`tk.Text` + `ttk.Scrollbar`, not `ScrolledText`)
- `.planning/STATE.md` — decision log, threading model decisions, Phase 3 open items

### Secondary (MEDIUM confidence)

- Python stdlib Tkinter threading FAQ — `after()` poll pattern for inter-thread communication
- Python `ttk.Notebook` docs — tab management, `<<NotebookTabChanged>>` event
- Python `ttk.Combobox` docs — `state="readonly"`, `<<ComboboxSelected>>` event, `values` option

### Tertiary (LOW confidence)

- None — all findings are grounded in direct codebase reads or Python stdlib docs.

---

## Metadata

**Confidence breakdown:**
- Queue message schema: HIGH — read directly from Phase 2 source file, verified against test file assertions
- Dialog signature: HIGH — read directly from `dialogs.py` lines 106-107 and 264
- Widget prescriptions: HIGH — stated explicitly in SUMMARY.md and critical architectural constraints
- ETA estimation: HIGH — derived directly from `elapsed_seconds` field present in `company_done` messages
- Window geometry: MEDIUM — current `420x580` confirmed from source; new size `900x660` is a reasoned recommendation, not measured from actual layout
- Test strategy: HIGH — follows existing `test_batch_orchestrator.py` pattern (skipif import guard, FakeProcessor inner class)

**Research date:** 2026-03-09
**Valid until:** Stable — stdlib-only stack; no fast-moving dependencies. Valid until `batch_orchestrator.py` is modified (unlikely per project constraints).
