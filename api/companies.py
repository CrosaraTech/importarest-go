"""GET /companies endpoint for the ImportaREST GO API.

Returns a filtered list of companies from Supabase. Each company includes
an `is_mine` flag indicating whether it belongs to the requesting analyst.

Usage:
    from api.companies import router as companies_router
    app.include_router(companies_router)

Auth: All routes require a valid Supabase JWT (via get_current_user dependency).
Data: Reads from Supabase `companies` table using the admin client (bypasses RLS).

Decisions (from STATE.md):
- Analysts see ALL companies but `is_mine` marks ownership.
- If analyst has no companies assigned, return empty list (frontend handles display).
- Never import from config.py — only config_web.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_current_user
from api.supabase_client import get_supabase_admin

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
async def list_companies(
    analyst: Optional[str] = Query(default=None, description="Filter by analyst name (analista column)"),
    municipio: Optional[str] = Query(default=None, description="Filter by municipality"),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return all companies with optional analyst/municipality filtering.

    Query parameters:
        analyst  — if provided, only returns companies where analista=<analyst>
        municipio — if provided, only returns companies where municipio=<municipio>

    Each company in the response includes:
        is_mine (bool) — True if company.analista == current user's analyst_name

    Returns:
        {"companies": [...]}

    The endpoint returns an empty list (not an error) when no companies match.
    """
    supabase = get_supabase_admin()

    # Build query — start with all columns
    query = supabase.table("companies").select("*")

    # Apply optional filters
    if analyst is not None:
        query = query.eq("analista", analyst)
    if municipio is not None:
        query = query.eq("municipio", municipio)

    result = query.execute()
    companies = result.data or []

    # Annotate each company with is_mine flag
    analyst_name = current_user.get("analyst_name")
    for company in companies:
        company["is_mine"] = (company.get("analista") == analyst_name)

    return {"companies": companies}
