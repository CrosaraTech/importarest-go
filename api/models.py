"""Pydantic request/response models for the job lifecycle API.

Exports:
    JobCreateResponse  — returned by POST /jobs
    JobStatusResponse  — returned by GET /jobs/{id}/status
    JobErrorDetail     — per-note error record (embedded in JobStatusResponse)
    ReviewItem         — review gate data returned in JobStatusResponse when status="review_needed"
    ReviewSubmission   — body for POST /jobs/{id}/review
    ReviewResponse     — response from POST /jobs/{id}/review
    FileEntry          — single downloadable file metadata
    JobSummary         — aggregate processing statistics
    JobFilesResponse   — response from GET /jobs/{id}/files
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class JobCreateResponse(BaseModel):
    """Response from POST /jobs — confirms job was accepted and queued."""
    job_id: str
    status: str = "queued"


class JobErrorDetail(BaseModel):
    """Per-note error record stored during processing."""
    note_name: str
    reason: str


class ReviewItem(BaseModel):
    """Review gate payload — returned in JobStatusResponse when status='review_needed'.

    Exposed fields only (no threading.Event, no dados_base).
    Frontend uses this to render the review form.
    """
    chave_nfse: str           # NFS-e key for display
    descricao: str            # Service description (read-only hint)
    municipio: str            # Municipality name or code (read-only hint)
    item_lc_original: str     # Original Item LC from XML
    from_n8n: bool            # Whether the note came through the n8n pipeline
    suggested_item_lc: str    # AI-suggested Item LC (read-only hint)
    timeout_at: str           # ISO 8601 UTC timestamp — when the gate expires


class ReviewSubmission(BaseModel):
    """Body for POST /jobs/{id}/review.

    item_lc must be exactly 4 digits.
    ddd is required when from_n8n=False (validated in endpoint/manager).
    """
    item_lc: str
    ddd: Optional[str] = None
    action: str = "confirm"   # "confirm" | "skip"


class ReviewResponse(BaseModel):
    """Response from POST /jobs/{id}/review."""
    accepted: bool
    reason: Optional[str] = None


class JobStatusResponse(BaseModel):
    """Response from GET /jobs/{id}/status — real-time progress snapshot."""
    job_id: str
    status: str  # "queued" | "running" | "completed" | "failed" | "review_needed"
    current_note: int
    total_notes: int
    percent: float
    recent_logs: list[str]           # last 20 log messages
    errors: list[str]                # per-note error strings
    result_ready: bool               # True when status == "completed" and result stored
    review_item: Optional[ReviewItem] = None  # populated only when status="review_needed"


# ---------------------------------------------------------------------------
# Download / file-listing models (Phase 4)
# ---------------------------------------------------------------------------

class FileEntry(BaseModel):
    """Metadata for a single downloadable file in a completed job."""
    type: Literal["txt", "csv", "txt_split"]
    label: str
    url: str
    vigencia: str = ""


class JobSummary(BaseModel):
    """Aggregate processing statistics for a completed job."""
    total: int
    errors: int
    skipped: int
    processing_seconds: Optional[float] = None


class JobFilesResponse(BaseModel):
    """Response from GET /jobs/{id}/files — lists all available downloads."""
    job_id: str
    emp_cod: str
    vigencia: str
    summary: JobSummary
    files: list[FileEntry]


# ---------------------------------------------------------------------------
# Batch mode models (Phase 5)
# ---------------------------------------------------------------------------

class BatchCompanyRow(BaseModel):
    """Per-company progress row in a batch job status response."""
    cod: str
    nome: str
    status: str        # "pending"|"running"|"completed"|"error"|"skipped"|"aborted"
    current_note: int
    total_notes: int
    elapsed_seconds: float
    error_detail: str


class BatchCreateResponse(BaseModel):
    """Response from POST /batch — confirms batch job was accepted."""
    batch_id: str
    status: str = "running"


class BatchStatusResponse(BaseModel):
    """Response from GET /batch/{id}/status — per-company progress snapshot."""
    batch_id: str
    status: str        # "running"|"completed"|"aborted"
    companies: list[BatchCompanyRow]
    current_company_cod: Optional[str]
    eta_seconds: Optional[float]
    review_item: Optional[ReviewItem] = None
    review_company_cod: Optional[str] = None
    summary: Optional[dict] = None


class AbortResponse(BaseModel):
    """Response from POST /jobs/{id}/abort or POST /batch/{id}/abort."""
    accepted: bool
