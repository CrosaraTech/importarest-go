"""ui/dmste_panel.py — Painel "DMST-e".

Aba dedicada a gerar CSVs DMST-e para 5 empresas hardcoded em cidades fora
das aceitas pelo ISSNet (Vianópolis, Crixás, Jussara, Trindade).
"""
from __future__ import annotations

import queue
import threading
import unicodedata
from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import ttkbootstrap as ttkb

from config import (
    COR_BG, COR_CARD, COR_CARD_HOVER, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO, COR_BORDA, COR_BORDA_LEVE,
    COR_ERRO, COR_ERRO_HV, COR_GOLD, COR_GOLD_CLARO,
    COR_LOG_BG, COR_LOG_OK, COR_LOG_WARN,
    FONT_BODY, FONT_DISPLAY, FONT_MONO,
)
from services.dmste_processor import processar_empresa_dmste, DmsteResult
from ui.components import eyebrow, hero_title, subtitle, divider, hero_card, hero_compacto, municipios_chips
from ui.editor_arquivo import abrir_editor_arquivo, COLUNAS_DMSTE


EMPRESAS_DMSTE = [
    {"cod": "1553", "razao": "LIMA MAT",                          "municipio": "VIANOPOLIS"},
    {"cod": "1552", "razao": "MINEIRA MATERIAIS",                 "municipio": "VIANOPOLIS"},
    {"cod": "1419", "razao": "SUPERMERCADO PRATTICO LTDA",        "municipio": "CRIXAS"},
    {"cod": "1112", "razao": "AM ATENDIMENTO HOSPITALAR LTDA",    "municipio": "JUSSARA"},
]


class PainelDmste(tk.Frame):
    """Painel DMST-e — processa as 5 empresas fixas e gera CSV por empresa."""

    def __init__(self, parent):
        super().__init__(parent, bg=COR_BG)

        self._running: bool = False
        self._q: queue.Queue | None = None
        self._var_vigencia = tk.StringVar(value=self._vigencia_padrao())
        self._pasta_raiz: Path | None = None
        # Estado de selecao por empresa — por padrao TODAS marcadas.
        self._var_emp_flags: dict[str, tk.BooleanVar] = {
            emp["cod"]: tk.BooleanVar(value=True) for emp in EMPRESAS_DMSTE
        }
        # Cada card guarda referencia ao Frame externo + inner pra atualizar visual
        # quando o checkbox muda de estado.
        self._cards_refs: dict[str, dict] = {}

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

        'Vianópolis' → 'Vianopolis'
        'Crixás'     → 'Crixas'
        'Jussara'    → 'Jussara'
        'Trindade'   → 'Trindade'
        """
        if not nome:
            return "Outros"
        n = "".join(
            c for c in unicodedata.normalize("NFD", nome)
            if unicodedata.category(c) != "Mn"
        ).strip()
        # Remove caracteres inválidos pra nome de pasta e troca espaço por _
        safe = "".join(
            c for c in n if c not in '<>:"/\\|?*\r\n\t'
        ).strip().replace(" ", "_")
        return safe.title() or "Outros"

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
            eyebrow_text="MegaSoft · Portal DMST-e",
            titulo="Geração",
            italico="DMST-e.",
            subtit="Substituição tributária — Vianópolis, Crixás e Jussara",
        ).pack(fill="x")

        # ── Chips com municípios atendidos ────────────────────────────
        chips_wrap = tk.Frame(self, bg=COR_BG)
        chips_wrap.pack(fill="x", padx=24, pady=(0, 10))
        municipios_chips(
            chips_wrap,
            ["Vianópolis", "Crixás", "Jussara"],
            prefix="Portal MegaSoft — municípios",
        ).pack(anchor="w")

        # ── Body (card elevado) ────────────────────────────────────────
        body = tk.Frame(self, bg=COR_CARD, padx=28, pady=22,
                        highlightbackground=COR_BORDA, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=32, pady=(16, 20))

        # ── Vigência ───────────────────────────────────────────────────
        tk.Label(
            body, text="VIGÊNCIA  ·  MMAAAA",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(anchor="w", pady=(0, 6))
        vig_row = tk.Frame(body, bg=COR_CARD)
        vig_row.pack(anchor="w", pady=(0, 18))
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

        # ── Lista das empresas (cards em grid estilo Soraluna) ─────────
        emp_header = tk.Frame(body, bg=COR_CARD)
        emp_header.pack(fill="x", pady=(4, 8))
        tk.Label(
            emp_header, text=f"EMPRESAS  ·  {len(EMPRESAS_DMSTE)} fixas",
            font=(FONT_BODY, 9, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        ).pack(side="left")
        # Atalhos pra selecao em massa
        self._btn_todas = ctk.CTkButton(
            emp_header, text="✓ todas",
            command=lambda: self._marcar_todas(True),
            width=70, height=22, corner_radius=999,
            font=(FONT_BODY, 9),
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA_LEVE,
        )
        self._btn_todas.pack(side="right", padx=(6, 0))
        self._btn_nenhuma = ctk.CTkButton(
            emp_header, text="✕ nenhuma",
            command=lambda: self._marcar_todas(False),
            width=90, height=22, corner_radius=999,
            font=(FONT_BODY, 9),
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_SUBTEXTO, border_width=1, border_color=COR_BORDA_LEVE,
        )
        self._btn_nenhuma.pack(side="right")
        grid_empresas = tk.Frame(body, bg=COR_CARD)
        grid_empresas.pack(fill="x", pady=(0, 16))
        for i, emp in enumerate(EMPRESAS_DMSTE):
            self._empresa_card(grid_empresas, emp).grid(
                row=i // 3, column=i % 3, sticky="nsew",
                padx=(0, 10) if i % 3 < 2 else (0, 0), pady=(0, 8),
            )
        for c in range(3):
            grid_empresas.grid_columnconfigure(c, weight=1, uniform="emp")

        # ── Linha sutil divisória ──────────────────────────────────────
        tk.Frame(body, bg=COR_BORDA_LEVE, height=1).pack(fill="x", pady=(0, 16))

        # ── Botões ─────────────────────────────────────────────────────
        btn_row = tk.Frame(body, bg=COR_CARD)
        btn_row.pack(fill="x", pady=(0, 14))
        self._btn_start = ctk.CTkButton(
            btn_row, text="▶  Gerar planilhas DMST-e",
            command=self._start, width=220, height=42,
            font=(FONT_BODY, 11, "bold"), corner_radius=999,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color="#FFFFFF",
        )
        self._btn_start.pack(side="left")
        self._btn_remover = ctk.CTkButton(
            btn_row, text="✏  Editar planilha CSV",
            command=self._abrir_remover_nota, width=200, height=42,
            font=(FONT_BODY, 10), corner_radius=999,
            fg_color="transparent", hover_color=COR_CARD_HOVER,
            text_color=COR_GOLD, border_width=1, border_color=COR_BORDA,
        )
        self._btn_remover.pack(side="left", padx=(10, 0))

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

        # Checkbox: marcar notas como baixadas na Autmais apos gerar CSV.
        self._var_marcar = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            btn_row, text="Marcar notas como baixadas na Autmais",
            variable=self._var_marcar,
            font=(FONT_BODY, 10),
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color=COR_TEXTO, corner_radius=4,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
        ).pack(side="right")

        # ── Barra de progresso ─────────────────────────────────────────
        prog_wrap = tk.Frame(body, bg=COR_CARD)
        prog_wrap.pack(fill="x", pady=(6, 8))
        self._progress = ttkb.Progressbar(
            prog_wrap, mode="determinate",
            bootstyle="warning",  # laranja Crosara
            maximum=len(EMPRESAS_DMSTE),
            length=400,
        )
        self._progress.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._lbl_progress = tk.Label(
            prog_wrap, text=f"0 / {len(EMPRESAS_DMSTE)}",
            font=(FONT_BODY, 10, "bold"),
            bg=COR_CARD, fg=COR_GOLD,
        )
        self._lbl_progress.pack(side="right")

        # ── Status ─────────────────────────────────────────────────────
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

        # ── Log ────────────────────────────────────────────────────────
        log_frame = tk.Frame(body, bg=COR_LOG_BG,
                             highlightbackground=COR_BORDA_LEVE, highlightthickness=1)
        log_frame.pack(fill="both", expand=True)
        self._txt_log = tk.Text(
            log_frame, height=12, bg=COR_LOG_BG, fg=COR_TEXTO,
            font=(FONT_MONO, 9), state="disabled",
            padx=12, pady=10, insertbackground=COR_GOLD,
            wrap="word", relief="flat", borderwidth=0,
        )
        self._txt_log.pack(fill="both", expand=True)
        self._txt_log.tag_config("ok", foreground=COR_LOG_OK)
        self._txt_log.tag_config("warn", foreground=COR_LOG_WARN)
        self._txt_log.tag_config("erro", foreground=COR_ERRO)

    def _empresa_card(self, parent, emp: dict) -> tk.Frame:
        """Card por empresa — clicável pra marcar/desmarcar processamento.

        Visual:
            ☑  1553       (gold quando marcada, esmaecido quando desmarcada)
                LIMA MAT
                [VIANOPOLIS]
        """
        cod = emp["cod"]
        var = self._var_emp_flags[cod]

        card = tk.Frame(
            parent, bg=COR_BG,
            highlightbackground=COR_BORDA_LEVE, highlightthickness=1,
            cursor="hand2",
        )
        inner = tk.Frame(card, bg=COR_BG, cursor="hand2")
        inner.pack(fill="both", expand=True, padx=10, pady=6)

        # Linha superior: checkbox + cod
        top = tk.Frame(inner, bg=COR_BG, cursor="hand2")
        top.pack(fill="x")
        chk = ctk.CTkCheckBox(
            top, text="", variable=var, width=20,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
            corner_radius=4,
            command=lambda c=cod: self._atualizar_visual_card(c),
        )
        chk.pack(side="left", padx=(0, 8))
        lbl_cod = tk.Label(
            top, text=cod,
            font=(FONT_DISPLAY, 15),
            fg=COR_GOLD, bg=COR_BG,
            cursor="hand2",
        )
        lbl_cod.pack(side="left")
        # Pill do municipio na MESMA linha (poupa altura)
        lbl_mun = tk.Label(
            top, text=f"  {emp['municipio']}  ",
            font=(FONT_BODY, 7, "bold"),
            fg=COR_GOLD_CLARO, bg=COR_CARD,
            padx=4, pady=1, cursor="hand2",
        )
        lbl_mun.pack(side="right")

        lbl_razao = tk.Label(
            inner, text=emp["razao"],
            font=(FONT_BODY, 9),
            fg=COR_TEXTO, bg=COR_BG,
            anchor="w", justify="left", wraplength=220,
            cursor="hand2",
        )
        lbl_razao.pack(anchor="w", pady=(2, 0))
        # Guarda refs pra updates visuais
        self._cards_refs[cod] = {
            "card": card, "inner": inner, "top": top,
            "lbl_cod": lbl_cod, "lbl_razao": lbl_razao, "lbl_mun": lbl_mun,
            "chk": chk,
        }

        def toggle(_event=None):
            var.set(not var.get())
            self._atualizar_visual_card(cod)

        # Click em qualquer area do card (exceto checkbox) faz toggle.
        for w in (card, inner, top, lbl_cod, lbl_razao, lbl_mun):
            w.bind("<Button-1>", toggle)

        return card

    def _atualizar_visual_card(self, cod: str):
        """Atualiza o visual do card conforme estado da checkbox.

        Marcada → cod em gold, borda normal.
        Desmarcada → cod esmaecido, borda mais sutil.
        """
        ref = self._cards_refs.get(cod)
        if not ref:
            return
        marcada = self._var_emp_flags[cod].get()
        if marcada:
            ref["card"].configure(highlightbackground=COR_BORDA_LEVE)
            ref["lbl_cod"].configure(fg=COR_GOLD)
            ref["lbl_razao"].configure(fg=COR_TEXTO)
            ref["lbl_mun"].configure(fg=COR_GOLD_CLARO)
        else:
            ref["card"].configure(highlightbackground=COR_BORDA_LEVE)
            ref["lbl_cod"].configure(fg=COR_SUBTEXTO)
            ref["lbl_razao"].configure(fg=COR_SUBTEXTO)
            ref["lbl_mun"].configure(fg=COR_SUBTEXTO)

    def _marcar_todas(self, marcado: bool):
        """Atalho: marca/desmarca todas as empresas de uma vez."""
        for cod, var in self._var_emp_flags.items():
            var.set(marcado)
            self._atualizar_visual_card(cod)

    def _empresas_selecionadas(self) -> list[dict]:
        return [emp for emp in EMPRESAS_DMSTE if self._var_emp_flags[emp["cod"]].get()]

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------

    def _start(self):
        if self._running:
            return
        vigencia = self._var_vigencia.get().strip()
        if len(vigencia) != 6 or not vigencia.isdigit():
            messagebox.showwarning(
                "Vigência inválida",
                "A vigência deve ter exatamente 6 dígitos (MMAAAA).",
            )
            return

        empresas_sel = self._empresas_selecionadas()
        if not empresas_sel:
            messagebox.showwarning(
                "Nenhuma empresa selecionada",
                "Marque pelo menos uma empresa para gerar as planilhas.",
            )
            return

        self._txt_log.configure(state="normal")
        self._txt_log.delete("1.0", tk.END)
        self._txt_log.configure(state="disabled")
        self._running = True
        self._processadas = 0
        self._total_sel = len(empresas_sel)
        self._progress.configure(maximum=self._total_sel)
        self._progress["value"] = 0
        self._lbl_progress.configure(text=f"0 / {self._total_sel}", fg=COR_GOLD)
        self._btn_start.configure(state="disabled")

        self._pasta_raiz = Path.home() / "Downloads" / f"Rest_MegaSoft-{vigencia}"
        self._pasta_raiz.mkdir(parents=True, exist_ok=True)
        self._log(f"📂 Pasta destino: {self._pasta_raiz}")
        # Pré-cria as subpastas dos municípios envolvidos (só das selecionadas)
        municipios_subpastas = {
            self._slug_municipio(emp["municipio"]) for emp in empresas_sel
        }
        for slug in sorted(municipios_subpastas):
            (self._pasta_raiz / slug).mkdir(parents=True, exist_ok=True)
        self._log(f"   Subpastas: {', '.join(sorted(municipios_subpastas))}")
        self._log(
            f"📋 {self._total_sel} de {len(EMPRESAS_DMSTE)} empresa(s) selecionada(s)",
        )
        self._log("─" * 60)

        marcar_baixadas = self._var_marcar.get()
        self._q = queue.Queue()
        t = threading.Thread(
            target=self._worker,
            args=(vigencia, self._pasta_raiz, marcar_baixadas, empresas_sel),
            daemon=True,
        )
        t.start()

    def _worker(self, vigencia: str, pasta_raiz: Path, marcar_baixadas: bool,
                empresas: list[dict]):
        try:
            for emp in empresas:
                self._q.put(("processando", emp))
                # CSV vai pra subpasta do município da empresa tomadora
                subpasta = pasta_raiz / self._slug_municipio(emp["municipio"])
                subpasta.mkdir(parents=True, exist_ok=True)
                res = processar_empresa_dmste(
                    cod=emp["cod"],
                    razao=emp["razao"],
                    municipio=emp["municipio"],
                    vigencia=vigencia,
                    pasta_saida=subpasta,
                    marcar_baixadas=marcar_baixadas,
                )
                self._q.put(("resultado", res))
        finally:
            self._q.put(("fim", None))

    # ------------------------------------------------------------------
    # Remover nota do CSV
    # ------------------------------------------------------------------

    def _abrir_pasta_saida(self):
        """Abre o Windows Explorer na pasta dos CSVs gerados."""
        import os
        import subprocess
        if not self._pasta_raiz or not self._pasta_raiz.exists():
            messagebox.showinfo(
                "Pasta indisponivel",
                "Gere primeiro as planilhas — a pasta de saida nao existe ainda.",
            )
            return
        try:
            os.startfile(str(self._pasta_raiz))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            # fallback (Linux/Mac em dev)
            subprocess.Popen(["explorer", str(self._pasta_raiz)])

    def _abrir_remover_nota(self):
        """Abre o editor visual de um CSV gerado.

        Mostra todas as notas em uma tabela com ícone de lixeira por linha
        para remover individualmente. Útil quando o portal recusa o lote por
        notas duplicadas — você marca quais excluir e salva o CSV preservando
        os CNPJs com zeros à esquerda (que o Excel apagaria).
        """
        vig = self._var_vigencia.get().strip()
        inicial = Path.home() / "Downloads"
        if vig:
            candidata = inicial / f"Rest_MegaSoft-{vig}"
            if candidata.exists():
                inicial = candidata
        arquivo = filedialog.askopenfilename(
            title="Selecione o CSV pra editar",
            filetypes=[("Arquivo CSV", "*.csv"), ("Todos", "*.*")],
            initialdir=str(inicial),
            parent=self.winfo_toplevel(),
        )
        if not arquivo:
            return
        self._abrir_editor_csv(Path(arquivo))

    def _abrir_editor_csv(self, arquivo):
        """Abre o editor visual de CSV DMST-e (compartilhado em ui/editor_arquivo)."""
        abrir_editor_arquivo(
            parent=self,
            arquivo=arquivo,
            titulo_eyebrow="Editar planilha · CSV DMST-e",
            colunas=COLUNAS_DMSTE,
            separador=";",
            tem_cabecalho=True,
            log_fn=self._log,
        )

    # ------------------------------------------------------------------
    # Poll loop
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
        kind, payload = evt
        if kind == "processando":
            emp = payload
            self._lbl_status.configure(
                text=f"▶ {emp['cod']} — {emp['razao']} ({emp['municipio']})",
                fg=COR_PRIMARIA,
            )
            total = getattr(self, "_total_sel", len(EMPRESAS_DMSTE))
            self._lbl_progress.configure(
                text=f"{self._processadas} / {total}  ·  {emp['cod']}",
            )
            self._log(f"\n▶ {emp['cod']} — {emp['razao']}")
        elif kind == "resultado":
            res: DmsteResult = payload
            self._processadas += 1
            total = getattr(self, "_total_sel", len(EMPRESAS_DMSTE))
            self._progress["value"] = self._processadas
            self._lbl_progress.configure(
                text=f"{self._processadas} / {total}",
            )
            if res.status == "ok":
                self._log(
                    f"   ✅ {res.notas_processadas} nota(s) → {res.arquivo_saida.name}",
                    "ok",
                )
                if res.notas_canceladas:
                    self._log(
                        f"      ⛔ {res.notas_canceladas} nota(s) cancelada(s) ignorada(s)",
                    )
                if res.notas_fora_vigencia:
                    self._log(
                        f"      ⏭ {res.notas_fora_vigencia} nota(s) fora da vigência ignorada(s)",
                        "warn",
                    )
                if res.notas_isentas:
                    self._log(
                        f"      🆓 {res.notas_isentas} nota(s) com item isento (alíquota 0%) ignorada(s)",
                        "warn",
                    )
                if res.notas_erro:
                    self._log(
                        f"      ⚠ {res.notas_erro} nota(s) com erro de extração",
                        "warn",
                    )
            elif res.status == "pasta_inexistente":
                self._log(f"   ⚠ {res.detalhe}", "warn")
            elif res.status == "vazio":
                self._log(f"   ⚠ {res.detalhe}", "warn")
            else:
                self._log(f"   ❌ {res.detalhe}", "erro")
        elif kind == "fim":
            self._running = False
            self._btn_start.configure(state="normal")
            self._btn_abrir.configure(state="normal")
            total = getattr(self, "_total_sel", len(EMPRESAS_DMSTE))
            self._progress["value"] = total
            self._lbl_progress.configure(
                text=f"{self._processadas} / {total}  ·  ✓",
                fg=COR_LOG_OK,
            )
            self._lbl_status.configure(text="✅ Concluído", fg=COR_LOG_OK)
            self._log("\n" + "─" * 60)
            self._log("✅ Processamento finalizado.", "ok")
            if self._pasta_raiz:
                self._log(f"📁 {self._pasta_raiz}", "ok")
