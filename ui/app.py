import ctypes
import threading
from pathlib import Path
from tkinter import messagebox, filedialog, ttk
import tkinter as tk
import ttkbootstrap as ttkb
import customtkinter as ctk

# Windows: set AppUserModelID so the taskbar uses our icon instead of Python's
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("crosara.importarest")
except Exception:
    pass

try:
    from PIL import Image, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

from config import (
    COR_BG, COR_CARD, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUCESSO, COR_SUCESSO_HV, COR_SUBTEXTO, COR_BORDA,
)
from core.txt_builder import montar_cabecalho
from services.processor import WorkflowProcessor
from services.report import gravar_relatorio
from ui.components import CircularProgress
from ui.dialogs import abrir_tela_manual_itemlc, pedir_dados_cabecalho
from ui.batch_panel import PainelLote


class JanelaCrosara:

    def __init__(self):
        self.conteudo_final = ""
        self._relatorio = []
        self._notas_vig_errada = {}
        self._im_tomador_cab = ""
        self._razao_tomador_cab = ""
        self._emp_cod = ""
        self._vigencia = ""

        self.janela = ttkb.Window(themename="litera")
        self.janela.title("Importador de NFS-e \u2013 REST")
        self.janela.geometry("900x660")
        self.janela.configure(bg=COR_BG)
        self.janela.resizable(False, False)

        ico = Path(__file__).resolve().parent.parent / "assets" / "logo_importarest.ico"
        if ico.exists():
            self.janela.iconbitmap(str(ico))

        self._construir_ui()
        self.janela.mainloop()

    # ──────────────────────────────────────────────────────────────────────────
    # Construção da UI
    # ──────────────────────────────────────────────────────────────────────────

    def _construir_ui(self):
        nb = ttk.Notebook(self.janela)
        nb.pack(fill="both", expand=True)

        tab_individual = tk.Frame(nb, bg=COR_BG)
        nb.add(tab_individual, text="Individual")

        tab_lote = tk.Frame(nb, bg=COR_BG)
        nb.add(tab_lote, text="Lote")

        self._construir_aba_individual(tab_individual)

        self._painel_lote = PainelLote(tab_lote)
        self._painel_lote.pack(fill="both", expand=True)

        # Lazy load: only call load_analysts when Lote tab is first activated
        # Prevents G: drive crash at startup if drive is unavailable
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._nb = nb
        self._lote_tab_id = nb.index(tab_lote)

    # ── Helpers ──────────────────────────────────────────────────────────────

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
            bg=bg, fg="#2C2C2C", anchor="w",
        ).pack(side="left")
        tk.Frame(frame, bg=COR_BORDA, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=(4, 0),
        )

    def _build_logo(self, parent):
        """Centered logo matching Lote tab style."""
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
                logo = ImageTk.PhotoImage(img)
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

    # ── Individual tab ───────────────────────────────────────────────────────

    def _construir_aba_individual(self, parent):
        main = tk.Frame(parent, bg=COR_BG)
        main.pack(fill="both", expand=True, padx=24, pady=(16, 20))

        # ── Header (centered logo + separator) ──
        self._build_logo(main)
        tk.Frame(main, bg=COR_BORDA, height=1).pack(fill="x", pady=(0, 16))

        # ── Two-column content ──
        content = tk.Frame(main, bg=COR_BG)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2, minsize=200)
        content.rowconfigure(0, weight=1)

        # ── Left: config card ──
        card = ctk.CTkFrame(
            content, fg_color=COR_CARD, corner_radius=12,
            border_width=1, border_color=COR_BORDA,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        body = tk.Frame(card, bg=COR_CARD)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        self._section_title(body, "IMPORTACAO INDIVIDUAL")

        # Código da Empresa
        tk.Label(
            body, text="Codigo da Empresa", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.ent_codigo = ctk.CTkEntry(
            body, height=34, font=("Segoe UI", 11), corner_radius=8,
            fg_color=COR_CARD, border_color=COR_BORDA,
            text_color="#2C2C2C",
        )
        self.ent_codigo.pack(fill="x", pady=(0, 12))
        self.ent_codigo.focus_set()

        # Vigência
        tk.Label(
            body, text="Vigencia (MMYYYY)", font=("Segoe UI", 9, "bold"),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x", pady=(0, 4))
        self.ent_vigencia = ctk.CTkEntry(
            body, height=34, font=("Segoe UI", 11), corner_radius=8,
            fg_color=COR_CARD, border_color=COR_BORDA,
            text_color="#2C2C2C", placeholder_text="MMAAAA",
        )
        self.ent_vigencia.pack(fill="x", pady=(0, 12))

        # MEI checkbox
        self._var_mei = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            body, text="Processar notas MEI tomadas",
            variable=self._var_mei, font=("Segoe UI", 10),
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color=COR_SUBTEXTO, corner_radius=4,
            border_color=COR_BORDA, checkmark_color="#FFFFFF",
        ).pack(anchor="w")

        # Separator + action button
        tk.Frame(body, bg=COR_BORDA, height=1).pack(fill="x", pady=(16, 14))

        self.btn_acao = ctk.CTkButton(
            body, text="\u25B6  INICIAR IMPORTA\u00C7\u00C3O",
            command=self.iniciar_processo,
            font=("Segoe UI", 11, "bold"), height=42,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
            text_color="#FFFFFF", corner_radius=8,
        )
        self.btn_acao.pack(fill="x")

        # ── Right: progress card ──
        prog_card = ctk.CTkFrame(
            content, fg_color=COR_CARD, corner_radius=12,
            border_width=1, border_color=COR_BORDA,
        )
        prog_card.grid(row=0, column=1, sticky="nsew")

        prog_body = tk.Frame(prog_card, bg=COR_CARD)
        prog_body.pack(fill="both", expand=True, padx=16, pady=16)

        self.progress = CircularProgress(prog_body, size=150, bg=COR_CARD)
        self.progress.pack(pady=(10, 14))

        self.lbl_contador = tk.Label(
            prog_body, text="", font=("Segoe UI", 9),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="center",
        )
        self.lbl_contador.pack(fill="x")

        self.lbl_status = tk.Label(
            prog_body, text="", font=("Segoe UI", 9),
            bg=COR_CARD, fg=COR_SUBTEXTO, anchor="center",
            wraplength=160,
        )
        self.lbl_status.pack(fill="x", pady=(4, 0))

        # Key bindings
        self.ent_codigo.bind("<Return>", lambda e: self.ent_vigencia.focus_set())
        self.ent_vigencia.bind("<Return>", lambda e: self.iniciar_processo())

    def _on_tab_changed(self, event=None):
        selected = self._nb.index(self._nb.select())
        if selected == self._lote_tab_id:
            self._painel_lote._trigger_load_analysts()

    # ──────────────────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────────────────

    def log(self, msg: str):
        cor = COR_SUBTEXTO
        if any(x in msg for x in ["\u2705", "\u2728", "\U0001f3c1"]):
            cor = "#1B8A1B"
        elif any(x in msg for x in ["\u274c"]):
            cor = "#C0392B"
        elif any(x in msg for x in ["\u26a0\ufe0f", "\u26a0"]):
            cor = "#B8860B"
        elif any(x in msg for x in ["\U0001f916", "\U0001f501", "\U0001f504"]):
            cor = "#2471A3"

        self.lbl_status.configure(text=msg.strip(), fg=cor)
        self.janela.update()

    # ──────────────────────────────────────────────────────────────────────────
    # Ações
    # ──────────────────────────────────────────────────────────────────────────

    def iniciar_processo(self):
        codigo = self.ent_codigo.get().strip()
        vigencia = self.ent_vigencia.get().strip()

        if not codigo or not vigencia:
            messagebox.showwarning("Aten\u00e7\u00e3o", "Preencha C\u00f3digo da Empresa e Vig\u00eancia.")
            return

        self.progress["value"] = 0
        self.lbl_contador.configure(text="")
        self.lbl_status.configure(text="")
        self.conteudo_final = ""
        self._relatorio = []
        self._emp_cod = codigo
        self._vigencia = vigencia

        self.btn_acao.configure(
            state="disabled",
            text="\u23f3  PROCESSANDO...",
            fg_color=COR_SUBTEXTO,
            hover_color=COR_SUBTEXTO,
        )
        threading.Thread(
            target=self.fluxo_trabalho,
            args=(codigo, vigencia),
            daemon=True
        ).start()

    def fluxo_trabalho(self, emp_cod: str, vigencia: str):
        try:
            processor = WorkflowProcessor(
                log_fn=self.log,
                progress_fn=lambda total: self._set_progress_max(total),
                contador_fn=self._set_contador,
                abrir_tela_manual_fn=self._abrir_tela_manual_wrapper,
                gerar_mei=self._var_mei.get(),
            )
            result = processor.processar(emp_cod, vigencia)

            if result is None:
                msg = self.lbl_status.cget("text").replace("\u274c", "").strip()
                messagebox.showerror("Erro", msg or "N\u00e3o foi poss\u00edvel processar.")
                self._resetar_botao()
                return

            self._relatorio = result.relatorio
            self._notas_vig_errada = result.notas_vig_errada
            self._im_tomador_cab = result.im_tomador_cab
            self._razao_tomador_cab = result.razao_tomador_cab
            self.conteudo_final = result.conteudo_final

            # Pedir dados faltantes do cabeçalho ao usuário
            if result.linhas_dict or result.notas_vig_errada:
                self._completar_cabecalho()

            if result.linhas_dict or result.notas_vig_errada:
                self.btn_acao.configure(
                    state="normal",
                    text="\u2b07  BAIXAR TXT",
                    fg_color=COR_SUCESSO,
                    hover_color=COR_SUCESSO_HV,
                    command=self.salvar_arquivo_txt,
                )
            else:
                self._exibir_resumo_erros(result.relatorio)
                self._resetar_botao()

            self._gravar_relatorio()

        except Exception as e:
            self.log(f"\u274c Erro inesperado: {e}")
            messagebox.showerror("Erro", f"Erro inesperado:\n\n{e}")
            self._resetar_botao()

    def _exibir_resumo_erros(self, relatorio: list):
        """Monta messagebox com motivo de falha de cada nota."""
        linhas = []
        for row in relatorio:
            if len(row) < 7:
                continue
            nome, status, motivo = row[0], row[4], row[6]
            if status in ("Erro", "Ignorada", "Cancelado"):
                linhas.append(f"\u2022 {nome}\n   {motivo}")
        if linhas:
            corpo = "Nenhuma nota foi processada com sucesso.\n\n" + "\n\n".join(linhas)
        else:
            corpo = "Nenhuma nota foi processada com sucesso."
        messagebox.showerror("Erro no processamento", corpo)

    def _set_progress_max(self, total: int):
        self.progress["maximum"] = total

    def _set_contador(self, atual: int, total: int):
        if atual == 0:
            self.lbl_contador.configure(text="")
        else:
            self.lbl_contador.configure(text=f"Processando {atual} de {total}")
        self.progress["value"] = atual

    def _abrir_tela_manual_wrapper(self, dados_base: dict, chave_nfse: str,
                                   from_n8n: bool = False) -> str | None:
        return abrir_tela_manual_itemlc(self.janela, dados_base, chave_nfse, from_n8n)

    def _completar_cabecalho(self):
        """Verifica se há campos faltantes no cabeçalho e pergunta ao usuário."""
        im = self._im_tomador_cab
        razao = self._razao_tomador_cab
        if im and razao:
            return

        resp = pedir_dados_cabecalho(self.janela, im, razao)
        if not resp:
            return

        im_novo, razao_nova = resp
        self._im_tomador_cab = im_novo
        self._razao_tomador_cab = razao_nova

        # Regenerar cabeçalho com dados do usuário
        vig = self._vigencia
        mes = vig[:2]
        ano = vig[2:]
        dt_iso = f"{ano}-{mes}-01T00:00:00"
        novo_cab = montar_cabecalho(im_novo, razao_nova, dt_iso)

        if self.conteudo_final:
            linhas = self.conteudo_final.split("\n", 1)
            self.conteudo_final = novo_cab + ("\n" + linhas[1] if len(linhas) > 1 else "")

    def _resetar_botao(self):
        self.btn_acao.configure(
            state="normal",
            text="\u25B6  INICIAR IMPORTA\u00C7\u00C3O",
            fg_color=COR_PRIMARIA,
            hover_color=COR_PRIMARIA_HV,
            command=self.iniciar_processo,
        )

    def _gravar_relatorio(self):
        try:
            gravar_relatorio(self._relatorio)
            self.log("\U0001f4ca Relat\u00f3rio de processamento salvo.")
        except Exception as e:
            self.log(f"\u26a0\ufe0f Erro ao salvar relat\u00f3rio: {e}")

    def salvar_arquivo_txt(self):
        nome_padrao = f"{self._emp_cod}_{self._vigencia}"
        arquivo_path = filedialog.asksaveasfilename(
            initialfile=nome_padrao,
            defaultextension=".txt",
            filetypes=[("Arquivo TXT", "*.txt")],
            title="Salvar arquivo de importa\u00e7\u00e3o"
        )
        if not arquivo_path:
            return

        if self.conteudo_final:
            with open(arquivo_path, 'w', encoding='utf-8') as f:
                f.write(self.conteudo_final)
            self.log(f"\u2705 Arquivo salvo: {Path(arquivo_path).name}")

        notas_vig_errada = self._notas_vig_errada
        if notas_vig_errada:
            pasta_destino = Path(arquivo_path).parent
            im_tom = self._im_tomador_cab
            razao_tom = self._razao_tomador_cab
            arquivos_extras = []
            erros_extras = []
            for vig_errada, linhas_erradas in notas_vig_errada.items():
                try:
                    dt_iso = f"{vig_errada[2:]}-{vig_errada[:2]}-01T00:00:00"
                    cab_extra = montar_cabecalho(im_tom, razao_tom, dt_iso)
                    partes_extra = ([cab_extra] if cab_extra else []) + linhas_erradas
                    conteudo_extra = "\n".join(partes_extra)
                    nome_extra = f"{self._emp_cod}_{vig_errada}.txt"
                    path_extra = pasta_destino / nome_extra
                    with open(path_extra, "w", encoding="utf-8") as f:
                        f.write(conteudo_extra)
                    self.log(f"\u2705 Arquivo adicional salvo: {nome_extra} ({len(linhas_erradas)} nota(s))")
                    arquivos_extras.append(nome_extra)
                except Exception as e_extra:
                    erros_extras.append(f"{vig_errada}: {e_extra}")

            total_notas_div = sum(len(v) for v in notas_vig_errada.values())
            aviso = (
                f"{total_notas_div} nota(s) tinham data de emiss\u00e3o de outro m\u00eas "
                f"e foram separadas em arquivo(s) adicional(is):\n\n"
                + "\n".join(f"\u2022 {arq}" for arq in arquivos_extras)
                + f"\n\nSalvos na mesma pasta do arquivo principal."
            )
            if erros_extras:
                aviso += "\n\nErros:\n" + "\n".join(erros_extras)
            messagebox.showwarning("Notas de outra vig\u00eancia", aviso)
        elif self.conteudo_final:
            messagebox.showinfo("Sucesso", f"Arquivo salvo com sucesso!\n{arquivo_path}")

        self.btn_acao.configure(
            state="normal",
            text="\U0001f504  NOVO TRABALHO",
            fg_color=COR_PRIMARIA,
            hover_color=COR_PRIMARIA_HV,
            command=self._recomecar,
        )

    def _recomecar(self):
        self.conteudo_final = ""
        self._notas_vig_errada = {}
        self._im_tomador_cab = ""
        self._razao_tomador_cab = ""
        self.ent_codigo.delete(0, tk.END)
        self.ent_vigencia.delete(0, tk.END)
        self.progress["value"] = 0
        self.lbl_contador.configure(text="")
        self.lbl_status.configure(text="")
        self._resetar_botao()
        self.ent_codigo.focus_set()
