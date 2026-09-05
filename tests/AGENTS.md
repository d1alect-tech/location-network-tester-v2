# tests/ — which suite to run

## OVERVIEW

~112 tracked files. Full run is 1269 pytest + 574 vitest + ~193 playwright — route by change type instead.

## WHICH SUITE FOR WHICH CHANGE

| You changed | Run |
|---|---|
| DSP / math (`psd/`, `spectrum`, `needles`, `uncertainty`) | `uv run pytest tests/science -q` + the matching `tests/test_<module>.py` |
| A facade you are splitting into leaves | the file's `*_characterization.py` — green BEFORE and AFTER the move |
| Manifest / session storage | `tests/test_manifest_characterization.py tests/test_v2_storage_contract.py -q` |
| CH1 setup, input-reference | `tests/test_ch1_manifest_contract.py tests/test_ch1_transfer_contract.py -q` |
| Any prod module's size | `tests/test_module_size.py tests/test_ui_chart_contract.py -q` |
| Frontend component / view logic | `cd frontend; npx vitest run <path>.test.ts` |
| Frontend wiring, a11y, visual flow | `cd frontend; npx playwright test --project=e2e <path>` |
| Chart render perf | `cd frontend; npm run bench:charts` — budgets, not correctness |

## LAYERS

- **`*_characterization.py` (5)** — refactor pins, NOT TDD-red. Written before a split; any diff = code-motion regression. Pin exact Russian `InputError` strings, driver code tables, sqlite snapshots, and facade re-export **by identity** (`except runner.X` must catch `runner_errors.X`).
- **`*_contract.py` (8)** — consumer-visible boundaries that must fail closed: schema rules, `store` facade re-export set, `DESIGN.md` ↔ `v2-tokens.css` ↔ `showcase.html` parity, static-JS DAG + chart a11y shells.
- **Golden values** — `tests/fixtures/manifest_frozen/` (3 valid must round-trip byte-identical incl. key order + trailing newline; 2 invalid must raise `InputError`), 5 report SHA-256 in `tests/reporting/test_reporting.py`, needles `golden.json`, `tests/analysis/test_events.py` `golden_test` preset at zero false positives.
- **`tests/science/`** — analytic truth corpus (`RATE_HZ 16384`, `COUNT 16384`, `SEED 20260811`, sha256 digest). Has its own AGENTS.md; read it before touching any golden.
- **`tests/js/*.test.mjs`** — `node --test`, not pytest.

## CONVENTIONS

- Config lives only in `pyproject.toml`: `testpaths=["tests"]`, `addopts="-ra --strict-markers"`. No `pytest.ini`.
- `tests/**` ruff ignores: `S101 PLR2004 SLF001 D ARG S603 FBT` — asserts, magic numbers and private access are expected here.
- Exactly ONE custom marker: `pristine`. Select `-m pristine` or exclude `-m "not pristine"`. Every other `@pytest.mark.*` is `parametrize`/`usefixtures`.
- `conftest.py` isolates AppData and seeds `rng(6022)`; `no_hantek_driver` poisons `sys.modules["PyHT6022"]` to force the no-driver path.
- Frontend split is by extension: `*.test.ts` = vitest (jsdom), `*.spec.ts` = playwright. `vitest.config.ts` excludes `*.spec.ts` explicitly — a spec named `.test.ts` silently runs in the wrong runner.
- Playwright is serial (`workers: 1`) against vite `:4101`; SSE specs need `installMockBackend` then `pumpAll`.

## SKIPS THAT ARE NOT FAILURES

- `test_pristine_gate.py` — skips without `.integrity/receipt-*.json` (machine-bound, untracked). If it FAILS instead, the receipt snapshot is stale against live `~/lnt-sessions`; regenerate the receipt, never edit session data.
- `test_scope_cancellation.py` poll test — skips without `PyHT6022`; hardware is an optional extra.
- `test_needles_bounded.py` golden half — skips without `.omo/start-work/evidence/b2-t17/golden.json`; the inline-legacy equivalence half still runs.
- No `xfail` exists anywhere. Any other red is a real regression.

## ANTI-PATTERNS

- Never widen a tolerance or edit a golden to turn red green — prod code changes to match goldens, not the reverse.
- Never derive expected values from the engine under test; corpus truth is analytic.
- Corpus change and `frontend/src/testkit/mockGolden.ts` update go in the SAME commit — frontend goldens mirror the corpus and must never diverge.
- Never delete a characterization test to make a refactor pass; that is the refactor failing.
