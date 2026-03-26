"""
config_web.py — Environment-driven config for the FastAPI web layer.

This file is imported ONLY by modules in api/. It never imports from config.py
(which has G: drive paths and is exclusively for the desktop application).

All required env vars must be set (either via .env file or actual environment).
See .env.example for required variable names.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Supabase credentials
# Required — will raise KeyError on startup if missing (fail fast, not silently)
# New key format: sb_publishable_... / sb_secret_... for projects after 2025 key migration
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_PUBLISHABLE_KEY: str = os.environ["SUPABASE_PUBLISHABLE_KEY"]
SUPABASE_SECRET_KEY: str = os.environ["SUPABASE_SECRET_KEY"]
SUPABASE_JWT_SECRET: str = os.environ["SUPABASE_JWT_SECRET"]

# ---------------------------------------------------------------------------
# n8n webhook (used in Phase 2+, configured now to centralise all config)
# ---------------------------------------------------------------------------
N8N_URL: str = os.environ.get(
    "N8N_URL",
    "https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing",
)
N8N_TIMEOUT: int = int(os.environ.get("N8N_TIMEOUT", "90"))

# ---------------------------------------------------------------------------
# Temporary upload directory (phases 2+)
# Created on import so it exists before any upload handler runs.
# ---------------------------------------------------------------------------
UPLOAD_TEMP_DIR: Path = Path(os.environ.get("UPLOAD_TEMP_DIR", "/tmp/importarest"))
UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# CORS — list of allowed frontend origins
# Comma-separated in env, e.g. "https://yourapp.lovable.app,http://localhost:5173"
# Must be explicit — wildcards + Authorization header violates CORS spec.
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS: list[str] = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173",
).split(",")
