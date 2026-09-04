# Inspect view (v6)

## OVERVIEW

Largest view: spectrum / spectrogram / v2 panels + pairbar + analysis band.

## WHERE TO LOOK

- `inspectV6.ts` — boot: mount, route parse, panel wiring, teardown.
- `inspectV6Load.ts` / `inspectV6Gram.ts` — session load + gram align entry.
- `v6Chrome.ts` — tabbar + commandbar shell.
- `w1Chrome.ts` / `w1Parse.ts` — w1 chrome variant + parse helpers.
- `spectrumPanelV6.ts` — spectrum panel render + axes + peak markers.
- `spectrogramLive*.ts` — live gram: ring 48x256, rAF draw, poll `spectrum|waveform` ~1500ms.
- `spectrogramOrient.ts` / `gramAlign.ts` / `gramPair.ts` — orientation, alignment, pairing.
- `pairbarV6.ts` / `pairState.ts` — pairbar slots + A/B state.
- `analysisBand.ts` — analysis band row under charts.
- `panels/fetch.ts` — fetch layer; never-fake-0 rule lives here.
- `panels/` — per-panel fetch + render split.
- `catalogColumn*.ts` — catalog column model + render.
- `peaksDelta.ts` / `thdVerdict.ts` — delta + verdict chips.
- `v6.css` / `w1Chrome.css` — view-scoped styles only.
- `*.spec.ts` — playwright; `*.test.ts` — vitest; `*.mount.test.ts` — mount harness.

## CONVENTIONS

- PSD axis labels: dBV/Hz, ref 1 V²/Hz. Never bare dB.
- Show RBW = 1.5 x resolution_hz next to spectrum.
- Display decimation: max-aggregation, never mean/subsample.
- [Scope|Input] toggle: scope = raw CSV; input = input-referred excess.
- Input unavailable -> silent fallback to scope, no error toast.
- Compare deltas always B - A.
- Live poll: single in-flight request; drop, never queue.

## ANTI-PATTERNS

- Commandbar is navigation, not capture: values discarded on apply.
- Deep-link ticket C1 open: do not wire commandbar into capture params.
- On fetch throw: `showError` only; never leave stale chart on screen.
- No synthetic PSD fill: missing bins stay missing, never zero-filled.
- Pairbar slots need keyboard access: tab/enter operable, visible focus.
- No cross-panel CSS leaks: scope to view root, no global selectors.
- No direct `fetch()` in panels: go through `panels/fetch.ts`.
