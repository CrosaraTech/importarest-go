# TESTING

## Current Status

**No automated tests exist.** Zero test files, no test framework dependencies in the project.

## Test Framework (Recommended)

- **Framework:** `pytest` (not yet installed)
- **Location:** `tests/` directory (not yet created)
- **Dependencies to add:** `pytest`, `pytest-mock`

## Testability Analysis

### Easy to Test (Pure Functions)
- `core/validators.py` — Input validation logic
- `core/formatters.py` — Data formatting utilities

### Hard to Test (Require Refactoring)
- `core/extractor.py` — Large functions (280+ lines), deeply coupled
- `WorkflowProcessor` class (~700 lines) — UI callbacks tightly integrated with business logic

## Coverage Gaps

| Area | Files | Status |
|------|-------|--------|
| Validation | `core/validators.py` | No tests |
| Formatting | `core/formatters.py` | No tests |
| Extraction | `core/extractor.py` | No tests |
| Workflow | `core/workflow.py` | No tests |
| UI layer | `gui/` | Not unit-testable as-is |

## Recommended Testing Strategy

### Phase 1 — Unit Tests (validators/formatters)
```python
# tests/test_validators.py
import pytest
from core.validators import validate_xml_input

def test_validate_xml_valid():
    # ...

def test_validate_xml_invalid():
    # ...
```

### Phase 2 — Extraction Logic
Requires splitting `core/extractor.py` into smaller, pure functions before testing.

### Phase 3 — Workflow Integration
Mock external calls (N8N webhook, IBGE API) using `pytest-mock`.

```python
# Mock N8N webhook
def test_workflow_sends_correct_payload(mocker):
    mock_post = mocker.patch("requests.post")
    # ...
```

## Mock Patterns

### External HTTP calls
```python
mocker.patch("requests.post", return_value=MockResponse(200, {...}))
mocker.patch("requests.get", return_value=MockResponse(200, {...}))
```

### File I/O
```python
mocker.patch("builtins.open", mock_open(read_data="xml content"))
```

## Notes

- No CI/CD pipeline configured
- UI layer (Tkinter/ttkbootstrap) is not unit-testable without significant refactoring
- Business logic mixed into UI callbacks is the primary blocker for testability
