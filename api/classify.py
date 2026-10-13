"""POST /classify thin-proxy endpoint.

Forwards JSON payloads to the n8n webhook and returns the response as JSON.
No authentication required — this endpoint is server-to-server (n8n to FastAPI).
"""
import requests
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from services.n8n_client import chamar_n8n

router = APIRouter(tags=["classify"])


@router.post("/classify")
async def classify(request: Request):
    """Forward the request payload to n8n and return its JSON response.

    Returns:
        200: n8n JSON response (passes through n8n's status code)
        502: when n8n returns non-JSON (e.g., Cloudflare HTML) or times out
    """
    payload = await request.json()

    try:
        response = chamar_n8n(payload)
    except requests.Timeout as exc:
        return JSONResponse(
            content={"error": "n8n timeout", "detail": str(exc)},
            status_code=502,
        )

    try:
        return JSONResponse(content=response.json(), status_code=response.status_code)
    except ValueError:
        return JSONResponse(
            content={"error": "n8n returned non-JSON", "body": response.text[:500]},
            status_code=502,
        )
