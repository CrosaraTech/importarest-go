"""Tests for BatchJobManager, abort support, and HTTP endpoints (Phase 5).

Manager-level tests (Plan 01):
- test_create_batch_job_returns_id
- test_create_batch_conflict_with_individual
- test_create_individual_conflict_with_batch
- test_batch_status_shape
- test_batch_status_excludes_internals
- test_batch_status_company_rows
- test_batch_status_not_found
- test_abort_batch_calls_orchestrator
- test_abort_individual_job
- test_abort_individual_unknown
- test_eta_calculation

HTTP endpoint tests (Plan 02):
POST /batch:
- test_post_batch_requires_auth
- test_post_batch_creates_job
- test_post_batch_conflict_409
- test_post_batch_missing_fields

GET /batch/{id}/status:
- test_get_batch_status_shape
- test_get_batch_status_not_found
- test_get_batch_status_wrong_owner

POST /jobs/{id}/abort:
- test_abort_individual_job_200
- test_abort_batch_job_200
- test_abort_not_found_404
- test_abort_wrong_owner_403
- test_abort_preserves_completed

POST /jobs/{id}/review dispatch:
- test_review_dispatch_to_batch
"""
import sys
import threading
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Module cache cleanup fixture (mirrors test_jobs.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_modules():
    """Clear cached api/batch_manager modules between tests.

    Note: Do NOT clear services.batch_orchestrator here — doing so would
    break test_batch_orchestrator.py tests that run in the same session
    (monkeypatch would patch a freshly loaded module while BatchOrchestrator
    objects hold references to the old module's globals).
    """
    yield
    for mod in list(sys.modules.keys()):
        if any(
            mod.startswith(prefix)
            for prefix in (
                "api.batch_manager",
                "api.job_manager",
                "api.models",
            )
        ):
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Manager creation tests
# ---------------------------------------------------------------------------


def test_create_batch_job_returns_id():
    """BatchJobManager.create_batch_job() returns a non-empty batch_id string and sets status to 'running'."""
    from api.batch_manager import BatchJobManager
    from api.job_manager import JobManager

    jm = JobManager()
    bjm = BatchJobManager(jm)

    companies = [{"cod": "001", "nome": "Empresa A"}, {"cod": "002", "nome": "Empresa B"}]

    with patch("api.batch_manager.BatchOrchestrator") as MockOrc:
        mock_orc_instance = MagicMock()
        MockOrc.return_value = mock_orc_instance
        # _run_batch will be started in a thread; patch threading.Thread to avoid actual execution
        with patch("api.batch_manager.threading.Thread") as MockThread:
            mock_thread = MagicMock()
            MockThread.return_value = mock_thread

            batch_id = bjm.create_batch_job(
                user_id="user-uuid-1",
                analyst_name="ANA BEATRIZ",
                vigencia="2025-01",
                gerar_mei=False,
                companies=companies,
                job_dir="/tmp/batch_test",
            )

    assert batch_id, "batch_id must be non-empty"
    assert isinstance(batch_id, str)

    status = bjm.get_batch_status(batch_id)
    assert status is not None
    assert status["status"] == "running"
    assert status["batch_id"] == batch_id


def test_create_batch_conflict_with_individual():
    """Creating a batch while analyst has active individual job raises ValueError."""
    from api.batch_manager import BatchJobManager
    from api.job_manager import JobManager

    jm = JobManager()
    # Manually inject an active individual job for the analyst
    jm._analyst_jobs["ANA BEATRIZ"] = "existing_job_001"
    jm._jobs["existing_job_001"] = {"status": "running", "job_id": "existing_job_001"}

    bjm = BatchJobManager(jm)

    companies = [{"cod": "001", "nome": "Empresa A"}]

    with pytest.raises(ValueError, match="already has an active job"):
        bjm.create_batch_job(
            user_id="user-uuid-1",
            analyst_name="ANA BEATRIZ",
            vigencia="2025-01",
            gerar_mei=False,
            companies=companies,
            job_dir="/tmp/batch_test",
        )


def test_create_individual_conflict_with_batch():
    """Creating individual job via job_manager while analyst has active batch raises ValueError."""
    from api.batch_manager import BatchJobManager
    from api.job_manager import JobManager

    jm = JobManager()
    bjm = BatchJobManager(jm)

    companies = [{"cod": "001", "nome": "Empresa A"}]

    with patch("api.batch_manager.BatchOrchestrator"):
        with patch("api.batch_manager.threading.Thread") as MockThread:
            MockThread.return_value = MagicMock()
            bjm.create_batch_job(
                user_id="user-uuid-1",
                analyst_name="ANA BEATRIZ",
                vigencia="2025-01",
                gerar_mei=False,
                companies=companies,
                job_dir="/tmp/batch_test",
            )

    # Now try to create an individual job for the same analyst — should raise ValueError
    with pytest.raises(ValueError):
        with patch("api.job_manager.threading.Thread"):
            jm.create_job(
                user_id="user-uuid-1",
                analyst_name="ANA BEATRIZ",
                emp_cod="003",
                vigencia="2025-01",
                gerar_mei=False,
                job_dir="/tmp/individual_test",
            )


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------


def _make_batch_with_companies(n_companies: int = 2):
    """Helper: returns (bjm, batch_id) with mock thread (no real execution)."""
    from api.batch_manager import BatchJobManager
    from api.job_manager import JobManager

    jm = JobManager()
    bjm = BatchJobManager(jm)
    companies = [{"cod": f"00{i+1}", "nome": f"Empresa {i+1}"} for i in range(n_companies)]

    with patch("api.batch_manager.BatchOrchestrator"):
        with patch("api.batch_manager.threading.Thread") as MockThread:
            MockThread.return_value = MagicMock()
            batch_id = bjm.create_batch_job(
                user_id="user-uuid-1",
                analyst_name="ANA BEATRIZ",
                vigencia="2025-01",
                gerar_mei=False,
                companies=companies,
                job_dir="/tmp/batch_test",
            )
    return bjm, batch_id


def test_batch_status_shape():
    """get_batch_status() returns dict with required top-level keys."""
    bjm, batch_id = _make_batch_with_companies(2)
    status = bjm.get_batch_status(batch_id)

    assert status is not None
    required_keys = {
        "batch_id", "status", "companies", "current_company_cod",
        "review_item", "review_company_cod", "summary",
    }
    for key in required_keys:
        assert key in status, f"Missing key: {key}"


def test_batch_status_excludes_internals():
    """get_batch_status() does NOT include internal objects in the response."""
    bjm, batch_id = _make_batch_with_companies(1)
    status = bjm.get_batch_status(batch_id)

    forbidden_keys = {"_orchestrator", "review_event", "review_result", "review_dados_base"}
    for key in forbidden_keys:
        assert key not in status, f"Internal key leaked: {key}"


def test_batch_status_company_rows():
    """Each company row has the required fields."""
    bjm, batch_id = _make_batch_with_companies(2)
    status = bjm.get_batch_status(batch_id)

    assert isinstance(status["companies"], list)
    assert len(status["companies"]) == 2

    required_row_fields = {"cod", "nome", "status", "current_note", "total_notes", "elapsed_seconds", "error_detail"}
    for row in status["companies"]:
        for field in required_row_fields:
            assert field in row, f"Company row missing field: {field}"


def test_batch_status_not_found():
    """get_batch_status() returns None for unknown batch_id."""
    from api.batch_manager import BatchJobManager
    from api.job_manager import JobManager

    bjm = BatchJobManager(JobManager())
    result = bjm.get_batch_status("nonexistent_batch_id")
    assert result is None


# ---------------------------------------------------------------------------
# Abort tests
# ---------------------------------------------------------------------------


def test_abort_batch_calls_orchestrator():
    """abort_batch() calls orchestrator.abort()."""
    bjm, batch_id = _make_batch_with_companies(2)

    # Inject a mock orchestrator into the batch state
    mock_orc = MagicMock()
    bjm._batches[batch_id]["_orchestrator"] = mock_orc

    bjm.abort_batch(batch_id)

    mock_orc.abort.assert_called_once()


def test_abort_individual_job():
    """JobManager.abort_job() sets job status to 'aborted'."""
    from api.job_manager import JobManager

    jm = JobManager()
    job_id = "abort_test_001"
    jm._jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "recent_logs": [],
        "errors": [],
    }

    result = jm.abort_job(job_id)

    assert result is True
    assert jm._jobs[job_id]["status"] == "aborted"


def test_abort_individual_unknown():
    """JobManager.abort_job() returns False for unknown job_id."""
    from api.job_manager import JobManager

    jm = JobManager()
    result = jm.abort_job("nonexistent_job_id")
    assert result is False


# ---------------------------------------------------------------------------
# ETA test
# ---------------------------------------------------------------------------


def test_eta_calculation():
    """When 2 of 5 companies completed with 10s each, ETA = 10 * 3 = 30s."""
    bjm, batch_id = _make_batch_with_companies(5)

    # Simulate 2 companies completed with 10s each
    with bjm._lock:
        batch = bjm._batches[batch_id]
        companies = batch["companies"]
        companies[0]["status"] = "completed"
        companies[0]["elapsed_seconds"] = 10.0
        companies[1]["status"] = "completed"
        companies[1]["elapsed_seconds"] = 10.0
        # remaining 3 are "pending"

    status = bjm.get_batch_status(batch_id)

    assert status["eta_seconds"] is not None
    assert status["eta_seconds"] == pytest.approx(30.0, abs=0.1)


# ===========================================================================
# HTTP Endpoint tests (Plan 02)
# ===========================================================================

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-uuid-batch-test"
TEST_EMAIL = "batch-test@crosara.com.br"
TEST_ANALYST_NAME = "ANA BEATRIZ"
TEST_BATCH_ID = "batchabc12345"
TEST_JOB_ID = "jobxyz654321"

SAMPLE_BATCH_STATUS = {
    "batch_id": TEST_BATCH_ID,
    "status": "running",
    "companies": [
        {
            "cod": "001",
            "nome": "Empresa A",
            "status": "completed",
            "current_note": 5,
            "total_notes": 5,
            "elapsed_seconds": 10.0,
            "error_detail": "",
        },
        {
            "cod": "002",
            "nome": "Empresa B",
            "status": "pending",
            "current_note": 0,
            "total_notes": 0,
            "elapsed_seconds": 0.0,
            "error_detail": "",
        },
    ],
    "current_company_cod": "002",
    "eta_seconds": 10.0,
    "review_item": None,
    "review_company_cod": None,
    "summary": None,
    "user_id": TEST_USER_ID,
}

SAMPLE_INDIVIDUAL_JOB_STATUS = {
    "job_id": TEST_JOB_ID,
    "status": "running",
    "current_note": 2,
    "total_notes": 10,
    "percent": 20.0,
    "recent_logs": [],
    "errors": [],
    "user_id": TEST_USER_ID,
    "analyst_name": TEST_ANALYST_NAME,
    "emp_cod": "001",
    "vigencia": "2025-01",
    "created_at": "2026-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_env_http(monkeypatch, tmp_path):
    """Set required env vars and clear cached modules for HTTP endpoint tests."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-key-32-chars-minimum!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    for mod in list(sys.modules.keys()):
        if any(
            mod.startswith(prefix)
            for prefix in (
                "config_web",
                "api.deps",
                "api.supabase_client",
                "api.companies",
                "api.jobs",
                "api.batch",
                "api.main",
                "api.models",
                "api.job_manager",
                "api.batch_manager",
            )
        ):
            sys.modules.pop(mod, None)


def _make_fake_user(user_id: str = TEST_USER_ID, analyst_name: str = TEST_ANALYST_NAME):
    """Return an async override for get_current_user dependency."""
    async def _fake_get_current_user():
        return {
            "user_id": user_id,
            "email": TEST_EMAIL,
            "analyst_name": analyst_name,
        }
    return _fake_get_current_user


# ---------------------------------------------------------------------------
# POST /batch endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_batch_requires_auth():
    """POST /batch without Authorization header returns 401 or 403."""
    from api.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/batch", json={
            "analyst_name": TEST_ANALYST_NAME,
            "vigencia": "2025-01",
            "gerar_mei": False,
        })

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_post_batch_creates_job():
    """POST /batch with valid body returns 200 with batch_id and status='running'."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"cod": "001", "nome": "Empresa A"},
            {"cod": "002", "nome": "Empresa B"},
        ]
        with patch("api.batch.get_supabase_admin", return_value=mock_supabase):
            with patch("api.batch.batch_job_manager") as mock_bjm:
                mock_bjm.create_batch_job.return_value = TEST_BATCH_ID
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post("/batch", json={
                        "analyst_name": TEST_ANALYST_NAME,
                        "vigencia": "2025-01",
                        "gerar_mei": False,
                    })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "batch_id" in body
    assert body["status"] == "running"
    mock_bjm.create_batch_job.assert_called_once()


@pytest.mark.asyncio
async def test_post_batch_conflict_409():
    """POST /batch when analyst already has an active job returns 409."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"cod": "001", "nome": "Empresa A"},
        ]
        with patch("api.batch.get_supabase_admin", return_value=mock_supabase):
            with patch("api.batch.batch_job_manager") as mock_bjm:
                mock_bjm.create_batch_job.side_effect = ValueError("Analyst already has active batch job")
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post("/batch", json={
                        "analyst_name": TEST_ANALYST_NAME,
                        "vigencia": "2025-01",
                        "gerar_mei": False,
                    })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_post_batch_missing_fields():
    """POST /batch without analyst_name returns 422."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/batch", json={
                "vigencia": "2025-01",
                "gerar_mei": False,
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /batch/{id}/status endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_batch_status_shape():
    """GET /batch/{id}/status returns BatchStatusResponse shape with companies list."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.batch.batch_job_manager") as mock_bjm:
            mock_bjm.get_batch_status.return_value = SAMPLE_BATCH_STATUS.copy()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/batch/{TEST_BATCH_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["batch_id"] == TEST_BATCH_ID
    assert "status" in body
    assert "companies" in body
    assert isinstance(body["companies"], list)
    assert len(body["companies"]) == 2
    assert "eta_seconds" in body


@pytest.mark.asyncio
async def test_get_batch_status_not_found():
    """GET /batch/nonexistent/status returns 404."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.batch.batch_job_manager") as mock_bjm:
            mock_bjm.get_batch_status.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/batch/nonexistent/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_batch_status_wrong_owner():
    """GET /batch/{id}/status for another user's batch returns 403."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user(user_id="user-A")
    other_user_batch = {**SAMPLE_BATCH_STATUS, "user_id": "user-B"}
    try:
        with patch("api.batch.batch_job_manager") as mock_bjm:
            mock_bjm.get_batch_status.return_value = other_user_batch
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/batch/{TEST_BATCH_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /jobs/{id}/abort endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_abort_individual_job_200():
    """POST /jobs/{id}/abort on individual job returns 200 accepted=true."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.batch_job_manager") as mock_bjm:
                mock_jm.get_status.return_value = SAMPLE_INDIVIDUAL_JOB_STATUS.copy()
                mock_jm.abort_job.return_value = True
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(f"/jobs/{TEST_JOB_ID}/abort")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    mock_jm.abort_job.assert_called_once_with(TEST_JOB_ID)


@pytest.mark.asyncio
async def test_abort_batch_job_200():
    """POST /jobs/{batch_id}/abort on batch job returns 200 accepted=true."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.batch_job_manager") as mock_bjm:
                # job_manager has no record of this ID
                mock_jm.get_status.return_value = None
                mock_bjm.get_batch_status.return_value = SAMPLE_BATCH_STATUS.copy()
                mock_bjm.abort_batch.return_value = True
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(f"/jobs/{TEST_BATCH_ID}/abort")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    mock_bjm.abort_batch.assert_called_once_with(TEST_BATCH_ID)


@pytest.mark.asyncio
async def test_abort_not_found_404():
    """POST /jobs/nonexistent/abort returns 404."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.batch_job_manager") as mock_bjm:
                mock_jm.get_status.return_value = None
                mock_bjm.get_batch_status.return_value = None
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post("/jobs/nonexistent_id/abort")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_abort_wrong_owner_403():
    """POST /jobs/{id}/abort for another user's job returns 403."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user(user_id="user-A")
    other_user_job = {**SAMPLE_INDIVIDUAL_JOB_STATUS, "user_id": "user-B"}
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.batch_job_manager") as mock_bjm:
                mock_jm.get_status.return_value = other_user_job
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(f"/jobs/{TEST_JOB_ID}/abort")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_abort_preserves_completed():
    """After aborting batch, completed companies remain accessible in status."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    completed_batch = {
        **SAMPLE_BATCH_STATUS,
        "status": "aborted",
        "companies": [
            {
                "cod": "001", "nome": "Empresa A", "status": "completed",
                "current_note": 5, "total_notes": 5, "elapsed_seconds": 10.0, "error_detail": "",
            },
            {
                "cod": "002", "nome": "Empresa B", "status": "aborted",
                "current_note": 0, "total_notes": 0, "elapsed_seconds": 0.0, "error_detail": "",
            },
        ],
    }
    try:
        with patch("api.batch.batch_job_manager") as mock_bjm:
            mock_bjm.get_batch_status.return_value = completed_batch
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/batch/{TEST_BATCH_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "aborted"
    completed = [c for c in body["companies"] if c["status"] == "completed"]
    assert len(completed) == 1
    assert completed[0]["cod"] == "001"


# ---------------------------------------------------------------------------
# POST /jobs/{id}/review dispatch test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_review_dispatch_to_batch():
    """POST /jobs/{batch_id}/review dispatches to batch_job_manager when job_manager returns None."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    batch_state_with_review = {
        **SAMPLE_BATCH_STATUS,
        "review_item": {
            "chave_nfse": "key-abc-123",
            "descricao": "Servico X",
            "municipio": "Goiania",
            "item_lc_original": "0105",
            "from_n8n": False,
            "suggested_item_lc": "0105",
            "timeout_at": "2026-12-31T00:00:00Z",
        },
    }
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.batch_job_manager") as mock_bjm:
                mock_jm.get_status.return_value = None
                mock_bjm.get_batch_status.return_value = batch_state_with_review
                mock_bjm.submit_review.return_value = {"accepted": True}
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        f"/jobs/{TEST_BATCH_ID}/review",
                        json={"item_lc": "0105", "ddd": "62", "action": "confirm"},
                    )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    mock_bjm.submit_review.assert_called_once()
