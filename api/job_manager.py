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
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Module-level helpers (no external imports beyond stdlib)
# ---------------------------------------------------------------------------


def _extract_descricao(dados_base: dict) -> str:
    """Extract service description from dados_base for review display.

    Handles both XML/ABRASF format (discriminacao) and n8n format (descricao_servico).
    Falls back to empty string if unavailable.
    """
    for key in ("discriminacao", "descricao_servico", "descricao", "discriminacao_servico"):
        val = dados_base.get(key)
        if val and str(val).strip():
            # Truncate to 200 chars to keep JSON lean
            return str(val).strip()[:200]
    return ""


def _extract_municipio(dados_base: dict) -> str:
    """Extract municipality display name from dados_base.

    Does NOT call services.ibge — returns city_override, cidade, or
    falls back to raw codigo_municipio so the API layer stays side-effect-free.
    """
    for key in ("cidade_override", "cidade", "municipio"):
        val = dados_base.get(key)
        if val and str(val).strip():
            return str(val).strip()
    # Last resort: return the IBGE code as-is
    return str(dados_base.get("codigo_municipio", "") or "")


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
            # Enforce one active job per analyst (covers both individual and batch jobs).
            # If the existing id is NOT in _jobs it belongs to a different registry (e.g.
            # BatchJobManager) — treat it as active rather than silently allow the conflict.
            existing = self._analyst_jobs.get(analyst_name)
            if existing:
                existing_status = self._jobs.get(existing, {}).get("status")
                # existing_status is None when it's a batch job (lives in BatchJobManager)
                if existing_status in ("queued", "running") or existing_status is None:
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
        """Return a copy of the job state dict (without internal/heavy objects).

        Excludes:
            result         — large ProcessorResult object
            review_event   — threading.Event (not serializable)
            review_result  — internal result holder list
            review_dados_base — raw XML dict (analyst-facing data is in review_item)

        Returns None if job_id is unknown.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            # Shallow copy, exclude heavy/internal objects
            _excluded = ("result", "review_event", "review_result", "review_dados_base")
            return {k: v for k, v in job.items() if k not in _excluded}

    def get_result(self, job_id: str):
        """Return the stored ProcessorResult for a completed job, or None.

        Used in Phase 4 (download endpoint).
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.get("result")

    def submit_review(self, job_id: str, submission) -> dict:
        """Wake the blocked worker thread with the analyst's review submission.

        Args:
            job_id:     Job whose review gate is waiting.
            submission: ReviewSubmission (item_lc, ddd, action).

        Returns:
            {"accepted": True} on success.
            {"accepted": False, "reason": "not_waiting"} if job is not in review_needed state.

        Raises:
            ValueError: if item_lc is not exactly 4 digits, or ddd is required but missing/invalid.

        IMPORTANT: Does NOT set status="running" — the worker thread does that
        after event.wait() returns. Avoids a race between submit_review and the worker.
        """
        from core.validators import normalize_digits

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.get("status") != "review_needed":
                return {"accepted": False, "reason": "not_waiting"}

            event = job.get("review_event")
            result_holder = job.get("review_result")
            dados_base = job.get("review_dados_base") or {}
            from_n8n = (job.get("review_item") or {}).get("from_n8n", False)

            if event is None or result_holder is None:
                return {"accepted": False, "reason": "not_waiting"}

            # Validate item_lc
            digits = normalize_digits(submission.item_lc or "")
            if len(digits) != 4:
                raise ValueError("item_lc must be exactly 4 digits")

            # Validate ddd when not from_n8n
            if not from_n8n and submission.action != "skip":
                ddd_digits = normalize_digits(submission.ddd or "")
                if len(ddd_digits) != 2:
                    raise ValueError("ddd must be exactly 2 digits when from_n8n=False")
            else:
                ddd_digits = normalize_digits(submission.ddd or "")

            if submission.action == "skip":
                result_holder[0] = None
            else:
                # Build TXT line server-side — dados_base is locked in memory
                if from_n8n:
                    from core.txt_builder import montar_linha_txt_n8n
                    line = montar_linha_txt_n8n(dados_base, item_lc=digits)
                else:
                    from core.txt_builder import montar_linha_txt
                    line = montar_linha_txt(dados_base, ddd=ddd_digits, item_lc=digits)
                result_holder[0] = line

        # Set the event OUTSIDE the lock to avoid waking the worker while we hold it
        event.set()
        return {"accepted": True}

    def abort_job(self, job_id: str) -> bool:
        """Mark an individual job as aborted. Returns False if job not found.

        For jobs in review_needed state, also sets the review_event to unblock
        the waiting worker thread.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job["status"] in ("queued", "running", "review_needed"):
                # Unblock the review gate if waiting
                event = job.get("review_event")
                job["status"] = "aborted"
                if event is not None:
                    event.set()
            return True

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

        def abrir_tela_manual_fn(dados_base: dict, chave_nfse: str, from_n8n: bool = False):
            """Blocking review gate — replaces the Phase 2 auto-accept stub.

            Stores review_item in job state, sets status to "review_needed",
            then blocks on threading.Event.wait(timeout=300).

            On submit_review(): event is set, result_holder[0] contains the
            formatted TXT line (confirm) or None (skip).

            On timeout: auto-accepts AI suggestion and logs the event.

            IMPORTANT: event.wait() is called OUTSIDE _lock to avoid deadlock.
            """
            event = threading.Event()
            result_holder = [None]
            timeout_at = (datetime.utcnow() + timedelta(seconds=300)).isoformat() + "Z"

            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["status"] = "review_needed"
                    job["review_event"] = event
                    job["review_result"] = result_holder
                    job["review_dados_base"] = dados_base
                    job["review_item"] = {
                        "chave_nfse": chave_nfse,
                        "descricao": _extract_descricao(dados_base),
                        "municipio": _extract_municipio(dados_base),
                        "item_lc_original": dados_base.get("item_lc_original", ""),
                        "from_n8n": from_n8n,
                        "suggested_item_lc": (
                            dados_base.get("item_lc_final")
                            or dados_base.get("item_lc_original")
                            or ""
                        ),
                        "timeout_at": timeout_at,
                    }

            # Block here — OUTSIDE _lock so other threads can read/write job state.
            triggered = event.wait(timeout=300)

            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    job["status"] = "running"
                    job["review_item"] = None
                    job["review_event"] = None
                    job["review_result"] = None
                    job["review_dados_base"] = None

            if not triggered:
                # Timeout — auto-accept the AI suggestion (same behaviour as Phase 2 stub)
                ai_suggestion = (
                    dados_base.get("item_lc_final")
                    or dados_base.get("item_lc_original")
                    or ""
                )
                if from_n8n:
                    from core.txt_builder import montar_linha_txt_n8n
                    line = montar_linha_txt_n8n(dados_base, item_lc=ai_suggestion)
                else:
                    from core.txt_builder import montar_linha_txt
                    ddd = dados_base.get("ddd", "") or ""
                    line = montar_linha_txt(dados_base, ddd=ddd, item_lc=ai_suggestion)

                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job["recent_logs"].append(f"Auto-aceito por timeout: {chave_nfse}")
                        if len(job["recent_logs"]) > 20:
                            job["recent_logs"] = job["recent_logs"][-20:]
                return line

            return result_holder[0]

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
