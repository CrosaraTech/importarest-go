# Test Fixtures for Byte-Fidelity Testing

Place desktop-generated reference files here to enable byte-level regression testing
against the web API output.

## Directory Structure

```
fixtures/
  goiania/
    input/      <- XML files that were processed by the desktop app
    expected/   <- TXT and CSV files the desktop app generated from those XMLs
  aparecida/
    input/
    expected/
  anapolis/
    input/
    expected/
  brasilia/
    input/
    expected/
```

## How to Add Fixtures

1. Pick a real job you have already run through the desktop app.
2. Copy the XML files from the job folder into `{municipality}/input/`.
3. Copy the desktop-generated output files into `{municipality}/expected/`.

## Filename Conventions

| File type       | Convention                            | Example                        |
|-----------------|---------------------------------------|--------------------------------|
| Main TXT        | `{emp_cod}_{vigencia}.txt`            | `001_032026.txt`               |
| Split TXT       | `{emp_cod}_{vig_errada}.txt`          | `001_022026.txt`               |
| CSV report      | `relatorio_{emp_cod}_{vigencia}.csv`  | `relatorio_001_032026.csv`     |

> **Note:** `vigencia` in filenames uses `MMYYYY` format (no separator), e.g. `032026` for March 2026.

## What the Tests Do

When expected files are present, `tests/test_byte_fidelity.py` will:

1. POST the input XMLs to the web API (using the same `emp_cod` and `vigencia`).
2. Download the resulting TXT/CSV via the download endpoints.
3. Compare the downloaded bytes against the expected files byte-by-byte.

Any encoding, line-ending, delimiter, or field-order regression will cause a test failure.

## Current Status

All 4 municipality fixture directories are empty. Tests will be **skipped** until you
add reference files. No test failures will occur with an empty fixtures directory.
