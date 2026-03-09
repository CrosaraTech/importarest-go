# Phase 2: Batch Orchestrator - Research

**Researched:** 2026-03-09
**Domain:** Python threading — queue.Queue + threading.Event worker loop, WorkflowProcessor callback injection, TXT file saving
**Confidence:** HIGH

## Summary

Phase 2 builds `services/batch_orchestrator.py` — a background worker that calls `WorkflowProcessor.processar()` once per company in a sequential loop, pipes progress events to the UI via `queue.Queue`, and pauses correctly for manual review dialogs via `threading.Event`. It has no UI code; it is pure worker logic that Phase 3 (UI) will consume.

The WorkflowProcessor contract is fully understood from direct source reading. It accepts 4 callbacks at construction time (`log_fn`, `progress_fn`, `contador_fn`, `abrir_tela_manual_fn`) and a `gerar_mei` flag. The `abrir_tela_manual_fn` callback is the critical integration point: in batch mode the worker must never open a Tkinter dialog directly. Instead, it signals the main thread via `queue.Queue`, blocks on `threading.Event.wait()`, and the main thread opens the dialog via `after()`, then sets the event with the result attached. This is the prescribed PROC-03 pattern and it is non-negotiable.

The TXT saving contract is also well-defined from existing `app.py`: `result.conteudo_final` is written to `{cod}_{vigencia}.txt`; `result.notas_vig_errada` produces additional `{cod}_{vig_errada}.txt` files. The orchestrator saves files immediately after each company completes, before moving to the next. The result summary accumulates `{cod, status, notes_count, error_detail}` per company and is returned to the caller (Phase 3 UI) at the end of the run.

**Primary recommendation:** Implement `BatchOrchestrator` as a class with a single public `run()` method that accepts a company list, a destination folder, a vigencia string, and a `queue.Queue`. The manual review callback follows the queue+Event pattern exactly as prescribed in STATE.md.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROC-01 | System processes all analyst companies (GOIANIA) sequentially without manual intervention between them | Sequential for-loop over `get_companies_for_analyst()` result; `WorkflowProcessor` constructed fresh per company via callback injection |
| PROC-02 | When a company fails, system logs the error and automatically skips to the next company | try/except around each `processor.processar()` call; catches `Exception`; appends error entry to result list; continues loop |
| PROC-03 | When a note requires manual review during batch, system pauses and displays the review dialog normally — after analyst responds, batch continues | `abrir_tela_manual_fn` replaced by queue+Event callback; worker puts `("manual_review", dados, chave, from_n8n, event, result_holder)` on queue; blocks on `event.wait()`; main thread opens dialog via `after()`, sets event |
| PROC-04 | Analyst can click "Abort" at any time — system stops after current company finishes | Worker checks `abort_event.is_set()` after each company loop iteration; if set, exits loop cleanly and returns partial summary |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `queue.Queue` | stdlib | Thread-safe message channel from worker to UI | Only safe way to pass data from background thread to Tkinter main thread; documented in Python threading FAQ |
| `threading.Event` | stdlib | Zero-CPU block/signal for pause (PROC-03) and abort (PROC-04) | `wait()` releases GIL; `set()` is atomic; correct primitive for "block until condition" |
| `threading.Thread` | stdlib | Background worker thread | Already used in `app.py` line 176 — same pattern extended to batch |
| `services.spreadsheet` | Phase 1 | Source of company list | `get_companies_for_analyst(analista)` returns `list[dict]` with `cod` key |
| `services.processor.WorkflowProcessor` | existing | Per-company NFS-e processing pipeline | Accepts callbacks at construction; no modifications required |
| `pathlib.Path` | stdlib | TXT file path construction and write | Already used throughout `processor.py` and `app.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `time` | stdlib | Per-company elapsed time for ETA calculation | Record `time.monotonic()` before/after each company; pass duration in queue message |
| `dataclasses.dataclass` | stdlib (3.7+) | `CompanyResult` value object | Cleaner than dict for structured result accumulation; no external dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `threading.Event` for pause | `threading.Condition` | Overkill; Event is sufficient for binary signal |
| `dataclass` for result | `TypedDict` or plain dict | TypedDict needs no import; plain dict is looser; dataclass is self-documenting — prefer dataclass |
| queue per message type | multiple queues | Single queue with message-type discriminator (tuple[str, ...]) is simpler to poll |

**Installation:** No new dependencies required. All imports are Python stdlib or already present in the project.

---

## Architecture Patterns

### Recommended Project Structure
```
services/
└── batch_orchestrator.py    # New file — this phase's entire deliverable
tests/
└── test_batch_orchestrator.py  # New file — Wave 0 test stubs + implementations
```

No other files are modified in this phase.

### Pattern 1: WorkflowProcessor Callback Contract

**What:** `WorkflowProcessor.__init__` accepts 4 callable parameters. The batch orchestrator replaces all 4 with batch-aware versions.

**Exact signature (from processor.py line 87-93):**
```python
WorkflowProcessor(
    log_fn: Callable,            # Called with (msg: str) — no return value used
    progress_fn: Callable,       # Called with (total: int) — sets max for progress bar
    contador_fn: Callable,       # Called with (atual: int, total: int) — updates counter
    abrir_tela_manual_fn: Callable,  # Called with (dados_base: dict, chave_nfse: str, from_n8n: bool) -> str | None
    gerar_mei: bool = False,
)
```

**Call sites for `abrir_tela_manual_fn` (4 locations in processor.py):**
- Line 298: `self._abrir_tela_manual(dados_manual, nome, from_n8n=True)` — extract incomplete, manual fill
- Line 355: `self._abrir_tela_manual(dados_manual, nome, from_n8n=True)` — Goiania MEI, extract
- Line 385: `self._abrir_tela_manual(dados_manual, nome, from_n8n=False)` — Goiania MEI, local fallback
- Line 492: `self._abrir_tela_manual(dados_manual, chave_nf, from_n8n=True)` — map_only retry

**Return value contract:** Returns `str | None`. The string is a semicolon-delimited TXT line. `None` means the analyst cancelled — processor logs "Cancelado" and continues to next note.

**processar() return value:**
```python
ProcessorResult | None
# None means: folder not found, or no XMLs found — company is a skip candidate
# ProcessorResult fields used by batch orchestrator:
#   .conteudo_final: str       — main TXT content (empty string if no valid notes)
#   .notas_vig_errada: dict    — {vig_str: [line, ...]} for off-vigencia notes
#   .linhas_dict: dict         — non-empty means there are notes to save
#   .im_tomador_cab: str       — header IM (may be empty — see caveat below)
#   .razao_tomador_cab: str    — header razao social (may be empty)
```

**CRITICAL CAVEAT — cabecalho completion:** In `app.py`, after `processar()` returns, `_completar_cabecalho()` is called if `result.linhas_dict or result.notas_vig_errada`. This opens `pedir_dados_cabecalho()` dialog when `im_tomador` or `razao_tomador` is empty. In batch mode this dialog MUST NOT be opened mid-loop. The batch orchestrator must handle the missing-header case differently: emit a `("warning", ...)` queue message and save the TXT as-is (with incomplete header), OR skip the header prompt and let the analyst fix TXTs after the run. The simplest correct approach is: save TXT as-is without prompting — the header fields are cosmetic metadata, not required for the import to function.

### Pattern 2: Queue Message Schema

**What:** The worker communicates all state changes to the UI as messages on `queue.Queue`. The UI polls the queue via `after(100, _poll_queue)` and dispatches each message.

**Message tuple schema:**

```python
# Progress: company started
("company_start", cod: str, index: int, total: int)

# Progress: per-note log line from processor callbacks
("log", cod: str, msg: str)

# Progress: note counter update from contador_fn
("counter", cod: str, atual: int, total: int)

# Manual review required — PROC-03 pause
("manual_review", dados_base: dict, chave_nfse: str, from_n8n: bool,
 event: threading.Event, result_holder: list)
# result_holder is a 1-element list: result_holder[0] = str|None after event is set

# Company complete
("company_done", cod: str, status: str, notes_count: int,
 elapsed_seconds: float, error_detail: str)
# status: "ok" | "error" | "skipped"
# error_detail: "" on success, exception message on error

# Batch complete (normal finish or abort)
("batch_done", summary: BatchSummary)
```

**BatchSummary dataclass:**
```python
@dataclass
class CompanyResult:
    cod: str
    status: str            # "ok" | "error" | "skipped"
    notes_count: int       # len(result.linhas_dict) on success, 0 on error/skip
    elapsed_seconds: float
    error_detail: str      # "" on success

@dataclass
class BatchSummary:
    total: int
    successes: int
    errors: int
    skipped: int
    aborted: bool
    company_results: list[CompanyResult]
    elapsed_total_seconds: float
```

### Pattern 3: PROC-03 Manual Review — Queue+Event Protocol

**What:** Worker cannot open Tkinter widgets. When `abrir_tela_manual_fn` is called by the processor, the batch callback puts a message on the queue, blocks, and waits for the main thread to respond.

**Worker side:**
```python
def _make_manual_review_callback(self, cod: str):
    def abrir_tela_manual_batch(dados_base: dict, chave_nfse: str,
                                from_n8n: bool = False) -> str | None:
        event = threading.Event()
        result_holder = [None]   # [0] will be set to str | None
        self._queue.put((
            "manual_review", dados_base, chave_nfse, from_n8n,
            event, result_holder
        ))
        event.wait()             # blocks worker; releases GIL
        return result_holder[0]  # str (TXT line) or None (cancelled)
    return abrir_tela_manual_batch
```

**Main thread side (in PainelLote._poll_queue, Phase 3):**
```python
elif msg_type == "manual_review":
    _, dados_base, chave_nfse, from_n8n, event, result_holder = msg
    def _open_dialog():
        result_holder[0] = abrir_tela_manual_itemlc(
            self.master, dados_base, chave_nfse, from_n8n
        )
        event.set()
    self.after(0, _open_dialog)
```

**Why `event.wait()` is safe:** The worker thread blocks with GIL released. The main thread remains responsive and drains its Tkinter event loop normally. The `after(0, _open_dialog)` callback fires in the next Tk event loop iteration. After the dialog closes, `event.set()` wakes the worker. This is the exact pattern prescribed in STATE.md and is standard Python threading FAQ guidance.

### Pattern 4: Abort Signal (PROC-04)

**What:** `abort_event` is a `threading.Event` created by the orchestrator. The UI calls `abort_event.set()` to signal abort. The worker checks it after each company.

```python
class BatchOrchestrator:
    def __init__(self, queue: queue.Queue):
        self._queue = queue
        self._abort_event = threading.Event()

    def abort(self):
        """Called from main thread (UI abort button)."""
        self._abort_event.set()

    def run(self, companies: list[dict], vigencia: str, dest_folder: Path):
        for i, company in enumerate(companies):
            if self._abort_event.is_set():
                break
            self._process_one(company, i, len(companies), vigencia, dest_folder)
        # Always emit batch_done — whether completed or aborted
        self._queue.put(("batch_done", self._build_summary(aborted=self._abort_event.is_set())))
```

**Key design:** Worker checks abort BEFORE starting each new company, not mid-company. This matches PROC-04: "system stops after current company finishes." Current company always completes its `processar()` call fully.

### Pattern 5: TXT File Saving

**What:** Mirrors `app.py.salvar_arquivo_txt()` but without any dialog interaction. Save happens immediately after `processar()` returns, inside the worker loop.

```python
def _save_txt(self, result: ProcessorResult, cod: str, vigencia: str, dest: Path):
    # Primary file
    if result.conteudo_final:
        path = dest / f"{cod}_{vigencia}.txt"
        path.write_text(result.conteudo_final, encoding="utf-8")

    # Off-vigencia overflow files
    for vig_errada, linhas in result.notas_vig_errada.items():
        dt_iso = f"{vig_errada[2:]}-{vig_errada[:2]}-01T00:00:00"
        cab_extra = montar_cabecalho(
            result.im_tomador_cab, result.razao_tomador_cab, dt_iso
        )
        partes = ([cab_extra] if cab_extra else []) + linhas
        path_extra = dest / f"{cod}_{vig_errada}.txt"
        path_extra.write_text("\n".join(partes), encoding="utf-8")
```

**notes_count calculation:** `len(result.linhas_dict)` — consistent with how `processor.py` uses `linhas_dict` as the success set.

### Anti-Patterns to Avoid

- **Calling `janela.update()` from worker:** The existing `app.py log()` method calls `self.janela.update()` at line 148. Batch callbacks must NEVER use this `log` method. They must use the queue-based log callback instead.
- **Opening `messagebox` or `Toplevel` from worker:** All dialog opens must go via `queue.put()` + `event.wait()`.
- **Constructing one `WorkflowProcessor` for all companies:** A fresh instance must be created per company because `WorkflowProcessor._gerar_mei` is per-instance and because processor methods accumulate per-run state in local variables (not truly stateful, but the pattern is clean and matches existing usage in `fluxo_trabalho()`).
- **Catching `SystemExit` or `KeyboardInterrupt` in error handler:** The `except Exception` around `processar()` should be `except Exception`, not `except BaseException` — let real interpreter interrupts propagate.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe UI updates | Custom locking / direct widget.configure() | `queue.Queue` + `after(100, poll)` | queue is atomic; after() executes in main thread; no lock needed |
| Worker pause for dialog | `time.sleep()` polling | `threading.Event.wait()` | sleep wastes CPU and introduces latency; Event wakes immediately when set |
| Abort detection | Shared boolean + lock | `threading.Event.is_set()` | Event reads are atomic in CPython; no explicit lock needed |
| File path building | String concatenation | `pathlib.Path` | Already standard throughout codebase; handles separator normalization |

**Key insight:** The Python stdlib has exactly the right primitive for every concurrency need here. Hand-rolling any of these with raw locks or shared variables introduces race conditions.

---

## Common Pitfalls

### Pitfall 1: Worker opens Tkinter widget directly (CRITICAL)
**What goes wrong:** If `abrir_tela_manual_fn` callback creates `tk.Toplevel` or calls `messagebox` from the worker thread, Tkinter enters re-entrant state on Windows. Result: intermittent freezes, widget corruption, or silent crash with no traceback.
**Why it happens:** The worker thread calls `_abrir_tela_manual()` — this is inside `processor.py` and happens 4 times in 3 processing paths.
**How to avoid:** The batch `abrir_tela_manual_fn` must NEVER create widgets. It puts a `("manual_review", ...)` tuple on the queue and calls `event.wait()`. Only the main thread (via `after()`) creates the dialog.
**Warning signs:** "main thread is not in main loop" RuntimeError in Tkinter; dialog appears then disappears immediately; UI freezes on first manual review.

### Pitfall 2: `janela.update()` called from batch log callback (HIGH)
**What goes wrong:** `app.py.log()` calls `self.janela.update()` at line 148. If the batch orchestrator passes `janela.log` as `log_fn`, this call happens from the worker thread. Under load, pumping the Tk event loop from off-thread can cause button clicks to fire mid-processing or cause visual artifacts.
**Why it happens:** Existing `app.py` was built for single-company runs where the worker is short-lived; `update()` off-thread was tolerable there but is not in a loop over 30+ companies.
**How to avoid:** The batch `log_fn` callback must be: `lambda msg: self._queue.put(("log", cod, msg))`. It never touches any widget.
**Warning signs:** Buttons become clickable mid-batch; UI appears to "stutter"; intermittent double-fire of button callbacks.

### Pitfall 3: `processar()` returns `None` is treated as error (MEDIUM)
**What goes wrong:** `WorkflowProcessor.processar()` returns `None` when the company's folder does not exist (`BASE_DIR / f"{cod}-" / vigencia`). This is not an exception — it's a valid "company has no files for this vigencia" case. If the orchestrator catches this as `Exception`, the status column is wrong and the error_detail is misleading.
**Why it happens:** Caller must check `if result is None` explicitly. The processor only raises exceptions for unexpected errors; missing folder is `return None`.
**How to avoid:** Check `if result is None:` first; record as status `"skipped"` with detail "Pasta de notas não encontrada" — not as `"error"`.
**Warning signs:** Companies with genuinely empty periods appear in the error list; summary error count inflated.

### Pitfall 4: notes_count miscalculated (LOW)
**What goes wrong:** Using `len(result.relatorio)` instead of `len(result.linhas_dict)` for `notes_count`. `relatorio` includes cancelled and errored notes; `linhas_dict` is only successfully processed notes.
**Why it happens:** `relatorio` is the larger, more visible structure; `linhas_dict` is the one that actually populates the TXT.
**How to avoid:** Always use `len(result.linhas_dict)` for `notes_count` in `CompanyResult`. The `relatorio` list is not needed by the orchestrator — leave it unused.
**Warning signs:** Success count in summary is higher than actual TXT line count.

### Pitfall 5: Abort event checked mid-company (MEDIUM)
**What goes wrong:** If abort is checked inside the `log_fn` callback (i.e., per-note), the worker can interrupt `processar()` mid-execution, leaving `linhas_dict` partially populated and TXT not yet saved.
**Why it happens:** Desire to make abort more responsive.
**How to avoid:** Check `abort_event.is_set()` only at the TOP of the loop, BEFORE calling `processar()`. Each call to `processar()` must run to completion. Per PROC-04: "stops after current company finishes."
**Warning signs:** Partial TXT files in destination folder; last company's file is truncated.

### Pitfall 6: Worker thread is not daemon (LOW)
**What goes wrong:** If the user closes the window while batch is running, the non-daemon worker thread keeps the Python process alive. App appears to have closed but process hangs.
**Why it happens:** `threading.Thread(daemon=False)` is the default.
**How to avoid:** Always `daemon=True` on the batch thread, consistent with existing `app.py` line 179 (`daemon=True`).
**Warning signs:** Python process visible in Task Manager after app window closes.

---

## Code Examples

### BatchOrchestrator skeleton
```python
# Source: derived from app.py fluxo_trabalho() pattern and STATE.md prescribed architecture
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.processor import WorkflowProcessor
from core.txt_builder import montar_cabecalho


@dataclass
class CompanyResult:
    cod: str
    status: str            # "ok" | "error" | "skipped"
    notes_count: int
    elapsed_seconds: float
    error_detail: str


@dataclass
class BatchSummary:
    total: int
    successes: int
    errors: int
    skipped: int
    aborted: bool
    company_results: list[CompanyResult] = field(default_factory=list)
    elapsed_total_seconds: float = 0.0


class BatchOrchestrator:

    def __init__(self, q: queue.Queue):
        self._queue = q
        self._abort_event = threading.Event()
        self._results: list[CompanyResult] = []

    def abort(self):
        self._abort_event.set()

    def run(self, companies: list[dict], vigencia: str, dest_folder: Path,
            gerar_mei: bool = False):
        batch_start = time.monotonic()
        total = len(companies)

        for i, company in enumerate(companies):
            if self._abort_event.is_set():
                break
            cod = company["cod"]
            self._queue.put(("company_start", cod, i, total))
            self._process_one(cod, vigencia, dest_folder, gerar_mei)

        elapsed = time.monotonic() - batch_start
        summary = self._build_summary(
            total=total,
            aborted=self._abort_event.is_set(),
            elapsed=elapsed,
        )
        self._queue.put(("batch_done", summary))

    def _process_one(self, cod: str, vigencia: str, dest_folder: Path,
                     gerar_mei: bool):
        t0 = time.monotonic()
        try:
            processor = WorkflowProcessor(
                log_fn=lambda msg: self._queue.put(("log", cod, msg)),
                progress_fn=lambda total: self._queue.put(("counter", cod, 0, total)),
                contador_fn=lambda a, t: self._queue.put(("counter", cod, a, t)),
                abrir_tela_manual_fn=self._make_manual_callback(cod),
                gerar_mei=gerar_mei,
            )
            result = processor.processar(cod, vigencia)

            if result is None:
                self._record(cod, "skipped", 0, time.monotonic() - t0, "Pasta não encontrada")
                self._queue.put(("company_done", cod, "skipped", 0,
                                 time.monotonic() - t0, "Pasta não encontrada"))
                return

            self._save_txt(result, cod, vigencia, dest_folder)
            notes = len(result.linhas_dict)
            elapsed = time.monotonic() - t0
            self._record(cod, "ok", notes, elapsed, "")
            self._queue.put(("company_done", cod, "ok", notes, elapsed, ""))

        except Exception as exc:
            elapsed = time.monotonic() - t0
            self._record(cod, "error", 0, elapsed, str(exc))
            self._queue.put(("company_done", cod, "error", 0, elapsed, str(exc)))

    def _make_manual_callback(self, cod: str):
        def callback(dados_base: dict, chave_nfse: str,
                     from_n8n: bool = False) -> Optional[str]:
            event = threading.Event()
            result_holder = [None]
            self._queue.put(("manual_review", dados_base, chave_nfse,
                             from_n8n, event, result_holder))
            event.wait()
            return result_holder[0]
        return callback

    def _save_txt(self, result, cod: str, vigencia: str, dest: Path):
        if result.conteudo_final:
            (dest / f"{cod}_{vigencia}.txt").write_text(
                result.conteudo_final, encoding="utf-8"
            )
        for vig_err, linhas in result.notas_vig_errada.items():
            dt_iso = f"{vig_err[2:]}-{vig_err[:2]}-01T00:00:00"
            cab = montar_cabecalho(result.im_tomador_cab,
                                   result.razao_tomador_cab, dt_iso)
            content = "\n".join(([cab] if cab else []) + linhas)
            (dest / f"{cod}_{vig_err}.txt").write_text(content, encoding="utf-8")

    def _record(self, cod, status, notes, elapsed, detail):
        self._results.append(
            CompanyResult(cod=cod, status=status, notes_count=notes,
                          elapsed_seconds=elapsed, error_detail=detail)
        )

    def _build_summary(self, total: int, aborted: bool,
                       elapsed: float) -> BatchSummary:
        return BatchSummary(
            total=total,
            successes=sum(1 for r in self._results if r.status == "ok"),
            errors=sum(1 for r in self._results if r.status == "error"),
            skipped=sum(1 for r in self._results if r.status == "skipped"),
            aborted=aborted,
            company_results=list(self._results),
            elapsed_total_seconds=elapsed,
        )
```

### Launching the orchestrator from UI (Phase 3 pattern)
```python
# Source: mirrors app.py lines 176-180; to be implemented in Phase 3
import queue, threading
from services.batch_orchestrator import BatchOrchestrator

# In PainelLote.iniciar_lote():
self._queue = queue.Queue()
self._orchestrator = BatchOrchestrator(self._queue)
t = threading.Thread(
    target=self._orchestrator.run,
    args=(companies, vigencia, dest_folder),
    daemon=True,
)
t.start()
self.after(100, self._poll_queue)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-company: `janela.update()` from worker (app.py:148) | Batch: `queue.Queue` + `after()` | Phase 2 introduces correct pattern | Batch is thread-safe; existing individual tab unchanged |
| `abrir_tela_manual_fn` opens dialog synchronously | Batch: queue+Event defers dialog to main thread | Phase 2 | PROC-03 works without Tkinter re-entrancy |

**Deprecated/outdated:**
- `janela.update()` from worker thread: acceptable in the existing single-company flow but never appropriate for batch loops. The batch orchestrator must never use this pattern — it is not "deprecated" globally but is explicitly banned in batch callbacks.

---

## Open Questions

1. **Missing cabecalho fields during batch (im_tomador / razao_tomador empty)**
   - What we know: `_completar_cabecalho()` in `app.py` opens a dialog if these are empty; dialogs cannot open from worker thread; TXT files can be written with empty header fields and remain functional for the REST import
   - What's unclear: Is an empty header field acceptable to the REST import system, or does it cause a downstream validation error?
   - Recommendation: Save TXT as-is (without prompting); emit a `("log", cod, "⚠️ Cabeçalho incompleto — IM ou Razão Social não encontrado nos XMLs")` warning message so the analyst sees it in the batch log. Phase 3 can expose this as a flag in the summary. Do not block batch progress.

2. **gerar_mei flag for batch mode**
   - What we know: `WorkflowProcessor` accepts `gerar_mei: bool` at construction; existing UI has a checkbox for it; the batch panel may or may not expose this option
   - What's unclear: Whether batch mode should always use `gerar_mei=False` (conservative) or expose the checkbox
   - Recommendation: Accept `gerar_mei` as a parameter to `BatchOrchestrator.run()` with default `False`; Phase 3 decides whether to expose a UI control for it.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (detected: `tests/conftest.py`, `tests/test_spreadsheet.py`) |
| Config file | none — pytest auto-discovers `tests/` |
| Quick run command | `pytest tests/test_batch_orchestrator.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROC-01 | Sequential loop processes all companies without skipping | unit | `pytest tests/test_batch_orchestrator.py::test_run_processes_all_companies -x` | Wave 0 |
| PROC-02 | Company exception is caught; loop continues to next company | unit | `pytest tests/test_batch_orchestrator.py::test_company_error_continues_loop -x` | Wave 0 |
| PROC-03 | manual_review message emitted; event.wait() called; result_holder populated | unit | `pytest tests/test_batch_orchestrator.py::test_manual_review_queue_event_protocol -x` | Wave 0 |
| PROC-04 | abort() sets event; loop exits after current company; summary has aborted=True | unit | `pytest tests/test_batch_orchestrator.py::test_abort_stops_after_current_company -x` | Wave 0 |

**Additional tests (supporting correctness):**
| Behavior | Test Type | Command |
|----------|-----------|---------|
| `None` result from processar() is status="skipped" not "error" | unit | `pytest tests/test_batch_orchestrator.py::test_none_result_is_skipped -x` |
| TXT file written to dest_folder with correct name | unit | `pytest tests/test_batch_orchestrator.py::test_txt_saved_to_dest_folder -x` |
| off-vigencia overflow TXT files saved | unit | `pytest tests/test_batch_orchestrator.py::test_overflow_vig_txt_saved -x` |
| BatchSummary totals are correct | unit | `pytest tests/test_batch_orchestrator.py::test_batch_summary_counts -x` |

### Sampling Rate
- **Per task commit:** `pytest tests/test_batch_orchestrator.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_batch_orchestrator.py` — covers PROC-01 through PROC-04 and all supporting tests (does not exist yet; must be created as first task of Wave 1)
- [ ] `services/batch_orchestrator.py` — module under test (does not exist yet)

*(conftest.py already exists with `tmp_xlsx` fixture; no changes needed)*

---

## Sources

### Primary (HIGH confidence)
- Direct codebase reading `services/processor.py` — WorkflowProcessor constructor signature (lines 87-93), `abrir_tela_manual_fn` call sites (lines 298, 355, 385, 492), `processar()` return contract (lines 95-141), `ProcessorResult` fields (lines 18-31)
- Direct codebase reading `ui/app.py` — existing threading pattern (lines 176-180), `janela.update()` violation (line 148), `fluxo_trabalho()` callback wiring (lines 184-191), TXT saving logic (lines 303-352)
- Direct codebase reading `ui/dialogs.py` — `abrir_tela_manual_itemlc()` signature (line 106-107), `parent_window.wait_window(dlg)` usage (line 264) confirming synchronous dialog behavior
- Direct codebase reading `services/spreadsheet.py` — `get_companies_for_analyst()` return type `list[dict]` with `cod` key (lines 158-173)
- Direct codebase reading `config.py` — `BASE_DIR`, `PLANILHA_EMPRESAS`, all constants
- `.planning/STATE.md` — Architecture decision on PROC-03 (queue.Queue + threading.Event + after()); janela.update() concern documented
- `.planning/research/SUMMARY.md` — Queue message schema draft, pitfall catalogue, phase ordering rationale

### Secondary (MEDIUM confidence)
- Python stdlib documentation — `queue.Queue` thread safety guarantees, `threading.Event.wait()` GIL release behavior, `threading.Thread(daemon=True)` semantics
- Python Tkinter threading FAQ — `after()` as the correct mechanism for scheduling UI updates from worker threads

### Tertiary (LOW confidence)
- N8N timeout behavior under batch load — `n8n_client.py` shows default 150s timeout; research summary recommends 60s for batch; actual batch timeout value not validated against production data

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are Python stdlib or already in project; no new dependencies
- Architecture: HIGH — callback contract read directly from processor.py source; queue+Event pattern is stdlib-documented
- Pitfalls: HIGH — identified from actual code paths (janela.update() at line 148, 4 abrir_tela_manual call sites); not speculative

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (stable stdlib patterns; processor.py is not modified in this phase)
