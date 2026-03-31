"""Tests for BatchJobManager and abort support (Phase 5, Plan 01).

All tests operate directly on manager classes — no HTTP layer.
Covers:
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
"""
import sys
import threading
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Module cache cleanup fixture (mirrors test_jobs.py pattern)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_modules():
    """Clear cached api/batch_manager modules between tests."""
    yield
    for mod in list(sys.modules.keys()):
        if any(
            mod.startswith(prefix)
            for prefix in (
                "api.batch_manager",
                "api.job_manager",
                "api.models",
                "services.batch_orchestrator",
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
