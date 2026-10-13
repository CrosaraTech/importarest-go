"""POST /batch and GET /batch/{id}/status endpoints for batch processing mode.

POST /batch
    Accepts JSON body with analyst_name, vigencia, gerar_mei.
    Fetches companies for the analyst from Supabase.
    Creates a batch staging directory at UPLOAD_TEMP_DIR / batch_{batch_id}.
    Starts batch processing in a background thread via batch_job_manager.

GET /batch/{id}/status
    Returns per-company progress, ETA, current company, review_item, and summary.
    Auth required; user must own the batch.

Auth: All endpoints require a valid Supabase JWT (via get_current_user).

Imports:
    batch_job_manager singleton from api.batch_manager
    BatchCreateResponse, BatchStatusResponse, BatchCompanyRow from api.models
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.batch_manager import batch_job_manager
from api.deps import get_current_user
from api.models import (
    BatchCompanyRow,
    BatchCreateResponse,
    BatchStatusResponse,
    ReviewItem,
)
from api.supabase_client import get_supabase_admin
from config_web import UPLOAD_TEMP_DIR

router = APIRouter(prefix="/batch", tags=["batch"])


# ---------------------------------------------------------------------------
# Request body model for POST /batch
# ---------------------------------------------------------------------------

class BatchCreateRequest(BaseModel):
    """Request body for POST /batch."""
    analyst_name: str
    vigencia: str
    gerar_mei: bool = False


# ---------------------------------------------------------------------------
# POST /batch
# ---------------------------------------------------------------------------

@router.post("", response_model=BatchCreateResponse)
async def create_batch(
    body: BatchCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> BatchCreateResponse:
    """Create and start a new batch processing job.

    Fetches all companies assigned to analyst_name from Supabase.
    Creates a batch job via batch_job_manager using UPLOAD_TEMP_DIR as base.
    After creation, creates a staging directory at UPLOAD_TEMP_DIR / batch_{batch_id}.

    The batch orchestrator processes from this directory; companies without
    uploaded XML folders are naturally skipped (returns status="skipped").

    Returns:
        BatchCreateResponse with batch_id and status="running"

    Raises:
        404: if no companies found for the analyst
        409: if analyst already has an active individual or batch job
    """
    supabase = get_supabase_admin()
    result = (
        supabase.table("companies")
        .select("cod,nome")
        .eq("analista", body.analyst_name)
        .execute()
    )
    companies = result.data or []

    if not companies:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No companies found for analyst '{body.analyst_name}'",
        )

    user_id = current_user["user_id"]

    # Use UPLOAD_TEMP_DIR as the base job_dir so the orchestrator finds
    # per-company XML folders that analysts pre-uploaded via POST /jobs.
    # The batch_id is returned by create_batch_job after internal generation.
    try:
        batch_id = batch_job_manager.create_batch_job(
            user_id=user_id,
            analyst_name=body.analyst_name,
            vigencia=body.vigencia,
            gerar_mei=body.gerar_mei,
            companies=companies,
            job_dir=UPLOAD_TEMP_DIR,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Create batch staging directory (idempotent, ok if already exists)
    batch_dir = UPLOAD_TEMP_DIR / f"batch_{batch_id}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    return BatchCreateResponse(batch_id=batch_id, status="running")


# ---------------------------------------------------------------------------
# GET /batch/{batch_id}/status
# ---------------------------------------------------------------------------

@router.get("/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(
    batch_id: str,
    current_user: dict = Depends(get_current_user),
) -> BatchStatusResponse:
    """Return current per-company processing progress for a batch job.

    Returns:
        BatchStatusResponse with company rows, ETA, current_company_cod,
        review_item (when applicable), and summary (when completed).

    Raises:
        404: if batch_id is unknown
        403: if batch belongs to a different user
    """
    batch_state = batch_job_manager.get_batch_status(batch_id)

    if batch_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job '{batch_id}' not found",
        )

    if batch_state.get("user_id") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this batch job",
        )

    # Build Pydantic company rows from raw dicts
    company_rows = [
        BatchCompanyRow(
            cod=row["cod"],
            nome=row["nome"],
            status=row["status"],
            current_note=row["current_note"],
            total_notes=row["total_notes"],
            elapsed_seconds=row["elapsed_seconds"],
            error_detail=row["error_detail"],
        )
        for row in batch_state.get("companies", [])
    ]

    # Build review_item if present
    raw_review_item = batch_state.get("review_item")
    review_item = ReviewItem(**raw_review_item) if raw_review_item else None

    return BatchStatusResponse(
        batch_id=batch_state["batch_id"],
        status=batch_state["status"],
        companies=company_rows,
        current_company_cod=batch_state.get("current_company_cod"),
        eta_seconds=batch_state.get("eta_seconds"),
        review_item=review_item,
        review_company_cod=batch_state.get("review_company_cod"),
        summary=batch_state.get("summary"),
    )
