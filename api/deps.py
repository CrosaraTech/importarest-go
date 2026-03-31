"""FastAPI dependencies for the ImportaREST GO API."""
import jwt
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from api.supabase_client import get_supabase_admin
from config_web import SUPABASE_URL, SUPABASE_JWT_SECRET

bearer_scheme = HTTPBearer()

def _get_jwt_secret():
    """Return secret supporting both HS256 (legacy) and ES256 (new) Supabase tokens."""
    return SUPABASE_JWT_SECRET

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    token = credentials.credentials

    # Detect algorithm from token header to avoid unnecessary network calls.
    # Supabase issues HS256 (legacy) or ES256 (new format) tokens.
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")
    except jwt.exceptions.DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    payload = None
    try:
        if alg == "ES256":
            # Fetch public key from Supabase JWKS (only when token is actually ES256)
            jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            response = httpx.get(jwks_url, timeout=10)
            jwks = response.json()
            public_key = jwt.algorithms.ECAlgorithm.from_jwk(jwks["keys"][0])
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )
        else:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
    except jwt.InvalidTokenError:
        pass

    if payload is None:
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