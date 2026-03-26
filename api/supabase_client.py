"""Supabase admin client singleton for the ImportaREST GO API.

Uses the service-role (secret) key so it can bypass RLS for server-side
operations (profile lookups, company upserts, etc.).

IMPORTANT: Never use the publishable key here. The publishable key is for the
frontend Supabase JS client only. The secret key must NEVER be exposed to the
browser.

Usage:
    from api.supabase_client import get_supabase_admin
    supabase = get_supabase_admin()
    result = supabase.table("companies").select("*").execute()
"""
from supabase import create_client, Client
from config_web import SUPABASE_URL, SUPABASE_SECRET_KEY

_client: Client | None = None


def get_supabase_admin() -> Client:
    """Return the Supabase admin client singleton.

    Instantiated on first call, reused on all subsequent calls.
    Thread-safe in a single-worker deployment (which is mandated by ARCHITECTURE.md).
    """
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    return _client
