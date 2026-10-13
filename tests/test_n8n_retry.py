"""Tests for chamar_n8n() retry logic in services/n8n_client.py.

Behaviors tested:
- test_retries_on_timeout: chamar_n8n() calls requests.post twice when first attempt raises Timeout; second call succeeds
- test_524_treated_as_timeout_and_retried: HTTP 524 treated as retriable; retries once and returns successful response
- test_raises_after_all_retries_exhausted: raises requests.Timeout when both attempts fail with timeout
- test_524_both_attempts_raises: raises requests.Timeout when both attempts return 524
- test_default_timeout_is_90: chamar_n8n() passes timeout=90 to requests.post (not 150)
- test_success_on_first_try: returns immediately on first successful request (no unnecessary retry)
"""
import sys
import pytest
import requests
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixture: patch env and clear module cache so config imports cleanly
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
        if mod.startswith("services.n8n_client") or mod == "services.n8n_client":
            sys.modules.pop(mod, None)


def _make_ok_response(status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"status": "ok"}
    return mock_resp


def _make_524_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 524
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_retries_on_timeout():
    """chamar_n8n() retries once when first attempt raises requests.Timeout."""
    from services.n8n_client import chamar_n8n

    ok_response = _make_ok_response()
    side_effects = [requests.Timeout("first attempt timed out"), ok_response]

    with patch("services.n8n_client.requests.post", side_effect=side_effects) as mock_post:
        result = chamar_n8n({"modo": "extract"})

    assert mock_post.call_count == 2
    assert result is ok_response


def test_524_treated_as_timeout_and_retried():
    """chamar_n8n() treats HTTP 524 as retriable; returns successful second response."""
    from services.n8n_client import chamar_n8n

    resp_524 = _make_524_response()
    ok_response = _make_ok_response()
    side_effects = [resp_524, ok_response]

    with patch("services.n8n_client.requests.post", side_effect=side_effects) as mock_post:
        result = chamar_n8n({"modo": "extract"})

    assert mock_post.call_count == 2
    assert result is ok_response


def test_raises_after_all_retries_exhausted():
    """chamar_n8n() raises requests.Timeout when both attempts fail with timeout."""
    from services.n8n_client import chamar_n8n

    with patch(
        "services.n8n_client.requests.post",
        side_effect=[
            requests.Timeout("attempt 1"),
            requests.Timeout("attempt 2"),
        ],
    ):
        with pytest.raises(requests.Timeout):
            chamar_n8n({"modo": "extract"})


def test_524_both_attempts_raises():
    """chamar_n8n() raises requests.Timeout when both attempts return 524."""
    from services.n8n_client import chamar_n8n

    with patch(
        "services.n8n_client.requests.post",
        side_effect=[_make_524_response(), _make_524_response()],
    ):
        with pytest.raises(requests.Timeout):
            chamar_n8n({"modo": "extract"})


def test_default_timeout_is_90():
    """chamar_n8n() passes timeout=90 to requests.post by default (not 150)."""
    from services.n8n_client import chamar_n8n

    ok_response = _make_ok_response()
    with patch("services.n8n_client.requests.post", return_value=ok_response) as mock_post:
        chamar_n8n({"modo": "extract"})

    _, kwargs = mock_post.call_args
    assert kwargs.get("timeout") == 90


def test_success_on_first_try():
    """chamar_n8n() returns immediately on first successful request, no retry."""
    from services.n8n_client import chamar_n8n

    ok_response = _make_ok_response()
    with patch("services.n8n_client.requests.post", return_value=ok_response) as mock_post:
        result = chamar_n8n({"modo": "extract"})

    assert mock_post.call_count == 1
    assert result is ok_response
