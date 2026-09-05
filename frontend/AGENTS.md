# frontend AGENTS.md — scoped, telegraphic

## OVERVIEW
- Vanilla TS + Vite, no framework; uPlot + echarts; custom state/router.

## STRUCTURE
- `src/main.ts`: bootstrap; no-store `index.html` + hashed-URL bootstrap contract.
- `src/AppShell.ts`: hash routing, view switching, shell chrome.
- `src/api/`: 24 typed clients, one per backend group; no fetch outside.
- `src/views/`: route screens; inspect largest; keep view-local logic inside.
- `src/components/charts/`: uPlot + echarts wrappers; token CSS only.
- `src/state/`: `buildGate` + `resource` + `routeState`; single source per concern.
- Rollup inputs: `index.html` + 13 `showcase*.html` (a/b/c/d, redesign, round2, v1-v6, base).
- `scripts/build-manifest.js`: emit asset manifest; `scripts/build-check.js`: byte-stable rebuild gate.

## CONVENTIONS
- Vite `base: /static/v2/`; `outDir: ../src/lnt/ui/static/v2`; `emptyOutDir: true`.
- Dev: `vite :4101`; prod served from backend static, never standalone.
- Biome only, no eslint; 2-space, 100-col; `tsc --noEmit` strict clean.
- Hashed assets: `assets/[name].[hash].js`; `manifest: true`; no inline scripts.
- Offline: vendored uPlot 1.6.32 + IBM Plex WOFF2; zero external requests.
- Tests: `*.test.ts` vitest unit; `*.spec.ts` playwright (`installMockBackend` + `pumpAll`).
- Charts: min/max decimation at server edge (spectra 5000, previews 4000); never mutate source data.
- Compare deltas `B - A`; line-quality sessions: no A/B, open metrics singly.
- Theme: system/light/dark toggle, `localStorage` persist; launch-nonce on mutating calls.

## ANTI-PATTERNS
- NEVER touch `src/showcase-round2/`; frozen reference, read-only — and it is NOT inert: `capture/spectrogramLivePaint.ts` + `spectrogramLiveRenderer.ts` import `showcase-round2/spectrogramPalette`, so an "unused prototype" edit breaks live capture rendering. A second, independent `components/charts/spectrogramPalette.ts` also exists; check which one a file imports before touching either.
- NEVER hand-edit built `src/lnt/ui/static/v2/`; rebuild via `npm run build`.
- Tokens on `.app-v6` only, never `:root`; no hardcoded colors outside tokens.
- DESIGN.md A/B semantics: A = cyan solid + circle marker; B = amber dashed + square marker.
- A11y floor: 44px targets, 2px focus ring, honor `prefers-reduced-motion`.
- No `innerHTML` for untrusted content; no `as any` / `@ts-ignore`.
- No React/Tailwind/Plotly/Electron; no new deps without offline + license check.
