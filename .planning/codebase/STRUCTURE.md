# Codebase Structure

**Analysis Date:** 2026-03-09

## Directory Layout

```
c:/Users/Havai/Desktop/Rest iss.net/
├── .planning/                      # GSD planning documents (this directory)
│   └── codebase/                   # Architecture analysis output
├── .git/                           # Git version control
├── assets/                         # Static resources
│   ├── logo_importarest.png        # Application logo
│   └── logo_crosara.png            # Company branding
├── core/                           # Business logic layer
│   ├── __init__.py
│   ├── xml_parser.py               # XML format detection, parsing helpers
│   ├── extractor.py                # 50+ field extraction from XMLs
│   ├── validators.py               # Business rule validation functions
│   ├── formatters.py               # Data type normalization and formatting
│   └── txt_builder.py              # REST output line assembly
├── services/                       # Integration and orchestration
│   ├── __init__.py
│   ├── processor.py                # Main workflow orchestrator
│   ├── n8n_client.py               # N8N webhook HTTP client
│   ├── ibge.py                     # Municipality IBGE API integration
│   └── report.py                   # CSV report generation
├── ui/                             # Desktop interface
│   ├── __init__.py
│   ├── app.py                      # Main window (JanelaCrosara class)
│   ├── components.py               # Reusable widgets (buttons, entries, progress)
│   └── dialogs.py                  # Manual review and input dialogs
├── n8n/                            # AI workflow definitions
│   ├── workflow.json               # Exportable N8N workflow definition
│   ├── workflow_completo.png       # Workflow diagram
│   └── workflow_config_base.png    # Data ingestion pipeline diagram
├── Workflow N8N/                   # Alternative workflow storage
│   └── NFS-e XML Processing...json # Full workflow export (backup)
├── main.py                         # Application entry point
├── config.py                       # Global configuration and constants
├── certificados.json               # Certificate metadata (not processed)
├── README.md                       # Project documentation
├── .gitignore                      # Git ignore patterns
└── __pycache__/                    # Python compiled cache (auto-generated)
```

## Directory Purposes

**core/:**
- Purpose: Pure business logic, no UI or network dependencies
- Contains: XML parsing, data extraction, validation rules, output formatting
- Key files: `xml_parser.py` (pattern detection), `extractor.py` (field extraction), `validators.py` (business rules)

**services/:**
- Purpose: External integrations and workflow orchestration
- Contains: Main processor workflow, HTTP clients for N8N and IBGE, reporting
- Key files: `processor.py` (orchestrator), `n8n_client.py` (AI integration)

**ui/:**
- Purpose: Desktop interface components and dialogs
- Contains: Tkinter window management, custom widgets, user input forms
- Key files: `app.py` (main window), `components.py` (reusable widgets)

**n8n/:**
- Purpose: AI workflow configuration and diagrams
- Contains: Exportable N8N workflow JSON, visual documentation
- Key files: `workflow.json` (importable workflow definition)

**assets/:**
- Purpose: Image and static resource storage
- Contains: PNG logos and icons
- Key files: Application and company branding images

## Key File Locations

**Entry Points:**
- `main.py`: Application startup. Instantiates `JanelaCrosara()` from `ui/app.py`

**Configuration:**
- `config.py`: All hardcoded paths (BASE_DIR, URL_N8N, RELATORIO_CSV), municipal codes, API endpoints, color palette

**Core Logic:**
- `core/xml_parser.py`: XML format detection and helper functions
- `core/extractor.py`: Extracts 50+ fields using multi-path XPath queries
- `core/validators.py`: Business rule checks (Goiânia detection, LC item validation)
- `core/formatters.py`: Data normalization (dates, aliquotas, field sanitization)
- `core/txt_builder.py`: Assembles validated fields into REST output format

**Orchestration:**
- `services/processor.py`: Main workflow class `WorkflowProcessor`. Coordinates extraction, validation, AI calls, and line assembly

**UI:**
- `ui/app.py`: Main window class `JanelaCrosara`. Manages input fields, progress display, file dialogs
- `ui/components.py`: Custom widgets (`CircularProgress`, `criar_botao`, `criar_entry`)
- `ui/dialogs.py`: Dialogs for manual data entry and item classification

**Integration:**
- `services/n8n_client.py`: Single function `chamar_n8n()` for webhook POST
- `services/ibge.py`: Municipality lookup with caching
- `services/report.py`: CSV report generation

**Testing:**
- Not present. No test files in repository

## Naming Conventions

**Files:**
- Snake_case: `xml_parser.py`, `n8n_client.py`
- Classes exported from modules: `JanelaCrosara`, `WorkflowProcessor`, `CircularProgress`, `ProcessorResult`

**Directories:**
- Lowercase plural/singular based on content: `core`, `services`, `ui`, `assets`, `n8n`

**Functions:**
- Portuguese names for business logic: `extrair_dados_python()`, `montar_linha_txt()`, `formatar_aliquota()`
- English for infrastructure: `chamar_n8n()` uses Portuguese despite context, `consulta_cidade_ibge()` is Portuguese
- Private functions prefixed with `_`: `_sanitizar_numero_end()`, `_redraw()`, `_carregar_fonte()`

**Variables:**
- Snake_case throughout: `conteudo_final`, `linhas_dict`, `dados`, `notas_xmls`
- Abbreviations in extraction: `cnpj_p` (prestador), `vlr_doc` (valor documento), `im_p` (inscrição municipal)
- Shorthand in UI: `btn_acao`, `ent_codigo`, `lbl_status`, `chk_mei`

**Types:**
- Core return values: Tuples `(status, dados)` from extraction, Dict from N8N responses
- Data carriers: `ProcessorResult` dataclass with slots for result bundling
- Type hints sparse but present in some signatures: `chamar_n8n(payload: dict, timeout: int = 150)`

## Where to Add New Code

**New Feature (e.g., support for new XML standard):**
- Primary code: `core/xml_parser.py` for detection, `core/extractor.py` for field mapping
- Validation rules: `core/validators.py` if new business rules needed
- Tests: Create `tests/test_[feature].py`

**New Component/Module (e.g., new external API):**
- Implementation: `services/[name].py` (e.g., `services/viacep.py` for address lookup)
- Configuration: Add endpoint URLs and credentials to `config.py`
- Usage: Import in `services/processor.py` and integrate into workflow

**Utilities (shared helpers):**
- Core utils: `core/formatters.py` or `core/validators.py` depending on type
- Service utils: Create `services/utils.py` if needed
- UI utils: Add to `ui/components.py` for widgets, `ui/dialogs.py` for dialog helpers

**New Dialog/Screen:**
- Implementation: `ui/dialogs.py` (for modal dialogs) or `ui/app.py` (for main window changes)
- Styling: Use color constants from `config.py` (COR_PRIMARIA, COR_SUCESSO, etc.)
- Callbacks: Pass UI update functions as constructor parameters following `JanelaCrosara` pattern

**New Output Format (besides REST TXT):**
- Line assembly: New function in `core/txt_builder.py` (e.g., `montar_linha_xml()`)
- Download handler: New method in `JanelaCrosara` or new dialog in `ui/dialogs.py`

## Special Directories

**`.planning/codebase/`:**
- Purpose: GSD mapping documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
- Generated: Yes (by gsd:map-codebase command)
- Committed: Yes (versioned with codebase)

**`.git/`:**
- Purpose: Git version control metadata
- Generated: Yes
- Committed: N/A (git internals)

**`__pycache__/`:**
- Purpose: Python compiled bytecode cache
- Generated: Yes (automatic on import)
- Committed: No (.gitignore excludes)

**`n8n/`:**
- Purpose: N8N workflow configuration (not application code)
- Generated: Partially (JSON exported from N8N editor)
- Committed: Yes (versioned workflow definition)

---

*Structure analysis: 2026-03-09*
