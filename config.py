from pathlib import Path

# ==============================================================================
# VERSAO E AUTO-UPDATE
# ==============================================================================
__version__ = "1.14"
GITHUB_REPO = "CrosaraTech/importarest-go"
INSTALL_DIR = r"C:\ImportaREST"

# ==============================================================================
# PATHS E ENDPOINTS
# ==============================================================================
# BASE_DIR mantido por compatibilidade — fluxo principal hoje busca via API Autmais.
BASE_DIR = Path(r"G:\Drives compartilhados\FISCAL\autmais\xml\Entradas\NFS-e")
URL_N8N = "https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing"
RELATORIO_CSV = r"G:\Drives compartilhados\FISCAL\autmais\REST\Relatorio.csv"
PLANILHA_EMPRESAS     = Path(r"G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx")

# ==============================================================================
# AUTMAIS API (NFS-e) — credenciais via .env, nunca commitadas
# ==============================================================================
import os as _os
try:
    from dotenv import load_dotenv as _load_dotenv
    # Procura .env ao lado deste config.py (dev) ou proximo do executavel (PyInstaller).
    import sys as _sys
    if getattr(_sys, "frozen", False):
        _env_path = Path(_sys.executable).parent / ".env"
    else:
        _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path)
except ImportError:
    pass

AUTMAIS_AUTH_HOST = _os.environ.get("AUTMAIS_AUTH_HOST", "https://api2.autmais.com.br/v1")
AUTMAIS_NFSE_HOST = _os.environ.get("AUTMAIS_NFSE_HOST", "https://apimongo.autmais.com.br/v1")
AUTMAIS_TENANT    = _os.environ.get("AUTMAIS_TENANT", "")
AUTMAIS_USERNAME  = _os.environ.get("AUTMAIS_USERNAME", "")
AUTMAIS_PASSWORD  = _os.environ.get("AUTMAIS_PASSWORD", "")
# Token cache (LocalAppData no Windows, ~/.cache no Linux).
_appdata = _os.environ.get("LOCALAPPDATA") or _os.path.expanduser("~/.cache")
AUTMAIS_TOKEN_CACHE = Path(_appdata) / "ImportaREST" / "autmais_token.json"

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


def ibge_por_nome_municipio(nome: str) -> str:
    """Normaliza nome e retorna IBGE 7 digitos. '' se nao achou.

    Aceita variacoes: 'Aparecida de Goiania', 'APARECIDA DE GOIÂNIA',
    'aparecida  de  goiania', etc.
    """
    import unicodedata
    s = (nome or "").strip()
    if not s:
        return ""
    s_norm = " ".join(
        c for c in unicodedata.normalize("NFD", s.upper())
        if unicodedata.category(c) != "Mn"
    ).split()
    key_norm = " ".join(s_norm)
    for chave, info in MUNICIPIOS_ACEITOS.items():
        chave_norm = " ".join(
            c for c in unicodedata.normalize("NFD", chave.upper())
            if unicodedata.category(c) != "Mn"
        ).split()
        if " ".join(chave_norm) == key_norm:
            return info["ibge7"]
    return ""

# ==============================================================================
# IBGE API
# ==============================================================================
IBGE_MUN_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{}"

# ==============================================================================
# PALETA — dark mode quente (v1.3, inspirado em Soraluna)
# Mantém o laranja Crosara como identidade, gold como acento sofisticado.
# ==============================================================================
COR_BG          = "#14110F"   # preto quente — fundo
COR_CARD        = "#1F1A17"   # superficie elevada (marrom escuro)
COR_CARD_HOVER  = "#2A231F"   # hover de cards
COR_PRIMARIA    = "#E58A4E"   # laranja Crosara — identidade preservada
COR_PRIMARIA_HV = "#FFA866"
COR_SUCESSO     = "#3DBA5C"
COR_SUCESSO_HV  = "#48D068"
COR_TEXTO       = "#F4EFE7"   # branco-luar (com leve calidez)
COR_SUBTEXTO    = "#9D9286"   # texto secundario quente
COR_BORDA       = "#3A312C"   # linha sutil
COR_BORDA_LEVE  = "#2A2421"

# Acento gold (eyebrows, detalhes premium)
COR_GOLD        = "#CBA75A"
COR_GOLD_CLARO  = "#E7CF96"

# Erro / destrutivo
COR_ERRO        = "#E25555"
COR_ERRO_HV     = "#FF6868"
COR_ERRO_LABEL  = "#FF7878"

# Log (terminal-like)
COR_LOG_BG      = "#0E0B0A"
COR_LOG_OK      = "#7ECC8B"
COR_LOG_WARN    = "#E7CF96"
COR_LOG_INFO    = "#6FB3D9"

# Dialogs
COR_DLG_SUB     = "#1F1A17"
COR_DESC_BG     = "#251D17"
COR_DESC_BORDA  = "#8A6638"
COR_MUN_BG      = "#1A2026"
COR_MUN_BORDA   = "#3A5060"
COR_MUN_TEXTO   = "#A8C7DA"

# ==============================================================================
# TIPOGRAFIA (inspirada em Soraluna)
# DISPLAY = serif elegante para títulos
# BODY    = sans-serif para corpo
# MONO    = monospace para log
# ==============================================================================
FONT_DISPLAY = "Georgia"
FONT_BODY    = "Segoe UI"
FONT_MONO    = "Consolas"
