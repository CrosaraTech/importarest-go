# ImportaREST GO Web

## What This Is

A web application that replaces the ImportaREST GO desktop app (Python/Tkinter) with a FastAPI backend and Lovable-generated React frontend. Multiple analysts at an accounting firm can log in, upload NFS-e XML invoices, process them into REST TXT files for ISS.NET import, review AI-flagged low-confidence records inline, and download results — all from a browser. The existing Python XML parsing logic (~3500 lines) is wrapped as an API, not rewritten.

## Core Value

Analysts can upload NFS-e XMLs and download byte-perfect REST TXT files for ISS.NET import, with AI-assisted service classification and inline manual review when confidence is low.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] FastAPI backend wrapping existing WorkflowProcessor as REST endpoints
- [ ] XML/ZIP file upload replacing G: drive reads
- [ ] Batch processing jobs with real-time progress polling
- [ ] Blocking manual review: job pauses, analyst corrects flagged record inline, job resumes
- [ ] TXT REST and CSV report download (byte-perfect format preservation)
- [ ] Company data in Supabase (one-time XLSX import, managed in DB going forward)
- [ ] Multi-user auth via Supabase Auth (analysts see only their companies/jobs)
- [ ] Lovable React frontend: upload form, progress dashboard, review queue, results download
- [ ] n8n webhook compatibility: FastAPI exposes same classification endpoint

### Out of Scope

- Rewriting Python XML parsing logic — wrap it, don't replace it
- Mobile-native app — web-first, responsive is sufficient
- Real-time WebSocket push — polling is acceptable for v1
- Migrating n8n workflows — they stay as-is
- Multi-municipality expansion beyond current 4 (Goiania, Aparecida, Anapolis, Brasilia)

## Context

### Existing System
- Python desktop app with Tkinter GUI, ~3500 lines across core/, services/, ui/
- XML parsing supports ABRASF and Nacional NFS-e standards, extracting 50+ fields
- Three processing modes: EXTRACT (full AI), MAP_ONLY (classification only), LOCAL (Goiania MEI)
- n8n webhook at `joaomarcos1303.app.n8n.cloud` handles AI classification via GPT-4o-mini + Supabase vector store
- IBGE API for municipality lookup, ViaCEP for address enrichment
- RELACAO_EMPRESAS.xlsx on G: drive with company registry filtered by municipality/analyst
- Output: semicolon-delimited TXT with 20 fields per line + header, CSV audit report

### Architecture Decision
- **Option A chosen**: Keep Python backend + web frontend (vs. Option B: all n8n/Lovable, or Option C: keep desktop)
- Rationale: Complex XML parsing logic is battle-tested in Python; rewriting in n8n Code nodes would be "Python in disguise" with less control

### Team
- 1 developer building and maintaining the system
- Accounting firm users (analysts) who process NFS-e invoices monthly

## Constraints

- **Format fidelity**: TXT REST output must be byte-perfect — same field order, delimiters, header format as current desktop app
- **n8n compatibility**: Classification webhook interface must remain unchanged so existing n8n workflows work without modification
- **Deployment**: FastAPI runs on a local office server; frontend hosted via Lovable/Supabase
- **Team size**: 1 developer — scope must be realistic and incremental
- **Existing logic**: Python core/ and services/ modules are wrapped, not rewritten

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI as backend framework | Async, fast, Python-native, excellent for wrapping existing code | -- Pending |
| Supabase for auth + company data | Lovable integrates natively; replaces XLSX file dependency | -- Pending |
| One-time XLSX import to Supabase | Cleaner than periodic re-uploads; company data managed in DB | -- Pending |
| Blocking manual review (not async queue) | Matches current desktop UX; analysts expect to fix-and-continue | -- Pending |
| Local server deployment for FastAPI | Office network access; no cloud hosting costs for backend | -- Pending |
| Polling for progress (not WebSocket) | Simpler for v1; 1-developer constraint | -- Pending |

---
*Last updated: 2026-03-26 after initialization*
