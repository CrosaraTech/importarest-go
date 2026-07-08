"""core/dmste_builder.py — Monta linhas do CSV de importação DMST-e.

Layout das colunas (separador `;`):
    CPF/CNPJ | ITEM DE SERVICO | REGIME TRIBUTARIO | DATA DE COMPETENCIA
    | NUMERO NFSe | VALOR DA NOTA | DEDUCAO | ALIQUOTA | LINK DA NOTA
    | CODIGO DE VERIFICACAO | ISS RETIDO | MUNICIPIO
"""
from __future__ import annotations

import csv
from pathlib import Path

from core.validators import normalize_digits, imposto_retido_norm


COLUNAS_DMSTE = [
    "CPF/CNPJ", "ITEM DE SERVICO", "REGIME TRIBUTARIO", "DATA DE COMPETENCIA",
    "NUMERO NFSe", "VALOR DA NOTA", "DEDUCAO", "ALIQUOTA", "LINK DA NOTA",
    "CODIGO DE VERIFICACAO", "ISS RETIDO", "MUNICIPIO",
]

_URL_NACIONAL = "https://www.nfse.gov.br/EmissorNacional/Consulta?chave={}"

# Mapa nome do município (uppercase, sem acento) → código IBGE 7 dígitos.
# Adicione novas cidades aqui quando expandir a lista.
IBGE_POR_NOME = {
    "VIANOPOLIS": "5222005",
    "CRIXAS":     "5206404",  # confirmado via IBGE oficial
    "JUSSARA":    "5212204",  # confirmado via IBGE oficial
    # Trindade não usa MegaSoft — declaração via outro portal.
}

_ALIQUOTA_DEFAULT_QUANDO_ZERO = "5,00"   # Portal exige 2–5%; usamos 5% como padrão

# Tabela oficial de alíquotas por município/item.
# Só preciso listar as EXCEÇÕES (itens cuja alíquota difere do default 5,0000).
# Fonte: PDF "Lista de Serviços" emitido pelo portal NFS-e MegaSoft do município.
ALIQUOTAS_OVERRIDE: dict[str, dict[str, str]] = {
    # Crixás - GO (IBGE 5206404)
    "5206404": {
        # 01 - TI / Software (todos 3%)
        "01.01.01": "3,00", "01.02.01": "3,00",
        "01.03.01": "3,00", "01.03.02": "3,00",
        "01.04.01": "3,00", "01.05.01": "3,00",
        "01.06.01": "3,00", "01.07.01": "3,00",
        "01.08.01": "3,00", "01.09.01": "3,00",
        "01.09.02": "3,00",
        # 02 - Pesquisa
        "02.01.01": "3,00",
        # 03 - Locações específicas
        "03.03.02": "3,00", "03.03.03": "3,00",
        "03.03.04": "3,00", "03.03.05": "3,00",
        "03.04.02": "3,00", "03.04.03": "3,00",
        # 04 - Saúde
        "04.01.01": "3,00", "04.01.02": "3,00",
        "04.02.01": "3,00", "04.02.02": "3,00",
        "04.02.03": "3,00", "04.02.04": "3,00",
        "04.02.05": "3,00",
        "04.03.01": "3,00", "04.03.02": "3,00",
        "04.03.03": "3,00",
        "04.04.01": "3,00", "04.05.01": "3,00",
        "04.06.01": "3,00",
        "04.07.01": "2,00",                       # Farmacêuticos
        "04.08.01": "3,00", "04.08.02": "3,00",
        "04.08.03": "3,00",
        "04.09.01": "3,00", "04.10.01": "3,00",
        "04.11.01": "3,00", "04.12.01": "3,00",
        "04.13.01": "3,00", "04.14.01": "3,00",
        "04.15.01": "3,00", "04.16.01": "3,00",
        "04.17.01": "3,00", "04.17.02": "3,00",
        "04.17.03": "3,00", "04.17.04": "3,00",
        "04.18.01": "3,00", "04.19.01": "3,00",
        "04.20.01": "3,00", "04.21.01": "3,00",
        "04.22.01": "3,00", "04.23.01": "3,00",
        # 05 - Veterinária (tudo 3%)
        "05.01.01": "3,00", "05.01.02": "3,00",
        "05.02.01": "3,00", "05.02.02": "3,00",
        "05.03.01": "3,00", "05.04.01": "3,00",
        "05.05.01": "3,00", "05.06.01": "3,00",
        "05.07.01": "3,00", "05.08.01": "3,00",
        "05.09.01": "3,00",
        # 08 - Ensino
        "08.01.01": "2,00",                       # Ensino regular pré/fund/médio
        "08.01.02": "3,00",                       # Superior
        "08.02.01": "2,00",                       # Instrução/treinamento
        # 09 - Hospedagem
        "09.01.02": "3,00", "09.01.03": "3,00",
        "09.01.04": "3,00", "09.02.02": "3,00",
        # 10 - Agenciamento/Corretagem
        "10.01.02": "3,00", "10.01.03": "3,00",
        "10.01.04": "3,00", "10.01.05": "3,00",
        "10.02.02": "3,00", "10.05.02": "3,00",
        "10.09.01": "3,00",
        # 14 - Manutenção
        "14.13.02": "3,00",                       # Serralheria
        "14.14.02": "3,00", "14.14.03": "3,00",
        "14.14.04": "3,00",
        # 17 - Apoio / Consultoria
        "17.01.02": "3,00",
        "17.02.02": "3,00", "17.02.03": "3,00",
        "17.02.04": "3,00", "17.02.05": "3,00",
        "17.03.02": "3,00", "17.03.03": "3,00",
        "17.11.02": "3,00",                       # Bufê
        "17.14.01": "0,00",                       # Advocacia
        # 19 - Loteria
        "19.01.01": "3,00",
        # 23 / 24
        "23.01.02": "3,00", "24.01.02": "3,00",
        # 27 - Assistência social
        "27.01.01": "3,00",
        # 30 - Química
        "30.01.02": "3,00",
        # 31 - Técnicos
        "31.01.02": "3,00", "31.01.03": "3,00",
        "31.01.04": "3,00",
        # 35 - Reportagem / Jornalismo
        "35.01.01": "3,00", "35.01.02": "3,00",
        "35.01.03": "3,00",
        # 99 - Sem incidência
        "99.01.01": "0,00",
    },
    # ===================================================================
    # Vianópolis - GO (IBGE 5222005)
    # Fonte: PDF "Lista de Serviços - Município de Vianópolis"
    # Default municipal: 5,00. Listamos só exceções.
    # ===================================================================
    "5222005": {
        # 01 - TI / Software (3%)
        "01.01.01": "3,00", "01.02.01": "3,00",
        "01.03.01": "3,00", "01.03.02": "3,00",
        "01.04.01": "3,00", "01.05.01": "3,00",
        "01.06.01": "3,00", "01.07.01": "3,00",
        "01.08.01": "3,00", "01.09.01": "3,00",
        "01.09.02": "3,00",
        # 04 - Saúde humana (3%, todos)
        "04.01.01": "3,00", "04.01.02": "3,00",
        "04.02.01": "3,00", "04.02.02": "3,00",
        "04.02.03": "3,00", "04.02.04": "3,00",
        "04.02.05": "3,00",
        "04.03.01": "3,00", "04.03.02": "3,00", "04.03.03": "3,00",
        "04.04.01": "3,00", "04.05.01": "3,00", "04.06.01": "3,00",
        "04.07.01": "3,00",
        "04.08.01": "3,00", "04.08.02": "3,00", "04.08.03": "3,00",
        "04.09.01": "3,00", "04.10.01": "3,00",
        "04.11.01": "3,00", "04.12.01": "3,00",
        "04.13.01": "3,00", "04.14.01": "3,00",
        "04.15.01": "3,00", "04.16.01": "3,00",
        "04.17.01": "3,00", "04.17.02": "3,00",
        "04.17.03": "3,00", "04.17.04": "3,00",
        "04.18.01": "3,00", "04.19.01": "3,00",
        "04.20.01": "3,00", "04.21.01": "3,00",
        "04.22.01": "3,00", "04.23.01": "3,00",
        # 05 - Veterinária (3%, todos)
        "05.01.01": "3,00", "05.01.02": "3,00",
        "05.02.01": "3,00", "05.02.02": "3,00",
        "05.03.01": "3,00", "05.04.01": "3,00",
        "05.05.01": "3,00", "05.06.01": "3,00",
        "05.07.01": "3,00", "05.08.01": "3,00",
        "05.09.01": "3,00",
        # 06 - Beleza/estética (3%)
        "06.01.01": "3,00", "06.02.01": "3,00",
        "06.03.01": "3,00", "06.04.01": "3,00",
        "06.05.01": "3,00", "06.06.01": "3,00",
        # 08 - Ensino (3%)
        "08.01.01": "3,00", "08.01.02": "3,00", "08.02.01": "3,00",
        # 09 - Hospedagem/turismo (4%)
        "09.01.01": "4,00", "09.01.02": "4,00",
        "09.01.03": "4,00", "09.01.04": "4,00",
        "09.02.01": "4,00", "09.02.02": "4,00",
        "09.03.01": "4,00",
        # 12 - Espetáculos/diversões (4%, todos)
        "12.01.01": "4,00", "12.02.01": "4,00", "12.03.01": "4,00",
        "12.04.01": "4,00", "12.05.01": "4,00", "12.06.01": "4,00",
        "12.07.01": "4,00", "12.08.01": "4,00",
        "12.09.01": "4,00", "12.09.02": "4,00", "12.09.03": "4,00",
        "12.10.01": "4,00", "12.11.01": "4,00", "12.12.01": "4,00",
        "12.13.01": "4,00", "12.14.01": "4,00",
        "12.15.01": "4,00", "12.16.01": "4,00", "12.17.01": "4,00",
        # 13 - Fonografia/gráfica (3%)
        "13.02.01": "3,00", "13.03.01": "3,00",
        "13.04.01": "3,00", "13.05.01": "3,00",
        # 14 - Manutenção/serviços (4%) + construção civil (3%)
        "14.01.01": "4,00", "14.02.01": "4,00", "14.03.01": "4,00",
        "14.04.01": "4,00", "14.05.01": "4,00", "14.06.01": "4,00",
        "14.07.01": "4,00", "14.08.01": "4,00", "14.09.01": "4,00",
        "14.10.01": "4,00", "14.11.01": "4,00", "14.12.01": "4,00",
        "14.13.01": "4,00", "14.13.02": "4,00",
        "14.14.01": "4,00", "14.14.02": "4,00",
        "14.14.03": "3,00", "14.14.04": "3,00",
        # 17 - Apoio/consultoria/auditoria (3%, quase todos exceto 17.10.02)
        "17.01.01": "3,00", "17.01.02": "3,00",
        "17.02.01": "3,00", "17.02.02": "3,00", "17.02.03": "3,00",
        "17.02.04": "3,00", "17.02.05": "3,00",
        "17.03.01": "3,00", "17.03.02": "3,00", "17.03.03": "3,00",
        "17.04.01": "3,00", "17.05.01": "3,00",
        "17.06.01": "3,00", "17.08.01": "3,00",
        "17.09.01": "3,00", "17.10.01": "3,00",
        "17.11.01": "3,00", "17.11.02": "3,00",
        "17.12.01": "3,00", "17.13.01": "3,00",
        "17.14.01": "3,00", "17.15.01": "3,00",
        "17.16.01": "3,00", "17.17.01": "3,00",
        "17.18.01": "3,00", "17.19.01": "3,00",
        "17.20.01": "3,00", "17.21.01": "3,00",
        "17.22.01": "3,00", "17.23.01": "3,00",
        "17.24.01": "3,00", "17.25.01": "3,00",
        # 18 - Seguros (3%)
        "18.01.01": "3,00", "18.01.02": "3,00", "18.01.03": "3,00",
        # 23 / 24 - Programação visual / chaveiros / placas (3%)
        "23.01.01": "3,00", "23.01.02": "3,00",
        "24.01.01": "3,00", "24.01.02": "3,00",
        # 25 - Funerais/cemitérios (3%)
        "25.01.01": "3,00",
        "25.02.01": "3,00", "25.02.02": "3,00",
        "25.03.01": "3,00", "25.04.01": "3,00", "25.05.01": "3,00",
        # 27 a 31 (3%, quase todos)
        "27.01.01": "3,00",
        "29.01.01": "3,00",
        "30.01.01": "3,00", "30.01.02": "3,00",
        "31.01.01": "3,00", "31.01.02": "3,00",
        "31.01.03": "3,00", "31.01.04": "3,00",
        # 33 a 40 (3%, todos)
        "33.01.01": "3,00", "34.01.01": "3,00",
        "35.01.01": "3,00", "35.01.02": "3,00", "35.01.03": "3,00",
        "36.01.01": "3,00", "37.01.01": "3,00",
        "38.01.01": "3,00", "39.01.01": "3,00",
        "40.01.01": "3,00",
        # 99 - Sem incidência
        "99.01.01": "3,00",
    },
    # ===================================================================
    # Jussara - GO (IBGE 5212204)
    # Fonte: PDF "Lista de Serviços - Poder Executivo de Jussara"
    # Default municipal: 5,00. Listamos só exceções.
    # ===================================================================
    "5212204": {
        # 01 - TI / Software (3%)
        "01.01.01": "3,00", "01.02.01": "3,00",
        "01.03.01": "3,00", "01.03.02": "3,00",
        "01.04.01": "3,00", "01.05.01": "3,00",
        "01.06.01": "3,00", "01.07.01": "3,00",
        "01.08.01": "3,00", "01.09.01": "3,00",
        "01.09.02": "3,00",
        # 02 - Pesquisa
        "02.01.01": "3,00",
        # 03 - Locações (3%, todas em Jussara)
        "03.02.01": "3,00",
        "03.03.01": "3,00", "03.03.02": "3,00",
        "03.03.03": "3,00", "03.03.04": "3,00",
        "03.03.05": "3,00",
        "03.04.01": "3,00", "03.04.02": "3,00",
        "03.04.03": "3,00",
        "03.05.01": "3,00",
        # 04 - Saúde humana (3%; 04.22/04.23 ficam no default 5%)
        "04.01.01": "3,00", "04.01.02": "3,00",
        "04.02.01": "3,00", "04.02.02": "3,00",
        "04.02.03": "3,00", "04.02.04": "3,00",
        "04.02.05": "3,00",
        "04.03.01": "3,00", "04.03.02": "3,00", "04.03.03": "3,00",
        "04.04.01": "3,00", "04.05.01": "3,00", "04.06.01": "3,00",
        "04.07.01": "3,00",
        "04.08.01": "3,00", "04.08.02": "3,00", "04.08.03": "3,00",
        "04.09.01": "3,00", "04.10.01": "3,00",
        "04.11.01": "3,00", "04.12.01": "3,00",
        "04.13.01": "3,00", "04.14.01": "3,00",
        "04.15.01": "3,00", "04.16.01": "3,00",
        "04.17.01": "3,00", "04.17.02": "3,00",
        "04.17.03": "3,00", "04.17.04": "3,00",
        "04.18.01": "3,00", "04.19.01": "3,00",
        "04.20.01": "3,00", "04.21.01": "3,00",
        # 05 - Veterinária (3%; 05.02.01 e 05.09.01 ficam no default 5%)
        "05.01.01": "3,00", "05.01.02": "3,00",
        "05.02.02": "3,00",
        "05.03.01": "3,00", "05.04.01": "3,00",
        "05.05.01": "3,00", "05.06.01": "3,00",
        "05.07.01": "3,00", "05.08.01": "3,00",
        # 06 - Beleza/estética (3%)
        "06.01.01": "3,00", "06.02.01": "3,00",
        "06.03.01": "3,00", "06.04.01": "3,00",
        "06.05.01": "3,00", "06.06.01": "3,00",
        # 07 - Engenharia (apenas 07.01.01 cai pra 3%, resto fica 5%)
        "07.01.01": "3,00",
        # 08 - Ensino (3%)
        "08.01.01": "3,00", "08.01.02": "3,00", "08.02.01": "3,00",
        # 09 - Hospedagem (3% em Jussara, diferente de Vianópolis)
        "09.01.01": "3,00", "09.01.02": "3,00",
        "09.01.03": "3,00", "09.01.04": "3,00",
        "09.02.01": "3,00", "09.02.02": "3,00",
        "09.03.01": "3,00",
        # 10 - Agenciamento (3% apenas em alguns; 10.09.01 é 2,5%)
        "10.01.02": "3,00", "10.01.03": "3,00",
        "10.01.04": "3,00", "10.01.05": "3,00",
        "10.02.02": "3,00", "10.05.02": "3,00",
        "10.09.01": "2,50",
        # 12 - Espetáculos (3%; 12.09.02 e 12.09.03 ficam no default 5%)
        "12.01.01": "3,00", "12.02.01": "3,00", "12.03.01": "3,00",
        "12.04.01": "3,00", "12.05.01": "3,00", "12.06.01": "3,00",
        "12.07.01": "3,00", "12.08.01": "3,00",
        "12.09.01": "3,00",
        "12.10.01": "3,00", "12.11.01": "3,00", "12.12.01": "3,00",
        "12.13.01": "3,00", "12.14.01": "3,00",
        "12.15.01": "3,00", "12.16.01": "3,00", "12.17.01": "3,00",
        # 13 - Fonografia/gráfica (3%)
        "13.02.01": "3,00", "13.03.01": "3,00",
        "13.04.01": "3,00", "13.05.01": "3,00",
        # 14 - Manutenção (3% em Jussara, todos)
        "14.01.01": "3,00", "14.02.01": "3,00", "14.03.01": "3,00",
        "14.04.01": "3,00", "14.05.01": "3,00", "14.06.01": "3,00",
        "14.07.01": "3,00", "14.08.01": "3,00", "14.09.01": "3,00",
        "14.10.01": "3,00", "14.11.01": "3,00", "14.12.01": "3,00",
        "14.13.01": "3,00", "14.13.02": "3,00",
        "14.14.01": "3,00", "14.14.02": "3,00",
        "14.14.03": "3,00", "14.14.04": "3,00",
        # 16 - Transporte coletivo (2,5%)
        "16.01.01": "2,50",
        "16.02.01": "2,50",
        # 17 - Apoio/consultoria (3%, quase todos; 17.04, 17.05, 17.10.02 ficam 5%)
        "17.01.01": "3,00", "17.01.02": "3,00",
        "17.02.01": "3,00", "17.02.02": "3,00", "17.02.03": "3,00",
        "17.02.04": "3,00", "17.02.05": "3,00",
        "17.03.01": "3,00", "17.03.02": "3,00", "17.03.03": "3,00",
        "17.06.01": "3,00", "17.08.01": "3,00",
        "17.09.01": "3,00",
        "17.10.01": "3,00",
        "17.11.01": "3,00", "17.11.02": "3,00",
        "17.12.01": "3,00", "17.13.01": "3,00",
        "17.14.01": "3,00", "17.15.01": "3,00",
        "17.16.01": "3,00", "17.17.01": "3,00",
        "17.18.01": "3,00", "17.19.01": "3,00",
        "17.20.01": "3,00", "17.21.01": "3,00",
        "17.22.01": "3,00", "17.23.01": "3,00",
        "17.24.01": "3,00", "17.25.01": "3,00",
        # 20 - Terminais (3%; 20.01.02 fica em LP/default)
        "20.01.01": "3,00",
        "20.02.01": "3,00", "20.03.01": "3,00",
        # 23 / 24 (3%)
        "23.01.01": "3,00", "23.01.02": "3,00",
        "24.01.01": "3,00", "24.01.02": "3,00",
        # 26 - Correios (apenas 26.01.01 fica 3%)
        "26.01.01": "3,00",
        # 27 a 32 (3%)
        "27.01.01": "3,00",
        "28.01.01": "3,00",
        "29.01.01": "3,00",
        "30.01.01": "3,00", "30.01.02": "3,00",
        "31.01.01": "3,00", "31.01.02": "3,00",
        "31.01.03": "3,00", "31.01.04": "3,00",
        "32.01.01": "3,00",
        # 33 a 40 (3%, todos)
        "33.01.01": "3,00", "34.01.01": "3,00",
        "35.01.01": "3,00", "35.01.02": "3,00", "35.01.03": "3,00",
        "36.01.01": "3,00", "37.01.01": "3,00",
        "38.01.01": "3,00", "39.01.01": "3,00",
        "40.01.01": "3,00",
        # 99 - Sem incidência
        "99.01.01": "3,00",
    },
}


def _aliquota_item_municipio(item_servico: str, ibge: str) -> str:
    """Retorna a alíquota cadastrada para o item LC no município.

    - Município COM tabela carregada → usa override; se o item não está listado,
      assume default do município (5,0000). Nunca cai pro XML do prestador,
      porque DMST-e é o tomador pagando conforme a tabela municipal.
    - Município SEM tabela (dict vazio) → retorna '' (chamador cai pro XML).
    """
    if not ibge:
        return ""
    tabela = ALIQUOTAS_OVERRIDE.get(ibge)
    if not tabela:
        return ""
    return tabela.get(item_servico, _ALIQUOTA_DEFAULT_QUANDO_ZERO)

_MAX_NUMERO_NFSE = 9   # Portal rejeita NUMERO NFSe com mais de 9 chars


def _formatar_valor_brl(v: str) -> str:
    """Converte número decimal para o formato pt-BR (vírgula como separador).

    XML usa ponto: '17.80', '1500.00'. Portal DMST-e é brasileiro e interpreta
    ponto como separador de milhar. Sem essa conversão, '17.80' vira '1.780,00'.
    """
    s = str(v or "").strip()
    if not s:
        return ""
    return s.replace(".", ",")


def _formatar_data_competencia(dt_fmt: str) -> str:
    """Portal DMST-e usa 'DD/MM/AAAA' (data completa de emissão).

    'ddmmaaaa' → 'DD/MM/AAAA'
    '02052026' → '02/05/2026'
    """
    d = (dt_fmt or "").strip()
    if len(d) == 8 and d.isdigit():
        return f"{d[:2]}/{d[2:4]}/{d[4:]}"
    return d


def _formatar_item_servico(dados: dict) -> str:
    """Devolve o código do serviço no formato 'XX.XX.XX' (3 níveis).

    O portal DMST-e espera LC 116 com item.subitem.subsubitem:
        '010501' → '01.05.01'
        '172401' → '17.24.01'

    Preferência: cTribNac (6 dígitos). Fallback: item LC 116 (4 dígitos
    com '.00' acrescentado no fim).
    """
    c_trib_nac = normalize_digits(dados.get("c_trib_nac", ""))
    if len(c_trib_nac) >= 6:
        d = c_trib_nac[:6]
        return f"{d[:2]}.{d[2:4]}.{d[4:6]}"
    if c_trib_nac:
        d = c_trib_nac.zfill(6)
        return f"{d[:2]}.{d[2:4]}.{d[4:6]}"
    # Fallback: LC 116 com sub-subitem '00'
    digitos = normalize_digits(dados.get("item_lc_final", ""))[:4]
    if len(digitos) < 4:
        return ""
    return f"{digitos[:2]}.{digitos[2:4]}.00"


def _formatar_aliquota(aliq: str) -> str:
    """Formata alíquota com 2 casas decimais e vírgula: '2' → '2,00'.

    Quando XML traz 0 ou vazio, usa o default (5,00) — portal DMST-e
    exige valor entre 2% e 5% quando ISS é retido.
    """
    v = (aliq or "").strip().replace("%", "").replace(",", ".").strip()
    if not v:
        return _ALIQUOTA_DEFAULT_QUANDO_ZERO
    try:
        num = float(v)
    except ValueError:
        return _ALIQUOTA_DEFAULT_QUANDO_ZERO
    if num <= 0:
        return _ALIQUOTA_DEFAULT_QUANDO_ZERO
    return f"{num:.2f}".replace(".", ",")


def _formatar_regime_tributario(optante_sn_mei: str) -> str:
    """Portal DMST-e aceita apenas '1' (Normal) ou '2' (Simples Nacional).

    MEI ('3') é tratado como Simples Nacional ('2') para fins de DMST-e.
    """
    v = str(optante_sn_mei or "").strip()
    if v == "3":   # MEI → SN nesse portal
        return "2"
    if v in ("1", "2"):
        return v
    return "1"   # Default conservador (Não Optante / Normal)


def _truncar_numero(numero: str, numero_dps: str) -> str:
    """Limita NUMERO NFSe a 9 caracteres.

    Estratégia:
    1. Se `numero` <= 9 chars → usa direto
    2. Senão, tenta `numero_dps` (sequencial real do NFS-e Nacional)
    3. Como último recurso, pega os últimos 9 dígitos
    """
    n = str(numero or "").strip()
    if len(n) <= _MAX_NUMERO_NFSE:
        return n
    dps = str(numero_dps or "").strip()
    if dps and len(dps) <= _MAX_NUMERO_NFSE:
        return dps
    # Fallback: últimos 9 dígitos (pior caso, pode causar colisão)
    return normalize_digits(n)[-_MAX_NUMERO_NFSE:]


def _ibge_municipio(nome_municipio: str) -> str:
    """Retorna código IBGE do município. Se desconhecido, devolve o nome
    original como fallback (portal vai rejeitar e operador identifica)."""
    chave = (nome_municipio or "").strip().upper()
    return IBGE_POR_NOME.get(chave, nome_municipio or "")


def _link_nota(dados: dict) -> str:
    """Monta o link de consulta da nota no portal nacional NFS-e (SPED)."""
    chave = (dados.get("chave_nfse_id") or "").strip()
    if not chave:
        return ""
    return _URL_NACIONAL.format(chave)


def build_dmste_row(dados: dict, municipio_empresa: str) -> dict[str, str]:
    """Constrói uma linha do CSV DMST-e a partir do dict `dados` do extractor.

    Args:
        dados: dict produzido por `extrair_dados_python`.
        municipio_empresa: nome do município da empresa tomadora (do cadastro).

    Returns:
        dict com chaves = COLUNAS_DMSTE e valores prontos pra escrita.
    """
    # ISS retido: respeita a convenção do padrão de NFS-e (ABRASF/Nacional).
    # ABRASF: <IssRetido> 1=retido, 2=não retido
    # Nacional: <tpRetISSQN> 1=não retido, 2=retido tomador, 3=retido intermediário
    iss_ret = imposto_retido_norm(
        dados.get("iss_ret", ""),
        dados.get("iss_ret_origem", "abrasf"),
    )
    item_servico = _formatar_item_servico(dados)
    ibge_tomador = _ibge_municipio(municipio_empresa)
    optante_str = str(dados.get("optante_sn_mei", "1") or "1")

    # MUNICIPIO (local do imposto) no DMST-e:
    # - ISS retido pelo tomador → município do tomador (declarante)
    # - ISS não retido → município do prestador (onde ele paga o ISS direto)
    ibge_prestador = normalize_digits(dados.get("codigo_municipio", ""))
    if iss_ret == "1":
        municipio_csv = ibge_tomador
    else:
        municipio_csv = ibge_prestador or ibge_tomador  # fallback

    # Alíquota:
    # - Prestador Simples Nacional / MEI → usa alíquota do XML (já é a do SN)
    # - Prestador não optante (regime normal) → usa SEMPRE a tabela do município
    #   declarante (Vianópolis / Crixás / Jussara conforme a empresa tomadora),
    #   porque é onde a DMST-e está sendo entregue e o portal valida contra a
    #   tabela do município declarante.
    if optante_str in ("2", "3"):
        aliquota = _formatar_aliquota(dados.get("aliq_val", ""))
    else:
        aliquota = _aliquota_item_municipio(item_servico, ibge_tomador) \
            or _formatar_aliquota(dados.get("aliq_val", ""))

    # Se a alíquota cadastrada é 0% (item isento como advocacia 17.14.01),
    # força ISS RETIDO = 0 e mantém a alíquota — sem isso o portal valida
    # "alíquota deve estar entre 2% e 5%" e rejeita.
    if aliquota.replace(",", ".").strip() in ("0", "0.00", "0.0000", "0.000"):
        iss_ret = "0"

    return {
        "CPF/CNPJ":              normalize_digits(dados.get("cnpj_p", "")),
        "ITEM DE SERVICO":       item_servico,
        "REGIME TRIBUTARIO":     _formatar_regime_tributario(dados.get("optante_sn_mei", "1")),
        "DATA DE COMPETENCIA":   _formatar_data_competencia(dados.get("dt_fmt", "")),
        "NUMERO NFSe":           _truncar_numero(
                                      dados.get("numero", ""),
                                      dados.get("numero_dps", "")),
        "VALOR DA NOTA":         _formatar_valor_brl(dados.get("vlr_doc", "")),
        "DEDUCAO":               _formatar_valor_brl(dados.get("valor_deducoes", "0.00") or "0.00"),
        "ALIQUOTA":              aliquota,
        "LINK DA NOTA":          _link_nota(dados),
        "CODIGO DE VERIFICACAO": str(dados.get("chave_nfse", "")).strip(),
        "ISS RETIDO":            iss_ret,
        "MUNICIPIO":             municipio_csv,
    }


def escrever_csv_dmste(linhas: list[dict[str, str]], destino: Path) -> None:
    """Escreve as linhas no CSV com cabeçalho `COLUNAS_DMSTE` (`;` delimitador)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=COLUNAS_DMSTE, delimiter=";",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for linha in linhas:
            writer.writerow(linha)
