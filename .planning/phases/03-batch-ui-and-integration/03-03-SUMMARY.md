---
phase: 03-batch-ui-and-integration
plan: 03
subsystem: ui
tags: [tkinter, ttk.Notebook, ttkbootstrap, batch-panel, notebook-tabs]

# Dependency graph
requires:
  - phase: 03-02
    provides: PainelLote(tk.Frame) with _trigger_load_analysts() public API

provides:
  - ttk.Notebook with Individual + Lote tabs integrated in JanelaCrosara
  - Lazy analyst loading via <<NotebookTabChanged>> event binding
  - Window geometry changed from 420x580 to 900x660
  - Individual tab content constrained to 420px via pack_propagate(False)

affects:
  - Any future phase touching ui/app.py or adding new Notebook tabs

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ttk.Notebook for multi-tab Tkinter UI
    - Lazy initialization: _trigger_load_analysts() called only on tab activation, not at startup
    - Fixed-width centering frame with pack_propagate(False) to prevent child stretch in wider window

key-files:
  created: []
  modified:
    - ui/app.py

key-decisions:
  - "Window geometry 900x660 — wide enough for PainelLote batch controls, preserves Individual tab look"
  - "Lazy analyst load on <<NotebookTabChanged>> — avoids G: drive crash at startup if drive is unavailable"
  - "Individual tab wrapped in 420px fixed-width frame with pack_propagate(False) — prevents content stretch in 900px window"
  - "Human approval (Task 2) is the gate for plan completion — visual/functional verification cannot be automated"

patterns-established:
  - "Lazy tab initialization: bind <<NotebookTabChanged>>, check index, call panel method on first activation"
  - "Inner centering frame pattern: tk.Frame(parent, width=N) + pack_propagate(False) + pack(anchor='n')"

requirements-completed: [SELEC-01, SELEC-04]

# Metrics
duration: ~5min
completed: 2026-03-09
---

# Phase 3 Plan 03: Refactor app.py — Notebook Wrapper + Geometry Summary

**JanelaCrosara refactored to ttk.Notebook with Individual (420px constrained) and Lote tabs; window resized to 900x660; lazy analyst loading on tab switch via <<NotebookTabChanged>>**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-09 (continuation from checkpoint)
- **Completed:** 2026-03-09
- **Tasks:** 2 (1 auto, 1 checkpoint:human-verify)
- **Files modified:** 1

## Accomplishments

- Refactored `ui/app.py` `JanelaCrosara._construir_ui()` to wrap existing individual workflow in a `ttk.Notebook` tab and add a second "Lote" tab mounting `PainelLote`
- Individual tab content visually unchanged — constrained to 420px width via `pack_propagate(False)` inner frame to prevent stretching in the wider 900x660 window
- Lazy analyst list loading: `_on_tab_changed` binds to `<<NotebookTabChanged>>` and calls `self._painel_lote._trigger_load_analysts()` only when the Lote tab is first selected, preventing G: drive crashes at startup
- Full pytest suite (25 tests) remains green after modification — zero regressions
- Human verified: both Individual and Lote tabs functional in running app

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor ui/app.py — Notebook wrapper + geometry change** - `fe2792b` (feat)
2. **Task 2: Verify both tabs functional in running app** - human-verify checkpoint; user typed "approved"

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `ui/app.py` - JanelaCrosara refactored: ttk.Notebook, Individual + Lote tabs, geometry 900x660, lazy analyst load, _exibir_logo accepts parent param, _construir_aba_individual with centering frame

## Decisions Made

- Window geometry changed from 420x580 to 900x660 — required to accommodate PainelLote batch controls without cramping
- Individual tab wrapped in 420px fixed-width frame (`pack_propagate(False)`) — maintains visual parity with pre-refactor single-window layout despite wider window
- Lazy `_trigger_load_analysts()` call on `<<NotebookTabChanged>>` event — prevents G: drive network share access at app startup; analyst list loads only when analyst switches to Lote tab
- `_exibir_logo` signature changed from `def _exibir_logo(self)` to `def _exibir_logo(self, parent)` — enables mounting logo in the centering frame rather than directly on `self.janela`

## Deviations from Plan

None - plan executed exactly as written. The centering frame fix for Pitfall 3 (Individual tab stretch) was already specified in the plan's `<interfaces>` section.

## Issues Encountered

None — Task 1 implemented cleanly on first attempt, syntax check passed, pytest suite green. Human approval for Task 2 received without issue.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 is fully complete. All 3 plans (03-01, 03-02, 03-03) delivered.
- The integrated app is ready for production use: analysts can switch between Individual and Lote (batch) workflows in a single window.
- Requirements SELEC-01 and SELEC-04 completed.
- No blockers for deployment or further feature work.

---
*Phase: 03-batch-ui-and-integration*
*Completed: 2026-03-09*
