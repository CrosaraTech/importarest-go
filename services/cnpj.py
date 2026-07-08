"""services/cnpj.py — Consulta CNPJ via APIs públicas.

Usado como fallback quando o XML não traz tags de regime tributário do
prestador (OptanteSimplesNacional / opSimpNac). Tenta CNPJ.ws primeiro
(mais generoso) e cai para BrasilAPI em caso de erro.
"""
from __future__ import annotations

import requests

from core.validators import normalize_digits

_URL_CNPJWS = "https://publica.cnpj.ws/cnpj/{}"
_URL_BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{}"
_TIMEOUT_SECS = 15
_cache: dict[str, dict | None] = {}


def _consulta_cnpjws(cnpj_digits: str) -> dict | None:
    r = requests.get(_URL_CNPJWS.format(cnpj_digits), timeout=_TIMEOUT_SECS)
    if r.status_code != 200:
        return None
    data = r.json()
    simples_block = data.get("simples") or {}
    return {
        "simples_nacional": (simples_block.get("simples") or "").lower() == "sim",
        "mei":              (simples_block.get("mei") or "").lower() == "sim",
        "razao_social":     (data.get("razao_social") or "").strip(),
    }


def _consulta_brasilapi(cnpj_digits: str) -> dict | None:
    r = requests.get(_URL_BRASILAPI.format(cnpj_digits), timeout=_TIMEOUT_SECS)
    if r.status_code != 200:
        return None
    data = r.json()
    return {
        "simples_nacional": bool(data.get("opcao_pelo_simples")),
        "mei":              bool(data.get("opcao_pelo_mei")),
        "razao_social":     (data.get("razao_social") or "").strip(),
    }


def consultar_cnpj(cnpj: str) -> dict | None:
    """Consulta CNPJ. Retorna dict ou None.

    Returns:
        dict com chaves: simples_nacional (bool), mei (bool), razao_social (str).
        None se CNPJ malformado, não encontrado, ou todas as APIs falharem.
    """
    cnpj_digits = normalize_digits(cnpj or "")
    if len(cnpj_digits) != 14:
        return None
    if cnpj_digits in _cache:
        return _cache[cnpj_digits]

    for fetcher in (_consulta_cnpjws, _consulta_brasilapi):
        try:
            result = fetcher(cnpj_digits)
            if result is not None:
                _cache[cnpj_digits] = result
                return result
        except (requests.RequestException, ValueError, KeyError):
            continue

    _cache[cnpj_digits] = None
    return None
