import pytest
from openpyxl import Workbook


def _make_xlsx(tmp_path, rows, headers=None):
    """Create a minimal XLSX file in tmp_path with given headers and rows.

    headers: list of column names for row 1 (default: ["COD", "EMPRESA", "MUNICIPIO", "ANALISTA"])
    rows: list of tuples — one per data row
    Returns: Path to the created .xlsx file.
    """
    if headers is None:
        headers = ["COD", "EMPRESA", "MUNICIPIO", "ANALISTA"]
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    path = tmp_path / "planilha.xlsx"
    wb.save(str(path))
    wb.close()
    return path


@pytest.fixture
def tmp_xlsx(tmp_path):
    """Factory fixture: call tmp_xlsx(rows, headers=None) to get an XLSX Path."""
    def _factory(rows, headers=None):
        return _make_xlsx(tmp_path, rows, headers)
    return _factory
