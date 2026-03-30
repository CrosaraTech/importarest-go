"""Tests for POST /jobs and GET /jobs/{id}/status endpoints.

All tests mock job_manager and get_current_user. No real threading or
processor execution occurs during tests.

Behaviors tested:
- test_post_jobs_requires_auth: no token returns 401/403
- test_post_jobs_no_files: missing files field returns 422
- test_post_jobs_invalid_file_type: non-XML/non-ZIP file returns 422 with "Invalid file type"
- test_post_jobs_empty_file: 0-byte file returns 422 with "Empty file"
- test_post_jobs_valid_xml: valid XML + emp_cod + vigencia returns 200 with job_id and status="queued"
- test_post_jobs_valid_zip: valid ZIP returns 200 with job_id
- test_post_jobs_active_job_409: second upload when analyst has active job returns 409
- test_get_status_returns_shape: GET /jobs/{id}/status returns JobStatusResponse shape
- test_get_status_not_found: GET /jobs/nonexistent/status returns 404
- test_post_jobs_missing_emp_cod: missing emp_cod form field returns 422
- test_get_status_wrong_owner: GET status for another user's job returns 403
"""
import io
import sys
import pytest
import httpx
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-uuid-5678"
TEST_EMAIL = "test@crosara.com.br"
TEST_ANALYST_NAME = "ANA BEATRIZ"
TEST_JOB_ID = "abc123def456"

SAMPLE_JOB_STATUS = {
    "job_id": TEST_JOB_ID,
    "status": "running",
    "current_note": 3,
    "total_notes": 10,
    "percent": 30.0,
    "recent_logs": ["Processing note 3..."],
    "errors": [],
    "result_ready": False,
    "user_id": TEST_USER_ID,
    "analyst_name": TEST_ANALYST_NAME,
    "emp_cod": "001",
    "vigencia": "2025-01",
    "created_at": "2026-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_user(
    user_id: str = TEST_USER_ID,
    analyst_name: str = TEST_ANALYST_NAME,
):
    async def _fake_get_current_user():
        return {
            "user_id": user_id,
            "email": TEST_EMAIL,
            "analyst_name": analyst_name,
        }
    return _fake_get_current_user


def _xml_file(name: str = "nota.xml", content: bytes = b"<NFS-e>test</NFS-e>"):
    return (name, io.BytesIO(content), "text/xml")


def _zip_file(name: str = "notas.zip", content: bytes = b"PK\x03\x04dummy"):
    return (name, io.BytesIO(content), "application/zip")


# ---------------------------------------------------------------------------
# Setup: patch env vars so config_web and api.main can be imported cleanly
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_env(monkeypatch, tmp_path):
    """Ensure required env vars exist and clear cached modules."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-key-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    for mod in list(sys.modules.keys()):
        if any(
            mod.startswith(prefix)
            for prefix in ("config_web", "api.deps", "api.supabase_client",
                           "api.companies", "api.jobs", "api.main", "api.models",
                           "api.job_manager")
        ):
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_jobs_requires_auth():
    """POST /jobs without Authorization header returns 401 or 403."""
    from api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/jobs")

    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_jobs_no_files():
    """POST /jobs with missing files field returns 422."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/jobs",
                data={"emp_cod": "001", "vigencia": "2025-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_jobs_invalid_file_type():
    """POST /jobs with non-XML/non-ZIP file returns 422 with 'Invalid file type' in detail."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/jobs",
                files={"files": ("report.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
                data={"emp_cod": "001", "vigencia": "2025-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Invalid file type" in response.text


@pytest.mark.asyncio
async def test_post_jobs_empty_file():
    """POST /jobs with 0-byte file returns 422 with 'Empty file' in detail."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/jobs",
                files={"files": ("empty.xml", io.BytesIO(b""), "text/xml")},
                data={"emp_cod": "001", "vigencia": "2025-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "Empty file" in response.text


@pytest.mark.asyncio
async def test_post_jobs_missing_emp_cod():
    """POST /jobs without emp_cod returns 422."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/jobs",
                files={"files": _xml_file()},
                data={"vigencia": "2025-01"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Happy-path tests (mock job_manager.create_job)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_jobs_valid_xml(tmp_path):
    """POST /jobs with valid XML returns 200 with job_id and status='queued'."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.create_job.return_value = TEST_JOB_ID
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/jobs",
                    files={"files": _xml_file()},
                    data={"emp_cod": "001", "vigencia": "2025-01"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "queued"
    mock_jm.create_job.assert_called_once()


@pytest.mark.asyncio
async def test_post_jobs_valid_zip(tmp_path):
    """POST /jobs with valid ZIP returns 200 with job_id."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.create_job.return_value = TEST_JOB_ID
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/jobs",
                    files={"files": _zip_file()},
                    data={"emp_cod": "001", "vigencia": "2025-01"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body
    mock_jm.create_job.assert_called_once()


@pytest.mark.asyncio
async def test_post_jobs_active_job_409():
    """POST /jobs when analyst already has active job returns 409."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.create_job.side_effect = ValueError("Analyst already has an active job")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/jobs",
                    files={"files": _xml_file()},
                    data={"emp_cod": "001", "vigencia": "2025-01"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Status endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_returns_shape():
    """GET /jobs/{id}/status returns JobStatusResponse-shaped JSON."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_JOB_STATUS.copy()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == TEST_JOB_ID
    assert "status" in body
    assert "current_note" in body
    assert "total_notes" in body
    assert "percent" in body
    assert "recent_logs" in body
    assert "errors" in body
    assert "result_ready" in body


@pytest.mark.asyncio
async def test_get_status_not_found():
    """GET /jobs/nonexistent/status returns 404."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/jobs/nonexistent/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_status_wrong_owner():
    """GET /jobs/{id}/status for another user's job returns 403."""
    from api.main import app
    from api.deps import get_current_user

    # Authenticated as user A but job belongs to user B
    app.dependency_overrides[get_current_user] = _make_fake_user(user_id="user-A")
    other_user_job = {**SAMPLE_JOB_STATUS, "user_id": "user-B"}
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = other_user_job
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
