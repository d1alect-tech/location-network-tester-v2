# LNT (Location Network Tester) — KNOWLEDGE BASE

**Generated:** 2026-10-16
**Commit:** a714f5a
**Branch:** master

## OVERVIEW

LNT (Location Network Tester): offline-first line/network measurement and analysis — Hantek scope capture, F-suite characterization, v1/v2 analysis pipelines. Stack: Python 3.12 (numpy/scipy) + FastAPI UI + CLI; vanilla TS + Vite offline frontend; no React.

## STRUCTURE

```
./
├── src/lnt/          # product: science + data plane + orchestration + ui/ (own AGENTS.md)
├── frontend/src/     # vanilla TS: api/ views/ components/ charts/ capture/ state/ testkit/
├── tests/            # 279 files / 1813 tests; flat + science/ (truth corpus) + js/ (own AGENTS.md)
├── docs/             # adr/ (9 ADRs), roadmap.md, operator/scientific manuals, golden recipe example
├── scripts/          # quality.ps1 (local gate authority), audit-scope.ps1 (own AGENTS.md)
├── packaging/        # PyInstaller dual-EXE + deterministic ZIP, frozen spikes (own AGENTS.md)
├── benchmarks/       # PEP 723 standalone uv scripts: baseline.py, scientific.py + schema.json
└── LICENSES/         # offline copies of license families named in dependency-manifest.json
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| New measurement math | `src/lnt/<domain>/` + `tests/science/corpus.py` | Truth must be analytic, never engine-derived |
| Analysis branches | `src/lnt/analysis_v2/engine*.py` | v1 `analysis.py` is legacy facade; see `src/lnt/analysis_v2/AGENTS.md` |
| F-suite (f01–f18) | `src/lnt/characterization/` | locked recipes; artifacts = 3 files, 64 MiB cap |
| Recipe schema / artifact store | `src/lnt/analysis_store/` | v1/v2 dispatch, strict keys, content-addressed publish |
| SQLite catalog | `src/lnt/catalog/` | the only SQLite surface: ro-URI reader, O_EXCL+Wal writer, forward-only MIGRATIONS |
| HTTP/SSE/jobs | `src/lnt/ui/` | Single-job 409, launch-nonce gate |
| Frontend view | `frontend/src/views/<area>/` | Inspect is largest; showcase-round2 frozen |
| Charts | `frontend/src/components/charts/` | uPlot + echarts, token CSS only |
| Live capture | `frontend/src/capture/` | capture wizard, SSE hub, live spectrogram; mode contracts mirror `CaptureRequest` |
| Session format | `manifest.py` + `analysis_store/` | v1 legacy / v2 strict, bytes frozen |
| Local gates | `scripts/quality.ps1` | gate authority; exit-code contract in `scripts/AGENTS.md`; CI replays `-Full` |
| Release build | `packaging/` | dual-EXE spec, forbidden-pattern gates; see `packaging/AGENTS.md` |
| Tickets | GitHub Issues via `gh` | See `docs/agents/issue-tracker.md` |
| Onboarding / setup | `README.md`, `docs/agent-setup.md` | Public-facing; simulation path works with no hardware |
| Queue | `docs/roadmap.md` | A→B→C, mobile explicitly dropped |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `analyze_session` | func | `src/lnt/analysis.py` | cli, cli_compare, cm_dm/dispatch, ui/operations | v1 engine behind thin facade |
| `engine*` family | module | `src/lnt/analysis_v2/` | run_characterization, jobs, slices, spectrogram, projection | v2 orchestration over v1 engines |
| `CLI_SUBCOMMANDS` | const | `src/lnt/launcher.py` | mirrors `cli.py` parser | launcher↔parser contract (roadmap A4) |
| `resolve_session_dir` | func | `src/lnt/ui/sessions.py` | catalog + spectrum endpoints | dir-name OR session_id; `SessionAmbiguousError` on ambiguity |
| `characterization_contract` | module | `src/lnt/analysis_store/` | F-suite ID source of truth | locks f01–f18, recipe v1/v2 dispatch |
| `LntBackend.analyze_and_write/compare` | method | `src/lnt/ui/operations.py` | UI layer | v1 analysis bridge |
| `CaptureRequest` | model | `src/lnt/ui/models.py` | mirrored by `frontend/src/capture/modes.ts` | change both or neither |
| `el()` | func | `frontend/src/components/` | channelbar/status primitives | DOM-builder hub |
| `mockGolden.ts` | module | `frontend/src/testkit/` | e2e specs | goldens mirror `tests/science/corpus.py` |

## CONVENTIONS

- TDD RED→GREEN; module ≤250 pure LOC (`tests/test_module_size.py`) — enforced on Python AND frontend modules (testkit excluded). The ledger is EMPTY since D3 — every module must pass on its own. Split, never add an entry.
- `uv run --python 3.12` everything; ruff `ALL` (RUF001-003 off for Russian text); basedpyright `all`; biome + `tsc --noEmit` strict for frontend.
- CLI exits 0/1/2/3, one-line stderr, no traceback. Sessions atomic `.partial-*` + rename. Compare deltas `B - A`.
- Tests: `*.test.ts` = vitest, `*.spec.ts` = playwright (vite :4101, `installMockBackend` + `pumpAll`), `tests/js/*.mjs` = node:test.
- Domain docs: root `CONTEXT.md` is tracked — read it + touching ADRs; use glossary terms verbatim; flag ADR conflicts.

## ANTI-PATTERNS (THIS PROJECT)

- NEVER touch `frontend/src/showcase-round2/` or `frontend/bench/{DECISION.md,results.json}` (frozen). `showcase-redesign` is editable, but round2/round3 import its `data.ts`/`spectrum.ts`/`fonts.css` — renames break frozen code.
- Never update golden/corpus values silently: `frontend/src/testkit/mockGolden.ts` mirrors `tests/science/corpus.py` (update via the corpus only), and the spectrogram palette is a byte-equal copy of showcase-round2 values, pinned by test.
- NEVER: Plotly, React/Tailwind/Electron, opaque ML, UPX/onefile, auto-update, geolocation/telemetry collection.
- NEVER write into original `location-network-tester` tree or real `~\lnt-sessions`. `.integrity/` + `_recovery/` are untracked (still on disk); receipts never auto-update — regenerate explicitly or `test_pristine_gate` skips.
- NEVER claim calibrated voltage / IEC compliance / GUM / causation; `unavailable, never fabricated`.
- Built `src/lnt/ui/static/v2/` is committed — rebuild via `npm run build` (byte-stable gate `build:check`), never hand-edit.
- `docs/examples/characterization-recipe-v2.json` is byte-frozen: ~48 tests pin its exact bytes (sha256 in `docs/recipe-characterization-v1.md`).
- `.cortexkit/.gitignore` carries a tool-managed marker block — never hand-edit between the cortexkit markers.
- No `as any`, `@ts-ignore`; no `innerHTML` for untrusted content; tokens on `.app-v6`, never `:root`.

## UNIQUE STYLES

- Language split: Russian for operator/agent-facing docs and frontend UI/comments (RU-first); English for ADRs and process docs.
- Frontend and `src/lnt/ui/` are one deployable: Vite builds into the committed `static/v2/`; Python tests police frontend code (module size, chart DOM contract).
- Goldens exist in two languages — `tests/science/corpus.py` ↔ `frontend/src/testkit/mockGolden.ts` — the corpus is the single source of truth.
- Frontend mutations carry `x-lnt-mutation-nonce`; job progress streams over SSE `/api/jobs/{id}/events`.

## COMMANDS

```powershell
uv run --python 3.12 pytest -q          # full suite incl. e2e CLI
uv run --python 3.12 ruff check .; uv run --python 3.12 ruff format --check .
uv run --python 3.12 basedpyright
node --test "tests/js/*.test.mjs"
# frontend/: npm run typecheck, lint, test (vitest run), test:e2e (playwright :4101)
npm --prefix frontend run build:check    # byte-stable rebuild of committed static/v2
npm --prefix frontend run licenses:check
```

## NOTES

- Session lookup (roadmap D1, CLOSED): `ui/sessions.resolve_session_dir` accepts BOTH the directory name and the `manifest.json` `session_id` (ambiguity raises `SessionAmbiguousError`). The catalog shows the `id`; when it differs from the directory name the spectrum endpoint still serves 200.
- `lnt ui` holds a single-instance lease: a second launch exits 2. Kill the first before retrying, and free ports 8765/8770.
- Vite builds INTO `src/lnt/ui/static/v2` (base `/static/v2/`); byte-stable rebuild gate `npm --prefix frontend run build:check`, wired into `scripts/quality.ps1`.
- Offline: vendored uPlot 1.6.32 + IBM Plex; echarts 5.6.0 is the only other frontend runtime dep; server binds 127.0.0.1 only, Swagger/ReDoc off.
- Repo is PUBLIC under `GPL-3.0-only` (`LICENSE`). Hantek6022API is pinned to git `e65d52b` and is also `GPL-3.0-only`; its import remains lazy in `scope_io.py`.
- A Windows release (version 0.1.2 in `pyproject.toml`, tag `v0.1.2`, see `packaging/SOURCE.txt`) publishes four assets on one GitHub Release: `LNT-0.1.2-win64.zip{,.sha256}` and `LNT-0.1.2-corresponding-source.zip{,.sha256}`. The v0.1.0 release published the same four-asset shape: `LNT-0.1.0-win64.zip`, `LNT-0.1.0-win64.zip.sha256`, `LNT-0.1.0-corresponding-source.zip`, `LNT-0.1.0-corresponding-source.zip.sha256`. Publication is local and manual after the gates; CI uploads nothing. See `docs/distribution-policy.md`.
- Before publishing anything, run `git grep -n -I -F -- (Split-Path $env:USERPROFILE -Leaf)` and require no tracked-file matches.
- CI: `.github/workflows/build.yml` (job `reproducible-build`, windows-latest) replays `scripts/quality.ps1 -Full` + `compare-builds.ps1`; deliberately no upload/release/secrets.
- `benchmarks/`: PEP 723 standalone scripts — `baseline.py` (needs `ui` extra; `--json`/`--self-check`), `scientific.py` (self-inserts `src/`; enforced budgets); outputs validated against `benchmarks/schema.json`.

## ГРАНИЦА v1/v2 (очередь C4)

- v1 `analysis.py` — тонкий фасад: типы (`analysis_types`), пейлоады
  (`analysis_payload`), рендер (`analysis_render`), запись (`analysis_write`);
  движок `analyze_session` без изменений. Потребители v1: `cli.py`
  (`_cmd_analyze`), `cli_compare.py` (артефакты + откат на `analyze_session`),
  `cm_dm/dispatch.py` (маршрутизация v1 vs CM/DM), `ui/operations.py`
  (`LntBackend.analyze_and_write/compare`), `ui/payloads.py` (имена файлов).
- v2 `analysis_v2/engine*.py` — оркестрация веток ПОВЕРХ v1-движков
  (`cm_dm.analysis`, `line_quality` via `line_quality_v2`, `psd`/welch,
  events/features); математику не дублировать — переиспользовать v1.
- `line_quality.py`/`needles.py`/`spectrum.py` — движки v1, фасадами над v2
  не накрывать (дорого, риск дрейфа golden): граница задокументирована
  здесь вместо рефакторинга.
- `lnt compare` читает `metrics.json`+`spectrum.csv` (откат на полный
  анализ при отсутствии/порче); перед сравнением нужен `lnt analyze`.
  `spectrum.csv` хранит PSD в `%.9g` — дельты сходятся на точности рендера
  (0.1 дБ), не побитово.

## Agent skills

### Issue tracker

Tickets live as GitHub issues on `d1alect-tech/location-network-tester-v2`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `AGENTS.md` + `docs/adr/` + tracked root `CONTEXT.md`; see `docs/agents/domain.md` (its "no CONTEXT.md" note is stale).
