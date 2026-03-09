"""
Tests for services/spreadsheet.py — Phase 1 (PLAN-01 through PLAN-05).

These tests drive the implementation in Plan 02.
Run: pytest tests/test_spreadsheet.py -x -q
"""
import zipfile
import pytest
from unittest.mock import patch

# Guard import: tests are collected as xfail until services/spreadsheet.py is created.
try:
    from services.spreadsheet import (
        load_analysts,
        get_companies_for_analyst,
        SpreadsheetAccessError,
        SpreadsheetFormatError,
    )
    _SPREADSHEET_AVAILABLE = True
except ImportError:
    _SPREADSHEET_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _SPREADSHEET_AVAILABLE,
    reason="services.spreadsheet not yet implemented (Plan 02 will create it)",
)


# ---------------------------------------------------------------------------
# PLAN-01 — load_analysts() returns a list from a valid XLSX
# ---------------------------------------------------------------------------

def test_load_analysts_returns_list(tmp_xlsx, monkeypatch):
    """load_analysts() returns a sorted list of analyst names present in GOIÂNIA rows."""
    path = tmp_xlsx([
        ("001", "Empresa A", "GOIÂNIA", "Ana"),
        ("002", "Empresa B", "GOIÂNIA", "Bia"),
        ("003", "Empresa C", "SAO PAULO", "Bia"),  # non-GOIÂNIA — excluded
    ])
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    result = load_analysts()
    assert isinstance(result, list)
    assert "Ana" in result
    assert "Bia" in result
    assert len(result) == 2  # SAO PAULO row excluded


# ---------------------------------------------------------------------------
# PLAN-02 — Only GOIÂNIA rows are included
# ---------------------------------------------------------------------------

def test_filters_goiania_only(tmp_xlsx, monkeypatch):
    """Rows with MUNICIPIO != 'GOIÂNIA' are excluded from results."""
    path = tmp_xlsx([
        ("001", "Empresa A", "GOIÂNIA", "Ana"),
        ("002", "Empresa B", "SAO PAULO", "Ana"),
        ("003", "Empresa C", "BRASILIA", "Ana"),
    ])
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    companies = get_companies_for_analyst("Ana")
    assert len(companies) == 1
    assert companies[0]["cod"] == "001"


# ---------------------------------------------------------------------------
# PLAN-03 — Missing required headers raise SpreadsheetFormatError
# ---------------------------------------------------------------------------

def test_missing_header_raises_format_error(tmp_xlsx, monkeypatch):
    """XLSX missing COD column in header row raises SpreadsheetFormatError."""
    # Headers without COD column
    path = tmp_xlsx(
        [("001", "Empresa A", "GOIÂNIA", "Ana")],
        headers=["CODIGO", "EMPRESA", "MUNICIPIO", "ANALISTA"],  # COD renamed
    )
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    with pytest.raises(SpreadsheetFormatError):
        load_analysts()


def test_missing_analista_header_raises_format_error(tmp_xlsx, monkeypatch):
    """XLSX missing ANALISTA column in header row raises SpreadsheetFormatError."""
    path = tmp_xlsx(
        [("001", "Empresa A", "GOIÂNIA", "Ana")],
        headers=["COD", "EMPRESA", "MUNICIPIO", "RESPONSAVEL"],  # ANALISTA renamed
    )
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    with pytest.raises(SpreadsheetFormatError):
        load_analysts()


# ---------------------------------------------------------------------------
# PLAN-04 — Access errors raise SpreadsheetAccessError
# ---------------------------------------------------------------------------

def test_missing_file_raises_access_error(tmp_path, monkeypatch):
    """Non-existent path raises SpreadsheetAccessError."""
    missing = tmp_path / "nao_existe.xlsx"
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", missing)
    with pytest.raises(SpreadsheetAccessError):
        load_analysts()


def test_locked_file_raises_access_error(tmp_xlsx, monkeypatch):
    """PermissionError from load_workbook is wrapped in SpreadsheetAccessError."""
    path = tmp_xlsx([("001", "Empresa A", "GOIÂNIA", "Ana")])
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    with patch("services.spreadsheet.load_workbook", side_effect=PermissionError):
        with pytest.raises(SpreadsheetAccessError) as exc_info:
            load_analysts()
    assert "aberta" in str(exc_info.value).lower() or "bloqueada" in str(exc_info.value).lower()


def test_corrupt_file_raises_format_error(tmp_xlsx, monkeypatch):
    """zipfile.BadZipFile from load_workbook is wrapped in SpreadsheetFormatError."""
    path = tmp_xlsx([("001", "Empresa A", "GOIÂNIA", "Ana")])
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    with patch("services.spreadsheet.load_workbook", side_effect=zipfile.BadZipFile):
        with pytest.raises(SpreadsheetFormatError):
            load_analysts()


# ---------------------------------------------------------------------------
# PLAN-05 — Company count per analyst
# ---------------------------------------------------------------------------

def test_company_count_per_analyst(tmp_xlsx, monkeypatch):
    """get_companies_for_analyst() returns exactly the GOIÂNIA companies for that analyst."""
    path = tmp_xlsx([
        ("001", "Empresa A", "GOIÂNIA", "Ana"),
        ("002", "Empresa B", "GOIÂNIA", "Ana"),
        ("003", "Empresa C", "GOIÂNIA", "Bia"),
        ("004", "Empresa D", "SAO PAULO", "Ana"),  # filtered out
    ])
    monkeypatch.setattr("services.spreadsheet.PLANILHA_EMPRESAS", path)
    result = get_companies_for_analyst("Ana")
    assert len(result) == 2
    cods = {r["cod"] for r in result}
    assert cods == {"001", "002"}
