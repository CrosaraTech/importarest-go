from pathlib import Path

# ==============================================================================
# PATHS E ENDPOINTS
# ==============================================================================
BASE_DIR = Path(r"G:\Drives compartilhados\FISCAL\autmais\xml\Entradas\NFS-e")
URL_N8N = "https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing"
RELATORIO_CSV = r"G:\Drives compartilhados\FISCAL\autmais\REST\Relatorio.csv"
PLANILHA_EMPRESAS     = Path(r"G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx")
PLANILHA_COL_COD      = 0   # Coluna A (índice 0-based)
PLANILHA_COL_ANALISTA = 3   # Coluna D (índice 0-based)
PLANILHA_COL_IM       = 7   # Coluna H (índice 0-based) — Inscrição Municipal
PLANILHA_COL_RAZAO    = 1   # Coluna B (índice 0-based) — Nome Empresa

# ==============================================================================
# MUNICÍPIOS ACEITOS (serviços tomados)
# ==============================================================================
GOIANIA_IBGE_7 = "5208707"
GOIANIA_IBGE_6 = "520870"
GOIANIA_DDD = "62"

MUNICIPIOS_ACEITOS = {
    "GOIÂNIA":              {"ibge7": "5208707", "ibge6": "520870",  "ddd": "62"},
    "APARECIDA DE GOIÂNIA": {"ibge7": "5201405", "ibge6": "520140",  "ddd": "62"},
    "ANÁPOLIS":             {"ibge7": "5201108", "ibge6": "520110",  "ddd": "62"},
    "BRASÍLIA":             {"ibge7": "5300108", "ibge6": "530010",  "ddd": "61"},
}

IBGE_ACEITOS = set()
for _m in MUNICIPIOS_ACEITOS.values():
    IBGE_ACEITOS.add(_m["ibge7"])
    IBGE_ACEITOS.add(_m["ibge6"])

# ==============================================================================
# IBGE API
# ==============================================================================
IBGE_MUN_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{}"

# ==============================================================================
# PALETA DE CORES
# ==============================================================================
COR_BG          = "#F5F5F5"
COR_CARD        = "#FFFFFF"
COR_PRIMARIA    = "#E58A4E"
COR_PRIMARIA_HV = "#C9703A"
COR_SUCESSO     = "#28A745"
COR_SUCESSO_HV  = "#1E7E34"
COR_TEXTO       = "#2C2C2C"
COR_SUBTEXTO    = "#6C757D"
COR_BORDA       = "#E0E0E0"

# Erro / destrutivo
COR_ERRO        = "#C0392B"
COR_ERRO_HV     = "#A93226"
COR_ERRO_LABEL  = "#DC3545"

# Log
COR_LOG_BG      = "#FAFAFA"
COR_LOG_OK      = "#1B8A1B"
COR_LOG_WARN    = "#B8860B"
COR_LOG_INFO    = "#2471A3"

# Diálogos
COR_DLG_SUB     = "#FFFFFF"
COR_DESC_BG     = "#FFF8F3"
COR_DESC_BORDA  = "#F0C090"
COR_MUN_BG      = "#F0F8FF"
COR_MUN_BORDA   = "#90C0E0"
COR_MUN_TEXTO   = "#1A5276"
