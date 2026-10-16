# src/lnt/analysis_store — recipes + content-addressed artifacts

## OVERVIEW

19 modules, two jobs: strict recipe parsing (schema v1 + v2 characterization) and the content-addressed `ArtifactStore`. ~60 files across `src/` and `tests/` import it.

## WHERE TO LOOK

| Task | Location |
|---|---|
| Public API (11 names, `__init__.py` `__all__`) | `AnalysisRecipe`, `AnalysisRecipeDocument`, `ArtifactConflictError`, `ArtifactCorruptError`, `ArtifactInputs`, `ArtifactStore`, `CharacterizationRecipe`, `CodeIdentity`, `NamedDigest`, `RecipeError`, `parse_analysis_recipe` |
| Schema dispatch | `recipe_parse.py`: `schema_version` 1 → `AnalysisRecipe`, 2 → `CharacterizationRecipe` |
| v1 recipe validation | `recipe.py` (largest module, 245 LOC) |
| v2 characterization recipe | `recipe_v2.py` + 9 `characterization_*.py` leaves |
| Welch / spectrogram settings | `settings.py` (`WelchSettings`, `SpectrogramSettings`) |
| Characterization settings | `characterization_settings.py` (`PhaseSettings`, `StftSettings`, `ResourceLimits` — ~40 importers, mostly `TYPE_CHECKING`) |
| Store / publish / verify | `store.py`, `manifest.py` (`verify_artifact`), `provenance.py`, `identity.py` (`CodeIdentity`, `SHA256_LENGTH`), `errors.py` |

## CONVENTIONS

- Strict schema parsing: exact key-set match; errors list unknown/missing keys (`неизвестные=…, отсутствуют=…`).
- v2 requires exactly 18 families in `FAMILY_IDS` order (`zip(..., strict=True)`).
- `artifact_key` = SHA-256 of canonical payload of recipe hash + 4 declared dependency groups + `code_identity` string `lnt=<v>;numpy=<v>;scipy=<v>`.
- Digests are lowercase SHA-256 (64 hex) validated at construction; canonical JSON via `lnt.context.json_codec.encode_canonical`.
- All errors subclass `lnt.errors.InputError`; `ArtifactCorruptError` carries a machine-readable `reason_code`.
- `publish` writes `<key>.partial-<uuid>` then atomic rename — never overwrites; `invalidate` renames to `<key>.invalid-<uuid>`, no deletion. Outputs fsynced (`xb` + `os.fsync`); symlink/reparse defense via `lnt.safe_paths`.

## ANTI-PATTERNS

- No new recipe fields without a validation update here (`recipe.py` / `recipe_v2.py`) — `analysis_v2` dispatch depends on this gate.
- `FAMILY_FIELDS` (18 families × method + field list) and `LOCKED_VALUES` are consumed by validation, fNN bundles, and the frontend family table — a change is cross-cutting.
- The store guarantees identical bytes only within the same locked environment; never claim cross-platform bit-identity.
