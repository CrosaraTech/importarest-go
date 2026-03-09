# Technology Stack

**Analysis Date:** 2026-03-09

## Languages

**Primary:**
- Python 3.10+ - Primary language for all application logic, XML processing, and workflow orchestration

## Runtime

**Environment:**
- Python 3.10 or superior (required)
- Windows 10/11 (desktop application)

**Package Manager:**
- pip - Python package manager
- Lockfile: Not present (dependencies listed in README but no requirements.txt committed)

## Frameworks

**Core:**
- ttkbootstrap - Modern themed Tkinter widgets for desktop GUI
- tkinter (stdlib) - Native Python GUI toolkit

**XML Processing:**
- xml.etree.ElementTree (stdlib) - XML parsing and manipulation

**HTTP Communication:**
- requests - HTTP library for API calls to N8N webhook and external services

**Image Processing:**
- Pillow (PIL) - Image handling for UI components and logo rendering

**Data & Reporting:**
- csv (stdlib) - CSV file reading/writing for reports

## Key Dependencies

**Critical:**
- `ttkbootstrap` - Modern desktop UI theme and widgets
- `Pillow` - Image display and circular progress indicator rendering
- `requests` - HTTP communication with N8N and external APIs

**Infrastructure:**
- zipfile (stdlib) - ZIP file handling (for XML parsing in ZIP containers)
- threading (stdlib) - Async background processing for UI responsiveness
- pathlib (stdlib) - Cross-platform path handling

## Configuration

**Environment:**
- Configuration via `config.py` hardcoded paths and parameters
- `.env` file referenced in `.gitignore` but not tracked (contains sensitive data)
- CSV output path: Shared Google Drive path via environment variable

**Build:**
- No build configuration files (py files directly executed)
- Entry point: `main.py` launches `JanelaCrosara` desktop application

## Platform Requirements

**Development:**
- Python 3.10+
- Windows OS (paths hardcoded as Windows paths)
- Access to shared Google Drive (XML input directory)
- n8n.cloud account with API webhook
- OpenAI API key (for GPT-4o-mini via n8n)
- Supabase project (for vector embeddings)
- HuggingFace API key (for embeddings)

**Production:**
- Windows 10/11 desktop
- Network access to:
  - N8N cloud instance: `https://joaomarcos1303.app.n8n.cloud/webhook/nfse-processing`
  - IBGE API: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{}`
  - Google Drive (shared network path)

---

*Stack analysis: 2026-03-09*
