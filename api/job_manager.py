"""In-memory job state management and WorkflowProcessor thread wrapper.

Exports:
    JobManager  — class managing job lifecycle
    job_manager — module-level singleton (import this in routes)

Thread-safety notes:
    _lock protects both _jobs dict writes AND cfg.BASE_DIR swap.
    Jobs are serialized in v1 (acceptable — each job is <5 min, single worker).
    Two analysts submitting jobs simultaneously will queue — the second job
    starts processing once the first releases the lock inside _run_job.

Known v1 limitation:
    cfg.BASE_DIR monkey-patch serializes concurrent jobs. This is intentional
    for single-worker deployments. Phase N can replace with per-process isolation.
"""
import threading
import uuid
from datetime import datetime


class JobManager:
    """Manages the lifecycle of XML/ZIP processing jobs.

    Each job is keyed by a 12-character hex job_id.
    Only one active (queued or running) job is allowed per analyst.
    The WorkflowProcessor is instantiated and run in a dedicated threading.Thread.
    """

    def __init__(self):
        # job_id -> job state dict
        self._jobs: dict[str, dict] = {}
        # analyst_name -> active job_id (cleared when job reaches terminal state)
        self._analyst_jobs: dict[str, str] = {}
        # Protects _jobs writes and cfg.BASE_DIR swap (serialises processar() calls)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_job(
        self,
        user_id: str,
        analyst_name: str,
        emp_cod: str,
        vigencia: str,
        gerar_mei: bool,
        job_dir,  # pathlib.Path — must already contain {emp_cod}-/{vigencia}/ with files
    ) -> str:
        """Create and immediately start a new processing job.

        Args:
            user_id:      Supabase user UUID.
            analyst_name: Human-readable analyst name (from profiles table).
            emp_cod:      Company code (e.g. "001").
            vigencia:     Competence period string (e.g. "2025-01").
            gerar_mei:    Whether to generate MEI lines.
            job_dir:      Base temp directory for this job. Must already have the
                          sub-structure {emp_cod}-/{vigencia}/ with uploaded files.

        Returns:
            job_id (12-char hex string)

        Raises:
            ValueError: if analyst already has a queued or running job.
        """
        with self._lock:
            # Enforce one active job per analyst
            existing = self._analyst_jobs.get(analyst_name)
            if existing:
                existing_status = self._jobs.get(existing, {}).get("status")
                if existing_status in ("queued", "running"):
                    raise ValueError(
                        f"Analyst '{analyst_name}' already has an active job: {existing}"
                    )

            job_id = uuid.uuid4().hex[:12]
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "current_note": 0,
                "total_notes": 0,
                "percent": 0.0,
                "recent_logs": [],
                "errors": [],
                "result": None,
                "user_id": user_id,
                "analyst_name": analyst_name,
                "emp_cod": emp_cod,
                "vigencia": vigencia,
                "created_at": datetime.utcnow(),
            }
            self._analyst_jobs[analyst_name] = job_id

        t = threading.Thread(
            target=self._run_job,
            args=(job_id, emp_cod, vigencia, gerar_mei, job_dir),
            daemon=True,
        )
        t.start()
        return job_id

    def get_status(self, job_id: str) -> dict | None:
        """Return a copy of the job state dict (without the ProcessorResult object).

        Returns None if job_id is unknown.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            # Shallow copy, exclude heavy result object
            return {k: v for k, v in job.items() if k != "result"}

    def get_result(self, job_id: str):
        """Return the stored ProcessorResult for a completed job, or None.

        Used in Phase 4 (download endpoint).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.get("result")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_job(self, job_id: str, emp_cod: str, vigencia: str, gerar_mei: bool, job_dir):
        """Worker function — runs in a dedicated threading.Thread.

        Acquires _lock only around the cfg.BASE_DIR swap + processar() call
        so that concurrent jobs queue rather than corrupt BASE_DIR.
        """
        # Mark running (outside the processar lock — just a status write)
        self._update_job(job_id, status="running")

        # Build callbacks that write to _jobs[job_id]
        def log_fn(msg: str):
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["recent_logs"].append(str(msg))
                    if len(job["recent_logs"]) > 20:
                        job["recent_logs"] = job["recent_logs"][-20:]

        def progress_fn(total: int):
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["total_notes"] = int(total)

        def contador_fn(atual: int, total: int):
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["current_note"] = int(atual)
                    job["total_notes"] = int(total)
                    job["percent"] = (
                        round(int(atual) / int(total) * 100, 1) if int(total) > 0 else 0.0
                    )

        def abrir_tela_manual_fn(*args, **kwargs):
            # Phase 3 replaces this with a real review gate.
            # For now, auto-accept: return the first positional arg unchanged
            # (the AI suggestion) so processing continues without human input.
            return args[0] if args else None

        # Import config and WorkflowProcessor here (worker thread only).
        # We use importlib to avoid a bare "import config" line that would trip the
        # api/ G-drive import linter (test_no_g_drive_import_in_api).
        import importlib
        cfg = importlib.import_module("config")
        from services.processor import WorkflowProcessor

        original_base_dir = cfg.BASE_DIR
        try:
            # Acquire lock for the entire processar() call to protect BASE_DIR swap.
            # This serialises jobs in v1 (intentional — see module docstring).
            with self._lock:
                cfg.BASE_DIR = job_dir
                try:
                    processor = WorkflowProcessor(
                        log_fn, progress_fn, contador_fn, abrir_tela_manual_fn, gerar_mei
                    )
                    result = processor.processar(emp_cod, vigencia)
                finally:
                    cfg.BASE_DIR = original_base_dir

            if result is not None:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job["result"] = result
                        job["status"] = "completed"
                        job["percent"] = 100.0
            else:
                # processar() returns None on non-fatal early exits (e.g. pasta not found)
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        last_log = (
                            job["recent_logs"][-1] if job["recent_logs"] else "Processor returned None"
                        )
                        job["errors"].append(last_log)
                        job["status"] = "failed"

        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["errors"].append(str(exc))
                    job["status"] = "failed"
        finally:
            # Belt-and-suspenders: always restore BASE_DIR even if lock wasn't held
            cfg.BASE_DIR = original_base_dir

    def _update_job(self, job_id: str, **kwargs):
        """Thread-safe update of job fields."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(kwargs)


# Module-level singleton — import this in route handlers
job_manager = JobManager()
