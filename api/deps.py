"""FastAPI dependencies for the ImportaREST GO API.

Provides `get_current_user` — the JWT verification dependency injected into
all protected routes. Decodes the Supabase-issued HS256 JWT and looks up the
analyst's name from the profiles table.

Usage:
    from api.deps import get_current_user
    from fastapi import Depends

    @router.get("/protected")
    async def protected_route(current_user: dict = Depends(get_current_user)):
        return {"hello": current_user["analyst_name"]}
"""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.supabase_client import get_supabase_admin
from config_web import SUPABASE_JWT_SECRET

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Verify the Bearer JWT and return the authenticated user context.

    Returns:
        dict with keys: user_id (str), email (str | None), analyst_name (str | None)

    Raises:
        HTTPException 401: If JWT is missing, malformed, expired, or lacks 'sub'.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase does not set aud claim
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )

    # Look up analyst_name from profiles table.
    # This is the secure approach — we do NOT trust user_metadata in the JWT
    # because users can edit their own user_metadata via the Supabase JS client.
    # The profiles table can only be written by the service role (admin).
    supabase = get_supabase_admin()
    result = (
        supabase.table("profiles")
        .select("analyst_name")
        .eq("id", user_id)
        .single()
        .execute()
    )
    analyst_name = result.data.get("analyst_name") if result.data else None

    return {
        "user_id": user_id,
        "email": payload.get("email"),
        "analyst_name": analyst_name,
    }
