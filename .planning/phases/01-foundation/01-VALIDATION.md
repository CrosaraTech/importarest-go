---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (not yet installed — Wave 0 installs) |
| **Config file** | none — Wave 0 creates `tests/` structure |
| **Quick run command** | `pytest tests/test_spreadsheet.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_spreadsheet.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~3 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | PLAN-01..05 | setup | `pip install pytest && pytest tests/ -q` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | PLAN-01 | unit | `pytest tests/test_spreadsheet.py::test_load_analysts_returns_list -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 1 | PLAN-02 | unit | `pytest tests/test_spreadsheet.py::test_filters_goiania_only -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 1 | PLAN-03 | unit | `pytest tests/test_spreadsheet.py::test_missing_header_raises_format_error -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 1 | PLAN-04 | unit | `pytest tests/test_spreadsheet.py::test_missing_file_raises_access_error -x` | ❌ W0 | ⬜ pending |
| 1-01-06 | 01 | 1 | PLAN-04 | unit | `pytest tests/test_spreadsheet.py::test_locked_file_raises_access_error -x` | ❌ W0 | ⬜ pending |
| 1-01-07 | 01 | 1 | PLAN-04 | unit | `pytest tests/test_spreadsheet.py::test_corrupt_file_raises_format_error -x` | ❌ W0 | ⬜ pending |
| 1-01-08 | 01 | 1 | PLAN-05 | unit | `pytest tests/test_spreadsheet.py::test_company_count_per_analyst -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — empty init to make tests a package
- [ ] `tests/conftest.py` — shared `tmp_xlsx` fixture (creates minimal XLSX via openpyxl `Workbook()`, no external files needed)
- [ ] `tests/test_spreadsheet.py` — stubs for all 7 test cases (PLAN-01 through PLAN-05)
- [ ] `pip install pytest` — pytest not yet in project

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real locked file on G: drive shows correct error | PLAN-04 | Cannot simulate real network drive lock in unit tests | Open `RELACAO_EMPRESAS_atualizada.xlsx` in Excel, then call `load_spreadsheet()` and verify error message mentions "bloqueada" or "aberta por outro usuário" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
