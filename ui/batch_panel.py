"""
ui/batch_panel.py — Batch processing panel.

PainelLote: tk.Frame subclass encapsulating all batch UI logic —
selection widgets, progress display, queue poll loop, PROC-03 manual
review handler, and post-run summary.
"""
import queue
import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from config import (
    COR_BG, COR_CARD, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO, COR_BORDA,
)
from services.spreadsheet import load_analysts, get_companies_for_analyst
from services.spreadsheet import SpreadsheetError
from services.batch_orchestrator import BatchOrchestrator, BatchSummary
from ui.dialogs import abrir_tela_manual_itemlc
from ui.components import criar_botao, CircularProgress


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
    # UI construction helpers
    # ------------------------------------------------------------------

    def _make_card(self, parent, title: str):
        """Card with orange left accent bar and optional section title.
        Returns (outer, body). Caller must pack/grid outer."""
        outer = tk.Frame(parent, bg=COR_BORDA, padx=1, pady=1)

        card = tk.Frame(outer, bg=COR_CARD)
        card.pack(fill="both", expand=True)

        # 4px orange left accent
        tk.Frame(card, bg=COR_PRIMARIA, width=4).pack(side="left", fill="y")

        body = tk.Frame(card, bg=COR_CARD)
        body.pack(side="left", fill="both", expand=True, padx=(14, 16), pady=12)

        if title:
            hdr = tk.Frame(body, bg=COR_CARD)
            hdr.pack(fill="x", pady=(0, 10))
            tk.Label(
                hdr, text=title.upper(),
                font=("Segoe UI", 8, "bold"),
                bg=COR_CARD, fg=COR_PRIMARIA, anchor="w",
            ).pack(side="left")
            tk.Frame(hdr, bg=COR_BORDA, height=1).pack(
                side="left", fill="x", expand=True, padx=(8, 0), pady=(4, 0)
            )

        return outer, body

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=COR_BG)
        hdr.pack(fill="x", padx=20, pady=(16, 12))

        logo_shown = False
        if _PIL_OK:
            try:
                logo_path = (
                    Path(__file__).resolve().parent.parent / "assets" / "logo_importarest.png"
                )
                img = Image.open(logo_path)
                img = img.resize((168, 47), Image.LANCZOS)
                logo = _PILImageTk.PhotoImage(img)
                lbl = tk.Label(hdr, image=logo, bg=COR_BG)
                lbl.image = logo
                lbl.pack(side="left", padx=(0, 16))
                logo_shown = True
            except (FileNotFoundError, OSError):
                pass
        if not logo_shown:
            tk.Label(
                hdr, text="IMPORTAREST GO",
                font=("Segoe UI", 14, "bold"),
                bg=COR_BG, fg=COR_PRIMARIA,
            ).pack(side="left", padx=(0, 16))

        # Vertical divider
        tk.Frame(hdr, bg=COR_BORDA, width=1).pack(side="left", fill="y", padx=(0, 16))

        # Title block
        title_block = tk.Frame(hdr, bg=COR_BG)
        title_block.pack(side="left")
        tk.Label(
            title_block, text="Processamento em Lote",
            font=("Segoe UI", 13, "bold"),
            bg=COR_BG, fg=COR_TEXTO,
        ).pack(anchor="w")
        tk.Label(
            title_block, text="Importe múltiplas empresas de uma vez",
            font=("Segoe UI", 9),
            bg=COR_BG, fg=COR_SUBTEXTO,
        ).pack(anchor="w")

        # ── Two-column body (config+buttons | progress circle) ───────────
        body = tk.Frame(self, bg=COR_BG)
        body.pack(fill="both", expand=True, padx=20)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=0, minsize=180)
        body.rowconfigure(2, weight=1)

        # ── LEFT col, row 0: Card Configuração ──────────────────────────
        outer_cfg, cfg = self._make_card(body, "Configuração do Lote")
        outer_cfg.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 10))

        # Analyst selector
        tk.Label(
            cfg, text="Analista", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x")
        cmb_border = tk.Frame(cfg, bg=COR_BORDA, padx=1, pady=1)
        cmb_border.pack(fill="x", pady=(2, 0))
        self._cmb_analyst = ttk.Combobox(
            cmb_border, textvariable=self._var_analyst,
            state="readonly", font=("Segoe UI", 10),
        )
        self._cmb_analyst.pack(fill="x")
        self._cmb_analyst.bind("<<ComboboxSelected>>", self._on_analyst_selected)

        self._lbl_count = tk.Label(
            cfg, text="", font=("Segoe UI", 8, "italic"),
            bg=COR_CARD, fg=COR_PRIMARIA, anchor="w",
        )
        self._lbl_count.pack(anchor="w", pady=(4, 8))

        # Vigência + MEI side by side
        row_vig = tk.Frame(cfg, bg=COR_CARD)
        row_vig.pack(fill="x", pady=(0, 8))

        col_vig = tk.Frame(row_vig, bg=COR_CARD)
        col_vig.pack(side="left", padx=(0, 32))
        tk.Label(
            col_vig, text="Vigência (MMAAAA)", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO,
        ).pack(anchor="w")
        vig_border = tk.Frame(col_vig, bg=COR_BORDA, padx=1, pady=1)
        vig_border.pack(anchor="w", pady=(2, 0))
        tk.Entry(
            vig_border, textvariable=self._var_vigencia, width=12,
            font=("Segoe UI", 10), relief="flat", bg=COR_CARD,
            fg=COR_TEXTO, insertbackground=COR_TEXTO, bd=0,
        ).pack(padx=4, pady=3)

        col_mei = tk.Frame(row_vig, bg=COR_CARD)
        col_mei.pack(side="left", pady=(16, 0))
        tk.Checkbutton(
            col_mei, text="Gerar notas MEI (Goiânia)",
            variable=self._var_mei,
            font=("Segoe UI", 9), bg=COR_CARD, fg=COR_SUBTEXTO,
            activebackground=COR_CARD, activeforeground=COR_TEXTO,
            selectcolor=COR_CARD, anchor="w", cursor="hand2",
        ).pack()

        # Destination folder
        tk.Label(
            cfg, text="Pasta de destino", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x")
        dest_row = tk.Frame(cfg, bg=COR_CARD)
        dest_row.pack(fill="x", pady=(2, 0))
        dest_border = tk.Frame(dest_row, bg=COR_BORDA, padx=1, pady=1)
        dest_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Entry(
            dest_border, textvariable=self._var_dest,
            font=("Segoe UI", 9), relief="flat", bg=COR_CARD,
            state="readonly", fg=COR_TEXTO, bd=0,
        ).pack(fill="x", padx=4, pady=3)
        tk.Button(
            dest_row, text="Escolher  ›",
            command=self._choose_dest,
            font=("Segoe UI", 9, "bold"), bg=COR_PRIMARIA, fg="#FFFFFF",
            activebackground=COR_PRIMARIA_HV, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", pady=5, padx=10, bd=0,
        ).pack(side="left")

        # ── LEFT col, row 1: Action buttons ─────────────────────────────
        btn_frame = tk.Frame(body, bg=COR_BG)
        btn_frame.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(0, 10))

        self._btn_start = criar_botao(
            btn_frame, "▶  INICIAR LOTE",
            self._start_batch, COR_PRIMARIA, width=18, font_size=10,
        )
        self._btn_start.configure(state="disabled")
        self._btn_start.pack(side="left", padx=(0, 10))

        self._btn_abort = tk.Button(
            btn_frame, text="✕  ABORTAR",
            command=self._abort,
            state="disabled", font=("Segoe UI", 10, "bold"),
            bg="#C0392B", fg="#FFFFFF",
            activebackground="#A93226", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", pady=8, padx=14, bd=0,
        )
        self._btn_abort.bind(
            "<Enter>",
            lambda e: self._btn_abort.configure(bg="#A93226")
            if str(self._btn_abort["state"]) == "normal" else None,
        )
        self._btn_abort.bind(
            "<Leave>",
            lambda e: self._btn_abort.configure(bg="#C0392B")
            if str(self._btn_abort["state"]) == "normal" else None,
        )
        self._btn_abort.pack(side="left")

        # ── RIGHT col, rows 0-1: Card Progresso ─────────────────────────
        outer_prog, prog = self._make_card(body, "Progresso")
        outer_prog.grid(row=0, column=1, rowspan=2, sticky="nsew", pady=(0, 10))

        self._pb = CircularProgress(prog, size=110, bg=COR_CARD)
        self._pb.pack(pady=(0, 10))

        self._lbl_current = tk.Label(
            prog, text="—", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_TEXTO, anchor="center", wraplength=140,
        )
        self._lbl_current.pack(fill="x")

        self._lbl_count_prog = tk.Label(
            prog, text="", font=("Segoe UI", 8),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="center",
        )
        self._lbl_count_prog.pack(fill="x", pady=(2, 0))

        self._lbl_eta = tk.Label(
            prog, text="", font=("Segoe UI", 8),
            bg=COR_CARD, fg=COR_PRIMARIA, anchor="center",
        )
        self._lbl_eta.pack(fill="x", pady=(2, 0))

        # ── BOTTOM row 2: Card Log ───────────────────────────────────────
        outer_log, log_body = self._make_card(body, "Log de Processamento")
        outer_log.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 16))

        self._txt_log = tk.Text(
            log_body, height=8, font=("Consolas", 8),
            bg="#FAFAFA", fg=COR_TEXTO, relief="flat",
            state="disabled", wrap="word", bd=0,
        )
        sb = ttk.Scrollbar(log_body, orient="vertical", command=self._txt_log.yview)
        self._txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._txt_log.pack(side="left", fill="both", expand=True)

        self._txt_log.tag_configure("ok",      foreground="#1B8A1B", font=("Consolas", 8, "bold"))
        self._txt_log.tag_configure("error",   foreground="#C0392B", font=("Consolas", 8, "bold"))
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
        """Update progress circle and company labels."""
        self._total_companies = total
        self._pb["maximum"] = total
        self._pb["value"] = i + 1
        self._lbl_current.configure(text=cod)
        self._lbl_count_prog.configure(text=f"Empresa {i + 1} de {total}")

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
            self._lbl_eta.configure(text="Concluído ✓")

        icon = {"ok": "✓", "error": "✗", "skipped": "—"}.get(status, "·")
        tag = status if status in ("ok", "error", "skipped") else "info"
        msg = f"{icon} [{cod}]  {detail or f'{notes} nota(s)'}"
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
            lines.append("\nEmpresas com erro:")
            for r in summary.company_results:
                if r.status == "error":
                    lines.append(f"  \u2022 {r.cod} \u2014 {r.error_detail}")
        return "\n".join(lines)

    def _on_batch_done(self, summary: BatchSummary):
        """Handle batch_done queue message — reset state and show summary."""
        self._running = False
        self._btn_start.configure(state="normal")
        self._btn_abort.configure(state="disabled")
        self._lbl_current.configure(text="—")
        self._lbl_count_prog.configure(text="")
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
            n = len(companies)
            self._lbl_count.configure(
                text=f"{n} empresa{'s' if n != 1 else ''} em GOIÂNIA"
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
            self._var_dest.set(path)

    def _start_batch(self):
        """Start the batch in a daemon thread with a fresh queue."""
        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", tk.END)
        self._txt_log.configure(state="disabled")
        self._lbl_eta.configure(text="")
        self._lbl_current.configure(text="—")
        self._lbl_count_prog.configure(text="")
        self._pb["value"] = 0
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
