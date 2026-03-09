# Architecture

**Analysis Date:** 2026-03-09

## Pattern Overview

**Overall:** Multi-layered pipeline architecture with desktop GUI orchestration

**Key Characteristics:**
- Separation of concerns across UI, services, and core business logic layers
- Workflow-driven processing with AI integration via N8N webhooks
- XML parsing with automatic format detection (ABRASF vs. Nacional standards)
- Stream-based file processing with caching for external service calls

## Layers

**UI Layer:**
- Purpose: Desktop interface for user input and workflow control
- Location: `ui/app.py`, `ui/components.py`, `ui/dialogs.py`
- Contains: Tkinter-based window management, custom progress indicator, input forms, manual review dialogs
- Depends on: Services layer (processor, report), core validators
- Used by: Entry point (`main.py`)

**Services Layer:**
- Purpose: Orchestration of processing workflow and external integrations
- Location: `services/processor.py`, `services/n8n_client.py`, `services/ibge.py`, `services/report.py`
- Contains: Main workflow orchestrator, N8N HTTP client, IBGE API integration, CSV reporting
- Depends on: Core extraction and validation modules
- Used by: UI layer to trigger document processing

**Core Logic Layer:**
- Purpose: Fiscal document processing, data extraction, validation, and formatting
- Location: `core/xml_parser.py`, `core/extractor.py`, `core/validators.py`, `core/formatters.py`, `core/txt_builder.py`
- Contains: XML parsing, field extraction (50+ fields), business rule validation, output formatting
- Depends on: Standard library only (xml.etree.ElementTree, datetime, pathlib)
- Used by: Services layer for data transformation

**Configuration Layer:**
- Purpose: Centralized settings for paths, endpoints, colors, and constants
- Location: `config.py`
- Contains: Network endpoints (N8N webhook), file paths, municipal codes, color palettes
- Depends on: None
- Used by: All layers

## Data Flow

**Document Processing Workflow:**

1. **Input Phase** → User enters company code and period (MMYYYY) in UI
2. **File Loading** → `processor.py` scans file system for XML/ZIP files
3. **File Reading** → XMLs extracted from disk/archives with UTF-8 fallback
4. **Pattern Detection** → `xml_parser.py` detects ABRASF or Nacional standard
5. **Local Extraction** → `extractor.py` extracts 50+ fiscal fields using XPath queries
6. **Status Evaluation** → Determines processing path (complete/incomplete/unknown)
7. **AI Processing** → `n8n_client.py` sends to webhook for LLM classification
8. **Line Assembly** → `txt_builder.py` formats validated data into REST output format
9. **File Generation** → Complete TXT file saved to user's selected location
10. **Report Generation** → `report.py` creates CSV audit trail of all documents

**State Management:**
- Workflow state tracked in `ProcessorResult` dataclass (`linhas_dict`, `relatorio`, `notas_vig_errada`)
- Per-note state during processing: success/error/manual_review
- UI progress updates streamed via callbacks (`progress_fn`, `log_fn`, `contador_fn`)
- Cache maintained for IBGE municipality lookups to reduce API calls

## Key Abstractions

**WorkflowProcessor:**
- Purpose: Orchestrates the entire document processing pipeline
- Examples: `services/processor.py` (main class)
- Pattern: Callback-based event delegation for UI updates. Methods named `_processar_[tipo]` for different XML types. Private state initialization via constructor injection of UI callbacks

**XML Pattern Detection:**
- Purpose: Routes documents through appropriate parsing logic
- Examples: `core/xml_parser.py:detectar_padrao_nfse()`
- Pattern: Fingerprint matching via namespace detection and tag presence heuristics. Returns "abrasf", "nacional", or "desconhecido"

**Field Extraction:**
- Purpose: Safely navigates variable XML structures and extracts data
- Examples: `core/xml_parser.py:find_text()`, `core/extractor.py:extrair_dados_python()`
- Pattern: XPath-style multi-path fallback (`[path1, path2, path3]`). Returns first match or default. Uses namespace-agnostic tag matching (`{*}TagName`)

**Data Normalization:**
- Purpose: Standardizes values across different document formats
- Examples: `core/validators.py`, `core/formatters.py`
- Pattern: Pure functions with minimal dependencies. Date formats normalized to DDMMYYYY, alphanumeric cleanup, type coercion with fallback defaults

**N8N Integration:**
- Purpose: Delegates AI classification when local extraction incomplete
- Examples: `services/n8n_client.py:chamar_n8n()`, `services/processor.py:_processar_ia_extract()`
- Pattern: Webhook POST with JSON payload. Multiple response shapes handled via fallback parsing (`_extrair_n8n_obj`). Timeout of 150 seconds for long-running AI operations

## Entry Points

**main.py:**
- Location: `main.py`
- Triggers: User runs `python main.py` from command line
- Responsibilities: Instantiates `JanelaCrosara` UI window, creates tkinter event loop

**JanelaCrosara (Main Window):**
- Location: `ui/app.py`
- Triggers: Application startup, user interaction with buttons
- Responsibilities: Manages UI state (inputs, progress display), spawns background worker thread for processing, handles download/save dialogs

**WorkflowProcessor.processar():**
- Location: `services/processor.py`
- Triggers: User clicks "INICIAR IMPORTAÇÃO" button
- Responsibilities: Main entry point for processing. Validates folders, loads XMLs, coordinates extraction→validation→AI→assembly pipeline, returns ProcessorResult

## Error Handling

**Strategy:** Multi-layered with graceful degradation

**Patterns:**
- **XML Parse Errors:** Wrapped in try/except blocks. Fall through to pattern detection heuristics. Logged with `_log()` callback
- **Missing Fields:** XPath queries return empty string defaults. Validators check `has_value()` before processing
- **External Service Failures:** N8N timeouts/HTTP errors logged but don't crash UI. Falls back to `manual_review` mode opening UI dialog for human input
- **File I/O:** Disk read failures logged. Missing folders reported to user with specific path
- **Data Validation:** Business rule checks in validators (e.g., `item_lc_valido()`, `eh_goiania()`) return boolean or normalized value, never raise exceptions

## Cross-Cutting Concerns

**Logging:** Custom callback function `_log` passed to processor. All significant events logged: file counts, parsing results, AI calls, errors. UI display via `lbl_status` label widget

**Validation:** Distributed across modules:
- `core/validators.py` - Business rules (Goiânia detection, LC 116 item range, ISS retention flags)
- `core/formatters.py` - Type/format validation (date parsing, aliquota formatting, field sanitization)
- `core/txt_builder.py` - Output format assembly with field count verification

**Authentication:** None. Application assumes:
- Windows file system access to network drive (configured in `config.py:BASE_DIR`)
- Network access to N8N webhook endpoint
- Network access to IBGE API
- Credentials stored in N8N workflow configuration (not in application code)

**Cancellation Handling:** XML event files with pattern `*_event_*.xml` checked for cancellation markers (child tag matching `e10\d+`). Matched notes filtered from processing before data extraction

---

*Architecture analysis: 2026-03-09*
