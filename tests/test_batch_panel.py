"""
Tests for ui/batch_panel.py — Phase 3 (SELEC-01..04, PROG-01..04, RESULT-02).

These stubs define the behavior contract that Wave 2 must satisfy.
Run: pytest tests/test_batch_panel.py -x -q
"""
import pytest
import tkinter as tk

# ---------------------------------------------------------------------------
# Import guard: tests are skipped until ui/batch_panel.py is created.
# Mirrors the pattern used in test_batch_orchestrator.py.
# ---------------------------------------------------------------------------
try:
    from ui.batch_panel import PainelLote
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False

try:
    from services.batch_orchestrator import BatchSummary, CompanyResult
    _ORCH_OK = True
except Exception:
    _ORCH_OK = False

pytestmark = pytest.mark.skipif(
    not _IMPORT_OK,
    reason="ui/batch_panel.py not yet implemented",
)


# ---------------------------------------------------------------------------
# SELEC-01 — Analyst list populated in combobox
# ---------------------------------------------------------------------------

def test_analyst_list_populated(tk_root):
    """_load_analysts_into_combobox() populates the analyst combobox values."""
    painel = PainelLote(tk_root)
    painel._load_analysts_into_combobox(["Ana", "Bia"])
    assert painel._cmb_analyst["values"] == ("Ana", "Bia")


# ---------------------------------------------------------------------------
# SELEC-02 — Vigencia input variable
# ---------------------------------------------------------------------------

def test_vigencia_input(tk_root):
    """_var_vigencia StringVar holds and returns the vigencia value."""
    painel = PainelLote(tk_root)
    painel._var_vigencia.set("012025")
    assert painel._var_vigencia.get() == "012025"


# ---------------------------------------------------------------------------
# SELEC-03 — Destination folder variable
# ---------------------------------------------------------------------------

def test_dest_folder_set(tk_root):
    """_var_dest StringVar holds and returns the destination folder path."""
    painel = PainelLote(tk_root)
    painel._var_dest.set("/tmp/saida")
    assert painel._var_dest.get() == "/tmp/saida"


# ---------------------------------------------------------------------------
# SELEC-04 — Start button disabled until all fields are filled
# ---------------------------------------------------------------------------

def test_start_disabled_until_all_fields(tk_root):
    """Start button is disabled initially; enabled when all fields are set."""
    painel = PainelLote(tk_root)
    # Initially disabled (no analyst, vigencia, or dest set)
    assert str(painel._btn_start["state"]) == "disabled"
    # Fill all three fields
    painel._cmb_analyst.set("Ana")
    painel._var_vigencia.set("012025")
    painel._var_dest.set("/tmp/saida")
    painel._update_start_state()
    assert str(painel._btn_start["state"]) == "normal"


# ---------------------------------------------------------------------------
# PROG-01 — Progress bar updates on company_start
# ---------------------------------------------------------------------------

def test_progress_bar_updates(tk_root):
    """_on_company_start() increments the progress bar value."""
    painel = PainelLote(tk_root)
    painel._on_company_start("001", 0, 5)
    assert painel._pb["value"] == 1
    assert painel._pb["maximum"] == 5


# ---------------------------------------------------------------------------
# PROG-02 — Current company label shows cod
# ---------------------------------------------------------------------------

def test_current_company_label(tk_root):
    """_on_company_start() sets the current company label to include the cod."""
    painel = PainelLote(tk_root)
    painel._on_company_start("001", 0, 5)
    assert "001" in painel._lbl_current.cget("text")


# ---------------------------------------------------------------------------
# PROG-03 — ETA label updates after first company done
# ---------------------------------------------------------------------------

def test_eta_after_first_done(tk_root):
    """_on_company_done() updates ETA label with 'ETA' text."""
    painel = PainelLote(tk_root)
    painel._total_companies = 3
    painel._on_company_done("001", "ok", 2, 10.0, "")
    assert "ETA" in painel._lbl_eta.cget("text")


# ---------------------------------------------------------------------------
# PROG-04 — Log entry appended
# ---------------------------------------------------------------------------

def test_log_entry_appended(tk_root):
    """_log() appends a line to the log text widget."""
    painel = PainelLote(tk_root)
    painel._log("empresa 001 ok", "ok")
    assert "001" in painel._txt_log.get("1.0", tk.END)


# ---------------------------------------------------------------------------
# RESULT-02 — Summary text lists errors with detail
# ---------------------------------------------------------------------------

def test_summary_lists_errors(tk_root):
    """_build_summary_text() includes error company cod and error detail."""
    painel = PainelLote(tk_root)
    summary = BatchSummary(
        total=2,
        successes=1,
        errors=1,
        skipped=0,
        aborted=False,
        company_results=[
            CompanyResult("002", "error", 0, 1.0, "Timeout"),
        ],
    )
    result = painel._build_summary_text(summary)
    assert "002" in result
    assert "Timeout" in result
