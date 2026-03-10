"""
ui/batch_panel.py — Batch processing panel.

PainelLote: tk.Frame subclass encapsulating all batch UI logic —
selection widgets, progress display, queue poll loop, PROC-03 manual
review handler, and post-run summary.

Redesigned with CustomTkinter for a modern, premium look.
"""
import queue
import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

try:
    from PIL import Image, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from config import (
    COR_BG, COR_CARD, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO, COR_BORDA,
    COR_ERRO, COR_ERRO_HV,
    COR_LOG_BG, COR_LOG_OK, COR_LOG_WARN,
)
from services.spreadsheet import load_analysts, get_companies_for_analyst
from services.spreadsheet import SpreadsheetError
from services.batch_orchestrator import BatchOrchestrator, BatchSummary
from ui.dialogs import abrir_tela_manual_itemlc
from ui.components import CircularProgress


class _CompatComboBox(ctk.CTkComboBox):
    """CTkComboBox with dict-style access (``widget["values"]``) for test compat."""

    def __getitem__(self, key):
        val = self.cget(key)
        if key == "values":
            return tuple(val) if val else ()
        return val


class _CompatButton(ctk.CTkButton):
    """CTkButton with dict-style access (``widget["state"]``) for test compat."""

    def __getitem__(self, key):
        return self.cget(key)


class PainelLote(tk.Frame):
    """Batch processing panel — selection, progress, log, and summary."""

    def __init__(self, parent):
        super().__init__(parent, bg=COR_BG)

        ctk.set_appearance_mode("light")

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

    def _section_title(self, parent, text: str):
        """Render a section title with small orange accent line."""
        bg = parent.cget("bg") if isinstance(parent, tk.Frame) else COR_CARD
        frame = tk.Frame(parent, bg=bg)
        frame.pack(fill="x", pady=(0, 10))

        tk.Frame(frame, bg=COR_PRIMARIA, width=3, height=14).pack(
            side="left", padx=(0, 8),
        )
        tk.Label(
            frame, text=text, font=("Segoe UI", 8, "bold"),
            bg=bg, fg=COR_TEXTO, anchor="w",
        ).pack(side="left")
        tk.Frame(frame, bg=COR_BORDA, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=(4, 0),
        )

    def _build_ui(self):
        main = tk.Frame(self, bg=COR_BG)
        main.pack(fill="both", expand=True, padx=24, pady=(16, 20))

        # ── Header ────────────────────────────────────────────────────
        self._build_header(main)
        tk.Frame(main, bg=COR_BORDA, height=1).pack(fill="x", pady=(0, 16))

        # ── Two-column content ────────────────────────────────────────
        content = tk.Frame(main, bg=COR_BG)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2, minsize=200)
        content.rowconfigure(0, weight=1)

        self._build_config_card(content)
        self._build_progress_card(content)
        self._build_hidden_log()

    # ── Header ────────────────────────────────────────────────────────

    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=COR_BG)
        hdr.pack(fill="x", pady=(0, 14))

        logo_shown = False
        if _PIL_OK:
            try:
                logo_path = (
                    Path(__file__).resolve().parent.parent
                    / "assets" / "logo_importarest.png"
                )
                img = Image.open(logo_path)
                img = img.resize((240, 67), Image.LANCZOS)
                logo = _PILImageTk.PhotoImage(img)
                lbl = tk.Label(hdr, image=logo, bg=COR_BG)
                lbl.image = logo
                lbl.pack()
                logo_shown = True
            except (FileNotFoundError, OSError):
                pass
        if not logo_shown:
            tk.Label(
                hdr, text="IMPORTAREST GO",
                font=("Segoe UI", 18, "bold"),
                bg=COR_BG, fg=COR_PRIMARIA,
            ).pack()

    # ── Configuration card ────────────────────────────────────────────

    def _build_config_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=COR_CARD, corner_radius=12,
            border_width=1, border_color=COR_BORDA,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=(0, 12))

        body = tk.Frame(card, bg=COR_CARD)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        self._section_title(body, "CONFIGURACAO DO LOTE")

        # ── Analyst selector ──
        tk.Label(
            body, text="Analista", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self._cmb_analyst = _CompatComboBox(
            body, variable=self._var_analyst,
            state="readonly", values=[],
            command=self._on_analyst_selected,
            font=("Segoe UI", 11),
            height=34,
            fg_color=COR_CARD, border_color=COR_BORDA,
            button_color=COR_PRIMARIA, button_hover_color=COR_PRIMARIA_HV,
            dropdown_fg_color=COR_CARD, dropdown_hover_color="#FFF0E0",
            dropdown_text_color=COR_TEXTO, text_color=COR_TEXTO,
            corner_radius=8,
        )
        self._cmb_analyst.pack(fill="x")
        self._cmb_analyst.set("")

        self._lbl_count = tk.Label(
            body, text="", font=("Segoe UI", 8, "italic"),
            bg=COR_CARD, fg=COR_PRIMARIA, anchor="w",
        )
        self._lbl_count.pack(anchor="w", pady=(4, 10))

        # ── Vigencia + MEI row ──
        row_vig = tk.Frame(body, bg=COR_CARD)
        row_vig.pack(fill="x", pady=(0, 12))

        col_vig = tk.Frame(row_vig, bg=COR_CARD)
        col_vig.pack(side="left", padx=(0, 24))
        tk.Label(
            col_vig, text="Vigencia (MMAAAA)",
            font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO,
        ).pack(anchor="w", pady=(0, 4))
        self._ent_vigencia = ctk.CTkEntry(
            col_vig, textvariable=self._var_vigencia,
            width=140, height=34,
            font=("Segoe UI", 11), corner_radius=8,
            fg_color=COR_CARD, border_color=COR_BORDA,
            text_color=COR_TEXTO, placeholder_text="MMAAAA",
        )
        self._ent_vigencia.pack(anchor="w")

        col_mei = tk.Frame(row_vig, bg=COR_CARD)
        col_mei.pack(side="left", pady=(18, 0))
        self._chk_mei = ctk.CTkCheckBox(
            col_mei, text="Gerar notas MEI (Goiania)",
            variable=self._var_mei,
            font=("Segoe UI", 10),
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color=COR_SUBTEXTO, corner_radius=4,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
        )
        self._chk_mei.pack()

        # ── Destination folder ──
        tk.Label(
            body, text="Pasta de destino", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x", pady=(0, 4))

        dest_row = tk.Frame(body, bg=COR_CARD)
        dest_row.pack(fill="x", pady=(0, 16))

        self._ent_dest = ctk.CTkEntry(
            dest_row, textvariable=self._var_dest,
            height=34, font=("Segoe UI", 10), corner_radius=8,
            fg_color="#F8F8F8", border_color=COR_BORDA,
            text_color=COR_TEXTO, state="disabled",
        )
        self._ent_dest.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            dest_row, text="Escolher", command=self._choose_dest,
            font=("Segoe UI", 10, "bold"), width=100, height=34,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color="#FFFFFF", corner_radius=8,
        ).pack(side="left")

        # ── Separator + action buttons ──
        tk.Frame(body, bg=COR_BORDA, height=1).pack(fill="x", pady=(0, 14))

        btn_row = tk.Frame(body, bg=COR_CARD)
        btn_row.pack(fill="x")

        self._btn_start = _CompatButton(
            btn_row, text="\u25B6  INICIAR LOTE",
            command=self._start_batch,
            font=("Segoe UI", 11, "bold"), height=42,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color="#FFFFFF", corner_radius=8, state="disabled",
        )
        self._btn_start.pack(side="left", padx=(0, 10))

        self._btn_abort = _CompatButton(
            btn_row, text="\u2715  ABORTAR",
            command=self._abort,
            font=("Segoe UI", 11, "bold"), height=42,
            fg_color=COR_ERRO, hover_color=COR_ERRO_HV,
            text_color="#FFFFFF", corner_radius=8, state="disabled",
        )
        self._btn_abort.pack(side="left")

    # ── Progress card ─────────────────────────────────────────────────

    def _build_progress_card(self, parent):
        card = ctk.CTkFrame(
            parent, fg_color=COR_CARD, corner_radius=12,
            border_width=1, border_color=COR_BORDA,
        )
        card.grid(row=0, column=1, sticky="nsew", pady=(0, 12))

        body = tk.Frame(card, bg=COR_CARD)
        body.pack(fill="both", expand=True, padx=16, pady=16)

        self._pb = CircularProgress(body, size=150, bg=COR_CARD)
        self._pb.pack(pady=(10, 14))

        self._lbl_current = tk.Label(
            body, text="\u2014", font=("Segoe UI", 10, "bold"),
            bg=COR_CARD, fg=COR_TEXTO, anchor="center", wraplength=155,
        )
        self._lbl_current.pack(fill="x")

        self._lbl_count_prog = tk.Label(
            body, text="", font=("Segoe UI", 9),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="center",
        )
        self._lbl_count_prog.pack(fill="x", pady=(2, 0))

        self._lbl_eta = tk.Label(
            body, text="", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_PRIMARIA, anchor="center",
        )
        self._lbl_eta.pack(fill="x", pady=(4, 0))

    # ── Hidden log (keeps _txt_log functional for _log / tests) ─────

    def _build_hidden_log(self):
        self._txt_log = tk.Text(self, height=1, state="disabled")
        self._txt_log.tag_configure(
            "ok", foreground=COR_LOG_OK, font=("Consolas", 9, "bold"),
        )
        self._txt_log.tag_configure(
            "error", foreground=COR_ERRO, font=("Consolas", 9, "bold"),
        )
        self._txt_log.tag_configure("skipped", foreground=COR_LOG_WARN)
        self._txt_log.tag_configure("info", foreground=COR_SUBTEXTO)

    # ------------------------------------------------------------------
    # Public helper methods (called by tests)
    # ------------------------------------------------------------------

    def _load_analysts_into_combobox(self, names: list[str]):
        """Populate the analyst combobox with the given list of names."""
        self._cmb_analyst.configure(values=names)

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
            self._lbl_eta.configure(text="Concluido \u2713")

        icon = {"ok": "\u2713", "error": "\u2717", "skipped": "\u2014"}.get(status, "\u00B7")
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
        self._lbl_current.configure(text="\u2014")
        self._lbl_count_prog.configure(text="")
        text = self._build_summary_text(summary)
        if summary.errors > 0:
            messagebox.showwarning("Lote Concluido com Erros", text)
        else:
            messagebox.showinfo("Lote Concluido", text)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_analyst_selected(self, value=None):
        """Load companies for the selected analyst."""
        name = self._var_analyst.get()
        try:
            companies = get_companies_for_analyst(name)
            self._companies = companies
            n = len(companies)
            self._lbl_count.configure(
                text=f"{n} empresa{'s' if n != 1 else ''} em GOIANIA"
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
        self._lbl_current.configure(text="\u2014")
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
