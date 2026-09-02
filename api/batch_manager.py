"""In-memory batch job state management, wrapping BatchOrchestrator.

Exports:
    BatchJobManager  — class managing batch job lifecycle
    batch_job_manager — module-level singleton (import this in routes)

Thread-safety notes:
    _lock protects _batches dict writes and per-company state updates.
    Batch orchestrator runs in a dedicated threading.Thread.
    Review gate follows the same Phase 3 pattern: event.wait() OUTSIDE _lock.

Anti-patterns explicitly avoided:
    - Do NOT hold self._lock during event.wait() — deadlock risk
    - Do NOT use bare "import config" — G-drive import linter violation
    - Do NOT expose _orchestrator, review_event, review_result, review_dados_base
      in get_batch_status() output
"""
import queue
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.batch_orchestrator import BatchOrchestrator


def _extract_descricao(dados_base: dict) -> str:
    """Extract service description from dados_base for review display."""
    for key in ("discriminacao", "descricao_servico", "descricao", "discriminacao_servico"):
        val = dados_base.get(key)
        if val and str(val).strip():
            return str(val).strip()[:200]
    return ""


def _extract_municipio(dados_base: dict) -> str:
    """Extract municipality display name from dados_base."""
    for key in ("cidade_override", "cidade", "municipio"):
        val = dados_base.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return str(dados_base.get("codigo_municipio", "") or "")


class BatchJobManager:
    """Manages the lifecycle of batch processing jobs.

    Each batch job is keyed by a 12-character hex batch_id.
    Shares _analyst_jobs with the provided JobManager instance to enforce
    one-active-job-per-analyst across both individual and batch jobs.
    """

    def __init__(self, job_manager):
        # batch_id -> batch state dict
        self._batches: dict[str, dict] = {}
        # Protects _batches dict and per-company state updates
        self._lock = threading.Lock()
        # Shared reference to JobManager (for _analyst_jobs enforcement)
        self._job_manager = job_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_batch_job(
        self,
        user_id: str,
        analyst_name: str,
        vigencia: str,
        gerar_mei: bool,
        companies: list[dict],
        job_dir,  # str or pathlib.Path — destination folder for TXT output
    ) -> str:
        """Create and immediately start a new batch processing job.

        Args:
            user_id:      Supabase user UUID.
            analyst_name: Human-readable analyst name.
            vigencia:     Competence period string (e.g. "2025-01").
            gerar_mei:    Whether to generate MEI lines.
            companies:    List of dicts with at least "cod" and "nome" keys.
            job_dir:      Base temp directory for batch output.

        Returns:
            batch_id (12-char hex string)

        Raises:
            ValueError: if analyst already has a queued, running, or active batch job.
        """
        with self._lock:
            # Check individual job manager's registry (shared with batches)
            existing_id = self._job_manager._analyst_jobs.get(analyst_name)
            if existing_id:
                # Check if it's a running individual job
                individual_job = self._job_manager._jobs.get(existing_id, {})
                if individual_job.get("status") in ("queued", "running"):
                    raise ValueError(
                        f"Analyst '{analyst_name}' already has an active job: {existing_id}"
                    )
                # Check if it's a running batch job
                batch_job = self._batches.get(existing_id, {})
                if batch_job.get("status") == "running":
                    raise ValueError(
                        f"Analyst '{analyst_name}' already has an active batch job: {existing_id}"
                    )

            batch_id = uuid.uuid4().hex[:12]

            # Build company rows with pending status
            company_rows = [
                {
                    "cod": c["cod"],
                    "nome": c.get("nome", ""),
                    "status": "pending",
                    "current_note": 0,
                    "total_notes": 0,
                    "elapsed_seconds": 0.0,
                    "error_detail": "",
                    "recent_logs": [],
                    "_result": None,  # ProcessorResult when completed
                }
                for c in companies
            ]

            # Create queue for orchestrator communication
            q = queue.Queue()
            orc = BatchOrchestrator(q)

            self._batches[batch_id] = {
                "batch_id": batch_id,
                "status": "running",
                "companies": company_rows,
                "current_company_cod": None,
                "review_item": None,
                "review_company_cod": None,
                "review_event": None,
                "review_result": None,
                "review_dados_base": None,
                "summary": None,
                "_orchestrator": orc,
                "user_id": user_id,
                "analyst_name": analyst_name,
                "vigencia": vigencia,
                # utcnow() esta depreciado. now(timezone.utc).replace(tzinfo=None) devolve o
                # mesmo datetime naive em UTC, preservando o formato ISO ja exposto pela API
                # (sem sufixo +00:00, que quebraria o contrato com o frontend).
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }

            # Register in shared analyst_jobs so individual job creation is blocked
            self._job_manager._analyst_jobs[analyst_name] = batch_id

        t = threading.Thread(
            target=self._run_batch,
            args=(batch_id, orc, q, companies, vigencia, job_dir, gerar_mei),
            daemon=True,
        )
        t.start()
        return batch_id

    def abort_batch(self, batch_id: str) -> bool:
        """Signal the orchestrator to abort after the current company.

        Returns True if batch found, False if unknown batch_id.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return False
            orc = batch.get("_orchestrator")
            if orc is not None:
                orc.abort()
            return True

    def get_batch_status(self, batch_id: str) -> Optional[dict]:
        """Return a snapshot of batch state, excluding internal objects.

        Excludes: _orchestrator, review_event, review_result, review_dados_base
        Includes: ETA calculation based on completed company average time.

        Returns None if batch_id is unknown.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return None

            _excluded_batch = {
                "_orchestrator", "review_event", "review_result", "review_dados_base"
            }
            _excluded_row = {"recent_logs", "_result"}

            # Build safe company rows (exclude internal fields)
            safe_companies = [
                {k: v for k, v in row.items() if k not in _excluded_row}
                for row in batch["companies"]
            ]

            # Compute ETA
            eta_seconds = self._compute_eta(batch["companies"])

            return {
                "batch_id": batch["batch_id"],
                "status": batch["status"],
                "companies": safe_companies,
                "current_company_cod": batch["current_company_cod"],
                "eta_seconds": eta_seconds,
                "review_item": batch["review_item"],
                "review_company_cod": batch["review_company_cod"],
                "summary": batch["summary"],
            }

    def submit_review(self, batch_id: str, submission) -> dict:
        """Wake the blocked batch worker with the analyst's review submission.

        Follows the same pattern as JobManager.submit_review().
        """
        from core.validators import normalize_digits

        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None or batch.get("review_item") is None:
                return {"accepted": False, "reason": "not_waiting"}

            event = batch.get("review_event")
            result_holder = batch.get("review_result")
            dados_base = batch.get("review_dados_base") or {}
            from_n8n = (batch.get("review_item") or {}).get("from_n8n", False)

            if event is None or result_holder is None:
                return {"accepted": False, "reason": "not_waiting"}

            digits = normalize_digits(submission.item_lc or "")
            if len(digits) != 4:
                raise ValueError("item_lc must be exactly 4 digits")

            if not from_n8n and submission.action != "skip":
                ddd_digits = normalize_digits(submission.ddd or "")
                if len(ddd_digits) != 2:
                    raise ValueError("ddd must be exactly 2 digits when from_n8n=False")
            else:
                ddd_digits = normalize_digits(submission.ddd or "")

            if submission.action == "skip":
                result_holder[0] = None
            else:
                if from_n8n:
                    from core.txt_builder import montar_linha_txt_n8n
                    line = montar_linha_txt_n8n(dados_base, item_lc=digits)
                else:
                    from core.txt_builder import montar_linha_txt
                    line = montar_linha_txt(dados_base, ddd=ddd_digits, item_lc=digits)
                result_holder[0] = line

        event.set()
        return {"accepted": True}

    def get_company_result(self, batch_id: str, company_cod: str):
        """Return stored ProcessorResult for a completed company (for download).

        Returns None if batch/company not found or not yet completed.
        """
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return None
            for row in batch["companies"]:
                if row["cod"] == company_cod:
                    return row.get("_result")
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_eta(company_rows: list[dict]) -> Optional[float]:
        """Compute ETA from average elapsed time of completed companies.

        Formula: avg_time_per_company * remaining_count
        Returns None if no companies are completed yet.
        """
        completed = [
            r for r in company_rows
            if r["status"] in ("completed", "ok", "error", "skipped")
        ]
        remaining = [r for r in company_rows if r["status"] in ("pending", "running")]

        if not completed or not remaining:
            return None

        total_elapsed = sum(r["elapsed_seconds"] for r in completed)
        avg = total_elapsed / len(completed)
        return avg * len(remaining)

    def _run_batch(
        self,
        batch_id: str,
        orc: BatchOrchestrator,
        q: queue.Queue,
        companies: list[dict],
        vigencia: str,
        job_dir,
        gerar_mei: bool,
    ):
        """Worker function — runs in a dedicated threading.Thread.

        Starts BatchOrchestrator.run() in a nested thread, then consumes
        queue messages to update per-company state.

        NOTA: o swap de cfg.BASE_DIR foi removido — o processor agora consulta
        a API Autmais diretamente e nao le mais notas do disco. job_dir e
        mantido como diretorio de saida do batch.
        """
        from pathlib import Path

        job_dir_path = Path(str(job_dir))

        try:
            # Start orchestrator in a nested thread (orc.run() is blocking)
            orc_thread = threading.Thread(
                target=orc.run,
                args=(companies, vigencia, job_dir_path, gerar_mei),
                daemon=True,
            )
            orc_thread.start()

            # Consumer loop
            while True:
                try:
                    msg = q.get(timeout=0.5)
                    self._handle_queue_msg(batch_id, msg)
                    if msg[0] == "batch_done":
                        break
                except queue.Empty:
                    # Check if orchestrator thread finished unexpectedly
                    if not orc_thread.is_alive():
                        break

            orc_thread.join(timeout=5.0)

        except Exception as exc:  # noqa: BLE001
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is not None:
                    batch["status"] = "error"
                    batch["summary"] = {"error": str(exc)}
        finally:
            # Clear analyst slot
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is not None:
                    analyst_name = batch.get("analyst_name")
                    if analyst_name:
                        self._job_manager._analyst_jobs.pop(analyst_name, None)

    def _handle_queue_msg(self, batch_id: str, msg: tuple):
        """Process a single queue message from BatchOrchestrator.

        Message types:
            ("company_start", cod, index, total)
            ("counter", cod, current, total)
            ("company_done", cod, status, notes, elapsed, error_detail)
            ("manual_review", dados_base, chave_nfse, from_n8n, event, result_holder)
            ("log", cod, message)
            ("batch_done", BatchSummary)
        """
        if not msg:
            return

        msg_type = msg[0]

        if msg_type == "company_start":
            _, cod, _idx, _total = msg
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    return
                batch["current_company_cod"] = cod
                row = self._find_row(batch, cod)
                if row is not None:
                    row["status"] = "running"

        elif msg_type == "counter":
            _, cod, current, total = msg
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    return
                row = self._find_row(batch, cod)
                if row is not None:
                    row["current_note"] = int(current)
                    row["total_notes"] = int(total)

        elif msg_type == "company_done":
            _, cod, status, notes, elapsed, error_detail = msg
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    return
                row = self._find_row(batch, cod)
                if row is not None:
                    # Normalize status: orchestrator uses "ok" but UI expects "completed"
                    row["status"] = "completed" if status == "ok" else status
                    row["total_notes"] = int(notes)
                    row["elapsed_seconds"] = float(elapsed)
                    row["error_detail"] = str(error_detail) if error_detail else ""

        elif msg_type == "manual_review":
            _, dados_base, chave_nfse, from_n8n, event, result_holder = msg
            timeout_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=300)).isoformat() + "Z"

            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    event.set()
                    return
                cod = batch.get("current_company_cod", "")
                batch["review_event"] = event
                batch["review_result"] = result_holder
                batch["review_dados_base"] = dados_base
                batch["review_company_cod"] = cod
                batch["review_item"] = {
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

            # Block OUTSIDE lock — same Phase 3 deadlock-prevention pattern
            triggered = event.wait(timeout=300)

            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is not None:
                    batch["review_item"] = None
                    batch["review_event"] = None
                    batch["review_result"] = None
                    batch["review_dados_base"] = None
                    batch["review_company_cod"] = None

            if not triggered:
                # Timeout — auto-accept AI suggestion
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
                result_holder[0] = line
                with self._lock:
                    batch = self._batches.get(batch_id)
                    if batch is not None:
                        cod = batch.get("current_company_cod", "?")
                        row = self._find_row(batch, cod)
                        if row is not None:
                            row["recent_logs"].append(
                                f"Auto-aceito por timeout: {chave_nfse}"
                            )
                            if len(row["recent_logs"]) > 5:
                                row["recent_logs"] = row["recent_logs"][-5:]

        elif msg_type == "log":
            _, cod, message = msg
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    return
                row = self._find_row(batch, cod)
                if row is not None:
                    row["recent_logs"].append(str(message))
                    if len(row["recent_logs"]) > 5:
                        row["recent_logs"] = row["recent_logs"][-5:]

        elif msg_type == "batch_done":
            _, summary = msg
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch is None:
                    return
                batch["current_company_cod"] = None
                batch["status"] = "aborted" if summary.aborted else "completed"
                batch["summary"] = {
                    "total": summary.total,
                    "successes": summary.successes,
                    "errors": summary.errors,
                    "skipped": summary.skipped,
                    "aborted": summary.aborted,
                    "elapsed_total_seconds": summary.elapsed_total_seconds,
                }

    @staticmethod
    def _find_row(batch: dict, cod: str) -> Optional[dict]:
        """Find a company row by cod. Returns None if not found."""
        for row in batch["companies"]:
            if row["cod"] == cod:
                return row
        return None


# Module-level singleton — import this in route handlers
from api.job_manager import job_manager  # noqa: E402
batch_job_manager = BatchJobManager(job_manager)
