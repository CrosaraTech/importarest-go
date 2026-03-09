---
phase: 2
slug: batch-orchestrator
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — `tests/conftest.py`, `tests/test_spreadsheet.py`) |
| **Config file** | none — pytest auto-discovers `tests/` |
| **Quick run command** | `pytest tests/test_batch_orchestrator.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_batch_orchestrator.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | PROC-01..04 | setup | `pytest tests/test_batch_orchestrator.py -q` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | PROC-01 | unit | `pytest tests/test_batch_orchestrator.py::test_run_processes_all_companies -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 1 | PROC-02 | unit | `pytest tests/test_batch_orchestrator.py::test_company_error_continues_loop -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 1 | PROC-03 | unit | `pytest tests/test_batch_orchestrator.py::test_manual_review_queue_event_protocol -x` | ❌ W0 | ⬜ pending |
| 2-01-05 | 01 | 1 | PROC-04 | unit | `pytest tests/test_batch_orchestrator.py::test_abort_stops_after_current_company -x` | ❌ W0 | ⬜ pending |
| 2-01-06 | 01 | 1 | PROC-02 | unit | `pytest tests/test_batch_orchestrator.py::test_none_result_is_skipped -x` | ❌ W0 | ⬜ pending |
| 2-01-07 | 01 | 1 | PROC-01 | unit | `pytest tests/test_batch_orchestrator.py::test_txt_saved_to_dest_folder -x` | ❌ W0 | ⬜ pending |
| 2-01-08 | 01 | 1 | PROC-01 | unit | `pytest tests/test_batch_orchestrator.py::test_batch_summary_counts -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_batch_orchestrator.py` — stubs for PROC-01 through PROC-04 and all supporting tests (8 test stubs total)
- [ ] `services/batch_orchestrator.py` — module under test (created in Wave 1 TDD)

*`tests/conftest.py` already exists with `tmp_xlsx` fixture — no changes needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Manual review dialog appears and batch resumes after analyst responds | PROC-03 | Cannot simulate real Tkinter `after()` + dialog interaction in unit tests | Start a batch run with a company that triggers manual review; verify dialog appears; respond; verify batch continues to next company |
| Abort during active company waits for company to finish | PROC-04 | Requires real timing and thread interaction | Click Abort while a company is mid-processing; verify current company completes before batch stops |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
