"""Tests for scripts/migrate_companies.py — XLSX-to-Supabase migration.

All tests mock the Supabase client. No live Supabase connection required.
No live XLSX file required — tests build temporary XLSX files using tmp_xlsx fixture.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_migrate_xlsx(tmp_xlsx, rows, headers=None):
    """Build a realistic XLSX for migration tests.

    Default headers match the real RELACAO_EMPRESAS.xlsx layout including
    dynamic columns (CNPJ, MUNICIPIO, NOME EMPRESA).
    """
    if headers is None:
        headers = [
            "COD",            # index 0
            "RAZAO SOCIAL",   # index 1
            "",               # index 2 (unused)
            "ANALISTA",       # index 3
            "CNPJ",           # index 4 (dynamic)
            "MUNICIPIO",      # index 5 (dynamic)
            "ESTADO",         # index 6 (ignored)
            "IM",             # index 7
            "NOME EMPRESA",   # index 8 (dynamic)
        ]
    return tmp_xlsx(rows, headers=headers)


def _default_row(
    cod="001",
    razao="Empresa Teste",
    analista="ANA BEATRIZ",
    cnpj="12.345.678/0001-90",
    municipio="GOIANIA",
    estado="GO",
    im="123456",
    nome_empresa="Teste LTDA",
):
    """Return a default data row matching _make_migrate_xlsx headers."""
    return (cod, razao, None, analista, cnpj, municipio, estado, im, nome_empresa)


def _run_migrate(xlsx_path):
    """Import and call the migrate() function."""
    from scripts.migrate_companies import migrate
    return migrate(xlsx_path)


# ---------------------------------------------------------------------------
# Setup: patch env vars
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_migrate_env(monkeypatch):
    """Patch env vars required by migrate_companies.py before each test."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret-32-chars-minimum!!!")
    monkeypatch.setenv("UPLOAD_TEMP_DIR", "/tmp/test_uploads")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")


# ---------------------------------------------------------------------------
# Task 2 behavior tests
# ---------------------------------------------------------------------------

def test_migrate_reads_all_rows(tmp_xlsx):
    """Migration reads ALL rows regardless of municipality — no filter applied."""
    path = _make_migrate_xlsx(tmp_xlsx, [
        _default_row(cod="001", municipio="GOIANIA"),
        _default_row(cod="002", municipio="SAO PAULO"),
        _default_row(cod="003", municipio="BRASILIA"),
        _default_row(cod="004", municipio="MANAUS"),
    ])

    captured_records = []

    mock_result = MagicMock()
    mock_result.data = []

    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result

    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = lambda records, **kwargs: (
        captured_records.extend(records) or mock_upsert
    )

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)

    assert len(captured_records) == 4, (
        f"Expected 4 rows (all municipalities), got {len(captured_records)}"
    )


def test_migrate_extracts_7_columns(tmp_xlsx):
    """Each record contains all 7 required columns."""
    path = _make_migrate_xlsx(tmp_xlsx, [_default_row()])
    captured_records = []

    mock_result = MagicMock()
    mock_result.data = []
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result
    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = lambda records, **kwargs: (
        captured_records.extend(records) or mock_upsert
    )
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)

    assert len(captured_records) == 1
    record = captured_records[0]
    required_keys = {"cod", "razao", "analista", "municipio", "im", "cnpj", "nome_empresa"}
    assert required_keys == set(record.keys()), (
        f"Record keys mismatch. Expected {required_keys}, got {set(record.keys())}"
    )


def test_migrate_skips_empty_cod(tmp_xlsx):
    """Rows with empty/None COD column are silently skipped."""
    path = _make_migrate_xlsx(tmp_xlsx, [
        _default_row(cod="001"),
        (None, "No COD row", None, "ANA", "cnpj", "GOIANIA", "GO", "im", "nome"),  # empty cod
        ("", "Empty string COD", None, "ANA", "cnpj", "GOIANIA", "GO", "im", "nome"),  # empty str
        _default_row(cod="004"),
    ])
    captured_records = []

    mock_result = MagicMock()
    mock_result.data = []
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result
    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = lambda records, **kwargs: (
        captured_records.extend(records) or mock_upsert
    )
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)

    assert len(captured_records) == 2
    cods = [r["cod"] for r in captured_records]
    assert "001" in cods
    assert "004" in cods


def test_migrate_upserts_on_cod(tmp_xlsx):
    """Upsert call uses on_conflict='cod' for idempotency."""
    path = _make_migrate_xlsx(tmp_xlsx, [_default_row()])
    upsert_kwargs = {}

    mock_result = MagicMock()
    mock_result.data = []
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result

    def capture_upsert(records, **kwargs):
        upsert_kwargs.update(kwargs)
        return mock_upsert

    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = capture_upsert
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)

    assert upsert_kwargs.get("on_conflict") == "cod", (
        f"Expected on_conflict='cod', got: {upsert_kwargs}"
    )


def test_migrate_idempotent(tmp_xlsx):
    """Running migration twice with same data produces no duplicates (upsert semantics)."""
    path = _make_migrate_xlsx(tmp_xlsx, [
        _default_row(cod="001"),
        _default_row(cod="002"),
    ])

    upsert_call_args_list = []

    mock_result = MagicMock()
    mock_result.data = []
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result

    def capture_upsert(records, **kwargs):
        upsert_call_args_list.append(records[:])  # copy of records each run
        return mock_upsert

    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = capture_upsert
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)
        _run_migrate(path)

    # Both runs should have upserted the same 2 rows (not 4 — no accumulation)
    assert len(upsert_call_args_list) == 2
    assert len(upsert_call_args_list[0]) == 2
    assert len(upsert_call_args_list[1]) == 2
    # CODs must be identical across runs
    cods_run1 = {r["cod"] for r in upsert_call_args_list[0]}
    cods_run2 = {r["cod"] for r in upsert_call_args_list[1]}
    assert cods_run1 == cods_run2


def test_migrate_discovers_columns_by_header(tmp_xlsx):
    """CNPJ, MUNICIPIO, and NOME EMPRESA are found by header name, not hardcoded index."""
    # Put CNPJ and NOME EMPRESA in non-standard positions
    custom_headers = [
        "COD",         # 0
        "RAZAO SOCIAL",# 1
        "",            # 2
        "ANALISTA",    # 3
        "ESTADO",      # 4 (skip)
        "IM",          # 5 — NOTE: not at index 7 here
        "CNPJ",        # 6 — dynamic discovery
        "MUNICIPIO",   # 7 — dynamic discovery
        "NOME EMPRESA",# 8 — dynamic discovery
    ]
    path = tmp_xlsx([
        ("001", "Empresa X", None, "JOSE", "GO", "IM123", "11.222.333/0001-44", "GOIANIA", "Nome X"),
    ], headers=custom_headers)

    captured_records = []
    mock_result = MagicMock()
    mock_result.data = []
    mock_upsert = MagicMock()
    mock_upsert.execute.return_value = mock_result
    mock_table_obj = MagicMock()
    mock_table_obj.upsert.side_effect = lambda records, **kwargs: (
        captured_records.extend(records) or mock_upsert
    )
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table_obj

    with patch("scripts.migrate_companies.create_client", return_value=mock_client):
        _run_migrate(path)

    assert len(captured_records) == 1
    rec = captured_records[0]
    # These must be discovered dynamically — they're in non-standard positions
    assert rec["cnpj"] == "11.222.333/0001-44"
    assert rec["municipio"] == "GOIANIA"
    assert rec["nome_empresa"] == "Nome X"
