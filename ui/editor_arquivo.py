"""Editor visual generico de arquivos delimitados (CSV/TXT).

Reaproveitado por:
- MegaSoft (CSV DMST-e, separador ';')
- ISSNet   (TXT, separador ';' com header proprio)

Visual dark mode com edicao celula a celula + lixeira por linha.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from config import (
    COR_BG, COR_BORDA, COR_BORDA_LEVE, COR_CARD, COR_CARD_HOVER,
    COR_ERRO, COR_GOLD, COR_GOLD_CLARO, COR_PRIMARIA, COR_PRIMARIA_HV,
    COR_SUBTEXTO, COR_TEXTO,
    FONT_BODY, FONT_DISPLAY,
)


@dataclass
class ColunaEditor:
    """Descreve uma coluna visivel no editor."""
    header: str         # texto do cabecalho
    indice_csv: int     # posicao no array de partes da linha
    largura: int = 100  # largura da coluna no Treeview
    align: str = "w"    # alinhamento (w/e/center)


def abrir_editor_arquivo(
    *,
    parent: tk.Misc,
    arquivo: Path,
    titulo_eyebrow: str,
    colunas: list[ColunaEditor],
    separador: str = ";",
    tem_cabecalho: bool = True,
    log_fn=None,
    largura_window: int = 980,
    altura_window: int = 620,
):
    """Abre janela de edicao do arquivo.

    Args:
        parent: widget pai (pra modal toplevel).
        arquivo: Path do CSV/TXT a editar.
        titulo_eyebrow: ex "EDITAR PLANILHA · CSV DMST-E"
        colunas: lista de ColunaEditor (cada uma mapeia 1 coluna visivel
                 para uma posicao no array de partes).
        separador: ';' por padrao (CSV/TXT).
        tem_cabecalho: True => primeira linha do arquivo e header e e preservada;
                       False => todas as linhas sao tratadas como dados.
        log_fn: callback opcional para registrar evento de save no log do painel.
        largura_window/altura_window: dimensoes da janela.
    """
    # ── Le o arquivo ──────────────────────────────────────────────────
    try:
        with open(arquivo, "r", encoding="utf-8-sig", newline="") as f:
            linhas = f.readlines()
    except OSError as exc:
        messagebox.showerror("Erro", f"Não consegui ler {arquivo.name}:\n{exc}")
        return

    if tem_cabecalho:
        if len(linhas) < 2:
            messagebox.showinfo("Vazio", "Arquivo não tem linhas de dados pra editar.")
            return
        cabecalho = linhas[0]
        linhas_dados = linhas[1:]
    else:
        if not linhas:
            messagebox.showinfo("Vazio", "Arquivo está vazio.")
            return
        cabecalho = ""
        linhas_dados = linhas

    # estado[iid] = list[str] (partes da linha, sem \n)
    estado: dict[str, list[str]] = {}
    ordem: list[str] = []
    modificado = {"flag": False}

    # Mapping coluna treeview (#1..) → indice no array de partes
    COL_TO_FIELD: dict[str, int] = {
        f"#{i+1}": col.indice_csv for i, col in enumerate(colunas)
    }
    # ultima coluna e sempre a acao (lixeira)
    COL_ACAO = f"#{len(colunas) + 1}"

    # ── Janela ────────────────────────────────────────────────────────
    win = tk.Toplevel(parent)
    win.title(f"Editar — {arquivo.name}")
    win.geometry(f"{largura_window}x{altura_window}")
    win.transient(parent.winfo_toplevel() if hasattr(parent, "winfo_toplevel") else parent)
    win.grab_set()
    win.configure(bg=COR_BG)

    # ── Hero compacto ─────────────────────────────────────────────────
    hero = tk.Frame(win, bg=COR_BG)
    hero.pack(fill="x", padx=24, pady=(20, 12))
    eb = tk.Frame(hero, bg=COR_BG)
    eb.pack(anchor="w")
    tk.Frame(eb, bg=COR_GOLD, width=26, height=1).pack(side="left", padx=(0, 10), pady=4)
    tk.Label(
        eb, text=titulo_eyebrow.upper(),
        font=(FONT_BODY, 9, "bold"),
        fg=COR_GOLD, bg=COR_BG,
    ).pack(side="left")
    tk.Label(
        hero, text=arquivo.name,
        font=(FONT_DISPLAY, 16), fg=COR_TEXTO, bg=COR_BG,
    ).pack(anchor="w", pady=(6, 2))
    lbl_contagem = tk.Label(
        hero, text="", font=(FONT_BODY, 9),
        fg=COR_SUBTEXTO, bg=COR_BG,
    )
    lbl_contagem.pack(anchor="w")
    tk.Label(
        hero,
        text="Duplo-clique numa célula pra editar  ·  clique 🗑 pra remover a linha",
        font=(FONT_BODY, 9, "italic"),
        fg=COR_SUBTEXTO, bg=COR_BG,
    ).pack(anchor="w", pady=(2, 0))

    body = tk.Frame(win, bg=COR_CARD, padx=14, pady=12,
                    highlightbackground=COR_BORDA, highlightthickness=1)
    body.pack(fill="both", expand=True, padx=24, pady=(6, 12))

    # ── Treeview ──────────────────────────────────────────────────────
    style = ttk.Style()
    style.configure(
        "Editor.Treeview",
        background=COR_BG, foreground=COR_TEXTO,
        fieldbackground=COR_BG, rowheight=26, borderwidth=0,
    )
    style.configure(
        "Editor.Treeview.Heading",
        background=COR_CARD_HOVER, foreground=COR_GOLD,
        font=(FONT_BODY, 9, "bold"), borderwidth=0,
    )
    style.map(
        "Editor.Treeview",
        background=[("selected", COR_CARD_HOVER)],
        foreground=[("selected", COR_GOLD_CLARO)],
    )

    cols_ids = [f"c{i}" for i in range(len(colunas))] + ["acao"]
    tree = ttk.Treeview(
        body, columns=cols_ids, show="headings", height=16,
        style="Editor.Treeview",
    )
    for i, col in enumerate(colunas):
        tree.heading(f"c{i}", text=col.header)
        tree.column(f"c{i}", width=col.largura, anchor=col.align)
    tree.heading("acao", text="")
    tree.column("acao", width=50, anchor="center")

    scroll = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    # ── Preenche linhas ────────────────────────────────────────────────
    def _vals(partes: list[str]) -> tuple:
        return tuple(
            partes[col.indice_csv] if col.indice_csv < len(partes) else ""
            for col in colunas
        ) + ("🗑",)

    for idx, linha in enumerate(linhas_dados, start=1):
        if not linha.strip():
            continue
        partes = linha.rstrip("\n").split(separador)
        # Tolera linhas com menos campos que esperado (padding vazio)
        max_idx = max((col.indice_csv for col in colunas), default=0)
        while len(partes) <= max_idx:
            partes.append("")
        iid = f"r{idx}"
        estado[iid] = partes
        ordem.append(iid)
        tree.insert("", "end", iid=iid, values=_vals(partes))

    def _atualizar_contagem():
        n = len(estado)
        status = "  ·  modificado, salve antes de fechar" if modificado["flag"] else ""
        lbl_contagem.configure(text=f"{n} linha(s){status}")

    _atualizar_contagem()

    # ── Edicao inline ──────────────────────────────────────────────────
    editor_widget = {"entry": None}

    def _fechar_editor(save: bool = True):
        ent = editor_widget["entry"]
        if not ent:
            return
        iid = ent._iid
        col_id = ent._col
        if save:
            novo_valor = ent.get().strip()
            partes = estado.get(iid)
            if partes is not None:
                campo = COL_TO_FIELD.get(col_id)
                if campo is not None and partes[campo] != novo_valor:
                    partes[campo] = novo_valor
                    tree.item(iid, values=_vals(partes))
                    modificado["flag"] = True
                    _atualizar_contagem()
        ent.destroy()
        editor_widget["entry"] = None

    def _abrir_editor_inline(iid: str, col_id: str):
        _fechar_editor(save=False)
        if col_id == COL_ACAO:
            return
        campo = COL_TO_FIELD.get(col_id)
        if campo is None:
            return
        partes = estado.get(iid)
        if partes is None:
            return
        x, y, w, h = tree.bbox(iid, col_id)
        valor_atual = partes[campo] if campo < len(partes) else ""
        ent = tk.Entry(
            tree, font=(FONT_BODY, 10),
            bg=COR_CARD_HOVER, fg=COR_TEXTO,
            insertbackground=COR_GOLD,
            relief="flat", borderwidth=1,
            highlightthickness=1,
            highlightbackground=COR_GOLD, highlightcolor=COR_GOLD,
        )
        ent._iid = iid
        ent._col = col_id
        ent.insert(0, valor_atual)
        ent.select_range(0, tk.END)
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()
        ent.bind("<Return>", lambda _: _fechar_editor(save=True))
        ent.bind("<KP_Enter>", lambda _: _fechar_editor(save=True))
        ent.bind("<Escape>", lambda _: _fechar_editor(save=False))
        ent.bind("<FocusOut>", lambda _: _fechar_editor(save=True))
        editor_widget["entry"] = ent

    def _on_double_click(event):
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col_id = tree.identify_column(event.x)
        iid = tree.identify_row(event.y)
        if not iid or col_id == COL_ACAO:
            return
        _abrir_editor_inline(iid, col_id)

    def _on_single_click(event):
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col_id = tree.identify_column(event.x)
        iid = tree.identify_row(event.y)
        if not iid:
            return
        if col_id == COL_ACAO:
            if editor_widget["entry"]:
                _fechar_editor(save=False)
            # Primeira coluna mostrada na confirmacao (chave visual da linha)
            primeiro_val = tree.set(iid, "c0")
            if messagebox.askyesno(
                "Remover linha",
                f"Remover a linha {primeiro_val}?",
                parent=win,
            ):
                tree.delete(iid)
                estado.pop(iid, None)
                if iid in ordem:
                    ordem.remove(iid)
                modificado["flag"] = True
                _atualizar_contagem()

    tree.bind("<Double-Button-1>", _on_double_click)
    tree.bind("<Button-1>", _on_single_click)

    # ── Botoes (salvar / cancelar) ────────────────────────────────────
    rod = tk.Frame(win, bg=COR_BG)
    rod.pack(fill="x", padx=24, pady=(0, 16))

    def _salvar():
        if editor_widget["entry"]:
            _fechar_editor(save=True)
        if not modificado["flag"]:
            messagebox.showinfo(
                "Nada pra salvar",
                "Você não fez nenhuma alteração.",
                parent=win,
            )
            return
        novas = [cabecalho] if cabecalho else []
        for iid in ordem:
            if iid in estado:
                nova_linha = separador.join(estado[iid])
                if not nova_linha.endswith("\n"):
                    nova_linha += "\n"
                novas.append(nova_linha)
        try:
            with open(arquivo, "w", encoding="utf-8-sig", newline="") as f:
                f.writelines(novas)
        except OSError as exc:
            messagebox.showerror(
                "Erro ao salvar",
                f"Não consegui salvar {arquivo.name}:\n{exc}",
                parent=win,
            )
            return
        n_total_orig = len(linhas_dados)
        n_atual = len(estado)
        n_removidas = n_total_orig - n_atual
        partes_msg = []
        if n_removidas:
            partes_msg.append(f"{n_removidas} linha(s) removida(s)")
        partes_msg.append(f"{n_atual} linha(s) salva(s) no arquivo")
        if log_fn:
            log_fn(f"💾 {arquivo.name} salvo (" + ", ".join(partes_msg) + ")", "ok")
        messagebox.showinfo("Salvo", "\n".join(partes_msg), parent=win)
        win.destroy()

    def _cancelar():
        if editor_widget["entry"]:
            _fechar_editor(save=False)
        if modificado["flag"]:
            if not messagebox.askyesno(
                "Descartar alterações?",
                "Você fez alterações que não foram salvas.\n\nDescartar e fechar?",
                parent=win,
            ):
                return
        win.destroy()

    ctk.CTkButton(
        rod, text="✖  Cancelar", command=_cancelar,
        width=120, height=36, corner_radius=999,
        font=(FONT_BODY, 10),
        fg_color="transparent", hover_color=COR_CARD_HOVER,
        text_color=COR_SUBTEXTO, border_width=1, border_color=COR_BORDA,
    ).pack(side="right", padx=(8, 0))
    ctk.CTkButton(
        rod, text="💾  Salvar alterações", command=_salvar,
        width=180, height=36, corner_radius=999,
        font=(FONT_BODY, 10, "bold"),
        fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HV,
        text_color="#FFFFFF",
    ).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", _cancelar)


# ============================================================================
# Configuracoes prontas por formato
# ============================================================================

# CSV DMST-e (MegaSoft) — 12 campos separados por ';'.
# Posicoes: 0=CPF/CNPJ, 1=ItemServico, 2=Regime, 3=Competencia, 4=NFSe, 5=Valor,
#           6=Deducao, 7=Aliq, 8=Link, 9=CodVerif, 10=IssRetido, 11=Municipio
COLUNAS_DMSTE = [
    ColunaEditor("NFS-e",        4, width := 110),
    ColunaEditor("CPF/CNPJ",     0, 160, "w"),
    ColunaEditor("Item",         1, 100, "center"),
    ColunaEditor("Competência",  3, 120, "center"),
    ColunaEditor("Valor",        5, 130, "e"),
    ColunaEditor("Alíq",         7, 80, "center"),
]


# TXT ISSNet — 23 campos separados por ';', primeira linha e o cabecalho.
# Posicoes (montar_linha_txt):
#  0=modelo, 1=numero, 2=vlr_trib, 3=vlr_doc, 4=aliq,
#  5=data_emissao, 6=data_pagamento, 7=cnpj, 8=razao, 9=im,
# 10=imposto_retido, 11=cep, 12=endereco, 13=numero_end, 14=bairro,
# 15=cidade, 16=uf, 17=ddd, 18=tributado_municipio, 19=item_lc,
# 20=unidade_economica, 21=local_prestacao, 22=optante_sn_mei
COLUNAS_ISSNET = [
    ColunaEditor("Número",       1, 90,  "w"),
    ColunaEditor("CNPJ",         7, 130, "w"),
    ColunaEditor("Razão Social", 8, 220, "w"),
    ColunaEditor("Valor",        3, 110, "e"),
    ColunaEditor("Alíq",         4, 70,  "center"),
    ColunaEditor("Emissão",      5, 90,  "center"),
    ColunaEditor("Item LC",      19, 80,  "center"),
]
