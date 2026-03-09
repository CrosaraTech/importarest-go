# Coding Conventions

**Analysis Date:** 2026-03-09

## Naming Patterns

**Files:**
- Modules: `lowercase_with_underscores.py` (e.g., `config.py`, `xml_parser.py`, `txt_builder.py`)
- No file prefix or suffix conventions observed
- Semantic grouping in directories: `core/`, `services/`, `ui/`

**Functions:**
- Snake case: `normalize_digits()`, `extrair_dados_python()`, `consulta_cidade_ibge()`
- Prefix with underscore for private/internal functions: `_sanitizar_numero_end()`, `_text()`, `_parse_json_safe()`
- Helper functions grouped with main function using underscore prefix
- Descriptive names in Portuguese for domain logic: `eh_goiania()`, `item_lc_valido()`, `imposto_retido_norm()`

**Variables:**
- Snake case: `codigo_municipio`, `vlr_trib`, `vlr_doc`, `cnpj_p`, `razao_p`, `im_p`
- Prefix with underscore for temporary/derived values: `_aliq_num`, `_iss`, `_base`, `_chave_dedup`
- Short abbreviations used: `cod`, `ddd`, `lc`, `nm`, `mun`, `uf`
- Dictionary keys match database/domain terminology (Portuguese for fiscal domain)

**Classes:**
- Pascal case: `JanelaCrosara`, `WorkflowProcessor`, `ProcessorResult`, `CircularProgress`
- Domain-specific naming: `JanelaCrosara` (UI window), `WorkflowProcessor` (main processing logic)

**Types:**
- Type hints used in function signatures: `def find_text(root, paths, default="") -> str:`
- Union types with pipe notation (Python 3.10+): `dict | None`, `list | dict`
- Return type annotations on public functions

**Constants:**
- All caps with underscores in `config.py`: `BASE_DIR`, `URL_N8N`, `RELATORIO_CSV`, `GOIANIA_IBGE_7`
- Color constants prefixed with `COR_`: `COR_BG`, `COR_PRIMARIA`, `COR_SUCESSO`
- Magic numbers embedded in functions rather than extracted as constants (see tuple assignments in `CircularProgress`)

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, `pyproject.toml`, or `setup.cfg` found)
- Two blank lines between module-level functions and class definitions
- Single blank line between method definitions in classes
- One blank line between function groups with similar purpose

**Line Length:**
- No strict line length enforced (observed lines up to 150+ characters)
- String concatenation with `+` operator common: `f"{endereco} {num}".strip()`

**Indentation:**
- 4 spaces (Python standard)

**Linting:**
- No `.eslintrc`, `.flake8`, or `pylintrc` configuration found
- Not detected whether linting is used in this codebase

## Import Organization

**Order:**
1. Standard library imports: `import xml.etree.ElementTree as ET`, `from datetime import datetime`, `import json`
2. Third-party imports: `import requests`, `import tkinter as tk`, `import ttkbootstrap as ttkb`
3. Local imports: `from config import ...`, `from core.xml_parser import ...`, `from services.processor import ...`

**Path Aliases:**
- No aliases detected; absolute imports from project root used throughout
- Imports use module paths: `from core.extractor import`, `from services.processor import`, `from ui.app import`

**Style:**
- Mix of `from X import Y` (specific) and `import X` (module) styles used
- Aliasing used for clarity: `import xml.etree.ElementTree as ET`, `import ttkbootstrap as ttkb`
- Multiple imports on single `from` line avoided; each import on separate line when possible

## Error Handling

**Patterns:**
- Try-except blocks common, typically catching broad exception types then passing
- Specific exception types caught when logic matters: `except (ValueError, TypeError):`, `except (ValueError, ZeroDivisionError):`
- Silent failures with `pass` used for optional XML parsing: `except ET.ParseError: pass`
- Graceful fallback returns: `return ""`, `return None`, `return False`, `return "0"`
- No custom exception classes observed

**Exception Handling Examples:**

```python
# Safe type conversion with fallback
try:
    num = float((val or "0").replace(",", "."))
except (ValueError, AttributeError):
    return val.strip() if val else "0"

# Silent XML parsing failure
try:
    root = ET.fromstring(xml_string)
except ET.ParseError:
    pass
    return False

# Multi-line parsing with multiple try blocks
try:
    dt_raw = dt_emissao.split("T")[0]
    dt_fmt = datetime.strptime(dt_raw, "%Y-%m-%d").strftime("%d%m%Y")
except (ValueError, IndexError):
    dt_fmt = ""
```

**Default Values:**
- Empty string defaults: `default=""`
- Empty dict/list for missing data structures
- Zero values: `return "0"`, `aliq_val = "0"`

## Logging

**Framework:** Console output via `print()` and UI logging callbacks

**Patterns:**
- Logging done through injected callback function: `self._log(f"message")`
- Status messages use emoji prefixes: `✅`, `❌`, `⚠️`, `🤖`, `⏭`, `⛔`, `🏁`, `📂`, `📋`, `─`
- Context-aware messages: process status, file counts, validation results
- No structured logging framework (no `logging` module used)

**Examples:**
```python
self._log(f"❌ Pasta de notas não encontrada: {pasta}")
self._log(f"📂 {len(dict_xmls)} arquivo(s) encontrado(s)")
self._log(f"🤖 Consultando IA para completar dados da nota: {nome}")
```

## Comments

**When to Comment:**
- Docstrings on public functions: `def find_text(root, paths, default=""):`
- Complex logic sections explained with inline comments
- Business rule reasoning commented: `# Escolhe a melhor descrição tributária disponível:`
- Fallback logic documented: `# xTribNac é descartado quando contém "(VETADO)" ou "sem a incidência"`

**JSDoc/Docstring Style:**

Triple quotes with description line:
```python
def formatar_aliquota(val: str) -> str:
    """Formata alíquota para o TXT. Remove zeros à direita desnecessários."""

def eh_evento_cancelamento(xml_string: str) -> bool:
    """Verifica se o XML de evento contém tag <e10xxxx> dentro de <infPedReg> (cancelamento)."""
```

**Comment Style:**
- Single-line comments with `#`: `# Fallback: fingerprint pelos elementos internos`
- Section separators with comment lines: `# ──────────────────────────────────────────────────────────────────────────`

## Function Design

**Size:** Large functions (200-300+ lines) in `processor.py` (e.g., `_processar_notas`, `extrair_dados_python`)

**Parameters:**
- Parameters use type hints: `def find_text(root, paths, default="") -> str:`
- Default values used liberally: `def detectar_padrao_nfse(root: ET.Element) -> str:`
- Callbacks passed as parameters: `log_fn: Callable`, `progress_fn: Callable`

**Return Values:**
- Tuples for multiple returns: `tuple[str, str]`, `tuple[bool, dict]`
- Dictionaries for structured data: `dict` with string keys
- None for optional results: `ProcessorResult | None`
- Default values on error: `return ""`, `return "desconhecido"`, `return False`

**Private Methods:**
- Underscore prefix: `self._log()`, `self._set_progress()`, `self._carregar_xmls()`
- @staticmethod for pure functions: `@staticmethod def _prioridade(item):`

## Module Design

**Exports:**
- No explicit `__all__` declarations observed
- Functions exported by default (no private module pattern)
- Classes exported directly

**Barrel Files:**
- `__init__.py` files present but empty: `core/__init__.py`, `services/__init__.py`, `ui/__init__.py`
- No re-exports or aggregation in `__init__.py`

**Module Responsibilities:**
- `core/extractor.py`: XML data extraction logic
- `core/validators.py`: Data validation and normalization
- `core/formatters.py`: Output formatting (UF, date, aliquot)
- `core/txt_builder.py`: Line building from extracted/formatted data
- `core/xml_parser.py`: XML parsing utilities and pattern detection
- `services/processor.py`: Orchestration, file handling, API calls
- `services/ibge.py`: External API integration with caching
- `services/n8n_client.py`: N8N webhook client
- `services/report.py`: CSV report writing
- `ui/app.py`: Main UI window
- `ui/components.py`: Reusable UI components
- `ui/dialogs.py`: Dialog windows (not examined in detail)
- `config.py`: Configuration constants

## Dependency Patterns

**Core Dependencies:**
- `requests`: HTTP calls to N8N and IBGE
- `ttkbootstrap`: Modern Tkinter theme
- `PIL` (Pillow): Image rendering for progress widget
- `pathlib`: File path handling
- `xml.etree.ElementTree`: XML parsing
- Standard library: `datetime`, `json`, `csv`, `re`, `zipfile`, `threading`

**Naming Convention Consistency:**
- Domain-specific Portuguese naming used consistently for fiscal domain
- English used for generic/framework concepts
- Abbreviations standardized: `cnpj_p`, `im_p`, `razao_p`, `vlr_trib`, `vlr_doc`, etc.

---

*Convention analysis: 2026-03-09*
