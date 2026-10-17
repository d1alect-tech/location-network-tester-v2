# src/lnt/characterization — F-suite f01–f18

## OVERVIEW

148 flat modules: 18 analysis families + shared substrate. Only `src/` consumer is `analysis_v2/`; unit tests live in `tests/characterization/` (own AGENTS.md).

## STRUCTURE

- 18 families `f01_phase_cycle` … `f18_bicoherence_triads` — IDs locked in `analysis_store/characterization_contract.py`.
- Family modules `fNN_<role>.py`: `engine` (`compute_fNN_*`), `result` (`FNNResult`), `bundle` (`build_fNN_family` + `decode_fNN_result`), `contract` (locked `Final` constants + `FNNDeclarations`), `arrays`, `tables`, `validation`, plus family-specific roles (`modes`, `math`, `surrogates`, `triads`, `multiple_testing`, …).
- Family sizes: f18=19, f12=15, f17=14 modules; f01–f05 = 2–5.
- Shared substrate (~27 modules): `phase`/`phase_model`/`phase_stats`, `events`/`event_models`, `envelopes`/`envelope_models`, `bands`, `clipping`, `stft`, `sync_grid`, `local_transform(+_models)`, `shared` (`SharedComputations`), `records`, `models`, `tables`, `family_envelope`, `characterization_bundle` (all-family splice), codecs `bundle_codec`/`array_codec`/`table_codec`/`metadata_codec`/`json_parse`/`metadata_mapping`, `ids` (re-export only), `errors`.

## WHERE TO LOOK

| Task | Location |
|---|---|
| Public API (28 names, pinned by `tests/characterization/test_public_api.py`) | `__init__.py` |
| Artifact filenames, byte caps, codec round-trip | `bundle_codec.py` |
| Records: `Status`, `Unit`, `Band`, `ScalarSummary`, `Support` | `records.py` |
| Phase substrate (`PhaseCycles`/`PhaseMeans`) | `phase.py` / `phase_model.py` / `phase_stats.py` |
| Root events | `events.py` / `event_models.py` |
| All-family bundle assembly | `characterization_bundle.py` |

## CONVENTIONS

- Locked-recipe pattern: family `contract` modules hold `Final` constants (`METHOD`, `METHOD_VERSION`, `PHASE_BINS=64`, `FALSE_DISCOVERY_RATE=0.05`, …) and closed `DECLARED_CODES` tuples.
- Results carry `status` (available/partial/unavailable) + `reason_codes` only from the declared tuple — unavailable is explicit, never fabricated.
- `Unit` StrEnum closed set (V, V^2, V^2 s, Hz, s, rad, ratio, count, V^2/Hz); persisted array names must end with the SI suffix matching their unit (`validate_unit_name`).
- `@dataclass(frozen=True, slots=True, kw_only=True)`; invariants in `__post_init__` raise `CharacterizationError(reason_code, detail)`.
- Artifact contract: exactly three files (`OUTPUT_FILENAMES`) — `characterization.json`, `characterization-arrays.npz`, `characterization-tables.json`; byte caps 64 MiB total = 2 metadata / 14 tables / 48 arrays.
- numpy at module top level; cross-module model types under `if TYPE_CHECKING`.

## ANTI-PATTERNS

- Wide recipe/bundle functions carry `# noqa: PLR0913, PLR0917` with a Russian justification comment — keep the justification when editing.
- Validation modules are the invariant mass (`f17_validation`, `f18_validation`, `f12_validation` are the largest raw files) — expect edits there when family semantics change.
- Family golden outputs are consumed by `tests/analysis_v2/test_fNN_e2e_reduced.py` — semantic changes ripple there, not only into `tests/characterization/`.
