---
phase: 3
slug: batch-ui-and-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — `tests/conftest.py`, `tests/test_spreadsheet.py`, `tests/test_batch_orchestrator.py`) |
| **Config file** | none — pytest auto-discovers `tests/` |
| **Quick run command** | `pytest tests/test_batch_panel.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_batch_panel.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | SELEC-01..04, PROG-01..04, RESULT-02 | setup | `pytest tests/test_batch_panel.py -q` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | SELEC-01 | unit | `pytest tests/test_batch_panel.py::test_analyst_list_populated -x` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | SELEC-02 | unit | `pytest tests/test_batch_panel.py::test_vigencia_input -x` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 1 | SELEC-03 | unit | `pytest tests/test_batch_panel.py::test_dest_folder_set -x` | ❌ W0 | ⬜ pending |
| 3-01-05 | 01 | 1 | SELEC-04 | unit | `pytest tests/test_batch_panel.py::test_start_disabled_until_all_fields -x` | ❌ W0 | ⬜ pending |
| 3-01-06 | 01 | 1 | PROG-01 | unit | `pytest tests/test_batch_panel.py::test_progress_bar_updates -x` | ❌ W0 | ⬜ pending |
| 3-01-07 | 01 | 1 | PROG-02 | unit | `pytest tests/test_batch_panel.py::test_current_company_label -x` | ❌ W0 | ⬜ pending |
| 3-01-08 | 01 | 1 | PROG-03 | unit | `pytest tests/test_batch_panel.py::test_eta_after_first_done -x` | ❌ W0 | ⬜ pending |
| 3-01-09 | 01 | 1 | PROG-04 | unit | `pytest tests/test_batch_panel.py::test_log_entry_appended -x` | ❌ W0 | ⬜ pending |
| 3-01-10 | 01 | 1 | RESULT-02 | unit | `pytest tests/test_batch_panel.py::test_summary_lists_errors -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_batch_panel.py` — 9 stubs covering SELEC-01..04, PROG-01..04, RESULT-02
- [ ] `tk_root` session fixture added to `tests/conftest.py` — creates hidden `tk.Tk()` root, yields, destroys at teardown

*`tests/conftest.py` already exists with `tmp_xlsx` fixture — append `tk_root` fixture only.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Post-run summary messagebox shows totals (successes, errors, skipped) | RESULT-01 | `messagebox.showinfo` requires real event loop response — cannot assert in headless pytest | Run a batch to completion; verify summary dialog appears with total, success, error, skipped counts |
| Existing Individual tab remains fully functional after Notebook refactor | SELEC-01 | Regression test of visual layout — no automated assertion for tab switching + full workflow | Open app, switch to Individual tab, process a single company normally, verify output |
| Manual review dialog appears during batch and batch resumes after response | PROC-03 (Phase 2) | Requires real Tkinter event loop with two threads interacting | Run batch with a company that triggers manual review; respond; verify next company starts |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
