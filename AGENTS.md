# LNT (Location Network Tester) — KNOWLEDGE BASE

**Stack:** Python 3.12 (numpy/scipy) + vanilla TS + Vite. No React. CLI + FastAPI UI + offline frontend.

## STRUCTURE

```
./
├── src/lnt/          # product: science + data plane + orchestration + ui/
├── frontend/src/     # vanilla TS: api/ views/ components/charts/ state/
├── tests/            # pytest flat + science/ (truth corpus) + js/ (node:test)
├── docs/             # adr/ (9 ADRs), roadmap.md, operator/scientific manuals
├── scripts/          # quality.ps1 (local gate authority), audit-scope.ps1
└── packaging/        # PyInstaller dual-EXE + deterministic ZIP, frozen spikes
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| New measurement math | `src/lnt/<domain>/` + `tests/science/corpus.py` | Truth must be analytic, never engine-derived |
| Analysis branches | `src/lnt/analysis_v2/engine*.py` | v1 `analysis.py` is legacy facade |
| HTTP/SSE/jobs | `src/lnt/ui/` | Single-job 409, launch-nonce gate |
| Frontend view | `frontend/src/views/<area>/` | Inspect is largest; showcase-round2 frozen |
| Charts | `frontend/src/components/charts/` | uPlot + echarts, token CSS only |
| Session format | `manifest.py` + `analysis_store/` | v1 legacy / v2 strict, bytes frozen |
| Tickets | GitHub Issues via `gh` | See `docs/agents/issue-tracker.md` |
| Queue | `docs/roadmap.md` | A→B→C, mobile explicitly dropped |

## CONVENTIONS

- TDD RED→GREEN; module ≤250 pure LOC (`tests/test_module_size.py`, `_GRANDFATHERED` pins exact — split, never grow).
- `uv run --python 3.12` everything; ruff `ALL` (RUF001-003 off for Russian text); basedpyright `all`; biome + `tsc --noEmit` strict for frontend.
- CLI exits 0/1/2/3, one-line stderr, no traceback. Sessions atomic `.partial-*` + rename. Compare deltas `B - A`.
- Tests: `*.test.ts` = vitest, `*.spec.ts` = playwright (vite :4101, `installMockBackend` + `pumpAll`), `tests/js/*.mjs` = node:test.
- Domain docs: read root `CONTEXT.md` (absent → proceed silently) + touching ADRs; use glossary terms verbatim; flag ADR conflicts.

## ANTI-PATTERNS (THIS PROJECT)

- NEVER touch `frontend/src/showcase-round2/` (frozen); never update golden/corpus values silently.
- NEVER: Plotly, React/Tailwind/Electron, opaque ML, UPX/onefile, auto-update, geolocation/telemetry collection.
- NEVER write into original `location-network-tester` tree or real `~\lnt-sessions`; receipts in `.integrity/` never auto-update.
- NEVER claim calibrated voltage / IEC compliance / GUM / causation; `unavailable, never fabricated`.
- Built `src/lnt/ui/static/v2/` is committed — rebuild via `npm run build`, never hand-edit.
- No `as any`, `@ts-ignore`; no `innerHTML` for untrusted content; tokens on `.app-v6`, never `:root`.

## COMMANDS

```powershell
uv run --python 3.12 pytest -q          # full suite incl. e2e CLI
uv run --python 3.12 ruff check .; uv run --python 3.12 ruff format --check .
uv run --python 3.12 basedpyright
node --test "tests/js/*.test.mjs"
# frontend/: npm run typecheck, lint, test (vitest run), test:e2e (playwright :4101)
```

## NOTES

- `CLI_SUBCOMMANDS` in `launcher.py` must mirror `cli.py` parser (see roadmap A4).
- Vite builds INTO `src/lnt/ui/static/v2` (base `/static/v2/`); byte-stable rebuild required by `build-check.js`.
- Offline: vendored uPlot 1.6.32 + IBM Plex; server binds 127.0.0.1 only, Swagger/ReDoc off.
- Hantek dep pinned to git `e65d52b` (GPL); private-use build must never leave the machine.
