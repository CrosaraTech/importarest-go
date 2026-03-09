"""
services/batch_orchestrator.py — Phase 2 deliverable.

Provides thread-safe sequential company processing, queue-based progress
reporting, and the PROC-03 manual review pattern (queue.Queue + threading.Event).

Phase 3 (UI) imports and uses this module without any modifications here.
"""
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.processor import WorkflowProcessor
from core.txt_builder import montar_cabecalho


@dataclass
class CompanyResult:
    cod: str
    status: str            # "ok" | "error" | "skipped"
    notes_count: int
    elapsed_seconds: float
    error_detail: str


@dataclass
class BatchSummary:
    total: int
    successes: int
    errors: int
    skipped: int
    aborted: bool
    company_results: list = field(default_factory=list)
    elapsed_total_seconds: float = 0.0


class BatchOrchestrator:

    def __init__(self, q: queue.Queue):
        self._queue = q
        self._abort_event = threading.Event()
        self._results: list[CompanyResult] = []

    def abort(self):
        """Called from main thread (UI abort button). Thread-safe."""
        self._abort_event.set()

    def run(self, companies: list[dict], vigencia: str,
            dest_folder: Path, gerar_mei: bool = False):
        batch_start = time.monotonic()
        total = len(companies)
        for i, company in enumerate(companies):
            if self._abort_event.is_set():
                break
            cod = company["cod"]
            self._queue.put(("company_start", cod, i, total))
            self._process_one(cod, vigencia, dest_folder, gerar_mei)
        elapsed = time.monotonic() - batch_start
        summary = self._build_summary(total, self._abort_event.is_set(), elapsed)
        self._queue.put(("batch_done", summary))

    def _process_one(self, cod, vigencia, dest_folder, gerar_mei):
        t0 = time.monotonic()
        try:
            processor = WorkflowProcessor(
                log_fn=lambda msg: self._queue.put(("log", cod, msg)),
                progress_fn=lambda total: self._queue.put(("counter", cod, 0, total)),
                contador_fn=lambda a, t: self._queue.put(("counter", cod, a, t)),
                abrir_tela_manual_fn=self._make_manual_callback(cod),
                gerar_mei=gerar_mei,
            )
            result = processor.processar(cod, vigencia)
            if result is None:
                elapsed = time.monotonic() - t0
                self._record(cod, "skipped", 0, elapsed, "Pasta não encontrada")
                self._queue.put(("company_done", cod, "skipped", 0, elapsed, "Pasta não encontrada"))
                return
            self._save_txt(result, cod, vigencia, dest_folder)
            notes = len(result.linhas_dict)
            elapsed = time.monotonic() - t0
            self._record(cod, "ok", notes, elapsed, "")
            self._queue.put(("company_done", cod, "ok", notes, elapsed, ""))
        except Exception as exc:
            elapsed = time.monotonic() - t0
            self._record(cod, "error", 0, elapsed, str(exc))
            self._queue.put(("company_done", cod, "error", 0, elapsed, str(exc)))

    def _make_manual_callback(self, cod: str):
        def callback(dados_base: dict, chave_nfse: str,
                     from_n8n: bool = False) -> Optional[str]:
            event = threading.Event()
            result_holder = [None]
            self._queue.put(("manual_review", dados_base, chave_nfse,
                             from_n8n, event, result_holder))
            event.wait()          # blocks worker; releases GIL
            return result_holder[0]
        return callback

    def _save_txt(self, result, cod: str, vigencia: str, dest: Path):
        if result.conteudo_final:
            (dest / f"{cod}_{vigencia}.txt").write_text(
                result.conteudo_final, encoding="utf-8"
            )
        for vig_err, linhas in result.notas_vig_errada.items():
            dt_iso = f"{vig_err[2:]}-{vig_err[:2]}-01T00:00:00"
            cab = montar_cabecalho(result.im_tomador_cab,
                                   result.razao_tomador_cab, dt_iso)
            content = "\n".join(([cab] if cab else []) + linhas)
            (dest / f"{cod}_{vig_err}.txt").write_text(content, encoding="utf-8")

    def _record(self, cod, status, notes, elapsed, detail):
        self._results.append(
            CompanyResult(cod=cod, status=status, notes_count=notes,
                          elapsed_seconds=elapsed, error_detail=detail)
        )

    def _build_summary(self, total: int, aborted: bool,
                       elapsed: float) -> BatchSummary:
        return BatchSummary(
            total=total,
            successes=sum(1 for r in self._results if r.status == "ok"),
            errors=sum(1 for r in self._results if r.status == "error"),
            skipped=sum(1 for r in self._results if r.status == "skipped"),
            aborted=aborted,
            company_results=list(self._results),
            elapsed_total_seconds=elapsed,
        )
