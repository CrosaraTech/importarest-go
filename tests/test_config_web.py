"""Tests for config_web.py — environment-driven config, no G: drive paths."""
import os
import importlib
import sys
import pytest


def _reload_config_web(monkeypatch):
    """Force a fresh import of config_web with current monkeypatched env."""
    # Remove cached module so env vars are re-read
    if "config_web" in sys.modules:
        del sys.modules["config_web"]
    import config_web
    return config_web


def test_config_web_has_supabase_url(monkeypatch, tmp_path):
    """config_web.SUPABASE_URL is read from os.environ, not hardcoded."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))

    cfg = _reload_config_web(monkeypatch)
    assert cfg.SUPABASE_URL == "https://test.supabase.co"


def test_config_web_has_supabase_jwt_secret(monkeypatch, tmp_path):
    """config_web.SUPABASE_JWT_SECRET is read from os.environ."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "my-jwt-secret-value")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))

    cfg = _reload_config_web(monkeypatch)
    assert cfg.SUPABASE_JWT_SECRET == "my-jwt-secret-value"


def test_config_web_no_g_drive_strings():
    """config_web.py source must not contain any G: drive path strings."""
    import pathlib
    source_path = pathlib.Path(__file__).parent.parent / "config_web.py"
    assert source_path.exists(), "config_web.py must exist"
    source = source_path.read_text(encoding="utf-8")
    assert "G:\\" not in source, "config_web.py must not contain G: drive paths"
    assert "G:/" not in source, "config_web.py must not contain G: drive paths"
    assert r"G:\\" not in source, "config_web.py must not contain G: drive paths"


def test_config_web_allowed_origins_default(monkeypatch, tmp_path):
    """ALLOWED_ORIGINS defaults to ['http://localhost:5173'] when not set."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    cfg = _reload_config_web(monkeypatch)
    assert cfg.ALLOWED_ORIGINS == ["http://localhost:5173"]


def test_config_web_allowed_origins_from_env(monkeypatch, tmp_path):
    """ALLOWED_ORIGINS splits comma-separated env var."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.lovable.app,http://localhost:5173")

    cfg = _reload_config_web(monkeypatch)
    assert "https://app.lovable.app" in cfg.ALLOWED_ORIGINS
    assert "http://localhost:5173" in cfg.ALLOWED_ORIGINS


def test_config_web_never_imports_config(monkeypatch, tmp_path):
    """config_web.py must not import from config.py."""
    import pathlib
    source_path = pathlib.Path(__file__).parent.parent / "config_web.py"
    assert source_path.exists(), "config_web.py must exist"
    source = source_path.read_text(encoding="utf-8")
    assert "from config import" not in source, "config_web.py must not import from config.py"
    assert "import config" not in source, "config_web.py must not import config.py"
