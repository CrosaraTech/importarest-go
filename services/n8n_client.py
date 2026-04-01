import requests
from config import URL_N8N

_RETRY_COUNT = 1
_TIMEOUT_SECS = 90


def chamar_n8n(payload: dict, timeout: int = _TIMEOUT_SECS):
    """Envia payload ao webhook N8N e retorna o objeto requests.Response.

    Retries once on requests.Timeout or HTTP 524 (Cloudflare tunnel timeout).
    Total attempts: _RETRY_COUNT + 1 = 2.
    """
    last_exc: requests.Timeout | None = None

    for attempt in range(_RETRY_COUNT + 1):
        try:
            r = requests.post(URL_N8N, json=payload, timeout=timeout)
            if r.status_code == 524:
                raise requests.Timeout(f"Cloudflare 524 on attempt {attempt + 1}")
            return r
        except requests.Timeout as exc:
            last_exc = exc
            continue

    raise last_exc
