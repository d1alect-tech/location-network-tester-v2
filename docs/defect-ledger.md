# Recovered baseline defect ledger

Measured on 2026-08-11. Entries contain only defects reproduced by fresh commands in the
isolated v2 repository. Baseline work records these failures without changing product or
pre-existing test infrastructure.

> **Todo 51 closure (2026-08-23):** every entry below now carries a resolution status:
> `RESOLVED` (reproduction + fix + regression evidence) or `ENVIRONMENT-BLOCKED`.
> No entry ends as "unknown fixed". See `.omo/start-work/evidence/task-51-lnt-complete-redesign/`
> (outside the product trees) for transcripts.

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
- **Status (2026-08-23): RESOLVED** — marker registered during earlier todos; fresh run
  `uv run pytest -q` exits 0 with all tests collected (774 passed at Todo 51 close),
  zero skipped counted as pass.

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
- **Status (2026-08-23): RESOLVED** — fresh runs exit 0: `ruff check .`,
  `ruff format --check .`, `basedpyright` (0 errors).

## DEF-003 — hypothesis/trends CLI rejects UTF-8-BOM JSON with empty field list

- **Reproduced (2026-08-23, before fix):** `_hypothesis_file` on a BOM-prefixed payload
  raised «гипотеза: некорректные поля …: » with an empty field list; same class in
  `run_trends`/`_descriptor`. Transcript: `repro-defects.log`.
- **Fix:** shared `read_payload()` in `src/lnt/cli_research.py` reads CLI JSON inputs with
  `encoding="utf-8-sig"`; wired into hypothesis/experiment/trends/check readers.
- **Regression:** `tests/test_cli_bom_inputs.py` (BOM accepted for hypothesis + trends,
  BOM-free still green, strict models unchanged).
- **Status: RESOLVED.**

## DEF-004 — basedpyright reports 6 errors in tests/test_launcher.py

- **Reproduced (2026-08-23, fresh gate before fix):** `uv run basedpyright` exited 1:
  reportPrivateUsage ×3 (`_build_parser`, `argparse._SubParsersAction`, `_run_uvicorn`),
  reportUnannotatedClassAttribute (`FakeConfig.application`), reportArgumentType ×2
  (sentinel object → FastAPI/socket).
- **Fix:** annotated `self.application: object`; precise `# pyright: ignore[rule]`
  comments for legitimate test-only private access and fake doubles.
- **Evidence:** post-fix `basedpyright`: 0 errors (gates-after-fixes.log).
- **Status: RESOLVED.**

## DEF-005 — v2 error boundary rendered error text as HTML (XSS sink)

- **Reproduced by inspection (2026-08-23):** `frontend/src/AppShell.ts::renderErrorBoundary`
  interpolated `error.stack || error.message` directly into innerHTML; server-provided
  API `detail` strings can reach Error objects, so hostile markup could execute.
- **Fix:** static template only; message assigned via `textContent`.
- **Regression:** `frontend/src/AppShell.test.ts` DEF-005 case asserts `<img>`/`<b>`
  payloads render inert (mutation proof: reverting to innerHTML fails the suite).
- **Status: RESOLVED.**

## GAP-1 — catalog_artifact_content_not_validated

- **Reproduced (2026-08-23, before change):** byte-flipped `ch1.npy` with preserved size
  and mtime left catalog health=`ok`, reconcile `skipped=1`, verify drift=0
  (transcript: `repro-defects.log`).
- **Decision (documented):** the catalog is a disposable rebuildable index and raw-array
  bytes carry no reference hash in the frozen manifest schema, so routine reconcile stays
  stat-based (10k-row budgets from Todo 10 are kept — asserted by test).
  Added explicit deep content verification instead:
  `lnt catalog verify --deep` hashes every relevant file (incl. raw `.npy`/`.csv`)
  against a baseline snapshot `<database>.deep.json`; any byte change after baseline is
  reported as drift. First run records the baseline.
- **Regression:** `tests/catalog/test_deep_verify.py` — flip caught by deep verify,
  invisible to shallow verify (documented), clean tree passes, reconcile budgets intact.
- **Status: RESOLVED (deep artifact-hash verification added; shallow semantics documented).**

## GAP-2 — no shared RUNTIME safe-path guard

- **Reproduced (2026-08-23, before fix):** hostile `manifest.ch1.filename = "..\\x.npy"`
  let `write_session` escape the partial directory AND `load_session` read a channel
  outside the session directory (transcript: `repro-defects.log`).
- **Fix:** central guard module `src/lnt/safe_paths.py`
  (`is_safe_filename` / `ensure_safe_filename` / `ensure_within_root`) wired into
  `session_store.write_session/load_session`, HTTP artifact serving
  (`routes_analysis_v2.artifact_file`), session resolution defense-in-depth
  (`ui/sessions.resolve_session_dir`) and catalog classification predicate
  (`reconcile_parse._safe_filename`).
- **Regression:** `tests/test_safe_paths.py` (16-case filename matrix, write/read escape
  rejection, legit round-trip unchanged); mutation proof: disabling the guard fails the
  corpus (mutation-proofs.md).
- **Status: RESOLVED (central runtime guard in place).**

## Non-defects and skips

- JavaScript: 79 passed, 0 failed, 0 skipped.
- CLI selftest and help both exited 0.
- Package build exited 0 and produced both sdist and wheel.
- No skipped result was counted as a pass.
