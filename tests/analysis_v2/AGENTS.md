# tests/analysis_v2 — v2 run-seam e2e

## OVERVIEW

22 files pinning the `analysis_v2` run seam (engine → orchestrator → artifact store → job API), not family math — family internals belong in `tests/characterization/` (own AGENTS.md).

## STRUCTURE

- `test_fNN_e2e_reduced.py` for f01–f18: public API only — `OUTPUT_FILENAMES`, `Status`, `load_bundle`, `encode_bundle` round-trips.
- `test_f11_wiring.py`, `test_f18_rate_baseline.py`: the sanctioned exception — reach internals (`f11_modes`, `f15_modes`, `fNN_bundle`, `fNN_contract`, `f18_triads`).
- `test_run_characterization.py`: characterization refactor pin (one of the 6 `*_characterization.py` files repo-wide).
- No own `conftest.py` — root `tests/conftest.py` applies.

## WHERE TO LOOK

| Task | File(s) |
|---|---|
| Run-seam refactor pin (`run_characterization`) | `test_run_characterization.py` |
| Family end-to-end (public API only) | `test_fNN_e2e_reduced.py` ×18 |
| Family internals (sanctioned exception) | `test_f11_wiring.py`, `test_f18_rate_baseline.py` |
| UI HTTP surface of the v2 seam | `tests/test_analysis_routes_v2.py` (root level) |

## CONVENTIONS

- The recipe comes from `docs/examples/characterization-recipe-v2.json` (`parents[2]` + `decode_object` + `parse_analysis_recipe`) in ~21 files — byte-stable fixture.
- Import surface: `lnt.analysis_v2` (engine, `jobs.AnalysisJobStore`, `recipes.RecipeCatalog`), `lnt.characterization` public names, `lnt.analysis_store`, `lnt.context.json_codec`, `lnt.simulate`, `lnt.ui.dependencies`/`models`.
- UI route behavior is pinned at root level (`tests/test_analysis_routes_v2.py`, 601 LOC); this directory stays on the Python seam. HTTP tests use `create_app` via FastAPI `TestClient` (httpx2), no live server.
- File naming mirrors roadmap waves: `test_fNN_{e2e_reduced,rate_baseline,wiring}.py`.
- `test_f18_e2e_reduced.py` (523 LOC) and `test_f18_rate_baseline.py` (493) are the growth zone — largest files here.

## ANTI-PATTERNS

- Don't reach into `lnt.characterization` internals from `test_fNN_e2e_reduced.py` — only wiring tests may cross that line.
- Expectations are analytic (synthetic signals with known harmonic/phase content), never engine output.
- Run-seam behavior changes (artifact keys, job payloads) are breaking here — `BranchFailureRecord` / `AnalyzeWriteResult` shapes are consumed by `lnt.ui`.
