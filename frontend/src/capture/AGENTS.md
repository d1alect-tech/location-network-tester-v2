# capture/ — capture wizard, SSE hub, live spectrogram

## OVERVIEW

3-step capture wizard + job SSE watching + live gram; entry `createCaptureView`
wired by AppShell. Earned by score 9 (distinct domain, 39 files).

## WHERE TO LOOK

- `captureView.ts`: wizard shell wiring a dozen siblings; e2e selector pins
  are preserved as dual classes when modules split.
- `modes.ts`: `CAPTURE_MODES`, `validateCaptureForm`, `buildJobRequest` — mode
  contracts mirror `CaptureRequest` in `src/lnt/ui/models.py`; drift breaks
  both sides.
- `sse.ts`: `watchJobEvents` — native `EventSource` on `/api/jobs/{id}/events`;
  nonce only for mutations; fallback poll `GET /api/jobs/{id}` after 4 s of
  silence (`DEFAULT_STALE_MS`); consumed by inspect (`w1JobProgress`) and
  settings too.
- `jobTimeline.ts`: pure state machine — `initialTimeline`, `applySnapshot`,
  `isTerminal`; drives `w1JobProgress`/`w1JobRail` in inspect.
- `jobTimelineView.ts` / `captureSteps.ts` / `captureRecovery.ts`: timeline
  render, step flow, recovery prompt after failed jobs.
- `captureDeepLink.ts`: `captureParamsToPrefill` + `applyCapturePrefill` —
  commandbar deep-link prefill from `views/inspect/inspectTicket`.
- `spectrogramLiveStore.ts`: live-gram ring — `TIME_BINS=48` × `FREQ_BINS=256`,
  `LIVE_FLOOR_DB=-120`.
- `spectrogramLivePoller.ts`: `LIVE_POLL_MS=1500` while a job is active, one
  post-hoc fetch after idle, empty state (not error) without data.
- `spectrogramLiveRenderer.ts` / `spectrogramLivePaint.ts`: uPlot gram;
  palette from `components/charts/spectrogramPalette.ts`, never from
  showcase-round2.
- Device HTTP goes through `api/client-device` (`createDeviceApi`), imported
  directly by `captureView` / `captureStartFlow`.
- `capture.css`: aggregator — import order = cascade order
  (core→forms→blocks→notices→spectrogramLive); pulled by `src/style.css`.

## CONVENTIONS

- Polling: single in-flight request, drop never queue — generation counter +
  AbortController, the `src/state/resource.ts` pattern.
- SSE deps injected (`SseDeps`, fake `EventSource` ctor in tests) — specs
  never sleep.
- All HTTP via `src/api/` clients; no fetch here.
- RU labels: `STAGE_LABELS_RU`, `Intl.NumberFormat("ru-RU")`.

## ANTI-PATTERNS

- Don't move the live gram back into `views/inspect/` — it moved out in
  ui-refactor-2.
- Never import `showcase-round2` for the palette — the live copy in charts/
  is the only importable one.
- Keep e2e selector pins stable when splitting modules.
- `modes.ts` never gains a mode without the matching backend model change.
