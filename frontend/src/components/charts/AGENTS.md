# charts/ — wrappers for waveform / spectrum / spectrogram

## OVERVIEW
uPlot + echarts wrappers with min/max decimation, CSV export, peaks/markers; display layer only, sessions stay raw.

## WHERE TO LOOK
- `series.ts`: `psdToDb` = 10*log10(psd), `psdToAsd`, `decimateMinMax`, `seriesToCsv`, `filterFinitePairs`
- `uplotView.ts` + `uplotOptions.ts`: uPlot mount, cursor emit, log-safe axes
- `echarts.ts` + `spectrogramView.ts`: echarts spectrogram shell, `baseOption`, markers A/B
- `spectrogramView.ts` (269 LOC) / `spectrogramPanel.ts` (288 LOC): grandfathered, split only
- `workbench.ts` (306 LOC): grandfathered multi-chart host, cursor bridge, detail open
- `spectrogramModel.ts`: tile requests, `TILE_CELL_CAP`, loader, slice
- `spectrogramSetup.ts` + `spectrogramSummary.ts`: tile init, window summary, matrix CSV
- `viewModels.ts`: `spectrumToRequest`, `waveformToRequest`, `POINT_BUDGETS`
- `annotations.ts`: `createPeaksPlugin`, band bounds, peaks summary
- `csvDownload.ts`: `downloadCsv` entry point
- `theme.ts` + `charts.css`: token reads, no hardcoded colors
- `types.ts`: `ChartHandle`, `ChartRenderRequest`, `MARKER_A/B`
- `register.ts`: `mountInspectWorkbench`, `mountInspectSpectrogram`
- `npz.ts`, `tileError.ts`, `readout.ts`, `eventList.ts`: artifact parse, errors, cursor readout

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
- Do not grow grandfathered files: spectrogramView / spectrogramPanel / workbench.
- No color literals in TS; route through tokens.
- No raw PSD on log axis; convert via `psdToDb` / `psdToAsd` first.
- No sync CSV stringify on full tiles; use sliced summary helpers.
