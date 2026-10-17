# views/ — workspace screens

## OVERVIEW

Five workspace views + capture wiring; routing map for AppShell. `inspect/`
has its own file (largest view). Earned by score 9.

## WHERE TO LOOK

| View | Entry (wired in `AppShell.ts`) | Domain |
|------|-------------------------------|--------|
| capture | `createCaptureView` (`src/capture/`) | wizard, SSE, live gram — see `src/capture/AGENTS.md` |
| inspect | `mountInspectV6` (`inspect/inspectV6.ts`) | spectrum/spectrogram/panels — see `inspect/AGENTS.md` |
| catalog | `mountCatalogWorkspace` (`catalog/catalogWorkspace.ts`) | session list, context inspector, profile manager |
| experiments | `mountExperimentsWorkspace` (`experiments/experimentsWorkspace.ts`) | wizard, member QC, comparisons, hypotheses, trends |
| reports | `mountReportsWorkspace` (`reports/reportsWorkspace.ts`) | client-side markdown report composition |
| settings | `mountSettingsWorkspace` (`settings/settingsWorkspace.ts`) | device state, preflight, root choice, support bundle |

- catalog: URL as state — filters + selection live in route params and
  survive reload; `QUERY_DEBOUNCE_MS=150` (`catalogWorkspace.ts`);
  race-guarded cursor pagination (generation + AbortController in
  `catalogStore.ts`).
- experiments: `experimentsStore.ts` (`ExperimentDetail`) is cross-view —
  reports imports it (`reportState`, `reportsStore`, `experimentModel` via
  `reportsWorkspace`); `comparisonView.ts` sits exactly at the 250
  pure-LOC ceiling.
- reports: composed client-side from statistics-runs + session details —
  backend has NO report endpoints, and the UI says so explicitly; never
  fabricate one.
- settings: reuses `capture/sse.watchJobEvents` and `capture/modes`
  (preflight).

## CONVENTIONS

- View entry: `mountXWorkspace(container, options) => cleanup`; the workspace
  imports its CSS barrel last (`reports.css`, `settings.css` are 6-line
  aggregators; cascade order = import order).
- Missing data renders н/д — «unavailable, never fabricated»
  (`catalog/contextMetrics.ts`; `contextThd.ts`: оценочные слова
  «норма»/«годен» запрещены).
- Cross-view reuse goes through the owning module's exports
  (reports→experiments), never DOM scraping.
- Report limitations are derived (`reportModel.deriveLimitations`), never
  invented.

## ANTI-PATTERNS

- No fetch in views — `src/api/` clients only.
- No view imports another view's CSS or private modules; only store/model
  exports cross the boundary.
- Catalog rows: label text may ellipsize, the type pill must not
  (`catalogRows.css`).
