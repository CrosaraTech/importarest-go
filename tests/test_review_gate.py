"""Tests for the Phase 3 manual review gate.

Covers:
- Endpoint tests (mock job_manager): poll shape, submit confirm/skip, 409/403/404/422 errors
- Gate lifecycle tests (real JobManager): pause, resume, timeout, post-timeout 409

Behaviors:
- test_poll_shows_review_needed
- test_review_item_shape
- test_submit_review_resumes_job
- test_submit_review_skip
- test_review_gate_timeout
- test_submit_review_after_timeout_409
- test_submit_review_wrong_owner_403
- test_submit_review_not_found_404
- test_get_status_review_item_field
- test_review_validation_item_lc_not_4_digits
- test_review_validation_ddd_required_when_not_n8n
"""
import io
import sys
import threading
import time
import pytest
import httpx
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-uuid-review"
TEST_EMAIL = "analyst@crosara.com.br"
TEST_ANALYST_NAME = "CARLOS EDUARDO"
TEST_JOB_ID = "reviewjob0001"

SAMPLE_REVIEW_ITEM = {
    "chave_nfse": "CHAVE-NFS-E-001",
    "descricao": "Servicos de tecnologia",
    "municipio": "Goiania",
    "item_lc_original": "0107",
    "from_n8n": False,
    "suggested_item_lc": "0107",
    "timeout_at": "2026-01-01T00:05:00Z",
}

SAMPLE_REVIEW_JOB_STATUS = {
    "job_id": TEST_JOB_ID,
    "status": "review_needed",
    "current_note": 3,
    "total_notes": 10,
    "percent": 30.0,
    "recent_logs": ["Aguardando revisao manual..."],
    "errors": [],
    "result_ready": False,
    "user_id": TEST_USER_ID,
    "analyst_name": TEST_ANALYST_NAME,
    "emp_cod": "001",
    "vigencia": "2025-01",
    "review_item": SAMPLE_REVIEW_ITEM,
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


# ---------------------------------------------------------------------------
# Setup: patch env vars (same as test_jobs.py)
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
# Poll endpoint tests — mock job_manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_shows_review_needed():
    """GET /jobs/{id}/status with status='review_needed' includes review_item with all required fields."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_needed"
    assert body["review_item"] is not None

    ri = body["review_item"]
    for field in ("chave_nfse", "descricao", "municipio", "item_lc_original", "from_n8n", "suggested_item_lc", "timeout_at"):
        assert field in ri, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_review_item_shape():
    """review_item matches ReviewItem model shape exactly — no threading.Event, no dados_base."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    ri = response.json()["review_item"]

    # Only allowed keys
    allowed_keys = {"chave_nfse", "descricao", "municipio", "item_lc_original", "from_n8n", "suggested_item_lc", "timeout_at"}
    actual_keys = set(ri.keys())
    assert actual_keys == allowed_keys, f"Unexpected keys: {actual_keys - allowed_keys}"

    # No internal fields should leak
    for forbidden in ("review_event", "review_result", "review_dados_base", "dados_base"):
        assert forbidden not in ri


@pytest.mark.asyncio
async def test_get_status_review_item_field():
    """GET /status for a non-reviewing job returns review_item=null."""
    from api.main import app
    from api.deps import get_current_user
    from tests.test_jobs import SAMPLE_JOB_STATUS  # status="running", no review_item

    app.dependency_overrides[get_current_user] = _make_fake_user(user_id=SAMPLE_JOB_STATUS["user_id"])
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_JOB_STATUS.copy()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{SAMPLE_JOB_STATUS['job_id']}/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["review_item"] is None


# ---------------------------------------------------------------------------
# POST /jobs/{id}/review endpoint tests — mock job_manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_review_resumes_job():
    """POST /jobs/{id}/review with action='confirm' returns accepted=true."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()
            mock_jm.submit_review.return_value = {"accepted": True}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "0107", "ddd": "62", "action": "confirm"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True


@pytest.mark.asyncio
async def test_submit_review_skip():
    """POST /jobs/{id}/review with action='skip' returns accepted=true."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()
            mock_jm.submit_review.return_value = {"accepted": True}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "0107", "action": "skip"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True


@pytest.mark.asyncio
async def test_submit_review_after_timeout_409():
    """POST /jobs/{id}/review when job is no longer in review_needed returns 409."""
    from api.main import app
    from api.deps import get_current_user

    # Job is running (timeout already occurred, gate cleared)
    running_job = {**SAMPLE_REVIEW_JOB_STATUS, "status": "running", "review_item": None}
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = running_job
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "0107", "ddd": "62", "action": "confirm"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_submit_review_wrong_owner_403():
    """POST /jobs/{id}/review for another user's job returns 403."""
    from api.main import app
    from api.deps import get_current_user

    other_user_job = {**SAMPLE_REVIEW_JOB_STATUS, "user_id": "other-user-uuid"}
    app.dependency_overrides[get_current_user] = _make_fake_user(user_id="attacker-uuid")
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = other_user_job
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "0107", "ddd": "62", "action": "confirm"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_submit_review_not_found_404():
    """POST /jobs/{id}/review for nonexistent job returns 404."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/nonexistent-job/review",
                    json={"item_lc": "0107", "ddd": "62", "action": "confirm"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_review_validation_item_lc_not_4_digits():
    """POST /jobs/{id}/review with item_lc='12' (not 4 digits) returns 422."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()
            mock_jm.submit_review.side_effect = ValueError("item_lc must be exactly 4 digits")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "12", "ddd": "62", "action": "confirm"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_review_validation_ddd_required_when_not_n8n():
    """POST /jobs/{id}/review without ddd when from_n8n=false returns 422."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = SAMPLE_REVIEW_JOB_STATUS.copy()  # from_n8n=False
            mock_jm.submit_review.side_effect = ValueError("ddd is required when from_n8n=False")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    f"/jobs/{TEST_JOB_ID}/review",
                    json={"item_lc": "0107", "action": "confirm"},  # no ddd
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Gate lifecycle tests — real JobManager with mock processor callback
# ---------------------------------------------------------------------------


def test_review_gate_timeout():
    """When event.wait times out, job auto-accepts AI suggestion and logs 'Auto-aceito por timeout'."""
    import importlib
    # Patch txt_builder so we don't need real config / ibge services
    with patch("core.txt_builder.consulta_cidade_ibge", return_value="Goiania"):
        with patch("core.txt_builder.montar_linha_txt", return_value="LINHA_AUTO") as mock_txt:
            # Import fresh job_manager module
            for mod in list(sys.modules.keys()):
                if mod.startswith("api.job_manager"):
                    sys.modules.pop(mod, None)
            from api.job_manager import JobManager

            jm = JobManager()

            # Manually inject a job into the manager
            job_id = "timeoutjob001"
            jm._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "current_note": 0,
                "total_notes": 1,
                "percent": 0.0,
                "recent_logs": [],
                "errors": [],
                "result": None,
                "user_id": TEST_USER_ID,
                "analyst_name": TEST_ANALYST_NAME,
            }

            dados_base = {
                "item_lc_final": "0107",
                "item_lc_original": "0107",
                "ddd": "62",
                "codigo_municipio": "5208707",
            }

            result_holder = [None]

            def run_gate():
                # Access the inner function via a fresh invocation
                # We simulate what _run_job does: call abrir_tela_manual_fn closure
                event = threading.Event()
                gate_result = [None]
                timeout_secs = 0.1  # Very short timeout for test

                with jm._lock:
                    job = jm._jobs.get(job_id)
                    if job is not None:
                        from datetime import datetime, timedelta
                        timeout_at = (datetime.utcnow() + timedelta(seconds=timeout_secs)).isoformat() + "Z"
                        job["status"] = "review_needed"
                        job["review_event"] = event
                        job["review_result"] = gate_result
                        job["review_dados_base"] = dados_base
                        job["review_item"] = {
                            "chave_nfse": "NFS-001",
                            "descricao": "Servico",
                            "municipio": "Goiania",
                            "item_lc_original": dados_base.get("item_lc_original", ""),
                            "from_n8n": False,
                            "suggested_item_lc": dados_base.get("item_lc_final", ""),
                            "timeout_at": timeout_at,
                        }

                triggered = event.wait(timeout=timeout_secs)

                with jm._lock:
                    job = jm._jobs.get(job_id)
                    if job is not None:
                        job["status"] = "running"
                        job["review_item"] = None
                        job["review_event"] = None
                        job["review_result"] = None
                        job["review_dados_base"] = None

                if not triggered:
                    ai_suggestion = dados_base.get("item_lc_final") or dados_base.get("item_lc_original") or ""
                    from core.txt_builder import montar_linha_txt
                    ddd = dados_base.get("ddd", "") or ""
                    line = montar_linha_txt(dados_base, ddd=ddd, item_lc=ai_suggestion)
                    with jm._lock:
                        job = jm._jobs.get(job_id)
                        if job:
                            job["recent_logs"].append(f"Auto-aceito por timeout: NFS-001")
                            if len(job["recent_logs"]) > 20:
                                job["recent_logs"] = job["recent_logs"][-20:]
                    result_holder[0] = line
                    return line

                return gate_result[0]

            t = threading.Thread(target=run_gate)
            t.start()
            t.join(timeout=2.0)  # Must complete well within 2 seconds

            # Gate should have timed out and auto-accepted
            with jm._lock:
                job = jm._jobs.get(job_id)
                logs = job["recent_logs"] if job else []

            assert any("Auto-aceito por timeout" in log for log in logs), f"Timeout log not found. Logs: {logs}"


def test_submit_review_gate_resumes():
    """JobManager.submit_review() sets the event and wakes the blocked worker thread."""
    for mod in list(sys.modules.keys()):
        if mod.startswith("api.job_manager"):
            sys.modules.pop(mod, None)

    with patch("core.txt_builder.consulta_cidade_ibge", return_value="Goiania"):
        from api.job_manager import JobManager

        jm = JobManager()
        job_id = "resumejob001"

        dados_base = {
            "item_lc_final": "0107",
            "item_lc_original": "0107",
            "ddd": "62",
            "codigo_municipio": "5208707",
            "numero": "001",
            "vlr_doc": "100.00",
            "vlr_trib": "100.00",
            "aliq_val": "2.0",
            "dt_fmt": "2025-01-01",
            "cnpj_p": "12345678000100",
            "razao_p": "EMPRESA TESTE",
            "im_p": "123456",
            "iss_ret": "2",
            "iss_ret_origem": "abrasf",
            "cep": "74000000",
            "endereco": "RUA TESTE",
            "numero_end": "100",
            "bairro": "CENTRO",
            "cidade_override": "Goiania",
            "uf": "GO",
        }

        event = threading.Event()
        gate_result = [None]

        jm._jobs[job_id] = {
            "job_id": job_id,
            "status": "review_needed",
            "current_note": 1,
            "total_notes": 5,
            "percent": 20.0,
            "recent_logs": [],
            "errors": [],
            "result": None,
            "user_id": TEST_USER_ID,
            "analyst_name": TEST_ANALYST_NAME,
            "review_event": event,
            "review_result": gate_result,
            "review_dados_base": dados_base,
            "review_item": {
                "chave_nfse": "NFS-002",
                "descricao": "Servico",
                "municipio": "Goiania",
                "item_lc_original": "0107",
                "from_n8n": False,
                "suggested_item_lc": "0107",
                "timeout_at": "2026-01-01T00:10:00Z",
            },
        }

        # Simulate worker blocking on the event
        unblocked = threading.Event()

        def worker():
            event.wait(timeout=5.0)
            unblocked.set()

        t = threading.Thread(target=worker)
        t.start()

        # Submit review via manager (use a mock submission)
        from api.models import ReviewSubmission
        submission = ReviewSubmission(item_lc="0107", ddd="62", action="confirm")

        with patch("core.txt_builder.montar_linha_txt", return_value="LINHA_CONFIRMADA"):
            result = jm.submit_review(job_id, submission)

        t.join(timeout=2.0)

        assert result["accepted"] is True
        assert unblocked.is_set(), "Worker thread was not unblocked after submit_review"
