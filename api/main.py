"""FastAPI application entry point for ImportaREST GO API.

IMPORTANT: Never import from config.py here — that module has G: drive paths.
All config must come from config_web.py.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config_web import ALLOWED_ORIGINS
from api.health import router as health_router
from api.companies import router as companies_router
from api.jobs import router as jobs_router

app = FastAPI(
    title="ImportaREST GO API",
    version="1.0.0",
    description="REST API for NFS-e XML processing and ISS.NET import generation.",
)

# ---------------------------------------------------------------------------
# CORS — list explicit origins; wildcards break JWT-in-Authorization flows
# allow_credentials=False because JWT is in Authorization header (not a cookie)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router)
app.include_router(companies_router)
app.include_router(jobs_router)
