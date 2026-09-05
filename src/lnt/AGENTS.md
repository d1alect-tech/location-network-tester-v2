# src/lnt — AGENTS.md

## OVERVIEW

Science + data-plane + orchestration packages, flat modules + ~26 subpacks.

## WHERE TO LOOK

| Area | Modules |
|---|---|
| Acquisition HW | `acquire.py`, `scope_io.py`, `capture_preflight.py`, `simulate.py`, `device_diagnostics.py` |
| Signal science | `psd/`, `spectrum/`, `spectrogram/`, `features/`, `needles/`, `harmonics/`, `apd/`, `burst/`, `cm_dm/`, `notching/`, `power_quality/`, `line_quality*/`, `uncertainty/`, `statistics/`, `trends/` |
| Data plane | `catalog/`, `archive/`, `session_store/`, `analysis_store/`, `manifest.py`, `manifest_*` |
| Orchestration | `experiments/`, `research/`, `reporting/`, `runtime/`, `config/` |
| Analysis tracts | `analysis.py` (facade), `analysis_v2/engine*.py` (active) |
| Entry | `cli.py`, `launcher.py`, `ui/` |

## CONVENTIONS

- `analysis.py` is legacy facade, active logic lives in `analysis_v2/engine*.py`.
- New analysis branches go in `analysis_v2/`, never extend `analysis.py`.
- `_private.py` / `_*.py` modules are internal to parent subpack, no cross imports.
- Russian comments allowed in science modules alongside English docstrings.
- `InputError` raised typed at check site, message carries context.
- EM/TRY ruff rules off here: raw messages plus direct raise preferred.
- Session layout authority: `manifest.py` + `manifest_*` plus `analysis_store/`.
- Deltas computed as `B - A`, compare path mirrors catalog IDs.

## ANTI-PATTERNS

- Zero Python modules on the grandfather ledger — every `src/lnt/**` file must stay ≤250 pure LOC on its own. A new oversize module fails `tests/test_module_size.py`; split it, never add a ledger entry.
- `CLI_SUBCOMMANDS` in `launcher.py` must mirror `cli.py` parser.
- Never interrupt atomic rename in `acquire.py` (`.partial-*` + rename).
- Never bypass `capture_preflight.py` checks in capture flows.
- Never import `ui/` from science or data-plane modules.
- Never fabricate calibration, compliance, or causation claims in reporting.
