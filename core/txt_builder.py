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


def montar_linha_txt(dados, ddd: str, item_lc: str) -> str:
    modelo = "2" if eh_goiania(dados) else "4"
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
    im = sanitizar_campo(dados.get("im_p", "")) if eh_goiania(dados) else ""
    imposto_retido = imposto_retido_norm(dados.get("iss_ret", "2"), dados.get("iss_ret_origem", "abrasf"))
    codigo_mun = dados.get("codigo_municipio", "")
    cidade = sanitizar_campo(dados.get("cidade_override", "") or consulta_cidade_ibge(codigo_mun) or "")
    uf = normalizar_uf(dados.get("uf", ""))
    tributado_no_municipio = "1" if eh_goiania(dados) else "0"
    unidade_economica = "0"
    cep = sanitizar_campo(dados.get("cep", ""))
    endereco = sanitizar_campo(dados.get("endereco", ""))
    numero_end = sanitizar_campo(dados.get("numero_end", ""))
    bairro = sanitizar_campo(dados.get("bairro", ""))

    numero_end, endereco = _sanitizar_numero_end(numero_end, endereco)
    item_lc = normalize_digits(item_lc)
    if item_lc:
        item_lc = item_lc.zfill(4)

    return (
        f"{modelo};{numero};{vlr_trib};{vlr_doc};{aliq};"
        f"{data_emissao};{data_pagamento};{cnpj};{razao};{im};"
        f"{imposto_retido};{cep};{endereco};{numero_end};{bairro};"
        f"{cidade};{uf};{ddd};{tributado_no_municipio};{item_lc};{unidade_economica}"
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

    return (
        f"{modelo};{numero};{vlr_trib};{vlr_doc};{aliq};"
        f"{data_emissao};{data_pagamento};{cnpj};{razao};{im};"
        f"{imposto_retido};{cep};{endereco};{numero_end};{bairro};"
        f"{cidade};{uf};{ddd};{trib_mun};{item_lc};{unidade_econ}"
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
    return (
        f"{im_tomador};{mes};{ano};"
        f"{hora_formatada} {data_formatada}{razao_tomador};"
        f"1;EXPORTACAO DECLARACAO ELETRONICA-ONLINE-NOTA CONTROL"
    )
