"""Pydantic request/response models for the job lifecycle API.

Exports:
    JobCreateResponse  — returned by POST /jobs
    JobStatusResponse  — returned by GET /jobs/{id}/status
    JobErrorDetail     — per-note error record (embedded in JobStatusResponse)
    ReviewItem         — review gate data returned in JobStatusResponse when status="review_needed"
    ReviewSubmission   — body for POST /jobs/{id}/review
    ReviewResponse     — response from POST /jobs/{id}/review
"""
from __future__ import annotations

from typing import Optional

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
