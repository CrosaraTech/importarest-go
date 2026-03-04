import requests
from config import URL_N8N


def chamar_n8n(payload: dict, timeout: int = 150):
    """Envia payload ao webhook N8N e retorna o objeto requests.Response."""
    return requests.post(URL_N8N, json=payload, timeout=timeout)
