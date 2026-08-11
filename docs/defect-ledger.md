# Recovered baseline defect ledger

Measured on 2026-08-11. Entries contain only defects reproduced by fresh commands in the
isolated v2 repository. Baseline work records these failures without changing product or
pre-existing test infrastructure.

## Entry schema

| Field | Meaning |
|---|---|
| ID | Stable `DEF-NNN` identifier |
| Reproduction | Fresh command run from the v2 repository root |
| Observed | Actual exit code and result |
| Expected | Gate contract |
| Owner | Later approved-plan todo responsible for resolution |
| Evidence | Fresh transcript and command metadata |

## DEF-001 — full pytest suite cannot collect

- **Reproduction:** `uv run pytest -q`
- **Observed:** exit 2 after 10.58 s pytest time (12.468 s wall time); 0 passed, 0 failed,
  0 skipped, and 1 collection error. `tests/test_pristine_gate.py` uses the `pristine`
  marker while the recovered `pyproject.toml` does not register it under strict markers.
- **Expected:** complete collection and execution with pass/fail/skip counts reported
  separately.
- **Owner:** Todo 51, “Close the defect, security, quality, size and performance ledger.”
  The defect must be reproduced there before changing the test/quality configuration.
- **Evidence:** `pytest.log`, `pytest.meta.txt`.

## DEF-002 — recovered static-quality gates reject the pristine gate test

- **Reproduction:** `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run basedpyright`
- **Observed:** each exits 1. Ruff reports 13 lint findings in
  `tests/test_pristine_gate.py`; format check reports that file would be reformatted;
  basedpyright reports 3 errors (unused import and incomplete `CompletedProcess` typing).
  The benchmark file was formatted during baseline authoring; no pre-existing test file
  was changed.
- **Expected:** lint, formatting, and strict type-check gates exit 0.
- **Owner:** Todo 51, which explicitly owns unified diagnostics/gates and quality-ledger
  closure.
- **Evidence:** `ruff-check.log`, `ruff-check.meta.txt`, `ruff-format.log`,
  `ruff-format.meta.txt`, `basedpyright.log`, `basedpyright.meta.txt`.

## Non-defects and skips

- JavaScript: 79 passed, 0 failed, 0 skipped.
- CLI selftest and help both exited 0.
- Package build exited 0 and produced both sdist and wheel.
- No skipped result was counted as a pass.
