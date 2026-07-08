from datetime import datetime

from core.validators import normalize_digits, eh_goiania, imposto_retido_norm
from core.formatters import formatar_aliquota, sanitizar_campo, normalizar_uf, normalizar_data_fmt
from services.ibge import consulta_cidade_ibge


def _sanitizar_numero_end(numero_end: str, endereco: str):
    """Se numero_end não for numérico (ex: S/N), move para endereço e retorna 0."""
    num = (numero_end or "").strip()
    if not num or not num.replace(" ", "").isdigit():
        if num:
            endereco = f"{endereco} {num}".strip()
        return "0", endereco
    return num[:10], endereco


def montar_linha_txt(dados, ddd: str, item_lc: str, empresa_ibge: str = "") -> str:
    # Modelo: 2 = prestador MESMO municipio da empresa tomadora, 4 = fora.
    # Fallback (empresa_ibge vazio): usa eh_goiania (legado).
    ibge_prest = normalize_digits(dados.get("codigo_municipio", ""))
    ibge_emp = normalize_digits(empresa_ibge or "")
    if ibge_emp:
        # compara pelos 6 primeiros digitos (IBGE 6 = municipio, 7 = com DV)
        mesmo_mun = bool(ibge_prest) and ibge_prest[:6] == ibge_emp[:6]
    else:
        mesmo_mun = eh_goiania(dados)  # legado sem empresa_ibge
    modelo = "2" if mesmo_mun else "4"
    numero = sanitizar_campo(dados.get("numero", ""))
    vlr_doc = sanitizar_campo(dados.get("vlr_doc", ""))
    vlr_trib = sanitizar_campo(dados.get("vlr_trib", ""))
    if not vlr_trib.strip():
        vlr_trib = vlr_doc or "0.00"
    if not vlr_doc.strip():
        vlr_doc = vlr_trib or "0.00"
    aliq = formatar_aliquota(dados.get("aliq_val", "0"))
    dt = normalizar_data_fmt(dados.get("dt_fmt", ""))
    data_emissao = dt
    data_pagamento = dt
    cnpj = sanitizar_campo(dados.get("cnpj_p", ""))
    razao = sanitizar_campo(dados.get("razao_p", ""))
    im = sanitizar_campo(dados.get("im_p", "")) if mesmo_mun else ""
    imposto_retido = imposto_retido_norm(dados.get("iss_ret", "2"), dados.get("iss_ret_origem", "abrasf"))
    codigo_mun = dados.get("codigo_municipio", "")
    # Resolução em cascata da cidade:
    # 1) cidade_override (ViaCEP local ou n8n) — preferido
    # 2) IBGE pelo codigo_municipio (extraído do XML)
    # 3) IBGE pelo local_prestacao (mais confiável que codigo_municipio)
    cidade = sanitizar_campo(
        dados.get("cidade_override", "")
        or consulta_cidade_ibge(codigo_mun)
        or consulta_cidade_ibge(dados.get("local_prestacao", ""))
        or ""
    )
    uf = normalizar_uf(dados.get("uf", ""))
    tributado_no_municipio = "1" if mesmo_mun else "0"
    unidade_economica = "0"
    cep = sanitizar_campo(dados.get("cep", ""))
    endereco = sanitizar_campo(dados.get("endereco", ""))
    numero_end = sanitizar_campo(dados.get("numero_end", ""))
    bairro = sanitizar_campo(dados.get("bairro", ""))

    numero_end, endereco = _sanitizar_numero_end(numero_end, endereco)
    item_lc = normalize_digits(item_lc)
    if item_lc:
        item_lc = item_lc.zfill(4)

    local_prestacao = normalize_digits(dados.get("local_prestacao", ""))
    optante_sn_mei = str(dados.get("optante_sn_mei", "1") or "1")
    if optante_sn_mei not in ("1", "2", "3"):
        optante_sn_mei = "1"

    return (
        f"{modelo};{numero};{vlr_trib};{vlr_doc};{aliq};"
        f"{data_emissao};{data_pagamento};{cnpj};{razao};{im};"
        f"{imposto_retido};{cep};{endereco};{numero_end};{bairro};"
        f"{cidade};{uf};{ddd};{tributado_no_municipio};{item_lc};{unidade_economica};"
        f"{local_prestacao};{optante_sn_mei};"
    )


def montar_linha_txt_n8n(dados, item_lc: str) -> str:
    """Monta linha de saída usando campos no formato dados_extraidos (n8n)."""
    modelo         = str(dados.get("modelo", "2") or "2")
    numero         = sanitizar_campo(dados.get("numero_documento", ""))
    vlr_doc        = sanitizar_campo(dados.get("valor_documento", ""))
    vlr_trib       = sanitizar_campo(dados.get("valor_tributavel", ""))
    if not vlr_trib.strip():
        vlr_trib = vlr_doc or "0.00"
    aliq           = formatar_aliquota(str(dados.get("aliquota", "0") or "0"))
    data_emissao   = normalizar_data_fmt(dados.get("data_emissao", ""))
    data_pagamento = normalizar_data_fmt(dados.get("data_pagamento", "")) or data_emissao
    cnpj           = sanitizar_campo(dados.get("cpf_cnpj", ""))
    razao          = sanitizar_campo(dados.get("razao_social", ""))
    im             = sanitizar_campo(dados.get("inscricao_municipal", "")) if modelo == "2" else ""
    imposto_retido = imposto_retido_norm(str(dados.get("imposto_retido", "2") or "2"), dados.get("iss_ret_origem", "abrasf"))
    cep            = sanitizar_campo(dados.get("cep", ""))
    endereco       = sanitizar_campo(dados.get("endereco", ""))
    numero_end     = sanitizar_campo(dados.get("numero", ""))
    bairro         = sanitizar_campo(dados.get("bairro", ""))
    cidade         = sanitizar_campo(dados.get("cidade", ""))
    uf             = normalizar_uf(dados.get("estado", ""))
    ddd            = normalize_digits(str(dados.get("ddd", "") or ""))[:2]
    trib_mun       = str(dados.get("tributado_municipio", "0") or "0")
    trib_mun       = "1" if trib_mun.strip() == "1" else "0"
    unidade_econ   = str(dados.get("unidade_economica", "0") or "0")

    numero_end, endereco = _sanitizar_numero_end(numero_end, endereco)
    item_lc = normalize_digits(item_lc)
    if item_lc:
        item_lc = item_lc.zfill(4)

    local_prestacao = normalize_digits(dados.get("local_prestacao", ""))
    optante_sn_mei = str(dados.get("optante_sn_mei", "1") or "1")
    if optante_sn_mei not in ("1", "2", "3"):
        optante_sn_mei = "1"

    return (
        f"{modelo};{numero};{vlr_trib};{vlr_doc};{aliq};"
        f"{data_emissao};{data_pagamento};{cnpj};{razao};{im};"
        f"{imposto_retido};{cep};{endereco};{numero_end};{bairro};"
        f"{cidade};{uf};{ddd};{trib_mun};{item_lc};{unidade_econ};"
        f"{local_prestacao};{optante_sn_mei};"
    )


def montar_cabecalho(im_tomador: str, razao_tomador: str, data_emissao: str) -> str:
    mes = ano = ""
    try:
        dt_obj = datetime.strptime(data_emissao.split("T")[0], "%Y-%m-%d")
        mes = dt_obj.strftime("%m")
        ano = dt_obj.strftime("%Y")
    except (ValueError, IndexError):
        pass
    agora = datetime.now()
    data_formatada = f"{agora.day}/{agora.month}/{agora.year}"
    hora_formatada = agora.strftime("%H:%M")

    # ISSNet rejeita IM com pontuação (ex: "304.415-7"). Tira tudo que não é dígito.
    im_clean = normalize_digits(im_tomador)
    # Razão social pode ter espaços duplos vindos da planilha; normaliza pra um.
    razao_clean = " ".join((razao_tomador or "").split())

    return (
        f"{im_clean};{mes};{ano};"
        f"{hora_formatada} {data_formatada}{razao_clean};"
        f"1;EXPORTACAO DECLARACAO ELETRONICA-ONLINE-NOTA CONTROL"
    )
