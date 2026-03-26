"""Tests for api/deps.py — JWT verification dependency.

All tests mock the Supabase client. No live Supabase connection required.
"""
import sys
import time
import pytest
import jwt as pyjwt
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# ---------------------------------------------------------------------------
# Constants used across tests
# ---------------------------------------------------------------------------
TEST_JWT_SECRET = "test-secret-key-32-chars-minimum!!"
TEST_USER_ID = "user-uuid-1234"
TEST_EMAIL = "ana@crosara.com.br"
TEST_ANALYST_NAME = "ANA BEATRIZ"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jwt(
    secret: str = TEST_JWT_SECRET,
    sub: str = TEST_USER_ID,
    email: str = TEST_EMAIL,
    exp_offset: int = 3600,  # seconds from now; negative = expired
    include_sub: bool = True,
    algorithm: str = "HS256",
) -> str:
    """Build a signed JWT for testing."""
    now = int(time.time())
    payload: dict = {"email": email, "iat": now, "exp": now + exp_offset}
    if include_sub:
        payload["sub"] = sub
    return pyjwt.encode(payload, secret, algorithm=algorithm)


def _make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _mock_supabase_profile(analyst_name: str = TEST_ANALYST_NAME):
    """Return a mock supabase admin client whose profiles table returns analyst_name."""
    mock_result = MagicMock()
    mock_result.data = {"analyst_name": analyst_name}

    mock_query = MagicMock()
    mock_query.execute.return_value = mock_result
    mock_query.single.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query

    mock_table = MagicMock()
    mock_table.return_value = mock_query

    mock_client = MagicMock()
    mock_client.table = mock_table
    return mock_client


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
        if mod in ("config_web", "api.deps", "api.supabase_client"):
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Task 1 behavior tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_jwt_returns_user():
    """A properly-signed HS256 JWT returns dict with user_id, email, analyst_name."""
    token = _make_jwt()
    creds = _make_credentials(token)
    mock_client = _mock_supabase_profile(TEST_ANALYST_NAME)

    with patch("api.deps.get_supabase_admin", return_value=mock_client), \
         patch("api.deps.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from api.deps import get_current_user
        result = await get_current_user(credentials=creds)

    assert result["user_id"] == TEST_USER_ID
    assert result["email"] == TEST_EMAIL
    assert result["analyst_name"] == TEST_ANALYST_NAME


@pytest.mark.asyncio
async def test_invalid_jwt_raises_401():
    """A JWT signed with the wrong secret raises HTTP 401."""
    token = _make_jwt(secret="wrong-secret-key-32-chars-minimum!")
    creds = _make_credentials(token)
    mock_client = _mock_supabase_profile()

    with patch("api.deps.get_supabase_admin", return_value=mock_client), \
         patch("api.deps.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_jwt_raises_401():
    """An expired JWT (exp in the past) raises HTTP 401."""
    token = _make_jwt(exp_offset=-3600)  # expired 1 hour ago
    creds = _make_credentials(token)
    mock_client = _mock_supabase_profile()

    with patch("api.deps.get_supabase_admin", return_value=mock_client), \
         patch("api.deps.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_sub_raises_401():
    """A valid JWT without a 'sub' claim raises HTTP 401."""
    token = _make_jwt(include_sub=False)
    creds = _make_credentials(token)
    mock_client = _mock_supabase_profile()

    with patch("api.deps.get_supabase_admin", return_value=mock_client), \
         patch("api.deps.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from api.deps import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_users_isolated():
    """Two sequential calls with different JWTs return different user contexts."""
    user1_id = "user-uuid-0001"
    user2_id = "user-uuid-0002"
    token1 = _make_jwt(sub=user1_id, email="user1@test.com")
    token2 = _make_jwt(sub=user2_id, email="user2@test.com")
    creds1 = _make_credentials(token1)
    creds2 = _make_credentials(token2)

    mock_client1 = _mock_supabase_profile("ANALYST ONE")
    mock_client2 = _mock_supabase_profile("ANALYST TWO")

    with patch("api.deps.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from api.deps import get_current_user

        with patch("api.deps.get_supabase_admin", return_value=mock_client1):
            result1 = await get_current_user(credentials=creds1)

        with patch("api.deps.get_supabase_admin", return_value=mock_client2):
            result2 = await get_current_user(credentials=creds2)

    # Results must differ — no cross-contamination
    assert result1["user_id"] == user1_id
    assert result2["user_id"] == user2_id
    assert result1["email"] != result2["email"]
    assert result1["analyst_name"] != result2["analyst_name"]


def test_supabase_client_singleton():
    """get_supabase_admin() returns the same instance on repeated calls."""
    with patch("api.supabase_client.create_client") as mock_create:
        mock_instance = MagicMock()
        mock_create.return_value = mock_instance

        # Force reset any cached singleton
        import api.supabase_client as sc
        sc._client = None

        from api.supabase_client import get_supabase_admin
        client1 = get_supabase_admin()
        client2 = get_supabase_admin()

    assert client1 is client2
    # create_client should only have been called once
    mock_create.assert_called_once()
