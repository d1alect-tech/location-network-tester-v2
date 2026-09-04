# analysis_v2 — AGENTS.md

## OVERVIEW
v2 analysis orchestrator + recipe dispatch, branch fan-out.

## WHERE TO LOOK
- `engine.py` — orchestration entry, run lifecycle, artifact assembly
- `engine_branches.py` — per-branch fan-out, branch inputs/outputs
- `default_recipe.py` — default recipe construction, baseline params
- `recipes.py` — recipe registry, named recipe definitions
- `artifact_inputs.py` — artifact input gathering, scope-plane prep
- `../analysis_store/settings.py` — `WelchSettings`, `SpectrogramSettings`
- `../analysis_store/recipe.py` — recipe validation, schema gate

## CONVENTIONS
- recipe first: validate via `analysis_store/recipe.py` before dispatch
- RBW selector extension point = recipe validation layer, not engine
- Hann window default, overlap 0.5, mean-only averaging
- `spectrum.csv` = raw scope-plane PSD, no smoothing applied here
- branch outputs merge into single artifact bundle, keep keys stable
- settings structs immutable, pass by value into branches
- new branch = new function in `engine_branches.py` + recipe entry
- dispatch table lives in `recipes.py`, no if-chains in `engine.py`
- default params frozen in `default_recipe.py`, overrides via recipe only
- `artifact_inputs.py` builds numpy views, no I/O inside branches
- branch keys stable across runs, rename = breaking change
- Welch/Spectrogram params flow from settings structs, no literals
- recipe name logged per run, traceable to artifact bundle

## ANTI-PATTERNS
- never duplicate fixes across v1/v2 tracts, v1 `analysis.py` is facade only
- no silent golden changes, corpus deltas need explicit sign-off
- no smoothing inside scope-plane path, smoothing lives downstream
- no direct settings mutation inside branch, copy on change
- no new recipe fields without validation update in `analysis_store/recipe.py`
- no cross-branch state sharing, branches stay independent
