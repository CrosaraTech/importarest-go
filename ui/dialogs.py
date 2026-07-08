import os
import tempfile
import tkinter as tk
import webbrowser
import urllib.parse

from config import (
    COR_BG, COR_CARD, COR_PRIMARIA,
    COR_SUCESSO, COR_SUBTEXTO, COR_TEXTO, COR_BORDA,
    COR_ERRO_LABEL, COR_DLG_SUB, COR_DESC_BG, COR_DESC_BORDA,
    COR_MUN_BG, COR_MUN_BORDA, COR_MUN_TEXTO,
)
from core.validators import normalize_digits
from core.txt_builder import montar_linha_txt, montar_linha_txt_n8n
from services.ibge import consulta_cidade_ibge
from ui.components import criar_entry, criar_botao


def pedir_dados_cabecalho(parent_window, im_atual: str, razao_atual: str) -> tuple | None:
    """Abre diálogo pedindo dados faltantes do cabeçalho.

    Retorna (im_tomador, razao_tomador) ou None se cancelado.
    """
    falta_im = not (im_atual or "").strip()
    falta_razao = not (razao_atual or "").strip()
    if not falta_im and not falta_razao:
        return (im_atual, razao_atual)

    resultado = [None]

    dlg = tk.Toplevel(parent_window)
    dlg.title("Dados do Cabeçalho")
    dlg.configure(bg=COR_BG)
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.transient(parent_window)

    hdr = tk.Frame(dlg, bg=COR_PRIMARIA, pady=10)
    hdr.pack(fill="x")
    tk.Label(hdr, text="📋  Dados do Cabeçalho",
             font=("Segoe UI", 12, "bold"),
             bg=COR_PRIMARIA, fg="#FFFFFF").pack()
    tk.Label(hdr, text="Campos nao encontrados nos XMLs",
             font=("Segoe UI", 9),
             bg=COR_PRIMARIA, fg=COR_DLG_SUB).pack()

    card = tk.Frame(dlg, bg=COR_CARD, padx=24, pady=16,
                    highlightbackground=COR_BORDA, highlightthickness=1)
    card.pack(fill="x", padx=16, pady=12)

    ent_im = ent_razao = None

    if falta_im:
        tk.Label(card, text="Inscrição Municipal do Tomador",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD,
                 fg=COR_SUBTEXTO, anchor="w").pack(fill="x")
        frm_im, ent_im = criar_entry(card, width=24)
        frm_im.pack(fill="x", pady=(3, 12))

    if falta_razao:
        tk.Label(card, text="Razão Social do Tomador",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD,
                 fg=COR_SUBTEXTO, anchor="w").pack(fill="x")
        frm_razao, ent_razao = criar_entry(card, width=40)
        frm_razao.pack(fill="x", pady=(3, 12))

    lbl_erro = tk.Label(card, text="", font=("Segoe UI", 9),
                        bg=COR_CARD, fg=COR_ERRO_LABEL)
    lbl_erro.pack()

    def confirmar(event=None):
        im = ent_im.get().strip() if ent_im else im_atual
        razao = ent_razao.get().strip() if ent_razao else razao_atual
        if falta_im and not im:
            lbl_erro.configure(text="\u26A0 Preencha a Inscricao Municipal.")
            if ent_im:
                ent_im.focus_set()
            return
        if falta_razao and not razao:
            lbl_erro.configure(text="\u26A0 Preencha a Razao Social.")
            if ent_razao:
                ent_razao.focus_set()
            return
        resultado[0] = (im, razao)
        dlg.destroy()

    def cancelar():
        dlg.destroy()

    frame_btns = tk.Frame(card, bg=COR_CARD)
    frame_btns.pack(fill="x", pady=(8, 0))

    btn_conf = criar_botao(frame_btns, "✔  CONFIRMAR", confirmar, COR_SUCESSO, width=16, font_size=10)
    btn_conf.pack(side="right", padx=(8, 0))

    btn_canc = criar_botao(frame_btns, "✖  CANCELAR", cancelar, COR_SUBTEXTO, width=12, font_size=10)
    btn_canc.pack(side="right")

    dlg.bind("<Return>", confirmar)
    dlg.bind("<Escape>", lambda e: cancelar())

    if ent_im:
        ent_im.focus_set()
    elif ent_razao:
        ent_razao.focus_set()

    parent_window.wait_window(dlg)
    return resultado[0]


def abrir_tela_manual_itemlc(parent_window, dados_base: dict, chave_nfse: str,
                              from_n8n: bool = False,
                              empresa_cod: str = "",
                              empresa_razao: str = "") -> str | None:
    """
    Abre diálogo de preenchimento manual de Item LC (e DDD quando aplicável).

    Retorna a linha TXT montada, ou None se o usuário cancelou.
    """
    janela_manual = tk.Toplevel(parent_window)
    janela_manual.title("Preenchimento Manual")
    altura_extra = 40 if (empresa_cod or empresa_razao) else 0
    _qtd_tags = sum(1 for k in ("c_trib_nac", "x_trib_nac", "x_nbs")
                    if (dados_base.get(k) or "").strip())
    if _qtd_tags:
        # Cada tag ocupa ~32px; reserva folga + cabecalho do bloco
        altura_extra += 24 + _qtd_tags * 36
    base_altura = 560 if from_n8n else 520
    janela_manual.geometry(f"540x{base_altura + altura_extra}")
    janela_manual.configure(bg=COR_BG)
    janela_manual.grab_set()
    janela_manual.resizable(False, False)

    resultado = {"linha": None}

    # Header
    hdr = tk.Frame(janela_manual, bg=COR_PRIMARIA, pady=12)
    hdr.pack(fill="x")
    tk.Label(
        hdr,
        text="⚠  Preenchimento Manual",
        font=("Segoe UI", 13, "bold"),
        bg=COR_PRIMARIA, fg="#FFFFFF"
    ).pack()

    nota_label_txt = chave_nfse.replace('.xml', '')
    xml_content = (dados_base.get("_xml_content") or "").strip()

    if xml_content:
        nota_frame = tk.Frame(hdr, bg=COR_PRIMARIA)
        nota_frame.pack()
        tk.Label(
            nota_frame, text="Nota: ",
            font=("Segoe UI", 9), bg=COR_PRIMARIA, fg=COR_DLG_SUB,
        ).pack(side="left")

        def _abrir_xml(_event=None):
            try:
                safe_prefix = "".join(
                    c if c.isalnum() or c in "-_" else "_"
                    for c in nota_label_txt
                )[:40] or "nota"
                fd, tmp_path = tempfile.mkstemp(
                    prefix=f"nota_{safe_prefix}_", suffix=".xml"
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(xml_content)
                webbrowser.open(f"file:///{tmp_path.replace(os.sep, '/')}")
            except OSError:
                pass

        lbl_link = tk.Label(
            nota_frame, text=f"{nota_label_txt}  🔗",
            font=("Segoe UI", 9, "underline"),
            bg=COR_PRIMARIA, fg="#FFFFFF", cursor="hand2",
        )
        lbl_link.pack(side="left")
        lbl_link.bind("<Button-1>", _abrir_xml)
    else:
        tk.Label(
            hdr,
            text=f"Nota: {nota_label_txt}",
            font=("Segoe UI", 9),
            bg=COR_PRIMARIA, fg=COR_DLG_SUB,
        ).pack()

    # Faixa de identificacao da empresa (codigo - razao social)
    if empresa_cod or empresa_razao:
        cod_txt = (empresa_cod or "").strip()
        razao_txt = (empresa_razao or "").strip()
        if cod_txt and razao_txt:
            empresa_label = f"{cod_txt} - {razao_txt}"
        else:
            empresa_label = cod_txt or razao_txt
        faixa = tk.Frame(janela_manual, bg=COR_MUN_BG,
                         highlightbackground=COR_MUN_BORDA, highlightthickness=1)
        faixa.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(
            faixa, text="Empresa", font=("Segoe UI", 8, "bold"),
            bg=COR_MUN_BG, fg=COR_SUBTEXTO, anchor="w",
        ).pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(
            faixa, text=empresa_label, font=("Segoe UI", 12, "bold"),
            bg=COR_MUN_BG, fg=COR_MUN_TEXTO, anchor="w",
            wraplength=500, justify="left",
        ).pack(fill="x", padx=10, pady=(0, 6))

    # Emitente da nota (prestador) — discreto, abaixo da faixa de empresa
    _emit_razao = (dados_base.get("razao_social") or "").strip()
    _emit_cnpj = normalize_digits(dados_base.get("cpf_cnpj") or "")
    if _emit_razao or _emit_cnpj:
        if len(_emit_cnpj) == 14:
            _emit_cnpj_fmt = (
                f"{_emit_cnpj[:2]}.{_emit_cnpj[2:5]}.{_emit_cnpj[5:8]}/"
                f"{_emit_cnpj[8:12]}-{_emit_cnpj[12:]}"
            )
        else:
            _emit_cnpj_fmt = _emit_cnpj
        if _emit_razao and _emit_cnpj_fmt:
            _emit_text = f"Emitente: {_emit_razao} · {_emit_cnpj_fmt}"
        else:
            _emit_text = f"Emitente: {_emit_razao or _emit_cnpj_fmt}"
        tk.Label(
            janela_manual, text=_emit_text, font=("Segoe UI", 8),
            bg=COR_BG, fg=COR_SUBTEXTO, anchor="w", wraplength=500, justify="left",
        ).pack(fill="x", padx=18, pady=(2, 0))

    # Card principal
    card = tk.Frame(janela_manual, bg=COR_CARD, padx=24, pady=16,
                    highlightbackground=COR_BORDA, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=16, pady=12)

    _item_orig = (dados_base.get("item_lc_original") or "").strip()
    if _item_orig in ("-", "—", "–") or _item_orig.startswith("{{"):
        _item_orig = ""
    if from_n8n:
        descricao_item = _item_orig or (dados_base.get("descricao") or "").strip() or "—"
    else:
        descricao_item = (dados_base.get("descricao") or "").strip() or _item_orig or "—"

    def _pesquisar_item_lc(texto: str):
        consulta = f"{texto.strip()} Item LC"
        url = f"https://www.google.com/search?q={urllib.parse.quote(consulta)}"
        webbrowser.open_new_tab(url)

    def _criar_botao_pesquisa(parent, valor: str):
        """Cria um botao pequeno e discreto que pesquisa '{valor} Item LC' no Google."""
        return tk.Button(
            parent, text="🔍",
            font=("Segoe UI", 8), bg=COR_DESC_BG, fg=COR_PRIMARIA,
            activebackground=COR_DESC_BORDA, activeforeground=COR_PRIMARIA,
            relief="flat", cursor="hand2", bd=0, padx=6, pady=0,
            command=lambda v=valor: _pesquisar_item_lc(v),
        )

    tk.Label(card, text="Descrição do serviço extraída da nota:",
             font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_SUBTEXTO,
             anchor="w").pack(fill="x")

    frame_desc = tk.Frame(card, bg=COR_DESC_BG, highlightbackground=COR_DESC_BORDA,
                          highlightthickness=1)
    frame_desc.pack(fill="x", pady=(4, 8))
    tk.Label(frame_desc, text=descricao_item, wraplength=420, justify="left",
             font=("Segoe UI", 9), bg=COR_DESC_BG, fg=COR_TEXTO,
             padx=8, pady=6).pack(side="left", fill="x", expand=True)
    if descricao_item and descricao_item != "—":
        _criar_botao_pesquisa(frame_desc, descricao_item).pack(
            side="right", padx=(0, 6), pady=4, anchor="ne",
        )

    # Tags adicionais do XML (cTribNac, xTribNac, xNBS) — quando houver, ajudam
    # o operador a classificar o Item LC correto.
    _tags_extra = [
        ("cTribNac", (dados_base.get("c_trib_nac") or "").strip()),
        ("xTribNac", (dados_base.get("x_trib_nac") or "").strip()),
        ("xNBS",     (dados_base.get("x_nbs") or "").strip()),
    ]
    _tags_visiveis = [(rotulo, valor) for rotulo, valor in _tags_extra if valor]
    if _tags_visiveis:
        frame_tags = tk.Frame(card, bg=COR_DESC_BG,
                              highlightbackground=COR_DESC_BORDA, highlightthickness=1)
        frame_tags.pack(fill="x", pady=(0, 12))
        for rotulo, valor in _tags_visiveis:
            linha = tk.Frame(frame_tags, bg=COR_DESC_BG)
            linha.pack(fill="x", padx=8, pady=3)
            tk.Label(
                linha, text=f"<{rotulo}>", font=("Consolas", 9, "bold"),
                bg=COR_DESC_BG, fg=COR_PRIMARIA, anchor="nw", width=12,
            ).pack(side="left", anchor="n")
            _criar_botao_pesquisa(linha, valor).pack(
                side="right", anchor="ne", padx=(4, 0),
            )
            tk.Label(
                linha, text=valor, font=("Segoe UI", 9), wraplength=370,
                justify="left", bg=COR_DESC_BG, fg=COR_TEXTO, anchor="w",
            ).pack(side="left", fill="x", expand=True)

    # Resolve município
    municipio_exibir = (dados_base.get("municipio") or "").strip()
    if not municipio_exibir or municipio_exibir.startswith("{{"):
        municipio_exibir = (dados_base.get("cidade") or "").strip()
    if not municipio_exibir:
        _cod_mun = (dados_base.get("codigo_municipio") or "").strip()
        if _cod_mun:
            municipio_exibir = consulta_cidade_ibge(_cod_mun)

    # Link LC 116
    def abrir_link(event):
        webbrowser.open_new("https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp116.htm")

    frame_link = tk.Frame(card, bg=COR_CARD)
    frame_link.pack(fill="x", pady=(0, 12))
    tk.Label(frame_link, text="Consulte a LC 116/2003:",
             font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_SUBTEXTO).pack(side="left")
    lbl_link = tk.Label(frame_link, text="  clique aqui →",
                        font=("Segoe UI", 9, "underline"),
                        fg=COR_PRIMARIA, bg=COR_CARD, cursor="hand2")
    lbl_link.pack(side="left")
    lbl_link.bind("<Button-1>", abrir_link)

    tk.Frame(card, bg=COR_BORDA, height=1).pack(fill="x", pady=8)

    frame_campos = tk.Frame(card, bg=COR_CARD)
    frame_campos.pack(fill="x")

    if municipio_exibir:
        tk.Label(frame_campos, text="Município da nota:",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_SUBTEXTO,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 2))
        frame_mun = tk.Frame(frame_campos, bg=COR_MUN_BG,
                             highlightbackground=COR_MUN_BORDA, highlightthickness=1)
        frame_mun.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        tk.Label(frame_mun, text=municipio_exibir, font=("Segoe UI", 10, "bold"),
                 bg=COR_MUN_BG, fg=COR_MUN_TEXTO, padx=8, pady=5).pack(fill="x")

    if from_n8n:
        frame_campos.columnconfigure(0, weight=1)
        tk.Label(frame_campos, text="Item LC (4 dígitos)",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_TEXTO).grid(
            row=2, column=0, sticky="w", pady=(0, 2))
        frame_item, ent_item = criar_entry(frame_campos, width=16)
        frame_item.grid(row=3, column=0, sticky="ew")
        ent_ddd = None
    else:
        frame_campos.columnconfigure(0, weight=1)
        frame_campos.columnconfigure(1, weight=1)
        tk.Label(frame_campos, text="Item LC (4 dígitos)",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_TEXTO).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 2))
        tk.Label(frame_campos, text="DDD (2 dígitos)",
                 font=("Segoe UI", 9, "bold"), bg=COR_CARD, fg=COR_TEXTO).grid(
            row=0, column=1, sticky="w", pady=(0, 2))
        frame_item, ent_item = criar_entry(frame_campos, width=10)
        frame_item.grid(row=1, column=0, sticky="ew", padx=(0, 8))
        frame_ddd, ent_ddd = criar_entry(frame_campos, width=6)
        frame_ddd.grid(row=1, column=1, sticky="ew")

    ent_item.focus_set()

    lbl_erro = tk.Label(card, text="", font=("Segoe UI", 9),
                        bg=COR_CARD, fg=COR_ERRO_LABEL)
    lbl_erro.pack(pady=(8, 0))

    def confirmar(event=None):
        item_manual = normalize_digits(ent_item.get())[:4]
        if len(item_manual) != 4:
            lbl_erro.configure(text="\u26A0 Item LC deve ter 4 digitos.")
            ent_item.focus_set()
            return
        if from_n8n:
            linha = montar_linha_txt_n8n(dados_base, item_lc=item_manual)
        else:
            ddd_manual = normalize_digits(ent_ddd.get())[:2]
            if len(ddd_manual) != 2:
                lbl_erro.configure(text="\u26A0 DDD deve ter 2 digitos.")
                ent_ddd.focus_set()
                return
            linha = montar_linha_txt(dados_base, ddd=ddd_manual, item_lc=item_manual)
        resultado["linha"] = linha
        janela_manual.destroy()

    btn_conf = criar_botao(card, "✔  CONFIRMAR", confirmar, COR_SUCESSO, width=20)
    btn_conf.pack(pady=16)

    janela_manual.bind("<Return>", confirmar)
    parent_window.wait_window(janela_manual)
    return resultado["linha"]
