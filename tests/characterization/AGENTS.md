# tests/characterization — F-suite analytic pins

## OVERVIEW

61 files / 779 test functions mirroring `src/lnt/characterization` module-per-module. Expectations are analytic and inline — no golden files in this directory.

## STRUCTURE

- `test_fNN_<aspect>.py` ↔ `lnt/characterization/fNN_<aspect>.py`; every family has `test_fNN_bundle.py` (18 files); rich families add aspect files (f12 leads with 9).
- 13 infrastructure tests: `test_bands`, `test_clipping`, `test_codec`, `test_codec_boundaries`, `test_envelopes`, `test_events`, `test_local_transform`, `test_models`, `test_phase`, `test_public_api`, `test_shared`, `test_stft`, `test_tables_store`.
- `conftest.py` is the only shared code: fixtures `bundle` / `arrays` / `tables`, helpers `make_bundle` / `make_arrays` / `make_tables` / `_support`.

## WHERE TO LOOK

| Task | File(s) |
|---|---|
| `fNNResult` → `FamilyResult` mapping + placeholders | `test_fNN_bundle.py` (×18) |
| Locked constants / declared codes | family contract tests (f12 has the fullest set) |
| Codec round-trip + byte caps | `test_codec.py`, `test_codec_boundaries.py` |
| Artifact-store publish + tamper detection | `test_tables_store.py` (byte flip on `characterization.json` → `ArtifactCorruptError`) |
| Phase substrate | `test_phase.py` |
| Public API pin (18 families, `Status` order) | `test_public_api.py` |

## CONVENTIONS

- 18 files exceed 500 LOC (`test_f17_bundle` 869, `test_f12_bundle` 837, `test_f18_bundle` 803 are the largest); f12 has the widest aspect coverage (9 files).
- ~21 files load the external recipe fixture `docs/examples/characterization-recipe-v2.json` via `Path(__file__).parents[2]` + `decode_object` + `parse_analysis_recipe` — the file's exact bytes are load-bearing.
- Each `test_fNN_bundle.py` verifies the `fNNResult` → `FamilyResult` mapping plus 17 `not_computed_family` placeholders — the unavailable path is first-class, not an error.
- Negative-path style: `pytest.raises(match=...)` on latin reason codes (single cyrillic match: `test_tables_store.py` `match="повреждён"`); values via `pytest.approx` / `np.testing`.
- Test files run 500–870 LOC by design — the module-size gate covers `src/lnt/**` only.
- Contract-validation density: `pytest.raises` (285) + `pytest.approx` (168) across the 779 tests — negative paths and reason codes are asserted, not just happy-path values.
- Artifact-store tests use `tmp_path`: `encode_bundle` → `ArtifactStore.publish` → `load_bundle`, then tamper-detection.
- No test classes, no async, no custom markers (only builtin `parametrize`); 60/61 files open with `from __future__ import annotations`.

## ANTI-PATTERNS

- Root-level `tests/test_{acquire,launcher,manifest,runner,store}_characterization.py` are facade refactor pins, NOT this package — a different "characterization" meaning; don't conflate.
- `scripts/quality.ps1` runs a pytest subset that does NOT include this directory — only the full suite gates it.
- `tests/test_module_size.py` never applies here; do not "fix" oversize test files by splitting them into fake coverage.
