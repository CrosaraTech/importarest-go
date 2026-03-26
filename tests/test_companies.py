"""Tests for GET /companies endpoint.

All tests mock the Supabase client. No live Supabase connection required.

Behaviors tested:
- test_companies_requires_auth: unauthenticated request returns 401/403
- test_companies_returns_all: authenticated request returns all companies
- test_filter_by_analyst: ?analyst=ANA filters by analista column
- test_filter_by_municipio: ?municipio=GOIANIA filters by municipio column
- test_filter_combined: both filters applied together
- test_is_mine_flag_true: company whose analista matches current user has is_mine=True
- test_is_mine_flag_false: company with different analista has is_mine=False
- test_no_companies_assigned: empty list returned (not error) when no match
- test_companies_from_supabase: verifies supabase.table("companies") is called
"""
import sys
import pytest
import httpx
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-secret-key-32-chars-minimum!!"
TEST_USER_ID = "user-uuid-1234"
TEST_EMAIL = "ana@crosara.com.br"
TEST_ANALYST_NAME = "ANA BEATRIZ"

SAMPLE_COMPANIES = [
    {
        "id": "uuid-1",
        "cod": "001",
        "razao": "Empresa Alpha Ltda",
        "analista": "ANA BEATRIZ",
        "municipio": "GOIANIA",
        "im": "12345",
        "cnpj": "00.000.000/0001-01",
        "nome_empresa": "ALPHA",
        "created_at": "2026-01-01T00:00:00Z",
    },
    {
        "id": "uuid-2",
        "cod": "002",
        "razao": "Empresa Beta Ltda",
        "analista": "CARLOS",
        "municipio": "ANAPOLIS",
        "im": "67890",
        "cnpj": "00.000.000/0001-02",
        "nome_empresa": "BETA",
        "created_at": "2026-01-01T00:00:00Z",
    },
]


# ---------------------------------------------------------------------------
# Helper: build a mock Supabase client for companies table
# ---------------------------------------------------------------------------

def _mock_supabase_companies(data: list):
    """Return a mock supabase admin client whose companies table returns `data`."""
    mock_result = MagicMock()
    mock_result.data = data

    mock_query = MagicMock()
    mock_query.execute.return_value = mock_result
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query

    mock_client = MagicMock()
    mock_client.table.return_value = mock_query

    return mock_client, mock_query


# ---------------------------------------------------------------------------
# Helper: fake get_current_user that returns a known analyst
# ---------------------------------------------------------------------------

def _make_fake_user(analyst_name: str = TEST_ANALYST_NAME):
    async def _fake_get_current_user():
        return {
            "user_id": TEST_USER_ID,
            "email": TEST_EMAIL,
            "analyst_name": analyst_name,
        }
    return _fake_get_current_user


# ---------------------------------------------------------------------------
# Setup: patch env vars for config_web import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    """Ensure config_web env vars are available for all tests in this module."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
    monkeypatch.setenv("UPLOAD_TEMP_DIR", "/tmp/test_uploads")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    # Clear cached modules so patched env vars take effect
    for mod in list(sys.modules.keys()):
        if mod in (
            "config_web",
            "api.deps",
            "api.supabase_client",
            "api.companies",
            "api.main",
        ):
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_companies_requires_auth():
    """GET /companies without Authorization header returns 401 or 403."""
    from api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/companies")

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_companies_returns_all():
    """Authenticated request returns all companies from Supabase."""
    from api.main import app
    from api.deps import get_current_user

    mock_client, _ = _mock_supabase_companies(SAMPLE_COMPANIES)

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "companies" in data
    assert len(data["companies"]) == 2


@pytest.mark.asyncio
async def test_filter_by_analyst():
    """GET /companies?analyst=ANA BEATRIZ returns only companies where analista='ANA BEATRIZ'."""
    from api.main import app
    from api.deps import get_current_user

    filtered = [SAMPLE_COMPANIES[0]]  # only ANA BEATRIZ's company
    mock_client, mock_query = _mock_supabase_companies(filtered)

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies", params={"analyst": "ANA BEATRIZ"})
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data["companies"]) == 1
    # Verify the filter was applied via eq("analista", ...)
    mock_query.eq.assert_any_call("analista", "ANA BEATRIZ")


@pytest.mark.asyncio
async def test_filter_by_municipio():
    """GET /companies?municipio=GOIANIA returns only companies in GOIANIA."""
    from api.main import app
    from api.deps import get_current_user

    filtered = [SAMPLE_COMPANIES[0]]  # only GOIANIA company
    mock_client, mock_query = _mock_supabase_companies(filtered)

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies", params={"municipio": "GOIANIA"})
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data["companies"]) == 1
    # Verify the filter was applied via eq("municipio", ...)
    mock_query.eq.assert_any_call("municipio", "GOIANIA")


@pytest.mark.asyncio
async def test_filter_combined():
    """GET /companies?analyst=ANA BEATRIZ&municipio=GOIANIA applies both filters."""
    from api.main import app
    from api.deps import get_current_user

    filtered = [SAMPLE_COMPANIES[0]]
    mock_client, mock_query = _mock_supabase_companies(filtered)

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/companies",
                    params={"analyst": "ANA BEATRIZ", "municipio": "GOIANIA"},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    # Both eq calls must have been made
    mock_query.eq.assert_any_call("analista", "ANA BEATRIZ")
    mock_query.eq.assert_any_call("municipio", "GOIANIA")


@pytest.mark.asyncio
async def test_is_mine_flag_true():
    """Company whose analista matches current user's analyst_name has is_mine=True."""
    from api.main import app
    from api.deps import get_current_user

    # ANA BEATRIZ's company — is_mine should be True for ANA BEATRIZ user
    mock_client, _ = _mock_supabase_companies([SAMPLE_COMPANIES[0]])

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user("ANA BEATRIZ")
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    companies = response.json()["companies"]
    assert len(companies) == 1
    assert companies[0]["is_mine"] is True


@pytest.mark.asyncio
async def test_is_mine_flag_false():
    """Company with different analista has is_mine=False for the requesting user."""
    from api.main import app
    from api.deps import get_current_user

    # CARLOS's company — is_mine should be False for ANA BEATRIZ user
    mock_client, _ = _mock_supabase_companies([SAMPLE_COMPANIES[1]])

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user("ANA BEATRIZ")
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    companies = response.json()["companies"]
    assert len(companies) == 1
    assert companies[0]["is_mine"] is False


@pytest.mark.asyncio
async def test_no_companies_assigned():
    """When no companies match, returns empty list (not an error)."""
    from api.main import app
    from api.deps import get_current_user

    mock_client, _ = _mock_supabase_companies([])

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user("UNKNOWN_ANALYST")
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/companies")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["companies"] == []


@pytest.mark.asyncio
async def test_companies_from_supabase():
    """Endpoint reads from Supabase companies table (not XLSX file)."""
    from api.main import app
    from api.deps import get_current_user

    mock_client, mock_query = _mock_supabase_companies(SAMPLE_COMPANIES)

    with patch("api.companies.get_supabase_admin", return_value=mock_client):
        app.dependency_overrides[get_current_user] = _make_fake_user()
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.get("/companies")
        finally:
            app.dependency_overrides.clear()

    # Verify supabase.table("companies") was called — proves data comes from Supabase
    mock_client.table.assert_called_once_with("companies")
    mock_query.select.assert_called_once_with("*")
