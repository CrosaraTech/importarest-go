"""Tests for POST /classify endpoint in api/classify.py.

Behaviors tested:
- test_classify_forwards_payload: /classify forwards JSON body to chamar_n8n() and returns n8n JSON
- test_classify_no_auth_required: /classify returns 200 without Authorization header
- test_classify_returns_502_on_html_response: /classify returns 502 when n8n returns non-JSON
- test_classify_returns_502_on_timeout: /classify returns 502 when chamar_n8n() raises requests.Timeout
"""
import sys
import pytest
import httpx
import requests
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixture: patch env and clear module cache so imports work cleanly
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_env(monkeypatch, tmp_path):
    """Ensure required env vars exist and clear cached modules."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-key-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    for mod in list(sys.modules.keys()):
        if any(
            mod.startswith(prefix)
            for prefix in (
                "config_web", "api.deps", "api.supabase_client",
                "api.companies", "api.jobs", "api.main", "api.models",
                "api.job_manager", "api.classify", "services.n8n_client",
            )
        ):
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_classify_forwards_payload():
    """POST /classify forwards JSON body to chamar_n8n() and returns n8n response."""
    from api.main import app

    ok_mock = MagicMock()
    ok_mock.status_code = 200
    ok_mock.json.return_value = [{"status": "ok"}]

    with patch("api.classify.chamar_n8n", return_value=ok_mock) as mock_chamar:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/classify", json={"modo": "extract"})

    assert response.status_code == 200
    assert response.json() == [{"status": "ok"}]
    mock_chamar.assert_called_once_with({"modo": "extract"})


@pytest.mark.anyio
async def test_classify_no_auth_required():
    """POST /classify returns 200 without any Authorization header."""
    from api.main import app

    ok_mock = MagicMock()
    ok_mock.status_code = 200
    ok_mock.json.return_value = {"result": "classified"}

    with patch("api.classify.chamar_n8n", return_value=ok_mock):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Explicitly do NOT set Authorization header
            response = await client.post("/classify", json={"modo": "extract"})

    assert response.status_code == 200


@pytest.mark.anyio
async def test_classify_returns_502_on_html_response():
    """POST /classify returns 502 when n8n returns non-JSON (e.g., Cloudflare HTML)."""
    from api.main import app

    html_mock = MagicMock()
    html_mock.status_code = 200
    html_mock.json.side_effect = ValueError("No JSON")
    html_mock.text = "<html>Cloudflare error</html>"

    with patch("api.classify.chamar_n8n", return_value=html_mock):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/classify", json={"modo": "extract"})

    assert response.status_code == 502
    body = response.json()
    assert "n8n returned non-JSON" in body.get("error", "")


@pytest.mark.anyio
async def test_classify_returns_502_on_timeout():
    """POST /classify returns 502 when chamar_n8n() raises requests.Timeout."""
    from api.main import app

    with patch(
        "api.classify.chamar_n8n",
        side_effect=requests.Timeout("all retries exhausted"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/classify", json={"modo": "extract"})

    assert response.status_code == 502
    body = response.json()
    assert "error" in body
