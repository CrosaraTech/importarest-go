"""POST /jobs and GET /jobs/{id}/status endpoints.

POST /jobs
    Accepts multipart upload with XML or ZIP files plus form fields.
    Validates file types and sizes, saves files to a temp directory with
    the structure the WorkflowProcessor expects, then starts a background job.

GET /jobs/{id}/status
    Returns real-time progress for a job owned by the authenticated user.

Auth: Both endpoints require a valid Supabase JWT (via get_current_user).

Imports:
    job_manager singleton from api.job_manager
    JobCreateResponse, JobStatusResponse from api.models
"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from api.deps import get_current_user
from api.job_manager import job_manager
from api.models import JobCreateResponse, JobStatusResponse, ReviewSubmission, ReviewResponse
from config_web import UPLOAD_TEMP_DIR

router = APIRouter(prefix="/jobs", tags=["jobs"])

# File extensions accepted for upload
_ALLOWED_EXTENSIONS = {".xml", ".zip"}


@router.post("", response_model=JobCreateResponse)
async def create_job(
    files: list[UploadFile],
    emp_cod: str = Form(...),
    vigencia: str = Form(...),
    gerar_mei: bool = Form(False),
    current_user: dict = Depends(get_current_user),
) -> JobCreateResponse:
    """Accept XML/ZIP uploads, validate them, and start a processing job.

    Form fields:
        emp_cod   — company code (e.g. "001")
        vigencia  — competence period string (e.g. "2025-01")
        gerar_mei — whether to generate MEI lines (default False)

    File constraints:
        - Extension must be .xml or .zip
        - File must not be empty (size > 0 bytes)

    Returns:
        JobCreateResponse with job_id and status="queued"

    Raises:
        422: if any file fails validation, or required form fields missing
        409: if analyst already has an active (queued/running) job
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one file must be uploaded",
        )

    # Validate all files before writing anything to disk
    validated: list[tuple[UploadFile, bytes]] = []
    for upload in files:
        filename = upload.filename or ""
        suffix = Path(filename).suffix.lower()

        if suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid file type for '{filename}'. Only .xml and .zip are accepted.",
            )

        content = await upload.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Empty file: '{filename}'. File must not be 0 bytes.",
            )

        validated.append((upload, content))

    # Build the directory structure that WorkflowProcessor expects:
    #   UPLOAD_TEMP_DIR / <job_id> / <emp_cod>- / <vigencia> /
    # processor.py line 97: pasta = BASE_DIR / f"{emp_cod}-" / vigencia
    # We will point config.BASE_DIR → job_dir before calling processar().
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOAD_TEMP_DIR / job_id
    nota_dir = job_dir / f"{emp_cod}-" / vigencia
    nota_dir.mkdir(parents=True, exist_ok=True)

    # Write validated files into the expected directory
    for upload, content in validated:
        filename = upload.filename or f"file_{uuid.uuid4().hex[:6]}.xml"
        dest = nota_dir / Path(filename).name
        dest.write_bytes(content)

    # Start background job — raises ValueError if analyst already has active job
    user_id = current_user["user_id"]
    analyst_name = current_user.get("analyst_name") or user_id

    try:
        actual_job_id = job_manager.create_job(
            user_id=user_id,
            analyst_name=analyst_name,
            emp_cod=emp_cod,
            vigencia=vigencia,
            gerar_mei=gerar_mei,
            job_dir=job_dir,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return JobCreateResponse(job_id=actual_job_id, status="queued")


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> JobStatusResponse:
    """Return current processing progress for a job.

    Returns:
        JobStatusResponse with current_note, total_notes, percent,
        recent_logs (last 20), errors, result_ready flag.

    Raises:
        404: if job_id is unknown
        403: if job belongs to a different user
    """
    job_state = job_manager.get_status(job_id)
    if job_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    if job_state.get("user_id") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job",
        )

    from api.models import ReviewItem

    raw_review_item = job_state.get("review_item")
    review_item = ReviewItem(**raw_review_item) if raw_review_item else None

    return JobStatusResponse(
        job_id=job_state["job_id"],
        status=job_state["status"],
        current_note=job_state["current_note"],
        total_notes=job_state["total_notes"],
        percent=job_state["percent"],
        recent_logs=job_state["recent_logs"],
        errors=job_state["errors"],
        result_ready=(job_state["status"] == "completed" and job_state.get("result") is not None)
        if "result" in job_state
        else (job_state["status"] == "completed"),
        review_item=review_item,
    )


@router.post("/{job_id}/review", response_model=ReviewResponse)
async def submit_job_review(
    job_id: str,
    body: ReviewSubmission,
    current_user: dict = Depends(get_current_user),
) -> ReviewResponse:
    """Submit a manual review decision for a paused job.

    The job must be in 'review_needed' state. The analyst provides the
    corrected Item LC (and optionally DDD) or chooses to skip the note.
    The blocked worker thread is woken and processing resumes.

    Returns:
        ReviewResponse with accepted=True on success.

    Raises:
        404: if job_id is unknown
        403: if job belongs to a different user
        409: if job is not currently in 'review_needed' state
        422: if item_lc is not 4 digits, or ddd is required but missing/invalid
    """
    job_state = job_manager.get_status(job_id)
    if job_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    if job_state.get("user_id") != current_user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this job",
        )

    if job_state.get("status") != "review_needed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not currently waiting for a review",
        )

    try:
        result = job_manager.submit_review(job_id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if not result.get("accepted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.get("reason", "Review gate no longer active"),
        )

    return ReviewResponse(accepted=True)
