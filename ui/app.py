import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
import ttkbootstrap as ttkb

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
from ui.components import criar_entry, criar_botao, CircularProgress
from ui.dialogs import abrir_tela_manual_itemlc, pedir_dados_cabecalho


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
        self.janela.title("Importador de NFS-e – REST")
        self.janela.geometry("420x580")
        self.janela.configure(bg=COR_BG)
        self.janela.resizable(False, False)

        self._construir_ui()
        self.janela.mainloop()

    # ──────────────────────────────────────────────────────────────────────────
    # Construção da UI
    # ──────────────────────────────────────────────────────────────────────────

    def _construir_ui(self):
        self._exibir_logo()

        card = tk.Frame(self.janela, bg=COR_CARD,
                        highlightbackground=COR_BORDA, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=(0, 8))

        inner = tk.Frame(card, bg=COR_CARD, padx=20, pady=16)
        inner.pack(fill="x")

        tk.Label(inner, text="Código da Empresa",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD,
                 fg=COR_SUBTEXTO, anchor="w").pack(fill="x")
        frm_cod, self.ent_codigo = criar_entry(inner, width=20)
        frm_cod.pack(fill="x", pady=(3, 12))
        self.ent_codigo.focus_set()

        tk.Label(inner, text="Vigência (MMYYYY)",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD,
                 fg=COR_SUBTEXTO, anchor="w").pack(fill="x")
        frm_vig, self.ent_vigencia = criar_entry(inner, width=20)
        frm_vig.pack(fill="x", pady=(3, 8))

        self._var_mei = tk.BooleanVar(value=False)
        self.chk_mei = tk.Checkbutton(
            inner, text="Gerar notas MEI (Goiânia)",
            variable=self._var_mei,
            font=("Segoe UI", 9), bg=COR_CARD, fg=COR_SUBTEXTO,
            activebackground=COR_CARD, activeforeground=COR_SUBTEXTO,
            selectcolor=COR_CARD, anchor="w",
        )
        self.chk_mei.pack(fill="x")

        self.btn_acao = criar_botao(
            self.janela, "▶  INICIAR IMPORTAÇÃO",
            self.iniciar_processo, COR_PRIMARIA
        )
        self.btn_acao.pack(pady=14, padx=24, fill="x")

        zone = tk.Frame(self.janela, bg=COR_BG)
        zone.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        self.progress = CircularProgress(zone, size=130, bg=COR_BG)
        self.progress.pack(pady=(14, 4))

        self.lbl_contador = tk.Label(
            zone, text="",
            font=("Segoe UI", 9), bg=COR_BG, fg=COR_SUBTEXTO
        )
        self.lbl_contador.pack()

        self.lbl_status = tk.Label(
            zone, text="",
            font=("Segoe UI", 8), bg=COR_BG, fg=COR_SUBTEXTO,
        )
        self.lbl_status.pack(pady=(2, 0))

        rodape = tk.Frame(self.janela, bg=COR_BG)
        rodape.pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(rodape, text="IMPORTAREST GO  •  v2.0",
                 font=("Segoe UI", 7), bg=COR_BG, fg="#BBBBBB").pack(side="right")

        self.ent_codigo.bind("<Return>", lambda e: self.ent_vigencia.focus_set())
        self.ent_vigencia.bind("<Return>", lambda e: self.iniciar_processo())

    def _exibir_logo(self):
        if _PIL_OK:
            try:
                logo_path = Path(__file__).resolve().parent.parent / "assets" / "logo_importarest.png"
                img = Image.open(logo_path)
                img = img.resize((280, 78), Image.LANCZOS)
                logo = ImageTk.PhotoImage(img)
                lbl = tk.Label(self.janela, image=logo, bg=COR_BG)
                lbl.image = logo
                lbl.pack(pady=(20, 10))
                return
            except (FileNotFoundError, OSError):
                pass
        tk.Label(
            self.janela, text="IMPORTAREST GO",
            font=("Segoe UI", 20, "bold"),
            bg=COR_BG, fg=COR_PRIMARIA
        ).pack(pady=(24, 8))

    # ──────────────────────────────────────────────────────────────────────────
    # Logging
    # ──────────────────────────────────────────────────────────────────────────

    def log(self, msg: str):
        cor = COR_SUBTEXTO
        if any(x in msg for x in ["✅", "✨", "🏁"]):
            cor = "#1B8A1B"
        elif any(x in msg for x in ["❌"]):
            cor = "#C0392B"
        elif any(x in msg for x in ["⚠️", "⚠"]):
            cor = "#B8860B"
        elif any(x in msg for x in ["🤖", "🔁", "🔄"]):
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
            messagebox.showwarning("Atenção", "Preencha Código da Empresa e Vigência.")
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
            text="⏳  PROCESSANDO...",
            bg=COR_SUBTEXTO,
            cursor="watch"
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
                msg = self.lbl_status.cget("text").replace("❌", "").strip()
                messagebox.showerror("Erro", msg or "Não foi possível processar.")
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
                    text="⬇  BAIXAR TXT",
                    bg=COR_SUCESSO,
                    cursor="hand2",
                    command=self.salvar_arquivo_txt
                )
                self.btn_acao.bind("<Enter>", lambda e: self.btn_acao.configure(bg=COR_SUCESSO_HV))
                self.btn_acao.bind("<Leave>", lambda e: self.btn_acao.configure(bg=COR_SUCESSO))
            else:
                self._exibir_resumo_erros(result.relatorio)
                self._resetar_botao()

            self._gravar_relatorio()

        except Exception as e:
            self.log(f"❌ Erro inesperado: {e}")
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
                linhas.append(f"• {nome}\n   {motivo}")
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
            text="▶  INICIAR IMPORTAÇÃO",
            bg=COR_PRIMARIA,
            cursor="hand2",
            command=self.iniciar_processo
        )
        self.btn_acao.bind("<Enter>", lambda e: self.btn_acao.configure(bg=COR_PRIMARIA_HV))
        self.btn_acao.bind("<Leave>", lambda e: self.btn_acao.configure(bg=COR_PRIMARIA))

    def _gravar_relatorio(self):
        try:
            gravar_relatorio(self._relatorio)
            self.log("📊 Relatório de processamento salvo.")
        except Exception as e:
            self.log(f"⚠️ Erro ao salvar relatório: {e}")

    def salvar_arquivo_txt(self):
        nome_padrao = f"{self._emp_cod}_{self._vigencia}"
        arquivo_path = filedialog.asksaveasfilename(
            initialfile=nome_padrao,
            defaultextension=".txt",
            filetypes=[("Arquivo TXT", "*.txt")],
            title="Salvar arquivo de importação"
        )
        if not arquivo_path:
            return

        if self.conteudo_final:
            with open(arquivo_path, 'w', encoding='utf-8') as f:
                f.write(self.conteudo_final)
            self.log(f"✅ Arquivo salvo: {Path(arquivo_path).name}")

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
                    self.log(f"✅ Arquivo adicional salvo: {nome_extra} ({len(linhas_erradas)} nota(s))")
                    arquivos_extras.append(nome_extra)
                except Exception as e_extra:
                    erros_extras.append(f"{vig_errada}: {e_extra}")

            total_notas_div = sum(len(v) for v in notas_vig_errada.values())
            aviso = (
                f"{total_notas_div} nota(s) tinham data de emissão de outro mês "
                f"e foram separadas em arquivo(s) adicional(is):\n\n"
                + "\n".join(f"• {arq}" for arq in arquivos_extras)
                + f"\n\nSalvos na mesma pasta do arquivo principal."
            )
            if erros_extras:
                aviso += "\n\nErros:\n" + "\n".join(erros_extras)
            messagebox.showwarning("Notas de outra vigência", aviso)
        elif self.conteudo_final:
            messagebox.showinfo("Sucesso", f"Arquivo salvo com sucesso!\n{arquivo_path}")

        self.btn_acao.configure(
            state="normal",
            text="🔄  NOVO TRABALHO",
            bg=COR_PRIMARIA,
            cursor="hand2",
            command=self._recomecar
        )
        self.btn_acao.bind("<Enter>", lambda e: self.btn_acao.configure(bg=COR_PRIMARIA_HV))
        self.btn_acao.bind("<Leave>", lambda e: self.btn_acao.configure(bg=COR_PRIMARIA))

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
