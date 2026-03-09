"""
Tests for services/batch_orchestrator.py — Phase 2 (PROC-01 through PROC-04).

These stubs define the contract before implementation exists.
Run: pytest tests/test_batch_orchestrator.py -x -q
"""
import queue
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import guard: tests are skipped until services/batch_orchestrator.py is
# created (Plan 02).  Mirrors the pattern used in test_spreadsheet.py.
# ---------------------------------------------------------------------------
try:
    from services.batch_orchestrator import (
        BatchOrchestrator,
        BatchSummary,
        CompanyResult,
    )
    from services.processor import ProcessorResult
    _import_ok = True
except ImportError:
    _import_ok = False

pytestmark = pytest.mark.skipif(
    not _import_ok,
    reason="services.batch_orchestrator not yet implemented (Plan 02 will create it)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_result(conteudo="header\n2;line", linhas_dict=None,
                 notas_vig_errada=None):
    """Build a minimal ProcessorResult for use in tests."""
    return ProcessorResult(
        linhas_dict=linhas_dict if linhas_dict is not None else {"key": "2;line"},
        relatorio=[],
        notas_vig_errada=notas_vig_errada or {},
        im_tomador_cab="12345",
        razao_tomador_cab="EMPRESA TESTE",
        conteudo_final=conteudo,
    )


def _companies(*cods):
    """Return a list of company dicts with the given codes."""
    return [{"cod": c} for c in cods]


def _drain_queue(q):
    """Return all messages currently on the queue as a list."""
    msgs = []
    while True:
        try:
            msgs.append(q.get_nowait())
        except queue.Empty:
            break
    return msgs


def _last_message(q):
    """Drain queue and return the last message."""
    return _drain_queue(q)[-1]


# ---------------------------------------------------------------------------
# PROC-01 — test_run_processes_all_companies
# ---------------------------------------------------------------------------

def test_run_processes_all_companies(tmp_path, monkeypatch):
    """processar() is called once per company; batch_done is the last queue event."""
    call_log = []

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            pass

        def processar(self, cod, vigencia):
            call_log.append(cod)
            return _fake_result()

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(_companies("001", "002", "003"), "0125", tmp_path)

    assert call_log == ["001", "002", "003"], (
        f"Expected processar called 3 times; got {call_log}"
    )
    msgs = _drain_queue(q)
    last = msgs[-1]
    assert last[0] == "batch_done", f"Last message should be 'batch_done', got {last[0]!r}"


# ---------------------------------------------------------------------------
# PROC-02 — test_company_error_continues_loop
# ---------------------------------------------------------------------------

def test_company_error_continues_loop(tmp_path, monkeypatch):
    """Exception on company[0] is caught; loop continues for companies[1] and [2]."""
    call_log = []

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            self._cod_capture = None

        def processar(self, cod, vigencia):
            call_log.append(cod)
            if cod == "001":
                raise Exception("simulated failure on 001")
            return _fake_result()

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(_companies("001", "002", "003"), "0125", tmp_path)

    assert len(call_log) == 3, (
        f"processar should be called for all 3 companies; called for {call_log}"
    )

    msgs = _drain_queue(q)
    company_done_msgs = [m for m in msgs if m[0] == "company_done"]

    # company_done tuple: ("company_done", cod, status, notes_count, elapsed, detail)
    status_by_cod = {m[1]: m[2] for m in company_done_msgs}
    assert status_by_cod.get("001") == "error", (
        f"company 001 should have status 'error'; got {status_by_cod.get('001')!r}"
    )
    assert status_by_cod.get("002") == "ok", (
        f"company 002 should have status 'ok'; got {status_by_cod.get('002')!r}"
    )


# ---------------------------------------------------------------------------
# PROC-03 — test_manual_review_queue_event_protocol
# ---------------------------------------------------------------------------

def test_manual_review_queue_event_protocol(tmp_path, monkeypatch):
    """Worker emits 'manual_review' on queue; unblocks when event is set."""

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            self._fn = abrir_tela_manual_fn

        def processar(self, cod, vigencia):
            # Trigger the manual review callback, which should put a message on
            # the queue and block until event.set() is called.
            result = self._fn({"dado": "x"}, "chave_" + cod, from_n8n=True)
            return _fake_result()

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)

    # Run orchestrator in background thread — it will block on event.wait()
    t = threading.Thread(
        target=orc.run,
        args=(_companies("001"), "0125", tmp_path),
        daemon=True,
    )
    t.start()

    # Drain queue until we get the manual_review message
    manual_msg = None
    for _ in range(50):
        try:
            msg = q.get(timeout=0.2)
            if msg[0] == "manual_review":
                manual_msg = msg
                break
        except queue.Empty:
            continue

    assert manual_msg is not None, "Expected 'manual_review' message on queue"

    # manual_review tuple: ("manual_review", dados_base, chave_nfse, from_n8n, event, result_holder)
    _, dados_base, chave_nfse, from_n8n, event, result_holder = manual_msg

    assert isinstance(dados_base, dict), "dados_base must be a dict"
    assert isinstance(chave_nfse, str), "chave_nfse must be a str"
    assert isinstance(from_n8n, bool), "from_n8n must be a bool"
    assert isinstance(event, threading.Event), "event must be a threading.Event"
    assert isinstance(result_holder, list) and len(result_holder) == 1, (
        "result_holder must be a 1-element list"
    )
    assert result_holder[0] is None, "result_holder[0] must start as None"

    # Simulate main thread responding
    result_holder[0] = "2;data;linha_manual"
    event.set()

    t.join(timeout=5)
    assert not t.is_alive(), "Orchestrator thread should have finished after event.set()"


# ---------------------------------------------------------------------------
# PROC-04 — test_abort_stops_after_current_company
# ---------------------------------------------------------------------------

def test_abort_stops_after_current_company(tmp_path, monkeypatch):
    """Calling abort() before run() causes zero companies to be processed."""
    call_log = []

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            pass

        def processar(self, cod, vigencia):
            call_log.append(cod)
            return _fake_result()

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.abort()  # abort BEFORE run() — loop should exit immediately
    orc.run(_companies("001", "002", "003"), "0125", tmp_path)

    assert call_log == [], (
        f"No company should be processed after pre-abort; got {call_log}"
    )

    msgs = _drain_queue(q)
    last = msgs[-1]
    assert last[0] == "batch_done", f"Expected 'batch_done', got {last[0]!r}"
    summary = last[1]
    assert isinstance(summary, BatchSummary), "Last message payload must be a BatchSummary"
    assert summary.aborted is True, "summary.aborted must be True"
    assert summary.successes == 0, f"successes must be 0; got {summary.successes}"


# ---------------------------------------------------------------------------
# PROC-02 (supporting) — test_none_result_is_skipped
# ---------------------------------------------------------------------------

def test_none_result_is_skipped(tmp_path, monkeypatch):
    """processar() returning None is status='skipped', not 'error'."""

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            pass

        def processar(self, cod, vigencia):
            return None  # no folder found

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(_companies("001"), "0125", tmp_path)

    msgs = _drain_queue(q)
    company_done = next((m for m in msgs if m[0] == "company_done"), None)
    assert company_done is not None, "Expected a company_done message"

    # ("company_done", cod, status, notes_count, elapsed, detail)
    _, cod, status, notes_count, elapsed, detail = company_done
    assert status == "skipped", f"Expected 'skipped', got {status!r}"
    assert notes_count == 0, f"notes_count must be 0 for skipped; got {notes_count}"

    last = msgs[-1]
    assert last[0] == "batch_done"
    summary = last[1]
    assert summary.skipped == 1, f"summary.skipped must be 1; got {summary.skipped}"
    assert summary.errors == 0, f"summary.errors must be 0; got {summary.errors}"


# ---------------------------------------------------------------------------
# PROC-01 (supporting) — test_txt_saved_to_dest_folder
# ---------------------------------------------------------------------------

def test_txt_saved_to_dest_folder(tmp_path, monkeypatch):
    """ProcessorResult.conteudo_final is written to {cod}_{vigencia}.txt."""
    expected_content = "header\n2;line1\n2;line2"

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            pass

        def processar(self, cod, vigencia):
            return _fake_result(conteudo=expected_content)

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(_companies("001"), "0125", tmp_path)

    expected_file = tmp_path / "001_0125.txt"
    assert expected_file.exists(), (
        f"Expected file {expected_file} to exist after run"
    )
    content = expected_file.read_text(encoding="utf-8")
    assert content == expected_content, (
        f"File content mismatch.\nExpected: {expected_content!r}\nGot: {content!r}"
    )


# ---------------------------------------------------------------------------
# PROC-01 (supporting) — test_overflow_vig_txt_saved
# ---------------------------------------------------------------------------

def test_overflow_vig_txt_saved(tmp_path, monkeypatch):
    """ProcessorResult.notas_vig_errada produces {cod}_{vig_errada}.txt files."""

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            pass

        def processar(self, cod, vigencia):
            return _fake_result(
                conteudo="",  # no primary content
                linhas_dict={},
                notas_vig_errada={"0125": ["2;linha_overflow"]},
            )

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    # Patch montar_cabecalho to return empty string (no header needed)
    monkeypatch.setattr(
        "services.batch_orchestrator.montar_cabecalho",
        lambda im, razao, dt: "",
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(_companies("001"), "0225", tmp_path)

    overflow_file = tmp_path / "001_0125.txt"
    assert overflow_file.exists(), (
        f"Expected overflow file {overflow_file} to exist"
    )


# ---------------------------------------------------------------------------
# PROC-01 (supporting) — test_batch_summary_counts
# ---------------------------------------------------------------------------

def test_batch_summary_counts(tmp_path, monkeypatch):
    """BatchSummary totals are correct: 2 ok, 1 error, 1 skipped."""

    class FakeProcessor:
        def __init__(self, log_fn, progress_fn, contador_fn,
                     abrir_tela_manual_fn, gerar_mei=False):
            self._cod = None  # stored below

        def processar(self, cod, vigencia):
            if cod == "error_co":
                raise Exception("forced error")
            if cod == "skip_cod":
                return None
            return _fake_result()

    monkeypatch.setattr(
        "services.batch_orchestrator.WorkflowProcessor", FakeProcessor
    )

    q = queue.Queue()
    orc = BatchOrchestrator(q)
    orc.run(
        _companies("ok_001", "ok_002", "error_co", "skip_cod"),
        "0125",
        tmp_path,
    )

    msgs = _drain_queue(q)
    last = msgs[-1]
    assert last[0] == "batch_done"
    s = last[1]
    assert isinstance(s, BatchSummary)
    assert s.total == 4, f"total should be 4; got {s.total}"
    assert s.successes == 2, f"successes should be 2; got {s.successes}"
    assert s.errors == 1, f"errors should be 1; got {s.errors}"
    assert s.skipped == 1, f"skipped should be 1; got {s.skipped}"
    assert s.aborted is False, f"aborted should be False; got {s.aborted}"
