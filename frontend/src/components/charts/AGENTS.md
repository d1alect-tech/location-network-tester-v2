# charts/ — wrappers for waveform / spectrum / spectrogram

## OVERVIEW
uPlot + echarts wrappers with min/max decimation, CSV strings, peaks/markers; display layer only, sessions stay raw.

## WHERE TO LOOK
- `series.ts`: `psdToDb` = 10*log10(psd), `psdToAsd`, `decimateMinMax`, `seriesToCsv`, `filterFinitePairs`
- `uplotView.ts` + `uplotOptions.ts`: uPlot mount, cursor emit, log-safe axes
- `echarts.ts`: modular ECharts registration (Heatmap only) + `initSpectrogramChart`; live consumer is `views/inspect/spectrogramOrient.ts`
- `spectrogramModel.ts`: tile requests, `TILE_CELL_CAP`, race-safe tile loader, `sliceTile`
- `spectrogramSetup.ts`: NPZ -> level (`levelFromNpz`), initial tile policy, small control factories
- `spectrogramPalette.ts`: 9-step matrix palette (independent of the frozen `showcase-round2` copy)
- `viewModels.ts`: `spectrumToRequest`, `waveformToRequest`, `POINT_BUDGETS`
- `annotations.ts`: `createPeaksPlugin`, band bounds, peaks summary
- `theme.ts` + `charts.css`: token reads, no hardcoded colors
- `types.ts`: `ChartHandle`, `ChartRenderRequest`, `MARKER_A/B`
- `npz.ts`, `tileError.ts`: artifact parse, typed tile errors

Live spectrogram path: `views/inspect/gramPair.ts` + `spectrogramOrient.ts` over
`spectrogramModel`/`spectrogramSetup`/`spectrogramPalette`/`echarts`. The old
`register`/`workbench`/`spectrogramPanel` cluster (unreachable from `main.ts`)
was deleted with its tests and the `bench/spectrogram-bench` harness; do not
re-add a second spectrogram shell here.

## CONVENTIONS
- Shells read CSS tokens via `theme.ts`; figures carry names, siblings carry statuses.
- Contract: `test_ui_chart_contract` checks named figures + sibling statuses.
- Decimation is min/max, display-only; never mutate session arrays.
- CSV mirrors plotted points; full-res export lives outside charts/.
- Log paths drop non-finite first via `filterLogSafePairs`.
- Peaks use plugin + summary pair; keep text RU-safe.
- Tile loads abortable; `isAbort` swallows cancels silently.

## ANTI-PATTERNS
- No third chart lib; no Plotly string anywhere in assets (`build-check` scans).
- No canvas-only output; every figure needs DOM name + status sibling.
- Keep every module under 250 pure LOC; `tests/test_module_size.py` enforces it with no exceptions left.
- No color literals in TS; route through tokens.
- No raw PSD on log axis; convert via `psdToDb` / `psdToAsd` first.
- No module that `main.ts` cannot reach: dead shells get deleted, not kept "for the bench".
