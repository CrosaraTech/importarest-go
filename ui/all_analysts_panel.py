"""
ui/all_analysts_panel.py — Painel "Todas Analistas".

Executa o batch sequencialmente para todas as analistas pré-configuradas,
reusando o BatchOrchestrator existente. Cada analista produz sua própria
pasta de saída em ~/Downloads/Rest{ANALISTA}-{vigencia}/.
"""
from __future__ import annotations

import queue
import threading
import unicodedata
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk
import ttkbootstrap as ttkb

from config import (
    COR_BG, COR_CARD, COR_CARD_HOVER, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO, COR_BORDA, COR_BORDA_LEVE,
    COR_ERRO, COR_ERRO_HV, COR_GOLD, COR_GOLD_CLARO,
    COR_LOG_BG, COR_LOG_OK, COR_LOG_WARN,
    FONT_BODY, FONT_DISPLAY, FONT_MONO,
)
from services.spreadsheet import (
    get_companies_for_analyst, SpreadsheetError,
)
from services.batch_orchestrator import BatchOrchestrator
from services.dmste_processor import processar_empresa_dmste
from ui.components import eyebrow, hero_title, subtitle, divider, hero_card, hero_compacto, municipios_chips
from ui.editor_arquivo import abrir_editor_arquivo, COLUNAS_ISSNET
from ui.dialogs import abrir_tela_manual_itemlc
from ui.dmste_panel import EMPRESAS_DMSTE


ANALISTAS_PADRAO = ("ELAINE", "VALQUIRIA", "FERNANDA", "ROSSANA", "RAFAELA")


class PainelTodasAnalistas(tk.Frame):
    """Painel que roda todas as analistas em sequência."""

    def __init__(self, parent):
        super().__init__(parent, bg=COR_BG)

        # Runtime state
        self._running: bool = False
        self._orc: BatchOrchestrator | None = None
        self._q: queue.Queue | None = None
        self._var_analist_flags: dict[str, tk.BooleanVar] = {
            n: tk.BooleanVar(value=True) for n in ANALISTAS_PADRAO
        }
        self._var_vigencia = tk.StringVar(value=self._vigencia_padrao())
        self._var_mei = tk.BooleanVar(value=False)
        self._var_marcar_baixadas = tk.BooleanVar(value=False)
        self._abort_gerar_tudo = False
        # Cada item da fila: (label_municipio, lista_de_empresas, pasta_dest)
        self._fila_municipios: list[tuple[str, list[dict], Path]] = []
        self._municipio_atual: str | None = None
        self._pasta_raiz: Path | None = None

        self._build_ui()
        self.after(150, self._poll_queue)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vigencia_padrao() -> str:
        hoje = date.today()
        if hoje.month == 1:
            mes, ano = 12, hoje.year - 1
        else:
            mes, ano = hoje.month - 1, hoje.year
        return f"{mes:02d}{ano}"

    @staticmethod
    def _slug_municipio(nome: str) -> str:
        """Normaliza nome de município pra usar como nome de subpasta.

        'Goiânia'              → 'Goiania'
        'Aparecida de Goiânia' → 'Aparecida'
        'Anápolis'             → 'Anapolis'
        outros                 → 'Outros'
        """
        if not nome:
            return "Outros"
        n = "".join(
            c for c in unicodedata.normalize("NFD", nome)
            if unicodedata.category(c) != "Mn"
        ).upper().strip()
        if "GOIANIA" in n and "APARECIDA" not in n:
            return "Goiania"
        if "APARECIDA" in n:
            return "Aparecida"
        if "ANAPOLIS" in n:
            return "Anapolis"
        # Fallback — sanitiza pra subpasta válida
        safe = "".join(
            c for c in nome if c not in '<>:"/\\|?*\r\n\t'
        ).strip().replace(" ", "_") or "Outros"
        return safe

    def _toggle_vigencia_editavel(self):
        atual = str(self._ent_vigencia.cget("state"))
        if atual in ("readonly", "disabled"):
            self._ent_vigencia.configure(state="normal")
            self._btn_vigencia.configure(text="Restaurar padrão")
            self._ent_vigencia.focus_set()
        else:
            self._var_vigencia.set(self._vigencia_padrao())
            self._ent_vigencia.configure(state="readonly")
            self._btn_vigencia.configure(text="Mudar vigência")

    def _log(self, msg: str, tag: str = "normal"):
        self._txt_log.configure(state="normal")
        self._txt_log.insert(tk.END, msg + "\n", tag)
        self._txt_log.see(tk.END)
        self._txt_log.configure(state="disabled")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        ctk.set_appearance_mode("dark")

        # ── Hero compacto (única linha pra economizar altura) ─────────
        hero_wrap = tk.Frame(self, bg=COR_BG)
        hero_wrap.pack(fill="x", padx=24, pady=(14, 6))
        hero_compacto(
            hero_wrap,
            eyebrow_text="ISSNet · Portal Municipal",
            titulo="Geração",
            italico="ISSNet.",
            subtit="Layout TXT oficial — Goiânia, Aparecida de Goiânia e Anápolis",
        ).pack(fill="x")

        # ── Chips com municípios atendidos ────────────────────────────
        chips_wrap = tk.Frame(self, bg=COR_BG)
        chips_wrap.pack(fill="x", padx=24, pady=(0, 10))
        municipios_chips(
            chips_wrap,
            ["Goiânia", "Aparecida de Goiânia", "Anápolis"],
            prefix="Portal ISSNet — municípios",
        ).pack(anchor="w")

        # ── Body (card elevado, mais ar) ───────────────────────────────
        body = tk.Frame(self, bg=COR_CARD, padx=28, pady=22,
                        highlightbackground=COR_BORDA, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=32, pady=(16, 20))

        # ── Linha 1: Vigência + checkboxes lado a lado ────────────────
        col_row = tk.Frame(body, bg=COR_CARD)
        col_row.pack(fill="x", pady=(0, 18))

        col_vig = tk.Frame(col_row, bg=COR_CARD)
        col_vig.pack(side="left", fill="y", padx=(0, 30))
        tk.Label(
            col_vig, text="VIGÊNCIA  ·  MMAAAA",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(anchor="w", pady=(0, 6))
        vig_row = tk.Frame(col_vig, bg=COR_CARD)
        vig_row.pack(anchor="w")
        self._ent_vigencia = ctk.CTkEntry(
            vig_row, textvariable=self._var_vigencia,
            width=130, height=34, font=(FONT_BODY, 11),
            corner_radius=6, fg_color=COR_BG, border_color=COR_BORDA,
            text_color=COR_TEXTO, state="readonly",
        )
        self._ent_vigencia.pack(side="left")
        self._btn_vigencia = ctk.CTkButton(
            vig_row, text="Mudar",
            command=self._toggle_vigencia_editavel,
            width=80, height=34, corner_radius=6,
            font=(FONT_BODY, 10),
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA,
        )
        self._btn_vigencia.pack(side="left", padx=(8, 0))

        col_opts = tk.Frame(col_row, bg=COR_CARD)
        col_opts.pack(side="left", fill="y")
        tk.Label(
            col_opts, text="OPÇÕES",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(anchor="w", pady=(0, 6))
        self._chk_mei = ctk.CTkCheckBox(
            col_opts, text="Processar notas MEI tomadas",
            variable=self._var_mei,
            font=(FONT_BODY, 10),
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color=COR_TEXTO, corner_radius=4,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
        )
        self._chk_mei.pack(anchor="w", pady=2)
        self._chk_marcar = ctk.CTkCheckBox(
            col_opts, text="Marcar notas como baixadas na Autmais",
            variable=self._var_marcar_baixadas,
            font=(FONT_BODY, 10),
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color=COR_TEXTO, corner_radius=4,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
        )
        self._chk_marcar.pack(anchor="w", pady=2)

        # ── Linha 2: Analistas ─────────────────────────────────────────
        tk.Label(
            body, text="ANALISTAS  ·  selecione um ou mais",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(anchor="w", pady=(4, 8))
        grid_analistas = tk.Frame(body, bg=COR_CARD)
        grid_analistas.pack(anchor="w", pady=(0, 20))
        for i, nome in enumerate(ANALISTAS_PADRAO):
            chk = ctk.CTkCheckBox(
                grid_analistas, text=nome,
                variable=self._var_analist_flags[nome],
                font=(FONT_BODY, 11),
                fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
                text_color=COR_TEXTO, corner_radius=4,
                border_color=COR_BORDA, checkmark_color="#FFFFFF",
            )
            chk.grid(row=i // 3, column=i % 3, sticky="w",
                     padx=(0, 36), pady=4)

        # ── Linha sutil divisória ──────────────────────────────────────
        tk.Frame(body, bg=COR_BORDA_LEVE, height=1).pack(fill="x", pady=(0, 16))

        # ── Botões ─────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=COR_CARD)
        btn_row.pack(fill="x", pady=(0, 14))
        self._btn_start = ctk.CTkButton(
            btn_row, text="▶  Processar Todas",
            command=self._start_all, width=200, height=42,
            font=(FONT_BODY, 11, "bold"), corner_radius=999,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color="#FFFFFF",
        )
        self._btn_start.pack(side="left")
        self._btn_abort = ctk.CTkButton(
            btn_row, text="■  Abortar",
            command=self._abort, width=120, height=42,
            font=(FONT_BODY, 11, "bold"), corner_radius=999,
            fg_color="transparent", hover_color=COR_ERRO_HV,
            border_width=1, border_color=COR_ERRO,
            text_color=COR_ERRO, state="disabled",
        )
        self._btn_abort.pack(side="left", padx=(10, 0))

        # Botao "Abrir pasta" — aparece habilitado quando geracao termina.
        self._btn_abrir = ctk.CTkButton(
            btn_row, text="📁  Abrir pasta",
            command=self._abrir_pasta_saida, width=140, height=42,
            font=(FONT_BODY, 10), corner_radius=999,
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA,
            state="disabled",
        )
        self._btn_abrir.pack(side="left", padx=(10, 0))

        # Botao "Editar TXT" — abre o editor visual de qualquer .txt gerado.
        self._btn_editar = ctk.CTkButton(
            btn_row, text="✏  Editar TXT",
            command=self._abrir_editor_txt, width=140, height=42,
            font=(FONT_BODY, 10), corner_radius=999,
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA,
        )
        self._btn_editar.pack(side="left", padx=(10, 0))

        # Botao discreto: gera ISSNet + MegaSoft em pastas separadas por analista.
        self._btn_tudo = ctk.CTkButton(
            btn_row, text="🌐 Gerar TUDO",
            command=self._start_gerar_tudo, width=130, height=42,
            font=(FONT_BODY, 10), corner_radius=999,
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA,
        )
        self._btn_tudo.pack(side="right")

        # ── Barra de progresso ─────────────────────────────────────────
        prog_wrap = tk.Frame(body, bg=COR_CARD)
        prog_wrap.pack(fill="x", pady=(6, 8))
        self._progress = ttkb.Progressbar(
            prog_wrap, mode="determinate",
            bootstyle="warning",  # laranja Crosara
            maximum=100,
            length=400,
        )
        self._progress.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._lbl_progress = tk.Label(
            prog_wrap, text="—",
            font=(FONT_BODY, 10, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        )
        self._lbl_progress.pack(side="right")

        # ── Status (pill estilo Soraluna) ──────────────────────────────
        status_wrap = tk.Frame(body, bg=COR_CARD)
        status_wrap.pack(fill="x", pady=(0, 10))
        tk.Label(
            status_wrap, text="STATUS",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(side="left", padx=(0, 12))
        self._lbl_status = tk.Label(
            status_wrap, text="aguardando", font=(FONT_BODY, 10),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        )
        self._lbl_status.pack(side="left", fill="x", expand=True)

        # ── Log (terminal-like, mais sofisticado) ──────────────────────
        log_frame = tk.Frame(body, bg=COR_LOG_BG,
                             highlightbackground=COR_BORDA_LEVE, highlightthickness=1)
        log_frame.pack(fill="both", expand=True)
        self._txt_log = tk.Text(
            log_frame, height=12, bg=COR_LOG_BG, fg=COR_TEXTO,
            font=(FONT_MONO, 9), state="disabled",
            wrap="word", relief="flat", borderwidth=0,
            padx=12, pady=10,
            insertbackground=COR_GOLD,
        )
        self._txt_log.pack(fill="both", expand=True)
        self._txt_log.tag_config("ok", foreground=COR_LOG_OK)
        self._txt_log.tag_config("warn", foreground=COR_LOG_WARN)
        self._txt_log.tag_config("erro", foreground=COR_ERRO)

    # ------------------------------------------------------------------
    # Start / Run
    # ------------------------------------------------------------------

    def _selecionadas(self) -> list[str]:
        return [n for n, v in self._var_analist_flags.items() if v.get()]

    def _start_all(self):
        if self._running:
            return
        analistas = self._selecionadas()
        if not analistas:
            messagebox.showwarning(
                "Nenhuma analista selecionada",
                "Marque pelo menos uma analista para processar.",
            )
            return
        vigencia = self._var_vigencia.get().strip()
        if len(vigencia) != 6 or not vigencia.isdigit():
            messagebox.showwarning(
                "Vigência inválida",
                "A vigência deve ter exatamente 6 dígitos (MMAAAA).",
            )
            return

        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", tk.END)
        self._txt_log.configure(state="disabled")
        self._running = True
        self._btn_start.configure(state="disabled")
        self._btn_abort.configure(state="normal")

        # Junta todas as empresas das analistas selecionadas + agrupa por município
        self._log(f"📋 Carregando empresas de {len(analistas)} analista(s)...")
        agrupado: dict[str, list[dict]] = {}
        codigos_vistos: set[str] = set()
        for analista in analistas:
            try:
                companies = get_companies_for_analyst(analista)
            except SpreadsheetError as exc:
                self._log(f"   ❌ Erro lendo '{analista}': {exc}", "erro")
                continue
            for emp in companies:
                # Dedup por código — se a mesma empresa aparece em 2 analistas
                # (raro mas possível), só processa uma vez
                if emp["cod"] in codigos_vistos:
                    continue
                codigos_vistos.add(emp["cod"])
                mun_slug = self._slug_municipio(emp.get("municipio", ""))
                agrupado.setdefault(mun_slug, []).append(emp)

        if not agrupado:
            self._log("   ⚠ Nenhuma empresa encontrada", "warn")
            self._encerrar()
            return

        # Pasta raiz única — Rest_ISSNet-{vig}/
        self._pasta_raiz = Path.home() / "Downloads" / f"Rest_ISSNet-{vigencia}"
        self._pasta_raiz.mkdir(parents=True, exist_ok=True)

        # Monta fila — uma entrada por município
        self._fila_municipios = []
        for mun_slug, empresas in sorted(agrupado.items()):
            dest_mun = self._pasta_raiz / mun_slug
            dest_mun.mkdir(parents=True, exist_ok=True)
            self._fila_municipios.append((mun_slug, empresas, dest_mun))

        total_empresas = sum(len(emp) for _, emp, _ in self._fila_municipios)
        resumo = ", ".join(
            f"{mun}={len(emp)}" for mun, emp, _ in self._fila_municipios
        )
        self._log(
            f"   Total: {total_empresas} empresa(s) → "
            f"{len(self._fila_municipios)} município(s) [{resumo}]"
        )
        self._log(f"   Pasta raiz: {self._pasta_raiz}")
        self._log("─" * 60)

        # Inicializa a barra de progresso baseada no total de empresas
        self._total_empresas = total_empresas
        self._empresas_concluidas = 0
        self._progress.configure(maximum=max(total_empresas, 1))
        self._progress["value"] = 0
        self._lbl_progress.configure(
            text=f"0 / {total_empresas}", fg=COR_GOLD,
        )

        self._processar_proxima()

    def _processar_proxima(self):
        if not self._fila_municipios:
            self._encerrar()
            return
        mun_slug, empresas, dest = self._fila_municipios.pop(0)
        self._municipio_atual = mun_slug
        self._lbl_status.configure(
            text=f"▶ Município: {mun_slug} ({len(empresas)} empresas)",
            fg=COR_PRIMARIA,
        )
        self._log(f"\n▶ {mun_slug} — {len(empresas)} empresa(s)", "ok")
        self._log(f"   → {dest}")

        vigencia = self._var_vigencia.get().strip()
        self._q = queue.Queue()
        self._orc = BatchOrchestrator(self._q)

        t = threading.Thread(
            target=self._orc.run,
            # passa mun_slug como "analista" pro CSV virar Faltantes_{Municipio}.csv
            args=(empresas, vigencia, dest, self._var_mei.get(), mun_slug,
                  self._var_marcar_baixadas.get()),
            daemon=True,
        )
        t.start()

    def _abrir_editor_txt(self):
        """Abre o editor visual de TXT ISSNet.

        Pede um arquivo via dialog (default = pasta da vigência atual).
        """
        from tkinter import filedialog
        vig = self._var_vigencia.get().strip()
        inicial = Path.home() / "Downloads"
        if vig:
            cand = inicial / f"Rest_ISSNet-{vig}"
            if cand.exists():
                inicial = cand
        arquivo = filedialog.askopenfilename(
            title="Selecione o TXT pra editar",
            filetypes=[("Arquivo TXT", "*.txt"), ("Todos", "*.*")],
            initialdir=str(inicial),
            parent=self.winfo_toplevel(),
        )
        if not arquivo:
            return
        abrir_editor_arquivo(
            parent=self,
            arquivo=Path(arquivo),
            titulo_eyebrow="Editar TXT · ISSNet",
            colunas=COLUNAS_ISSNET,
            separador=";",
            tem_cabecalho=True,
            log_fn=self._log,
        )

    def _abrir_pasta_saida(self):
        """Abre o Windows Explorer na pasta raiz dos arquivos gerados."""
        import os
        import subprocess
        if not self._pasta_raiz or not self._pasta_raiz.exists():
            messagebox.showinfo(
                "Pasta indisponivel",
                "Gere primeiro os arquivos — a pasta de saida nao existe ainda.",
            )
            return
        try:
            os.startfile(str(self._pasta_raiz))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            subprocess.Popen(["explorer", str(self._pasta_raiz)])

    def _abort(self):
        if self._orc:
            self._orc.abort()
        self._fila_municipios = []
        self._abort_gerar_tudo = True
        self._log("⛔ Abortado pelo usuário", "erro")
        self._lbl_status.configure(text="Abortado", fg=COR_ERRO)

    # ------------------------------------------------------------------
    # Gerar TUDO — ISSNet + MegaSoft por analista
    # ------------------------------------------------------------------

    def _start_gerar_tudo(self):
        """Para cada analista marcada, gera ISSNet + MegaSoft em
        ~/Downloads/Rest{vigencia}{ANALISTA}/{municipio}/."""
        if self._running:
            return
        analistas = self._selecionadas()
        if not analistas:
            messagebox.showwarning(
                "Nenhuma analista selecionada",
                "Marque pelo menos uma analista para o modo 'Gerar TUDO'.",
            )
            return
        # Conta empresas pra dar progresso visual estimado
        total_empresas_est = 0
        for analista in analistas:
            try:
                companies = get_companies_for_analyst(analista)
            except SpreadsheetError:
                continue
            total_empresas_est += len(companies)
        # MegaSoft: 5 empresas fixas por analista
        total_empresas_est += len(EMPRESAS_DMSTE) * len(analistas)

        vigencia = self._var_vigencia.get().strip()
        if len(vigencia) != 6 or not vigencia.isdigit():
            messagebox.showwarning(
                "Vigência inválida",
                "A vigência deve ter exatamente 6 dígitos (MMAAAA).",
            )
            return

        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", tk.END)
        self._txt_log.configure(state="disabled")
        self._running = True
        self._abort_gerar_tudo = False
        self._btn_start.configure(state="disabled")
        self._btn_tudo.configure(state="disabled")
        self._btn_abort.configure(state="normal")

        self._log(f"🌐 GERAR TUDO — {len(analistas)} analista(s)", "ok")
        self._log(f"   Modo: ISSNet + MegaSoft em pastas separadas por analista")
        self._log(f"   Vigência: {vigencia}")
        self._log("─" * 60)

        # Inicializa barra de progresso pro modo "Gerar TUDO"
        self._total_empresas = max(total_empresas_est, 1)
        self._empresas_concluidas = 0
        self._progress.configure(maximum=self._total_empresas)
        self._progress["value"] = 0
        self._lbl_progress.configure(
            text=f"0 / {self._total_empresas}", fg=COR_GOLD,
        )

        self._q = queue.Queue()
        t = threading.Thread(
            target=self._worker_gerar_tudo,
            args=(analistas, vigencia, self._var_mei.get(),
                  self._var_marcar_baixadas.get()),
            daemon=True,
        )
        t.start()

    def _worker_gerar_tudo(self, analistas, vigencia, gerar_mei, marcar_baixadas):
        """Loop por analista: filtra empresas, roda ISSNet por municipio,
        depois MegaSoft das 5 empresas hardcoded."""
        try:
            for analista in analistas:
                if self._abort_gerar_tudo:
                    break
                pasta = Path.home() / "Downloads" / f"Rest{vigencia}{analista}"
                pasta.mkdir(parents=True, exist_ok=True)
                self._q.put(("gt_log", f"\n━━━ {analista} ━━━", "ok"))
                self._q.put(("gt_log", f"   → {pasta}", "normal"))

                # === ISSNet ===
                try:
                    companies = get_companies_for_analyst(analista)
                except SpreadsheetError as exc:
                    self._q.put(("gt_log", f"❌ Erro planilha '{analista}': {exc}", "erro"))
                    continue

                agrupado: dict[str, list[dict]] = {}
                for emp in companies:
                    mun = self._slug_municipio(emp.get("municipio", ""))
                    agrupado.setdefault(mun, []).append(emp)

                total_iss = sum(len(v) for v in agrupado.values())
                resumo = ", ".join(f"{m}={len(v)}" for m, v in sorted(agrupado.items()))
                self._q.put((
                    "gt_log",
                    f"▶ ISSNet: {total_iss} empresa(s) em {len(agrupado)} mun. [{resumo}]",
                    "ok",
                ))

                for mun_slug, emps in sorted(agrupado.items()):
                    if self._abort_gerar_tudo:
                        break
                    dest = pasta / mun_slug
                    dest.mkdir(parents=True, exist_ok=True)
                    self._q.put(("gt_log", f"  • {mun_slug} ({len(emps)})", "normal"))
                    inner_q = queue.Queue()
                    orc = BatchOrchestrator(inner_q)
                    self._orc = orc
                    # Roda orc.run em thread separada — o consumidor abaixo
                    # processa manual_review e batch_done na mesma thread,
                    # evitando deadlock com event.wait() no callback de revisao.
                    inner_t = threading.Thread(
                        target=orc.run,
                        args=(emps, vigencia, dest, gerar_mei, mun_slug, marcar_baixadas),
                        daemon=True,
                    )
                    inner_t.start()
                    self._consumir_queue_silencioso(inner_q, inner_t)
                    inner_t.join(timeout=5.0)

                if self._abort_gerar_tudo:
                    break

                # === MegaSoft ===
                self._q.put((
                    "gt_log",
                    f"▶ MegaSoft: {len(EMPRESAS_DMSTE)} empresa(s) fixa(s)",
                    "ok",
                ))
                for emp_mega in EMPRESAS_DMSTE:
                    if self._abort_gerar_tudo:
                        break
                    mun_slug = self._slug_municipio(emp_mega["municipio"])
                    dest = pasta / mun_slug
                    dest.mkdir(parents=True, exist_ok=True)
                    res = processar_empresa_dmste(
                        cod=emp_mega["cod"],
                        razao=emp_mega["razao"],
                        municipio=emp_mega["municipio"],
                        vigencia=vigencia,
                        pasta_saida=dest,
                        marcar_baixadas=marcar_baixadas,
                    )
                    # Incrementa contador de progresso por empresa MegaSoft.
                    self._q.put(("gt_step", emp_mega["cod"], ""))
                    if res.status == "ok":
                        self._q.put((
                            "gt_log",
                            f"  ✅ {emp_mega['cod']} {emp_mega['razao'][:25]:<25} → {mun_slug}/ "
                            f"({res.notas_processadas} notas)",
                            "ok",
                        ))
                    elif res.status == "vazio":
                        self._q.put((
                            "gt_log",
                            f"  ⚠ {emp_mega['cod']} {emp_mega['razao'][:25]:<25} → sem notas",
                            "warn",
                        ))
                    else:
                        self._q.put((
                            "gt_log",
                            f"  ❌ {emp_mega['cod']} {emp_mega['razao'][:25]:<25} → "
                            f"{res.status}: {res.detalhe[:60]}",
                            "erro",
                        ))
        except Exception as exc:  # noqa: BLE001
            self._q.put(("gt_log", f"❌ Falha inesperada: {exc}", "erro"))
        finally:
            self._q.put(("gt_fim", None, ""))

    def _consumir_queue_silencioso(self, q: queue.Queue, worker_thread):
        """Drena a fila do BatchOrchestrator interno encaminhando eventos
        para o log principal. Continua ate batch_done ou worker morrer."""
        import queue as _q
        while True:
            try:
                evt = q.get(timeout=0.5)
            except _q.Empty:
                if not worker_thread.is_alive():
                    return
                continue
            kind = evt[0]
            if kind == "batch_done":
                summary = evt[1]
                self._q.put((
                    "gt_log",
                    f"    📊 {summary.successes} ok / {summary.errors} erro / "
                    f"{summary.skipped} skip ({summary.elapsed_total_seconds:.1f}s)",
                    "normal",
                ))
                return
            elif kind == "company_done":
                _, cod, status, notes, elapsed, detail = evt
                # Incrementa contador de progresso pro modo "Gerar TUDO"
                self._q.put(("gt_step", cod, ""))
                if status == "ok":
                    pass  # silencioso no modo "gerar tudo" pra nao poluir
                elif status == "skipped":
                    self._q.put(("gt_log", f"    ⛔ {cod}: {detail}", "warn"))
                else:
                    self._q.put(("gt_log", f"    ❌ {cod}: {detail}", "erro"))
            elif kind == "manual_review":
                # Em modo "gerar TUDO" nao abrimos modal — rejeita revisao
                # imediatamente liberando o event.wait() do worker.
                (_, dados_base, chave_nfse, from_n8n, event,
                 result_holder, cod, razao) = evt
                result_holder[0] = None
                event.set()
                self._q.put((
                    "gt_log",
                    f"    ⚠ {cod}: revisao manual pulada (modo gerar TUDO)",
                    "warn",
                ))

    def _encerrar(self):
        self._running = False
        self._municipio_atual = None
        self._btn_start.configure(state="normal")
        self._btn_abort.configure(state="disabled")
        self._btn_abrir.configure(state="normal")
        self._lbl_status.configure(text="✅ Concluído", fg=COR_LOG_OK)
        if hasattr(self, "_total_empresas") and self._total_empresas > 0:
            self._progress["value"] = self._total_empresas
            self._lbl_progress.configure(
                text=f"{self._empresas_concluidas} / {self._total_empresas}  ·  ✓",
                fg=COR_LOG_OK,
            )
        self._log("\n" + "─" * 60)
        self._log("✅ Processamento finalizado.", "ok")
        if self._pasta_raiz:
            self._log(f"📁 Pasta: {self._pasta_raiz}", "ok")

    # ------------------------------------------------------------------
    # Poll loop — drena a fila do orchestrator atual
    # ------------------------------------------------------------------

    def _poll_queue(self):
        if self._q is not None:
            try:
                while True:
                    evt = self._q.get_nowait()
                    self._handle_event(evt)
            except queue.Empty:
                pass
        self.after(150, self._poll_queue)

    def _handle_event(self, evt):
        kind = evt[0]
        # Eventos do modo "Gerar TUDO"
        if kind == "gt_log":
            _, msg, tag = evt
            self._log(msg, tag)
            return
        if kind == "gt_step":
            _, cod, _ = evt
            if hasattr(self, "_total_empresas") and self._total_empresas > 0:
                self._empresas_concluidas += 1
                self._progress["value"] = min(self._empresas_concluidas, self._total_empresas)
                self._lbl_progress.configure(
                    text=f"{self._empresas_concluidas} / {self._total_empresas}  ·  {cod}",
                )
            return
        if kind == "gt_fim":
            self._running = False
            self._abort_gerar_tudo = False
            self._btn_start.configure(state="normal")
            self._btn_tudo.configure(state="normal")
            self._btn_abort.configure(state="disabled")
            self._btn_abrir.configure(state="normal")
            self._lbl_status.configure(text="✅ Gerar TUDO concluído", fg=COR_LOG_OK)
            if hasattr(self, "_total_empresas") and self._total_empresas > 0:
                self._progress["value"] = self._total_empresas
                self._lbl_progress.configure(
                    text=f"{self._empresas_concluidas} / {self._total_empresas}  ·  ✓",
                    fg=COR_LOG_OK,
                )
            self._log("\n" + "─" * 60)
            self._log("✅ Gerar TUDO finalizado.", "ok")
            return
        if kind == "log":
            _, cod, msg = evt
            self._log(f"   [{cod}] {msg}")
        elif kind == "company_start":
            _, cod, i, total = evt
            self._lbl_status.configure(
                text=f"▶ {self._municipio_atual}: empresa {i+1}/{total} (cod {cod})",
                fg=COR_PRIMARIA,
            )
            # Atualiza label da barra mostrando empresa atual.
            if hasattr(self, "_total_empresas") and self._total_empresas > 0:
                self._lbl_progress.configure(
                    text=f"{self._empresas_concluidas} / {self._total_empresas}  ·  {cod}",
                )
        elif kind == "company_done":
            _, cod, status, notes, elapsed, detail = evt
            icone = "✅" if status == "ok" else ("⛔" if status == "skipped" else "❌")
            self._log(
                f"   {icone} [{cod}] {status} — {notes} nota(s) em {elapsed:.1f}s",
                "ok" if status == "ok" else "warn"
            )
            # Incrementa barra apos cada empresa concluida.
            if hasattr(self, "_total_empresas") and self._total_empresas > 0:
                self._empresas_concluidas += 1
                self._progress["value"] = self._empresas_concluidas
                self._lbl_progress.configure(
                    text=f"{self._empresas_concluidas} / {self._total_empresas}",
                )
        elif kind == "batch_done":
            _, summary = evt
            self._log(
                f"   📊 {self._municipio_atual}: "
                f"{summary.successes} ok / {summary.errors} erro / "
                f"{summary.skipped} skip (em {summary.elapsed_total_seconds:.1f}s)",
                "ok",
            )
            self.after(200, self._processar_proxima)
        elif kind == "manual_review":
            (_, dados_base, chave_nfse, from_n8n, event,
             result_holder, cod, razao) = evt
            try:
                linha = abrir_tela_manual_itemlc(
                    self.winfo_toplevel(), dados_base, chave_nfse,
                    from_n8n=from_n8n,
                    empresa_cod=cod, empresa_razao=razao,
                )
                result_holder[0] = linha
            finally:
                event.set()
