"""Tests for download endpoints in GET /jobs/{id}/download/... and GET /jobs/{id}/files.

All tests mock job_manager.get_status(), job_manager.get_result(), and
montar_cabecalho. No real processor execution occurs during tests.

Behaviors tested:
- test_download_txt_happy_path: returns 200, text/plain, correct Content-Disposition, no BOM
- test_download_txt_no_result: job not completed returns 409
- test_download_txt_not_found: unknown job_id returns 404
- test_download_txt_wrong_owner: another user's job returns 403
- test_download_csv_encoding: CSV body starts with UTF-8 BOM bytes
- test_download_csv_header: first row matches _CABECALHO exactly
- test_download_csv_filename: Content-Disposition filename is relatorio_{emp_cod}_{vigencia}.csv
- test_download_split_txt: returns split content with montar_cabecalho header as first line
- test_download_split_txt_not_found: unknown vigencia key returns 404
- test_files_metadata_shape: returns JobFilesResponse with required fields
- test_files_metadata_with_splits: notas_vig_errada entries appear as txt_split in files list
- test_files_metadata_no_splits: empty notas_vig_errada yields only main txt + csv
- test_files_metadata_not_ready: job not completed returns 409
"""
import csv
import io
import sys
import pytest
import httpx
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "user-uuid-5678"
TEST_EMAIL = "test@crosara.com.br"
TEST_ANALYST_NAME = "ANA BEATRIZ"
TEST_JOB_ID = "abc123def456"
TEST_EMP_COD = "001"
TEST_VIGENCIA = "2025-01"

_CSV_CABECALHO = [
    "Arquivo", "CNPJ Prestador", "Numero Nota", "Valor Documento",
    "Status", "Modo", "Detalhe", "Chave NFS-e", "Data/Hora Execucao", "Linha TXT"
]

COMPLETED_JOB_STATUS = {
    "job_id": TEST_JOB_ID,
    "status": "completed",
    "current_note": 10,
    "total_notes": 10,
    "percent": 100.0,
    "recent_logs": [],
    "errors": [],
    "user_id": TEST_USER_ID,
    "analyst_name": TEST_ANALYST_NAME,
    "emp_cod": TEST_EMP_COD,
    "vigencia": TEST_VIGENCIA,
    "created_at": "2026-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
# Mock ProcessorResult (simple object with __slots__ attributes)
# ---------------------------------------------------------------------------

class _FakeProcessorResult:
    __slots__ = (
        "linhas_dict", "relatorio", "notas_vig_errada",
        "im_tomador_cab", "razao_tomador_cab", "conteudo_final",
    )

    def __init__(self, notas_vig_errada=None):
        self.conteudo_final = "HEADER;LINE\nDATA;LINE"
        self.relatorio = [
            ("file.xml", "12345678000100", "001", "100.00", "OK",
             "auto", "", "NFSe-123", "2025-01-15 10:00", "DATA;LINE"),
            ("file2.xml", "12345678000100", "002", "50.00", "ERRO",
             "manual", "bad item", "NFSe-456", "2025-01-16 11:00", "BADLINE"),
        ]
        self.notas_vig_errada = notas_vig_errada if notas_vig_errada is not None else {
            "122024": ["SPLIT_LINE_1", "SPLIT_LINE_2"]
        }
        self.im_tomador_cab = "12345"
        self.razao_tomador_cab = "EMPRESA TESTE"
        self.linhas_dict = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_user(user_id: str = TEST_USER_ID, analyst_name: str = TEST_ANALYST_NAME):
    async def _fake_get_current_user():
        return {
            "user_id": user_id,
            "email": TEST_EMAIL,
            "analyst_name": analyst_name,
        }
    return _fake_get_current_user


# ---------------------------------------------------------------------------
# Setup: patch env vars so config_web and api.main can be imported cleanly
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
# TXT download tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_txt_happy_path():
    """GET /jobs/{id}/download/txt returns 200, text/plain, correct header, no BOM."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult()
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/txt")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Must be text/plain
    assert "text/plain" in response.headers.get("content-type", "")
    # Content-Disposition must be attachment with correct filename
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert f"{TEST_EMP_COD}_{TEST_VIGENCIA}.txt" in cd
    # Body must match conteudo_final, UTF-8 encoded, NO BOM
    body_bytes = response.content
    assert not body_bytes.startswith(b"\xef\xbb\xbf"), "TXT must not have BOM prefix"
    assert body_bytes == fake_result.conteudo_final.encode("utf-8")


@pytest.mark.asyncio
async def test_download_txt_no_result():
    """GET /jobs/{id}/download/txt when job not completed returns 409."""
    from api.main import app
    from api.deps import get_current_user

    running_status = {**COMPLETED_JOB_STATUS, "status": "running"}
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = running_status
            mock_jm.get_result.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/txt")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_download_txt_not_found():
    """GET /jobs/nonexistent/download/txt returns 404."""
    from api.main import app
    from api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/jobs/nonexistent/download/txt")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_txt_wrong_owner():
    """GET /jobs/{id}/download/txt for another user's job returns 403."""
    from api.main import app
    from api.deps import get_current_user

    other_user_status = {**COMPLETED_JOB_STATUS, "user_id": "other-user-uuid"}
    app.dependency_overrides[get_current_user] = _make_fake_user(user_id=TEST_USER_ID)
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = other_user_status
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/txt")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# CSV download tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_csv_encoding():
    """GET /jobs/{id}/download/csv body starts with UTF-8 BOM bytes and is text/csv."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult()
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    # Must start with UTF-8 BOM
    assert response.content.startswith(b"\xef\xbb\xbf"), "CSV must start with UTF-8 BOM"


@pytest.mark.asyncio
async def test_download_csv_header():
    """First row of CSV (after BOM) matches _CABECALHO exactly."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult()
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # Decode removing BOM via utf-8-sig
    text = response.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header_row = next(reader)
    assert header_row == _CSV_CABECALHO


@pytest.mark.asyncio
async def test_download_csv_filename():
    """Content-Disposition filename is 'relatorio_{emp_cod}_{vigencia}.csv'."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult()
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    cd = response.headers.get("content-disposition", "")
    assert "attachment" in cd
    expected_filename = f"relatorio_{TEST_EMP_COD}_{TEST_VIGENCIA}.csv"
    assert expected_filename in cd


# ---------------------------------------------------------------------------
# Split TXT download tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_split_txt():
    """GET /jobs/{id}/download/txt/{vigencia} returns split content with montar_cabecalho header."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult(notas_vig_errada={"122024": ["SPLIT_LINE_1", "SPLIT_LINE_2"]})
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            with patch("api.jobs.montar_cabecalho", return_value="MOCK_HEADER") as mock_cab:
                mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
                mock_jm.get_result.return_value = fake_result
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get(f"/jobs/{TEST_JOB_ID}/download/txt/122024")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body_text = response.content.decode("utf-8")
    lines = body_text.split("\n")
    # First line must be the montar_cabecalho output
    assert lines[0] == "MOCK_HEADER"
    # Remaining lines must be the split lines
    assert "SPLIT_LINE_1" in body_text
    assert "SPLIT_LINE_2" in body_text


@pytest.mark.asyncio
async def test_download_split_txt_not_found():
    """GET /jobs/{id}/download/txt/999999 returns 404 for unknown vigencia key."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult(notas_vig_errada={"122024": ["LINE"]})
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/download/txt/999999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Files metadata endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_files_metadata_shape():
    """GET /jobs/{id}/files returns JobFilesResponse with job_id, emp_cod, vigencia, summary, files."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult()
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == TEST_JOB_ID
    assert body["emp_cod"] == TEST_EMP_COD
    assert body["vigencia"] == TEST_VIGENCIA
    assert "summary" in body
    assert "files" in body
    summary = body["summary"]
    assert "total" in summary
    assert "errors" in summary
    assert "skipped" in summary


@pytest.mark.asyncio
async def test_files_metadata_with_splits():
    """When notas_vig_errada has entries, files list includes txt_split entries."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult(notas_vig_errada={"122024": ["SPLIT_LINE_1"], "012025": ["SPLIT_LINE_2"]})
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    files = body["files"]
    types = [f["type"] for f in files]
    # Must have main txt, csv, and 2 split entries
    assert "txt" in types
    assert "csv" in types
    split_entries = [f for f in files if f["type"] == "txt_split"]
    assert len(split_entries) == 2
    # URLs must reference the correct vigencia
    split_vigs = {f["vigencia"] for f in split_entries}
    assert split_vigs == {"122024", "012025"}
    for split_f in split_entries:
        assert f"/jobs/{TEST_JOB_ID}/download/txt/" in split_f["url"]


@pytest.mark.asyncio
async def test_files_metadata_no_splits():
    """When notas_vig_errada is empty, files list has only main txt and csv."""
    from api.main import app
    from api.deps import get_current_user

    fake_result = _FakeProcessorResult(notas_vig_errada={})
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = COMPLETED_JOB_STATUS.copy()
            mock_jm.get_result.return_value = fake_result
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    files = body["files"]
    assert len(files) == 2
    types = {f["type"] for f in files}
    assert types == {"txt", "csv"}


@pytest.mark.asyncio
async def test_files_metadata_not_ready():
    """GET /jobs/{id}/files when job not completed returns 409."""
    from api.main import app
    from api.deps import get_current_user

    queued_status = {**COMPLETED_JOB_STATUS, "status": "queued"}
    app.dependency_overrides[get_current_user] = _make_fake_user()
    try:
        with patch("api.jobs.job_manager") as mock_jm:
            mock_jm.get_status.return_value = queued_status
            mock_jm.get_result.return_value = None
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(f"/jobs/{TEST_JOB_ID}/files")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
