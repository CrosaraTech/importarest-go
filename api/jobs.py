"""POST /jobs and GET /jobs/{id}/status endpoints, plus download and file metadata endpoints.

POST /jobs
    Accepts multipart upload with XML or ZIP files plus form fields.
    Validates file types and sizes, saves files to a temp directory with
    the structure the WorkflowProcessor expects, then starts a background job.

GET /jobs/{id}/status
    Returns real-time progress for a job owned by the authenticated user.

GET /jobs/{id}/files
    Lists all available downloads (main TXT, CSV, and any split TXT files)
    for a completed job.

GET /jobs/{id}/download/txt
    Returns the main TXT file as UTF-8 (no BOM) bytes.

GET /jobs/{id}/download/csv
    Returns the relatorio CSV with UTF-8 BOM and semicolon delimiter.

GET /jobs/{id}/download/txt/{vigencia}
    Returns per-vigencia split TXT with its own montar_cabecalho header.

Auth: All endpoints require a valid Supabase JWT (via get_current_user).

Imports:
    job_manager singleton from api.job_manager
    JobCreateResponse, JobStatusResponse from api.models
"""
import csv
import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status

from api.deps import get_current_user
from api.job_manager import job_manager
from api.models import (
    FileEntry,
    JobCreateResponse,
    JobFilesResponse,
    JobStatusResponse,
    JobSummary,
    ReviewResponse,
    ReviewSubmission,
)
from config_web import UPLOAD_TEMP_DIR
from core.txt_builder import montar_cabecalho

router = APIRouter(prefix="/jobs", tags=["jobs"])

# File extensions accepted for upload
_ALLOWED_EXTENSIONS = {".xml", ".zip"}

# CSV report column header — mirrors services/report._CABECALHO exactly.
# Defined here to avoid importing services.report (which loads config.py).
_CSV_CABECALHO = [
    "Arquivo", "CNPJ Prestador", "Numero Nota", "Valor Documento",
    "Status", "Modo", "Detalhe", "Chave NFS-e", "Data/Hora Execucao", "Linha TXT"
]


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _get_completed_job_or_raise(job_id: str, current_user: dict):
    """Validate job access and return (job_state, result) for a completed job.

    Raises:
        404: if job_id is unknown or result is None
        403: if job belongs to a different user
        409: if job is not in 'completed' state
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

    if job_state.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job is not yet completed",
        )

    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Result for job '{job_id}' not available",
        )

    return job_state, result


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


# ---------------------------------------------------------------------------
# Download endpoints (Phase 4)
# IMPORTANT: exact-match routes are declared BEFORE parameterized routes to
# avoid FastAPI path ambiguity (e.g. /download/txt must precede /download/txt/{vigencia}).
# ---------------------------------------------------------------------------

@router.get("/{job_id}/files", response_model=JobFilesResponse)
async def get_job_files(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> JobFilesResponse:
    """List all available downloads for a completed job.

    Returns:
        JobFilesResponse with job_id, emp_cod, vigencia, summary, and a list
        of FileEntry objects (main TXT, CSV, and any split TXT files).

    Raises:
        404: if job_id is unknown or result unavailable
        403: if job belongs to a different user
        409: if job is not yet completed
    """
    job_state, result = _get_completed_job_or_raise(job_id, current_user)

    emp_cod = job_state["emp_cod"]
    vigencia = job_state["vigencia"]

    # Build summary — errors are rows where the Status column (index 4) is not "OK"
    total = len(result.relatorio)
    errors = sum(1 for row in result.relatorio if len(row) > 4 and row[4] != "OK")
    summary = JobSummary(total=total, errors=errors, skipped=0)

    # Always include main TXT and CSV
    files: list[FileEntry] = [
        FileEntry(
            type="txt",
            label=f"{emp_cod}_{vigencia}.txt",
            url=f"/jobs/{job_id}/download/txt",
        ),
        FileEntry(
            type="csv",
            label=f"relatorio_{emp_cod}_{vigencia}.csv",
            url=f"/jobs/{job_id}/download/csv",
        ),
    ]

    # Add one txt_split entry per vigencia key in notas_vig_errada
    for vig_key in (result.notas_vig_errada or {}):
        files.append(
            FileEntry(
                type="txt_split",
                label=f"{emp_cod}_{vig_key}.txt",
                url=f"/jobs/{job_id}/download/txt/{vig_key}",
                vigencia=vig_key,
            )
        )

    return JobFilesResponse(
        job_id=job_id,
        emp_cod=emp_cod,
        vigencia=vigencia,
        summary=summary,
        files=files,
    )


@router.get("/{job_id}/download/txt")
async def download_txt(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Download the main TXT output for a completed job.

    Returns UTF-8 encoded bytes (no BOM) with Content-Disposition attachment.

    Raises:
        404: if job_id is unknown or result unavailable
        403: if job belongs to a different user
        409: if job is not yet completed
    """
    job_state, result = _get_completed_job_or_raise(job_id, current_user)

    emp_cod = job_state["emp_cod"]
    vigencia = job_state["vigencia"]
    filename = f"{emp_cod}_{vigencia}.txt"

    return Response(
        content=result.conteudo_final.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/download/csv")
async def download_csv(
    job_id: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Download the relatorio CSV for a completed job.

    Returns UTF-8-sig (BOM) encoded CSV with semicolon delimiter.

    Raises:
        404: if job_id is unknown or result unavailable
        403: if job belongs to a different user
        409: if job is not yet completed
    """
    job_state, result = _get_completed_job_or_raise(job_id, current_user)

    emp_cod = job_state["emp_cod"]
    vigencia = job_state["vigencia"]
    filename = f"relatorio_{emp_cod}_{vigencia}.csv"

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(_CSV_CABECALHO)
    writer.writerows(result.relatorio)

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/download/txt/{vigencia}")
async def download_split_txt(
    job_id: str,
    vigencia: str,
    current_user: dict = Depends(get_current_user),
) -> Response:
    """Download a per-vigencia split TXT file for a completed job.

    The first line is the montar_cabecalho output; subsequent lines are the
    raw TXT lines stored in result.notas_vig_errada[vigencia].

    Raises:
        404: if job_id is unknown, result unavailable, or vigencia key not found
        403: if job belongs to a different user
        409: if job is not yet completed
    """
    job_state, result = _get_completed_job_or_raise(job_id, current_user)

    notas = result.notas_vig_errada or {}
    if vigencia not in notas:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No split TXT found for vigencia '{vigencia}'",
        )

    emp_cod = job_state["emp_cod"]
    filename = f"{emp_cod}_{vigencia}.txt"

    # vigencia key format is MMYYYY — build ISO date for montar_cabecalho
    # "122024" → dt_iso = "2024-12-01T00:00:00"
    mm = vigencia[:2]
    yyyy = vigencia[2:]
    dt_iso = f"{yyyy}-{mm}-01T00:00:00"

    cab = montar_cabecalho(result.im_tomador_cab, result.razao_tomador_cab, dt_iso)
    linhas = notas[vigencia]
    content_lines = ([cab] if cab else []) + list(linhas)
    content = "\n".join(content_lines).encode("utf-8")

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
