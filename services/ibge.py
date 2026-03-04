import requests
from config import IBGE_MUN_URL
from core.validators import normalize_digits

_ibge_cache: dict = {}


def consulta_cidade_ibge(codigo_municipio: str) -> str:
    cod = normalize_digits(codigo_municipio or "")
    if not cod:
        return ""
    if cod in _ibge_cache:
        return _ibge_cache[cod]
    try:
        r = requests.get(IBGE_MUN_URL.format(cod), timeout=20)
        if r.status_code == 200:
            js = r.json()
            nome = (js.get("nome") or "").strip().upper()
            _ibge_cache[cod] = nome
            return nome
    except (requests.RequestException, ValueError, KeyError):
        pass
    _ibge_cache[cod] = ""
    return ""
