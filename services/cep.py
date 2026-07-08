"""services/cep.py — Consulta de CEP com fallback entre múltiplas APIs.

Substitui a chamada que era feita no n8n. ViaCEP é primária (mais rica em
campos), AwesomeAPI cobre os buracos do ViaCEP (CEPs de cidades pequenas
que não estão lá), BrasilAPI é último recurso (mas não retorna DDD).
"""
from __future__ import annotations

import requests

from core.validators import normalize_digits

_URL_VIACEP    = "https://viacep.com.br/ws/{}/json/"
_URL_AWESOME   = "https://cep.awesomeapi.com.br/json/{}"
_URL_BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{}"
_TIMEOUT_SECS = 10
_cache: dict[str, dict | None] = {}

# DDD principal por UF — fallback quando o CEP está zerado/inválido na NFS-e.
# Em estados com múltiplos DDDs, usa o da capital/região metropolitana (a área
# de maior probabilidade). Não é perfeito, mas é melhor que DDD vazio.
_DDD_POR_UF = {
    "AC": "68", "AL": "82", "AM": "92", "AP": "96", "BA": "71",
    "CE": "85", "DF": "61", "ES": "27", "GO": "62", "MA": "98",
    "MG": "31", "MS": "67", "MT": "65", "PA": "91", "PB": "83",
    "PE": "81", "PI": "86", "PR": "41", "RJ": "21", "RN": "84",
    "RO": "69", "RR": "95", "RS": "51", "SC": "48", "SE": "79",
    "SP": "11", "TO": "63",
}


def ddd_por_uf(uf: str) -> str:
    """Retorna o DDD principal do estado, ou '' se UF inválido."""
    return _DDD_POR_UF.get((uf or "").strip().upper(), "")


_cache_cep_municipio: dict[tuple[str, str], str] = {}


def obter_cep_generico_municipio(uf: str, cidade: str) -> str:
    """Busca um CEP qualquer do município via ViaCEP search by city.

    Usado como fallback quando o XML traz CEP zerado/inválido (`00000000`).
    O CEP retornado é de uma rua qualquer da cidade — não é o endereço real
    do prestador, mas é válido no portal ISSNet (que checa formato + UF).

    Returns:
        CEP de 8 dígitos ou '' se não encontrar.
    """
    uf = (uf or "").strip().upper()
    cidade = (cidade or "").strip()
    if not uf or not cidade or len(cidade) < 3:
        return ""

    key = (uf, cidade.upper())
    if key in _cache_cep_municipio:
        return _cache_cep_municipio[key]

    # ViaCEP search exige logradouro com ≥3 chars. Tentamos termos comuns.
    for termo in ("rua", "avenida", "praca", "centro"):
        try:
            r = requests.get(
                f"https://viacep.com.br/ws/{uf}/{cidade}/{termo}/json/",
                timeout=_TIMEOUT_SECS,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if isinstance(data, list) and data:
                cep = normalize_digits(data[0].get("cep", ""))
                if len(cep) == 8 and cep != "00000000":
                    _cache_cep_municipio[key] = cep
                    return cep
        except (requests.RequestException, ValueError):
            continue

    _cache_cep_municipio[key] = ""
    return ""


def _from_viacep(cep_digits: str) -> dict | None:
    r = requests.get(_URL_VIACEP.format(cep_digits), timeout=_TIMEOUT_SECS)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("erro"):
        return None
    return {
        "logradouro": (data.get("logradouro") or "").strip(),
        "bairro":     (data.get("bairro") or "").strip(),
        "cidade":     (data.get("localidade") or "").strip(),
        "uf":         (data.get("uf") or "").strip().upper(),
        "ddd":        normalize_digits(str(data.get("ddd") or ""))[:2],
        "ibge":       normalize_digits(data.get("ibge") or ""),
    }


def _from_awesome(cep_digits: str) -> dict | None:
    r = requests.get(_URL_AWESOME.format(cep_digits), timeout=_TIMEOUT_SECS)
    if r.status_code != 200:
        return None
    data = r.json()
    # AwesomeAPI usa nomes diferentes: address_name = rua, district = bairro
    return {
        "logradouro": (data.get("address_name") or data.get("address") or "").strip(),
        "bairro":     (data.get("district") or "").strip(),
        "cidade":     (data.get("city") or "").strip(),
        "uf":         (data.get("state") or "").strip().upper(),
        "ddd":        normalize_digits(str(data.get("ddd") or ""))[:2],
        "ibge":       normalize_digits(data.get("city_ibge") or ""),
    }


def _from_brasilapi(cep_digits: str) -> dict | None:
    """BrasilAPI v2: mais resiliente para CEPs raros, mas não retorna DDD."""
    r = requests.get(_URL_BRASILAPI.format(cep_digits), timeout=_TIMEOUT_SECS)
    if r.status_code != 200:
        return None
    data = r.json()
    return {
        "logradouro": (data.get("street") or "").strip(),
        "bairro":     (data.get("neighborhood") or "").strip(),
        "cidade":     (data.get("city") or "").strip(),
        "uf":         (data.get("state") or "").strip().upper(),
        "ddd":        "",   # BrasilAPI v2 não devolve DDD
        "ibge":       "",
    }


def _merge_results(*results: dict | None) -> dict | None:
    """Combina resultados das APIs preenchendo campos vazios com a próxima fonte."""
    fields = ("logradouro", "bairro", "cidade", "uf", "ddd", "ibge")
    out: dict[str, str] = {f: "" for f in fields}
    saw_any = False
    for r in results:
        if not r:
            continue
        saw_any = True
        for f in fields:
            if not out[f] and r.get(f):
                out[f] = r[f]
    return out if saw_any else None


def consultar_cep(cep: str) -> dict | None:
    """Consulta CEP. Tenta múltiplas APIs até preencher todos os campos.

    Returns:
        dict com logradouro, bairro, cidade, uf, ddd, ibge.
        None se CEP malformado ou nenhuma API retornar.
    """
    cep_digits = normalize_digits(cep or "")
    if len(cep_digits) != 8:
        return None
    if cep_digits in _cache:
        return _cache[cep_digits]

    results: list[dict | None] = []
    for fetcher in (_from_viacep, _from_awesome, _from_brasilapi):
        try:
            res = fetcher(cep_digits)
        except (requests.RequestException, ValueError, KeyError):
            res = None
        results.append(res)
        # Para cedo se já temos DDD (o campo mais difícil de conseguir)
        if res and res.get("ddd"):
            break

    merged = _merge_results(*results)
    _cache[cep_digits] = merged
    return merged
