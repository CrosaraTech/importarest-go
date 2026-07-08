"""core/txt_validator.py — Deteccao de campos obrigatorios faltantes em linhas TXT.

Linhas TXT seguem o layout de 23 campos separados por ';' montado em
core/txt_builder.py (21 originais + local_prestacao + optante_sn_mei).
Aqui marcamos quais delas perderam algum campo critico para o sistema
de importacao.
"""

# Ordem dos campos conforme montar_linha_txt / montar_linha_txt_n8n
TXT_FIELD_NAMES = [
    "modelo", "numero", "vlr_trib", "vlr_doc", "aliq",
    "data_emissao", "data_pagamento", "cnpj", "razao", "im",
    "imposto_retido", "cep", "endereco", "numero_end", "bairro",
    "cidade", "uf", "ddd", "tributado_no_municipio", "item_lc",
    "unidade_economica", "local_prestacao", "optante_sn_mei",
]

# Campos cuja ausencia caracteriza linha incompleta para o relatorio.
# 'im' e 'tributado_no_municipio' sao opcionais por modelo;
# 'numero_end' tem fallback "0"; 'imposto_retido' e 'unidade_economica'
# sempre tem valor padrao -> nao listamos.
TXT_REQUIRED_FIELDS = [
    "numero", "vlr_doc", "data_emissao", "cnpj", "razao",
    "cep", "endereco", "bairro", "cidade", "uf", "ddd", "item_lc",
    "local_prestacao", "optante_sn_mei",
]


def detectar_campos_faltantes(linha: str) -> list[str]:
    """Retorna a lista de nomes de campos obrigatorios faltantes na linha.

    Linha com menos de 23 campos retorna ['LINHA_INCOMPLETA'].
    Linhas terminam em ';', então parts pode ter 24 elementos (último vazio).
    """
    partes = linha.split(";")
    # Tolerar trailing ';' descartando o último elemento vazio.
    while partes and partes[-1] == "":
        partes.pop()
    if len(partes) < len(TXT_FIELD_NAMES):
        return ["LINHA_INCOMPLETA"]
    faltantes = []
    for nome in TXT_REQUIRED_FIELDS:
        idx = TXT_FIELD_NAMES.index(nome)
        if not partes[idx].strip():
            faltantes.append(nome)
    return faltantes
