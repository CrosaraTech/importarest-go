"""Pydantic request/response models for the job lifecycle API.

Exports:
    JobCreateResponse — returned by POST /jobs
    JobStatusResponse — returned by GET /jobs/{id}/status
    JobErrorDetail    — per-note error record (embedded in JobStatusResponse)
"""
from pydantic import BaseModel


class JobCreateResponse(BaseModel):
    """Response from POST /jobs — confirms job was accepted and queued."""
    job_id: str
    status: str = "queued"


class JobErrorDetail(BaseModel):
    """Per-note error record stored during processing."""
    note_name: str
    reason: str


class JobStatusResponse(BaseModel):
    """Response from GET /jobs/{id}/status — real-time progress snapshot."""
    job_id: str
    status: str  # "queued" | "running" | "completed" | "failed"
    current_note: int
    total_notes: int
    percent: float
    recent_logs: list[str]   # last 20 log messages
    errors: list[str]        # per-note error strings
    result_ready: bool       # True when status == "completed" and result stored
