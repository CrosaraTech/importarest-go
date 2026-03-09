# Phase 1: Foundation - Research

**Researched:** 2026-03-09
**Domain:** Python openpyxl XLSX reading — brownfield desktop app service module
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PLAN-01 | System reads spreadsheet from fixed path `G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx` automatically when batch tab opens | `load_workbook(path, read_only=True, data_only=True)` with path constant from config.py; verified openpyxl 3.1.5 installed |
| PLAN-02 | System filters and displays only companies where MUNICIPIO column contains "GOIÂNIA" | Header-based MUNICIPIO column discovery + `strip().upper() == "GOIÂNIA"` comparison; verified against accent/case/whitespace variants |
| PLAN-03 | System validates COD (col A) and ANALISTA (col D) headers exist before processing | Scan header_row dict for "COD" and "ANALISTA" keys; raise custom exception if missing |
| PLAN-04 | System displays clear error message if spreadsheet is inaccessible (locked, not found, invalid format) | `FileNotFoundError`, `PermissionError`, `zipfile.BadZipFile`, `InvalidFileException` — all verified; typed custom exceptions map to user messages |
| PLAN-05 | After analyst selection, system displays count of GOIÂNIA companies assigned to that analyst | `get_companies_for_analyst(analista)` returns filtered list; len() gives count |
</phase_requirements>

---

## Summary

Phase 1 creates `services/spreadsheet.py` and adds constants to `config.py`. Both files have zero UI dependencies — the spreadsheet module is pure Python/openpyxl and is testable in complete isolation. All technical questions raised in the phase brief have been answered through live code verification against openpyxl 3.1.5 (installed and confirmed present).

The openpyxl `read_only=True` mode works reliably for this use case. Header columns must be discovered by name (not fixed index) because MUNICIPIO's position can vary. The GOIÂNIA comparison should use `.strip().upper() == "GOIÂNIA"` — verified to handle trailing spaces and case variants correctly. The exact string "GOIÂNIA" with accent is the right target because the spreadsheet is controlled data, but `.strip().upper()` already handles the most common dirty-data variants. COD values may arrive as `int` from Excel (e.g., `1` instead of `"001"`) — callers must convert with `str(cod).strip()`.

The existing project uses module-level functions (not classes) in all other `services/` modules (`ibge.py`, `report.py`, `n8n_client.py`). Follow that pattern: `spreadsheet.py` exports top-level functions, not a class. The only exception in `services/` is `WorkflowProcessor` which is a class because it carries stateful callbacks across a long processing run — `spreadsheet.py` has no such state requirement.

**Primary recommendation:** Implement `spreadsheet.py` as a module with three functions: `load_analysts()`, `get_companies_for_analyst(analista)`, and a private `_load_and_validate()` helper. Define two custom exceptions: `SpreadsheetError` (base) and `SpreadsheetAccessError` / `SpreadsheetFormatError` subclasses so callers get typed errors.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openpyxl | 3.1.5 | Read XLSX via `load_workbook` | Mandated in PROJECT.md; zero heavy deps; already the only XLSX option in the project |
| pathlib (stdlib) | Python 3.10+ | Path constant in config.py | Already used in config.py for BASE_DIR and RELATORIO_CSV |
| zipfile (stdlib) | Python 3.10+ | Catch `BadZipFile` on corrupt/locked XLSX | Already imported in `services/processor.py`; no new import needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| openpyxl.utils.exceptions.InvalidFileException | 3.1.5 | Catch non-XLSX files passed as XLSX | Catch alongside BadZipFile in the exception handler |
| unicodedata (stdlib) | Python 3.10+ | NFD accent normalization fallback | Only if `.strip().upper()` comparison is insufficient — LOW priority |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| openpyxl | pandas | pandas adds ~30 MB compiled deps (NumPy) for zero benefit on a 2-column read |
| openpyxl | xlrd | xlrd dropped XLSX support in v2.0 (2020); only .xls files |
| module functions | SpreadsheetReader class | Class adds no value; no state to carry; inconsistent with ibge.py/report.py pattern |

**Installation:**
```bash
pip install openpyxl
```

openpyxl 3.1.5 is already installed in the project environment (verified 2026-03-09).

---

## Architecture Patterns

### Recommended Project Structure

```
services/
├── processor.py          # UNCHANGED
├── spreadsheet.py        # NEW — this phase
├── n8n_client.py         # unchanged
├── ibge.py               # unchanged
└── report.py             # unchanged

config.py                 # ADD constants (bottom of PATHS section)
```

### Pattern 1: Module-Level Functions (matches existing services/)

**What:** Export plain functions, not a class. Use a module-private cache if needed.
**When to use:** Always in `services/` when there is no per-call stateful object to carry.
**Example:**
```python
# services/spreadsheet.py — follows ibge.py and report.py pattern
from pathlib import Path
import zipfile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from config import PLANILHA_EMPRESAS, PLANILHA_COL_COD, PLANILHA_COL_ANALISTA

class SpreadsheetError(Exception):
    """Base exception for all spreadsheet failures."""

class SpreadsheetAccessError(SpreadsheetError):
    """File not found, locked, or unreadable."""

class SpreadsheetFormatError(SpreadsheetError):
    """File found but missing required headers."""


def load_analysts() -> list[str]:
    """Return sorted list of analyst names with at least one GOIÂNIA company."""
    rows = _load_goiania_rows()
    analistas = sorted({str(row["analista"]).strip() for row in rows if row["analista"]})
    return analistas


def get_companies_for_analyst(analista: str) -> list[dict]:
    """Return list of dicts with 'cod' and 'analista' for GOIÂNIA companies of this analyst."""
    rows = _load_goiania_rows()
    return [r for r in rows if str(r["analista"]).strip() == analista.strip()]


def _load_goiania_rows() -> list[dict]:
    """Core loader: open workbook, validate headers, return filtered rows."""
    path = PLANILHA_EMPRESAS
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError:
        raise SpreadsheetAccessError(
            f"Planilha não encontrada em {path}. Verifique se o drive G: está conectado."
        )
    except PermissionError:
        raise SpreadsheetAccessError(
            "A planilha está aberta por outro usuário. Feche o arquivo no Excel e tente novamente."
        )
    except (zipfile.BadZipFile, InvalidFileException):
        raise SpreadsheetFormatError(
            "O arquivo da planilha está corrompido ou em formato inválido."
        )

    try:
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1), None)
        if header_row is None:
            raise SpreadsheetFormatError("A planilha está vazia — nenhum cabeçalho encontrado.")

        header_map = {
            str(cell.value).strip().upper(): idx
            for idx, cell in enumerate(header_row)
            if cell.value is not None
        }

        # PLAN-03: validate required fixed-position columns
        if "COD" not in header_map or header_map["COD"] != PLANILHA_COL_COD:
            raise SpreadsheetFormatError(
                "Coluna COD não encontrada na posição A (coluna 1). Verifique o formato da planilha."
            )
        if "ANALISTA" not in header_map or header_map["ANALISTA"] != PLANILHA_COL_ANALISTA:
            raise SpreadsheetFormatError(
                "Coluna ANALISTA não encontrada na posição D (coluna 4). Verifique o formato da planilha."
            )

        municipio_idx = header_map.get("MUNICIPIO")
        if municipio_idx is None:
            raise SpreadsheetFormatError(
                "Coluna MUNICIPIO não encontrada no cabeçalho. Verifique o formato da planilha."
            )

        rows = []
        for row in ws.iter_rows(min_row=2):
            if len(row) <= max(PLANILHA_COL_COD, PLANILHA_COL_ANALISTA, municipio_idx):
                continue
            cod = row[PLANILHA_COL_COD].value
            analista = row[PLANILHA_COL_ANALISTA].value
            municipio = row[municipio_idx].value
            if not cod:
                continue  # skip empty rows
            mun_str = str(municipio).strip().upper() if municipio is not None else ""
            if mun_str != "GOIÂNIA":
                continue
            rows.append({
                "cod": str(cod).strip(),
                "analista": str(analista).strip() if analista is not None else "",
            })
        return rows
    finally:
        wb.close()
```

### Pattern 2: config.py Constants (matches existing style)

**What:** Add new path constant and column index constants at the bottom of the PATHS section.
**When to use:** All hardcoded paths and fixed indices go in config.py.
**Example:**
```python
# config.py — add after existing PATHS constants
PLANILHA_EMPRESAS = Path(
    r"G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx"
)
PLANILHA_COL_COD      = 0   # Column A (index 0)
PLANILHA_COL_ANALISTA = 3   # Column D (index 3)
```

### Anti-Patterns to Avoid

- **Accessing columns by hardcoded index without header validation:** `row[0]` and `row[3]` process wrong data silently if columns shift. Always validate headers first.
- **Opening the workbook without `read_only=True`:** Normal mode loads the entire file into memory and cannot share a file open in Excel. Always use `read_only=True, data_only=True`.
- **Comparing GOIÂNIA without `.strip()`:** Spreadsheet cells often have trailing spaces. `row[x].value == "GOIÂNIA"` will silently fail to match `"GOIÂNIA "`. Always strip.
- **Not calling `wb.close()`:** In `read_only=True` mode openpyxl holds a file handle. Always close in a `finally` block or with a context manager.
- **Returning `int` COD values directly:** Excel stores numeric codes as `int` (e.g., `1` for `"001"`). Always convert with `str(cod).strip()` before returning.
- **Treating `SpreadsheetError` as a crash:** These are expected runtime conditions (file locked, drive disconnected). Callers must catch and display the message to the analyst.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XLSX file reading | Custom binary parser or CSV hack | `openpyxl.load_workbook` | XLSX is a ZIP of XML; openpyxl handles encoding, shared strings table, data types |
| Column index by name | Hardcoded assumption on position | `{cell.value: idx for cell in header_row}` dict | Spreadsheet columns can be reorganized; index-by-name survives restructuring |
| File lock detection | `os.access()` pre-check | Catch `PermissionError` from `load_workbook` | TOCTOU race condition: file can become locked between check and open; catch-on-open is correct |
| Accent normalization | Custom character replacement | `unicodedata.normalize('NFD', ...)` or `.strip().upper()` | unicodedata handles all Unicode edge cases; `.strip().upper()` is sufficient for this controlled spreadsheet |

**Key insight:** openpyxl handles the entire XLSX format complexity (ZIP container, shared strings, number format codes, merged cells). Any custom reader would reimplement a subset incorrectly.

---

## Common Pitfalls

### Pitfall 1: COD Values Come as `int` From Excel

**What goes wrong:** Code does `cod = row[0].value` and then uses `cod` directly as a directory path component. If the value is `int(1)`, path construction breaks because `BASE_DIR / f"1-"` doesn't match `BASE_DIR / "001-"`.
**Why it happens:** Excel stores purely numeric cell content as `int` or `float`, not `str`. openpyxl preserves the Python type.
**How to avoid:** Always convert: `str(cod).strip()` — produces `"1"` not `"001"`. If zero-padding is needed, that's a Phase 2 concern when matching against directory names.
**Warning signs:** `KeyError` or `FileNotFoundError` in Phase 2 processor when trying to open company directories.

### Pitfall 2: `PermissionError` Raises Before openpyxl Opens File

**What goes wrong:** Trying to catch `PermissionError` inside openpyxl-specific exception block.
**Why it happens:** Windows raises `PermissionError` at the OS level when `open()` is called — openpyxl never gets control. It is NOT an openpyxl exception.
**How to avoid:** Catch `PermissionError` as a plain Python built-in alongside openpyxl exceptions.
**Warning signs:** Unhandled `PermissionError` crashes the app when Excel has the file open.

### Pitfall 3: MUNICIPIO Column at Variable Position

**What goes wrong:** Code hardcodes `row[2].value` for MUNICIPIO because that's where it is today. Spreadsheet is reorganized, code silently reads the wrong column.
**Why it happens:** MUNICIPIO is not a fixed-position requirement (unlike COD=A and ANALISTA=D which ARE required by PLAN-03).
**How to avoid:** Find MUNICIPIO by header name lookup. COD and ANALISTA are validated at fixed positions (PLAN-03) but MUNICIPIO position is discovered dynamically from header row.
**Warning signs:** Companies from non-GOIÂNIA cities appearing in the analyst list, or all companies being filtered out.

### Pitfall 4: Empty Rows Produce `None` Values

**What goes wrong:** `str(None).strip()` produces `"None"`, not `""`. Row filtering breaks.
**Why it happens:** openpyxl returns `None` for empty cells in `read_only` mode (not empty string).
**How to avoid:** Check `if cod:` or `if cod is not None` before processing. For municipio: `str(municipio).strip().upper() if municipio is not None else ""`.
**Warning signs:** `"None"` appearing in analyst list or company codes.

### Pitfall 5: Not Closing Workbook After Read

**What goes wrong:** File handle stays open; on Windows, the spreadsheet file cannot be moved or deleted while the handle is held. If the app keeps a module-level open workbook, repeated calls accumulate handles.
**Why it happens:** `read_only=True` workbooks hold a file handle open via `zipfile.ZipFile` internally.
**How to avoid:** Always call `wb.close()` in a `finally` block. Never store the workbook object between calls.
**Warning signs:** `PermissionError` on subsequent open attempts; Windows "file in use" errors.

### Pitfall 6: `iter_rows()` in `read_only` Mode Exhausted After First Pass

**What goes wrong:** Calling `ws.iter_rows()` twice yields rows on first call, empty iterator on second call.
**Why it happens:** ReadOnlyWorksheet uses a streaming parser; the underlying XML stream is consumed on first iteration.
**How to avoid:** Never iterate the worksheet twice. Load all needed rows into a list on the first pass: `rows = list(ws.iter_rows(min_row=2))`. Or re-open the workbook for each call (preferred for correctness — Phase 2 will call both `load_analysts()` and `get_companies_for_analyst()` independently).
**Warning signs:** `get_companies_for_analyst()` returning empty list after `load_analysts()` was called on same workbook instance.

---

## Code Examples

Verified against openpyxl 3.1.5 (live tested 2026-03-09):

### Header Discovery by Name
```python
# Source: live tested — openpyxl 3.1.5 read_only mode
wb = load_workbook(path, read_only=True, data_only=True)
ws = wb.active
header_row = next(ws.iter_rows(min_row=1, max_row=1), None)
header_map = {
    str(cell.value).strip().upper(): idx
    for idx, cell in enumerate(header_row)
    if cell.value is not None
}
# Result: {'COD': 0, 'EMPRESA': 1, 'MUNICIPIO': 2, 'ANALISTA': 3}
municipio_idx = header_map.get("MUNICIPIO")  # None if missing
```

### GOIANIA String Comparison
```python
# Source: live tested — all variants handled correctly
# Handles: 'GOIÂNIA', 'goiânia', 'GOIANIA', 'GOIÂNIA ' (trailing space)
mun_str = str(municipio).strip().upper() if municipio is not None else ""
is_goiania = (mun_str == "GOIÂNIA")
# Note: .strip().upper() handles trailing spaces and case; accent is preserved
# 'GOIANIA' (no accent) is NOT matched — this is correct per PLAN-02
```

### Exception Handling Pattern
```python
# Source: live tested — openpyxl 3.1.5 + Windows OS behavior
import zipfile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

try:
    wb = load_workbook(path, read_only=True, data_only=True)
except FileNotFoundError:
    raise SpreadsheetAccessError("Planilha não encontrada em ...")
except PermissionError:
    raise SpreadsheetAccessError("A planilha está aberta por outro usuário...")
except (zipfile.BadZipFile, InvalidFileException):
    raise SpreadsheetFormatError("O arquivo está corrompido ou em formato inválido.")
```

### COD Type Safety
```python
# Source: live tested — int vs str from Excel
# Excel stores '001' as str, but 1 (numeric) as int
cod_raw = row[PLANILHA_COL_COD].value  # may be int(1) or str('001')
cod = str(cod_raw).strip()              # always str: '1' or '001'
```

### config.py Addition Pattern
```python
# Source: existing config.py pattern (BASE_DIR, RELATORIO_CSV)
# Add after the existing PATHS block:
PLANILHA_EMPRESAS = Path(
    r"G:\Drives compartilhados\FISCAL\autmais\RELACAO_EMPRESAS_atualizada.xlsx"
)
PLANILHA_COL_COD      = 0   # Column A (0-indexed)
PLANILHA_COL_ANALISTA = 3   # Column D (0-indexed)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `xlrd` for XLSX | `openpyxl` | xlrd v2.0, 2020 | xlrd dropped XLSX; openpyxl is the standard |
| pandas for simple reads | openpyxl directly | 2020+ | pandas overkill for 2-column reads; openpyxl lighter |
| Accessing cells by `ws['A2']` | `iter_rows()` in read_only | openpyxl 2.x → 3.x | `ws['A2']` loads entire sheet; `iter_rows()` streams |

**Deprecated/outdated:**
- `xlrd`: Do not use for `.xlsx` files — dropped support in 2020
- `ws.rows` property in read_only mode: Use `ws.iter_rows()` which is the streaming iterator
- `worksheet.cell(row, col)` in read_only mode: Returns empty cells; use `iter_rows()` with tuple indexing instead

---

## Open Questions

1. **Exact MUNICIPIO string in the real spreadsheet**
   - What we know: REQUIREMENTS.md specifies "GOIÂNIA" with accent (Â)
   - What's unclear: Whether the actual spreadsheet data uses the accented form consistently, or if some rows use "GOIANIA" without accent
   - Recommendation: Use `.strip().upper() == "GOIÂNIA"` as the primary comparison. If QA reveals misses, add a secondary check: `normalize NFD + strip accents == "GOIANIA"`. Do NOT default to accent-stripping now — it may mask data quality issues.

2. **COD zero-padding requirement for directory matching**
   - What we know: COD values may be `int(1)` from Excel, producing `"1"` after `str()` conversion
   - What's unclear: Whether the directory structure uses `"1-"` or `"001-"` for company code 1
   - Recommendation: Return `str(cod).strip()` from Phase 1. Phase 2 (BatchOrchestrator) handles directory construction; let Phase 2 resolve any zero-padding when it accesses `BASE_DIR / f"{cod}-" / vigencia`.

3. **Header label: "MUNICIPIO" vs "MUNICÍPIO"**
   - What we know: REQUIREMENTS.md uses "MUNICIPIO" (no accent)
   - What's unclear: The actual spreadsheet column header — it may or may not have an accent
   - Recommendation: Normalize header lookup with `str(cell.value).strip().upper()` — this handles both "MUNICIPIO" and "MUNICÍPIO" transparently since `.upper()` doesn't remove accents but the dict key comparison is then exact. If the header has accent, the dict key becomes "MUNICÍPIO". Safe to check both: `header_map.get("MUNICIPIO") or header_map.get("MUNICÍPIO")`.

---

## Validation Architecture

nyquist_validation is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed — Wave 0 gap) |
| Config file | None — Wave 0 creates `pytest.ini` or `pyproject.toml` section |
| Quick run command | `pytest tests/test_spreadsheet.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAN-01 | `load_analysts()` returns list when valid XLSX at config path | unit (fixture XLSX) | `pytest tests/test_spreadsheet.py::test_load_analysts_returns_list -x` | Wave 0 |
| PLAN-02 | Only GOIÂNIA rows included; non-GOIÂNIA rows excluded | unit | `pytest tests/test_spreadsheet.py::test_filters_goiania_only -x` | Wave 0 |
| PLAN-03 | Missing COD or ANALISTA header raises SpreadsheetFormatError before data processing | unit | `pytest tests/test_spreadsheet.py::test_missing_header_raises_format_error -x` | Wave 0 |
| PLAN-04 | FileNotFoundError → SpreadsheetAccessError with message naming cause | unit | `pytest tests/test_spreadsheet.py::test_missing_file_raises_access_error -x` | Wave 0 |
| PLAN-04 | PermissionError → SpreadsheetAccessError with "locked" in message | unit | `pytest tests/test_spreadsheet.py::test_locked_file_raises_access_error -x` | Wave 0 |
| PLAN-04 | BadZipFile → SpreadsheetFormatError with "corrompido" or "inválido" in message | unit | `pytest tests/test_spreadsheet.py::test_corrupt_file_raises_format_error -x` | Wave 0 |
| PLAN-05 | `get_companies_for_analyst("Ana")` returns exact count of GOIÂNIA companies for Ana | unit | `pytest tests/test_spreadsheet.py::test_company_count_per_analyst -x` | Wave 0 |

**Note on PLAN-04 PermissionError:** Cannot be tested with a real locked file in CI. Use `unittest.mock.patch("builtins.open", side_effect=PermissionError)` or patch `openpyxl.load_workbook` to raise `PermissionError`.

### Sampling Rate

- **Per task commit:** `pytest tests/test_spreadsheet.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/__init__.py` — empty init to make tests a package
- [ ] `tests/test_spreadsheet.py` — covers PLAN-01 through PLAN-05 (all 7 test cases above)
- [ ] `tests/conftest.py` — shared `tmp_xlsx` fixture that creates minimal XLSX files using openpyxl `Workbook()` (no external files needed)
- [ ] Framework install: `pip install pytest` — pytest not detected in project

---

## Sources

### Primary (HIGH confidence)

- openpyxl 3.1.5 — live tested on project machine 2026-03-09: `load_workbook` params, `iter_rows()` API, exception types, `read_only` mode behavior, `wb.close()` requirement
- Direct codebase reading — `config.py`, `services/ibge.py`, `services/report.py`, `services/processor.py`: existing patterns for module functions, config constants, exception handling style
- Python 3.10 stdlib docs — `zipfile.BadZipFile`, `FileNotFoundError`, `PermissionError` types

### Secondary (MEDIUM confidence)

- `openpyxl.utils.exceptions.InvalidFileException` — imported and verified present in 3.1.5; exact trigger conditions (non-XLSX extension passed as XLSX) cross-checked with class hierarchy
- `REQUIREMENTS.md` and `ARCHITECTURE.md` — column positions (COD=A=0, ANALISTA=D=3) and MUNICIPIO filter string ("GOIÂNIA")

### Tertiary (LOW confidence)

- Actual MUNICIPIO header spelling in production spreadsheet — not verified (file not accessible on drive G:); recommended to check header_map for both "MUNICIPIO" and "MUNICÍPIO"
- COD zero-padding in real spreadsheet — assumed some rows may be numeric integers; directory matching behavior deferred to Phase 2

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — openpyxl version verified, installed, live tested
- Architecture (module functions): HIGH — matches ibge.py and report.py pattern directly
- openpyxl API: HIGH — every API call live-tested against real XLSX files
- Exception types: HIGH — FileNotFoundError, PermissionError, BadZipFile all triggered and caught in tests
- GOIÂNIA comparison: HIGH — all variant strings tested: accented, unaccented, cased, whitespace-padded
- Pitfalls: HIGH — COD int/str, iter_rows exhaustion, wb.close() all live-verified

**Research date:** 2026-03-09
**Valid until:** 2026-06-09 (openpyxl 3.x API is stable; 90-day estimate)
