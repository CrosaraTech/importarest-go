"""
ui/batch_panel.py — Phase 3 deliverable.

PainelLote: tk.Frame subclass encapsulating all batch UI logic —
selection widgets, progress display, queue poll loop, PROC-03 manual
review handler, and post-run summary.

Phase 3 plan 03-02.
"""
import queue
import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter import ttk

from config import (
    COR_BG, COR_CARD, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO, COR_BORDA,
)
from services.spreadsheet import load_analysts, get_companies_for_analyst
from services.spreadsheet import SpreadsheetError
from services.batch_orchestrator import BatchOrchestrator, BatchSummary
from ui.dialogs import abrir_tela_manual_itemlc


class PainelLote(tk.Frame):
    """Batch processing panel — selection, progress, log, and summary."""

    def __init__(self, parent):
        super().__init__(parent, bg=COR_BG)

        # Runtime state
        self._companies: list[dict] = []
        self._running: bool = False
        self._elapsed_times: list[float] = []
        self._total_companies: int = 0
        self._orc: BatchOrchestrator | None = None
        self._q: queue.Queue | None = None

        # StringVars
        self._var_analyst = tk.StringVar()
        self._var_vigencia = tk.StringVar()
        self._var_dest = tk.StringVar()
        self._var_mei = tk.BooleanVar(value=False)

        # Trace vars so start button updates automatically
        self._var_vigencia.trace_add("write", self._update_start_state)
        self._var_dest.trace_add("write", self._update_start_state)

        self._build_ui()

        # Start the idle poll loop — runs for the lifetime of the panel
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- A. Selection section ----------------------------------------
        frame_sel = tk.Frame(self, bg=COR_BG)
        frame_sel.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(frame_sel, text="Analista:", font=("Segoe UI", 9, "bold"),
                 bg=COR_BG, fg=COR_TEXTO, anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        self._cmb_analyst = ttk.Combobox(
            frame_sel, textvariable=self._var_analyst,
            state="readonly", width=28
        )
        self._cmb_analyst.grid(row=1, column=0, sticky="w", pady=(0, 6))
        self._cmb_analyst.bind("<<ComboboxSelected>>", self._on_analyst_selected)

        self._lbl_count = tk.Label(
            frame_sel, text="", font=("Segoe UI", 8),
            bg=COR_BG, fg=COR_SUBTEXTO, anchor="w"
        )
        self._lbl_count.grid(row=2, column=0, sticky="w", pady=(0, 4))

        tk.Label(frame_sel, text="Vigência (MMAAAA):", font=("Segoe UI", 9, "bold"),
                 bg=COR_BG, fg=COR_TEXTO, anchor="w").grid(
            row=3, column=0, sticky="w", pady=(0, 2))
        tk.Entry(frame_sel, textvariable=self._var_vigencia, width=12).grid(
            row=4, column=0, sticky="w", pady=(0, 6))

        tk.Label(frame_sel, text="Pasta de destino:", font=("Segoe UI", 9, "bold"),
                 bg=COR_BG, fg=COR_TEXTO, anchor="w").grid(
            row=5, column=0, sticky="w", pady=(0, 2))

        frame_dest = tk.Frame(frame_sel, bg=COR_BG)
        frame_dest.grid(row=6, column=0, sticky="w", pady=(0, 8))
        tk.Entry(frame_dest, textvariable=self._var_dest, width=32,
                 state="readonly").pack(side="left", padx=(0, 4))
        tk.Button(frame_dest, text="Escolher...", command=self._choose_dest,
                  font=("Segoe UI", 8), bg=COR_PRIMARIA, fg="#FFFFFF",
                  activebackground=COR_PRIMARIA_HV, activeforeground="#FFFFFF",
                  relief="flat", cursor="hand2", pady=2, padx=6).pack(side="left")

        tk.Checkbutton(
            frame_sel, text="Gerar notas MEI (Goiânia)",
            variable=self._var_mei,
            font=("Segoe UI", 9), bg=COR_BG, fg=COR_SUBTEXTO,
            activebackground=COR_BG, activeforeground=COR_SUBTEXTO,
            selectcolor=COR_BG, anchor="w",
        ).grid(row=7, column=0, sticky="w", pady=(0, 6))

        frame_actions = tk.Frame(frame_sel, bg=COR_BG)
        frame_actions.grid(row=8, column=0, sticky="w", pady=(0, 4))

        self._btn_start = tk.Button(
            frame_actions, text="INICIAR LOTE", command=self._start_batch,
            state="disabled", font=("Segoe UI", 9, "bold"),
            bg=COR_PRIMARIA, fg="#FFFFFF",
            activebackground=COR_PRIMARIA_HV, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", pady=4, padx=12
        )
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_abort = tk.Button(
            frame_actions, text="ABORTAR", command=self._abort,
            state="disabled", font=("Segoe UI", 9),
            bg="#C0392B", fg="#FFFFFF",
            activebackground="#A93226", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", pady=4, padx=12
        )
        self._btn_abort.pack(side="left")

        # ---- B. Progress section -----------------------------------------
        frame_prog = tk.Frame(self, bg=COR_BG)
        frame_prog.pack(fill="x", padx=8, pady=(4, 4))

        self._pb = ttk.Progressbar(frame_prog, mode="determinate", length=400)
        self._pb.pack(fill="x", pady=(0, 4))

        self._lbl_current = tk.Label(
            frame_prog, text="", font=("Segoe UI", 8),
            bg=COR_BG, fg=COR_SUBTEXTO, anchor="w"
        )
        self._lbl_current.pack(fill="x")

        self._lbl_eta = tk.Label(
            frame_prog, text="", font=("Segoe UI", 8),
            bg=COR_BG, fg=COR_SUBTEXTO, anchor="w"
        )
        self._lbl_eta.pack(fill="x")

        # ---- C. Log section -----------------------------------------------
        frame_log = tk.Frame(self, bg=COR_BG)
        frame_log.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        self._txt_log = tk.Text(
            frame_log, height=12, font=("Segoe UI", 8),
            bg=COR_CARD, fg=COR_TEXTO, relief="flat",
            state="disabled", wrap="word"
        )
        sb = ttk.Scrollbar(frame_log, orient="vertical",
                           command=self._txt_log.yview)
        self._txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._txt_log.pack(side="left", fill="both", expand=True)

        self._txt_log.tag_configure("ok",      foreground="#1B8A1B")
        self._txt_log.tag_configure("error",   foreground="#C0392B")
        self._txt_log.tag_configure("skipped", foreground="#B8860B")
        self._txt_log.tag_configure("info",    foreground=COR_SUBTEXTO)

    # ------------------------------------------------------------------
    # Public helper methods (called by tests)
    # ------------------------------------------------------------------

    def _load_analysts_into_combobox(self, names: list[str]):
        """Populate the analyst combobox with the given list of names."""
        self._cmb_analyst["values"] = names

    def _trigger_load_analysts(self):
        """Load analyst names into the combobox — called lazily when Lote tab is activated.

        Safe to call multiple times; subsequent calls re-populate the combobox.
        Any SpreadsheetError is silently caught and shown as an error label so the
        app does not crash when G: drive is unavailable at startup.
        """
        try:
            names = load_analysts()
            self._load_analysts_into_combobox(names)
        except SpreadsheetError as exc:
            self._lbl_count.configure(text=f"Erro ao carregar analistas: {exc}")

    def _update_start_state(self, *_):
        """Enable/disable start button based on whether all three fields are set."""
        ok = (
            bool(self._var_analyst.get())
            and bool(self._var_vigencia.get().strip())
            and bool(self._var_dest.get().strip())
        )
        self._btn_start.configure(state="normal" if ok else "disabled")

    def _on_company_start(self, cod: str, i: int, total: int):
        """Update progress bar and current-company label."""
        self._total_companies = total
        self._pb.configure(maximum=total, value=i + 1)
        self._lbl_current.configure(text=f"Processando: {cod}")

    def _on_company_done(self, cod: str, status: str, notes: int,
                         elapsed: float, detail: str):
        """Update ETA label and log a per-company entry."""
        self._elapsed_times.append(elapsed)
        avg = sum(self._elapsed_times) / len(self._elapsed_times)
        remaining = self._total_companies - len(self._elapsed_times)
        if remaining > 0:
            eta = avg * remaining
            mins, secs = divmod(int(eta), 60)
            self._lbl_eta.configure(text=f"ETA: ~{mins}m {secs}s")
        else:
            self._lbl_eta.configure(text="")

        tag = status if status in ("ok", "error", "skipped") else "info"
        msg = f"[{cod}] {status.upper()} — {detail or f'{notes} nota(s)'}"
        self._log(msg, tag)

    def _log(self, msg: str, tag: str = "info"):
        """Append a line to the log text widget."""
        self._txt_log.configure(state="normal")
        self._txt_log.insert(tk.END, msg + "\n", tag)
        self._txt_log.see(tk.END)
        self._txt_log.configure(state="disabled")

    def _build_summary_text(self, summary: BatchSummary) -> str:
        """Return a formatted summary string (does NOT show a messagebox)."""
        lines = []
        aborted_note = " (ABORTADO)" if summary.aborted else ""
        lines.append(f"=== Resumo do Lote{aborted_note} ===")
        lines.append(
            f"Total: {summary.total}  |  OK: {summary.successes}"
            f"  |  Erro: {summary.errors}  |  Pulado: {summary.skipped}"
        )
        if summary.errors > 0:
            lines.append("Empresas com erro:")
            for r in summary.company_results:
                if r.status == "error":
                    lines.append(f"  \u2022 {r.cod} \u2014 {r.error_detail}")
        return "\n".join(lines)

    def _on_batch_done(self, summary: BatchSummary):
        """Handle batch_done queue message — reset state and show summary."""
        self._running = False
        self._btn_start.configure(state="normal")
        self._btn_abort.configure(state="disabled")
        text = self._build_summary_text(summary)
        if summary.errors > 0:
            messagebox.showwarning("Lote Concluído com Erros", text)
        else:
            messagebox.showinfo("Lote Concluído", text)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_analyst_selected(self, event=None):
        """Load companies for the selected analyst."""
        name = self._var_analyst.get()
        try:
            companies = get_companies_for_analyst(name)
            self._companies = companies
            self._lbl_count.configure(
                text=f"{len(companies)} empresa(s) em GOIÂNIA"
            )
        except SpreadsheetError as exc:
            messagebox.showerror("Erro na Planilha", str(exc))
            self._companies = []
            self._lbl_count.configure(text="")
        self._update_start_state()

    def _choose_dest(self):
        """Open a directory chooser and store the selected path."""
        path = filedialog.askdirectory(title="Selecionar pasta de destino")
        if path:
            self._var_dest.set(path)  # StringVar trace fires _update_start_state

    def _start_batch(self):
        """Start the batch in a daemon thread with a fresh queue."""
        # Reset log
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", tk.END)
        self._txt_log.configure(state="disabled")
        # Reset progress
        self._lbl_eta.configure(text="")
        self._lbl_current.configure(text="")
        self._pb.configure(value=0)
        # Fresh queue per batch (prevents stale messages)
        self._q = queue.Queue()
        self._orc = BatchOrchestrator(self._q)
        self._running = True
        self._elapsed_times = []
        self._btn_start.configure(state="disabled")
        self._btn_abort.configure(state="normal")

        vigencia = self._var_vigencia.get()
        dest = Path(self._var_dest.get())
        companies = self._companies

        t = threading.Thread(
            target=self._orc.run,
            args=(companies, vigencia, dest, self._var_mei.get()),
            daemon=True,
        )
        t.start()

    def _abort(self):
        """Request abort — batch_orchestrator will finish current company first."""
        if self._orc:
            self._orc.abort()

    # ------------------------------------------------------------------
    # Queue poll loop
    # ------------------------------------------------------------------

    def _poll_queue(self):
        """Drain all pending queue messages, then reschedule."""
        try:
            while True:
                msg = self._q.get_nowait()
                self._dispatch(msg)
        except (queue.Empty, AttributeError):
            pass
        self.after(100, self._poll_queue)

    def _dispatch(self, msg):
        """Route a queue message to the appropriate handler."""
        kind = msg[0]
        if kind == "company_start":
            _, cod, i, total = msg
            self._on_company_start(cod, i, total)
        elif kind == "log":
            _, cod, text = msg
            self._log(f"[{cod}] {text}")
        elif kind == "counter":
            pass  # optional detail — not surfaced in v1
        elif kind == "manual_review":
            _, dados_base, chave_nfse, from_n8n, event, result_holder = msg
            self.after(
                0,
                lambda d=dados_base, c=chave_nfse, f=from_n8n,
                       e=event, r=result_holder:
                self._handle_manual_review(d, c, f, e, r),
            )
        elif kind == "company_done":
            _, cod, status, notes, elapsed, detail = msg
            self._on_company_done(cod, status, notes, elapsed, detail)
        elif kind == "batch_done":
            _, summary = msg
            self._on_batch_done(summary)

    def _handle_manual_review(self, dados_base, chave_nfse, from_n8n,
                               event, result_holder):
        """Open the manual review dialog from the main thread and signal worker."""
        try:
            result = abrir_tela_manual_itemlc(
                self.winfo_toplevel(), dados_base, chave_nfse, from_n8n
            )
            result_holder[0] = result
        finally:
            event.set()  # ALWAYS set — never leave worker blocked
