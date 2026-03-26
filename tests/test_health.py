"""Tests for GET /health endpoint and FastAPI app startup correctness."""
import os
import sys
import pathlib
import pytest
import httpx


def _setup_env(monkeypatch, tmp_path):
    """Patch required env vars so api.main can be imported without a real .env file."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")

    # Force re-import so patched env vars are used
    for mod in ["config_web", "api", "api.main", "api.health"]:
        sys.modules.pop(mod, None)


@pytest.mark.asyncio
async def test_health_returns_ok(monkeypatch, tmp_path):
    """GET /health returns 200 with {"status": "ok"}."""
    _setup_env(monkeypatch, tmp_path)
    from api.main import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_cors_headers(monkeypatch, tmp_path):
    """OPTIONS preflight to /health with allowed origin gets correct CORS headers."""
    _setup_env(monkeypatch, tmp_path)
    from api.main import app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
    # The response must include the CORS origin header
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_no_g_drive_import_in_api():
    """No file in api/ imports from config.py (which has G: drive paths)."""
    # Use pure Python path scanning — works cross-platform without subprocess grep
    project_root = pathlib.Path(__file__).parent.parent
    api_dir = project_root / "api"
    if not api_dir.exists():
        pytest.skip("api/ directory does not exist yet")

    violations = []
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            # Match "from config import ..." but NOT "from config_web import ..."
            if stripped.startswith("from config import") and "config_web" not in stripped:
                violations.append(f"{py_file.name}: {stripped!r}")
            # Match bare "import config" but NOT "import config_web"
            if stripped == "import config" or stripped.startswith("import config "):
                violations.append(f"{py_file.name}: {stripped!r}")

    assert not violations, f"G: drive import violations found: {violations}"
