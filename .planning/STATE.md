---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: complete
stopped_at: v1.0 milestone complete — all 6 phases executed, all checkpoints approved
last_updated: "2026-04-01"
last_activity: 2026-04-01 — Phase 6 n8n Compatibility & Hardening complete; v1.0 milestone done
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 13
  completed_plans: 13
  percent: 100
---
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-26)

**Core value:** Analysts can upload NFS-e XMLs and download byte-perfect REST TXT files for ISS.NET import, with AI-assisted classification and inline manual review.
**Current focus:** v1.0 entregue. Pendencia aberta: fixtures de fidelidade byte a byte (ver Blockers).

## Current Position

Phase: 6 of 6 (n8n Compatibility & Hardening) — concluida
Plan: 13 of 13 concluidos
Status: milestone v1.0 completo com uma pendencia de verificacao em aberto
Last activity: 2026-04-01 — Phase 6 concluida

Progress: [██████████] 100% dos planos executados

ATENCAO: "planos executados" nao e o mesmo que "verificado". Os 8 testes de
fidelidade byte a byte seguem SKIPPED por falta de fixtures — a garantia
central do produto (TXT identico ao aceito pelo portal) nao tem cobertura
automatica em nenhum dos 4 municipios. Ver Blockers.

## Performance Metrics

**Velocity:**
- Total plans completed: 13 de 13

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| Phase 01-foundation P01 | 6 | 2 tasks | 9 files |
| Phase 01-foundation P02 | 18min | 2 tasks | 7 files |
| Phase 01-foundation P03 | 4 | 1 tasks | 3 files |
| Phase 02-job-lifecycle P01 | 6min | 2 tasks | 5 files |
| Phase 03-manual-review-gate P01 | 6min | 2 tasks | 5 files |
| Phase 04-output-delivery P01 | 46min | 2 tasks | 3 files |
| Phase 05-batch-mode P01 | 6min | 2 tasks | 5 files |
| Phase 05-batch-mode P02 | 32min | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Architecture: Keep Python backend + wrap with FastAPI (do NOT rewrite XML parsing logic)
- Deployment: Single uvicorn worker (`--workers 1`) — job state lives in-memory; this is intentional
- Review gate: Use `threading.Event` (not `asyncio.Event`) — worker runs in a dedicated thread, not a coroutine
- Job runner: Dedicated `threading.Thread` started at job creation, outside FastAPI's anyio threadpool
- Progress: HTTP polling at 2-3s (TanStack Query) — WebSockets explicitly out of scope for v1
- [Phase 01-foundation]: config_web.py reads all settings from os.environ with fail-fast KeyError for required Supabase keys; api/ modules never import config.py
- [Phase 01-foundation]: CORS uses explicit allow_origins from env var (no wildcards) with allow_credentials=False; JWT goes in Authorization header not cookie
- [Phase 01-foundation]: Redis test uses raw TCP socket PING/PONG with skipif guard — no redis-py dependency until Phase 2 arq integration
- [Phase 01-foundation]: Supabase admin client uses service-role key only; analyst_name looked up from profiles table per request (not JWT user_metadata) to prevent analyst impersonation
- [Phase 01-foundation]: Migration script discovers CNPJ, MUNICIPIO, NOME EMPRESA by header name (not hardcoded index); imports ALL rows with no municipality filter; upserts on_conflict=cod for idempotency
- [Phase 01-foundation]: Analysts see ALL companies (no server-side ownership filter) — is_mine flag marks ownership for frontend
- [Phase 01-foundation]: Empty list (not error) when analyst has no companies assigned — frontend handles display
- [Phase 02-job-lifecycle]: importlib.import_module('config') used in worker thread to avoid G-drive import linter violation in api/ modules
- [Phase 02-job-lifecycle]: Job serialization via _lock around processar() is intentional v1 limitation — safe for single-worker, <5 min jobs
- [Phase 02-job-lifecycle]: abrir_tela_manual_fn is auto-accept stub in Phase 2; Phase 3 replaces with threading.Event review gate
- [Phase 03-manual-review-gate]: event.wait(timeout=300) called OUTSIDE _lock to prevent deadlock — worker releases lock before blocking
- [Phase 03-manual-review-gate]: status=running set by worker after event.wait() returns, NOT by submit_review() — avoids race condition
- [Phase 03-manual-review-gate]: montar_linha_txt called inside submit_review() with stored dados_base; frontend sends raw item_lc/ddd only
- [Phase 04-output-delivery]: _CSV_CABECALHO defined as constant in api/jobs.py — avoids importing services.report (G-drive linter safe in api/ modules)
- [Phase 04-output-delivery]: Route order: /files, /download/txt, /download/csv, /download/txt/{vigencia} — exact-match routes before parameterized to prevent FastAPI ambiguity
- [Phase 04-output-delivery]: emp_cod and vigencia read from job_state (not ProcessorResult) — ProcessorResult only contains processing output, not job metadata
- [Phase 04-output-delivery]: errors count uses row[4] != "OK" (Status column index 4 per _CABECALHO)
- [Phase 04-output-delivery]: Byte-fidelity tests use pytest.skip (not xfail) so they appear as SKIPPED not FAILED until fixtures arrive
- [Phase 04-output-delivery]: Download buttons use fetch+blob+createObjectURL pattern (not plain anchor) to support JWT Authorization header in Lovable frontend
- [Phase 05-batch-mode]: Phase 5 spec is a self-contained addendum (Section 13) — no modifications to Sections 1-12 of lovable-spec.md
- [Phase 05-batch-mode]: ReviewCard reused as-is for batch; queryClient cache key changes from ['job-status', jobId] to ['batch-status', batchId]
- [Phase 05-batch-mode]: BatchJobManager takes JobManager as constructor arg to share _analyst_jobs registry for one-job-per-analyst enforcement across batch and individual jobs
- [Phase 05-batch-mode]: JobManager.create_job() raises ValueError when _analyst_jobs entry exists but job not in _jobs (means it is a batch job in another registry)
- [Phase 05-batch-mode]: ETA formula: avg_elapsed_per_completed_companies * remaining_count (matches desktop batch_panel.py)
- [Phase 05-batch-mode]: POST /batch uses UPLOAD_TEMP_DIR as job_dir base; batch_id subdir created post-creation; orchestrator skips companies without XML folders
- [Phase 05-batch-mode]: Dual-registry dispatch for abort and review: try job_manager first, batch_job_manager second — single endpoint for both job types
- [Phase 05-batch-mode]: POST /jobs/{id}/review fallthrough to batch_job_manager when job_manager returns None — avoids new /batch/{id}/review route

### Pending Todos

None yet.

### Blockers/Concerns

- Before Phase 1: Confirm Supabase project uses new key format (`sb_publishable_...` / `sb_secret_...`) — check Dashboard > Project Settings > API
- Before Phase 1: Audit config.py for all G: drive / BASE_DIR references and isolate in config_web.py before any server start
- EM ABERTO — Byte-level diff test against desktop-generated TXT for all 4
  municipalities (Goiania, Aparecida, Anapolis, Brasilia). Os testes existem em
  tests/test_byte_fidelity.py mas ficam SKIPPED: faltam as fixtures de
  referencia em tests/fixtures/<municipio>/expected/ (4 TXT + 4 CSV).
  Marcado como pendencia da Fase 4; o milestone foi fechado sem resolve-lo.
  Desbloqueio: obter TXT/CSV ja aceitos nos portais e os XMLs que os geraram.
- Phase 3 high risk: threading.Event gate is the most novel component — follow ARCHITECTURE.md Pattern 2 exactly; test review timeout explicitly

## Session Continuity

Last session: 2026-09-02
Stopped at: ambiente de desenvolvimento reconstruido (requirements + venv);
suite de testes de 69 falhas para 0. Pendencia unica: fixtures de fidelidade.
Resume file: None
