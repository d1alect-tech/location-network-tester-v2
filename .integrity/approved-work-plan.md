# lnt-complete-redesign - Work Plan

## TL;DR (For humans)
<!-- Fill this LAST, after the detailed plan below is written, so it summarizes the REAL plan. -->
<!-- Plain English for a non-engineer: NO file paths, NO todo numbers, NO wave/agent/tool names. -->

**What you'll get:** Отдельную LNT v2: безопасный и воспроизводимый научный инструмент с автосбором контекста, каталогом и профилями, более глубоким спектральным/временным анализом, экспериментами A/B/A и повторными сериями, полностью новым русским интерфейсом, отчётами/резервными копиями и переносимой Windows-сборкой без установленного Python.

**Why this approach:** Проверенные захват, форматы исходных данных и режимы не переписываются «с нуля»: новые возможности добавляются вокруг неизменяемых записей через версионированные контекст, рецепты анализа и эксперименты. Самая рискованная цепочка — осциллограф, libusb, прошивка и замороженная сборка — проверяется рано, а научные методы принимаются только по синтетической истине и явным ограничениям.

**What it will NOT do:** Не изменит нынешнюю LNT и реальные записи, не будет телеметрии/облака, не станет придумывать калибровку или причинность и не будет автоматически работать с опасной сетевой схемой. Сборка не устанавливает WinUSB сама и не обещает сертифицированное измерение. Публичная публикация не входит в работу из-за отдельного вопроса GPLv3.

**Effort:** XL
**Risk:** High — проект одновременно затрагивает научную корректность, гигабайтные записи, USB-драйвер/прошивку, полную замену UI и автономную Windows-упаковку.
**Decisions to sanity-check:** Каталог — восстанавливаемый локальный индекс, а не источник истины; старый манифест остаётся без новой версии; интерфейс — строгий инструмент/workbench; графики — uPlot + модульный ECharts; дистрибутив — one-folder ZIP только для владельца без передачи другим лицам; на этом ПК доказывается работа лишь в очищенном окружении эталонного хоста, не в новой чистой VM.

Your next move: после обязательного двойного high-accuracy review передать этот план отдельной рабочей сессии; этот planning-сеанс реализацию не запускает. Full execution detail follows below.

---

> TL;DR (machine): XL/high-risk; 7 implementation waves, 52 TDD todos and 4 final verifier tasks deliver isolated LNT v2 metadata/catalog, scientific analysis/experiments, full accessible UI, archives and private one-folder Windows package while preserving original code/sessions.

## Scope
### Must have
- Work exclusively in `C:\Users\Kirill\Documents\InputLag\location-network-tester-v2`; maintain reproducible SHA-256 receipts proving that the original product tree and `C:\Users\Kirill\lnt-sessions` were not changed.
- Preserve strict manifest schema v1/v2 and all existing single-channel, dual-channel, self-noise, baseline-correction and transformer line-quality behavior. Add optional versioned sidecars/artifacts rather than a manifest-v3 rewrite.
- Make raw `ch1.npy`/`ch2.npy` captures immutable evidence; make every context edit, analysis recipe, derived artifact, exclusion, comparison and export provenance-addressable and auditable.
- Add offline-safe typed context profiles and automatic app/OS/device/acquisition metadata; a rebuildable SQLite catalog; durable jobs; actionable device/preflight/quality diagnostics; cancellation and restart recovery.
- Add explicit, versioned and bounded-memory PSD/STFT recipes, spectrogram overviews with exact zoom, event/transient inventory, uncertainty semantics, richer line-quality and input-reference outputs, and a synthetic scientific validation corpus.
- Add experiment grouping/protocols for A/B, A/B/A, repeated blocks, cohorts and longitudinal observations; explicit comparability/QC; effect sizes, intervals, drift/confound checks; and structured, user-authored hypotheses without causal automation.
- Replace the current long dashboard with a Russian-first offline scientific workbench: Prepare → Capture → Inspect → Compare/Experiment → Explain/Export. Include responsive, keyboard, zoom, reduced-motion, forced-colors and non-color-cue support.
- End with exactly two purpose-fit local chart libraries: uPlot for dense 1-D waveform/spectrum views and modular ECharts for 2-D spectrogram/event exploration. Built assets ship locally; Node is never required at runtime.
- Add versioned JSON/CSV/HTML/ZIP exports, checksum-verified backup/restore, support bundles, docs, and a private-use PyInstaller 6.14.1 one-folder Windows x64 package that runs without Python/Node.
- Close every reproducible defect found by the baseline, migration, browser, hardware-diagnostic, frozen-runtime, security, performance and scope audits.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- MUST NOT edit product files in `location-network-tester`, mutate real captures/sessions, overwrite raw arrays, silently migrate a session, or use the SQLite catalog as the only copy of evidence.
- MUST NOT add manifest fields unknown to the strict v1/v2 reader; new state belongs in independently versioned `context.json`, audit logs, analysis directories and experiment records.
- MUST NOT silently collect geolocation, host names, process inventories, telemetry or cloud data; make sensitive metadata opt-in and source-labelled. No cloud account, CDN, remote DB or mandatory network.
- MUST NOT claim calibrated primary voltage, certified IEC/IEEE compliance, GUM completeness, causation, “improvement”, or anomaly certainty when calibration/repeats/estimand/direction are absent. Missing evidence is reason-coded `unavailable`, never fabricated.
- MUST NOT compare unlike session types or silently exclude bad captures. Line-quality compares only line-quality; HF compares only compatible measurement/self-noise recipes; every exclusion remains visible and reversible.
- MUST NOT introduce opaque ML, automatic theory generation, Electron, React, Tailwind, a third chart library, canvas-only information, decorative motion, generic card-soup UI or inaccessible million-cell DOM tables.
- MUST NOT leave Plotly in the committed v2 product after ECharts is added; uPlot replacement/removal happens first so no committed state contains three chart libraries.
- MUST NOT ship one-file/UPX packaging, bundle Zadig, install drivers, bypass administrator policy, silently auto-update, convey the package to another person, publish a release, relicense LNT or claim redistribution compatibility. The package is owner-internal; any conveyance requires a separate GPLv3 compliance decision.
- MUST NOT require human intervention to verify implementation. Unsafe mains capture is never automated; use simulator/fixtures plus a non-invasive real device diagnostic.
- MUST NOT accept worker self-report, grep-only checks, stale generated frontend assets, stale server processes, dirty-source overwrites, hidden test skips, or unmeasured performance claims as proof.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: strict RED→GREEN TDD. Python uses pytest + Ruff + basedpyright; TypeScript uses Vitest + `tsc --noEmit` + Biome; browser flows use Playwright; scientific numerics use deterministic synthetic/golden/property tests; frozen runtime uses PowerShell smoke scripts; final UI evidence uses `/visual-qa`; final handoff uses `/review-work`.
- Baseline commands (record exact stdout/counts before modification): `uv sync --all-extras --dev`; `uv run pytest -q`; `node --test tests/js/*.test.mjs`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run basedpyright`; `uv build`.
- Unified final commands: `uv run pytest -q`; `uv run ruff check .`; `uv run ruff format --check .`; `uv run basedpyright`; `npm --prefix frontend ci`; `npm --prefix frontend run lint`; `npm --prefix frontend run typecheck`; `npm --prefix frontend run test`; `npm --prefix frontend run build:check`; `npm --prefix frontend run test:e2e`; `uv build`; `pwsh -File packaging/build.ps1`; `pwsh -File packaging/smoke-portable.ps1`.
- Scientific invariants: Parseval/integrated-power tolerance, exact frequency-grid/units, synthetic tone/harmonic/event recovery, chunked-vs-SciPy Welch tolerance, deterministic recipe/output hashes in the locked build, cross-environment tolerance fixtures, repeatability-only Type-A intervals and reason-coded unavailable Type-B/combined uncertainty.
- Data invariants: legacy v1/v2 manifests round-trip byte/semantic fixtures; original and real-session hash manifests match; raw arrays remain unchanged; catalog can be deleted/rebuilt; backup→delete working copy→restore produces identical checksums and semantic index.
- UI/performance fixtures: 10,000 catalog rows; a memmapped 30 s × 8 MHz single-channel capture; 200,000 displayed 1-D points; stored 2048×1024 spectrogram overview served through the benchmark-selected bounded viewport tile; long Russian labels/Windows paths; all empty/loading/error/running/cancelled/interrupted/corrupt/missing-driver states.
- Performance gates on the recorded reference host: catalog warm query p95 ≤500 ms for 10,000 rows; warmed plot payload p95 ≤500 ms; 1-D initial render ≤1,000 ms and pan/zoom p95 ≤100 ms; spectrogram initial render ≤1,500 ms and interaction p95 ≤250 ms at the selected cap; 30 s × 8 MHz PSD ≤120 s, STFT overview ≤180 s, peak RSS ≤1.5 GiB, STFT temp ≤8 GiB and cancellation acknowledgement ≤500 ms; portable health ≤15 s cold; unzipped bundle ≤600 MiB. Record hardware/OS with every benchmark and never relax a gate from the same run it fails.
- Accessibility evidence: Playwright + axe (zero serious/critical violations), complete keyboard journeys, 200% zoom, 375/768/1280 px, light/dark/system/forced-colors/reduced-motion, non-color cues, Russian string assertions, CSV/summary alternatives for 1-D and summary/event/matrix downloads for 2-D.
- Evidence: `<attemptDir>/task-<N>-lnt-complete-redesign.<ext>` (attemptDir = currentAttemptDir from `omo ulw-loop status --json`; outside ulw-loop use `.omo/evidence/`). Every todo writes command logs plus structured JSON; UI tasks add screenshots/traces; no evidence is written into either product tree.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.

- **Wave 0 — isolation and measured baseline:** Todo 1, then Todos 2–5 in parallel. No other wave may start until the copy receipt and pristine guard pass.
- **Wave 1 — context and catalog foundation:** Todos 6–12; models/paths can parallelize, then converge on integration/API.
- **Wave 2 — trustworthy acquisition and jobs:** Todos 13–18; frozen-device spike is intentionally early because it can invalidate packaging assumptions.
- **Wave 3 — scientific analysis:** Todos 19–28 in dependency order with PSD, spectrogram and line-quality branches parallel after the artifact contract.
- **Wave 4 — experiments and inference:** Todos 29–35; store/protocol, QC, statistics and reports converge on APIs.
- **Wave 5 — frontend workbench:** Todos 36–44; design contract/toolchain first, then independent workflow surfaces, then integrated accessibility/responsiveness.
- **Wave 6 — portability, migration and hardening:** Todos 45–52; archive/launcher/package branches converge on frozen smoke, migration rehearsal, full defect/quality sweep and docs.
- **Final wave:** F1–F4 run in parallel only after all 52 implementation todos and their evidence exist; all four must approve.

### Milestone usability gates
- After Wave 1, v2 still runs every v1 command and can browse legacy sessions; context/catalog loss cannot lose a capture.
- After Wave 2, every current capture mode has durable/recoverable jobs, safe cancellation boundaries and actionable frozen-device diagnostics.
- After Wave 3, one session can be re-analysed reproducibly with bounded memory and inspected through stable APIs before experiments/UI redesign depend on it.
- After Wave 4, a complete synthetic A/B/A experiment can be created, validated, analysed and exported without the new UI.
- After Wave 5, all owner workflows are available in the new workbench and Plotly is absent.
- After Wave 6, the private-use ZIP, migration/restore tooling, docs and immutable-original proof are release-candidate complete.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | — | 2–52 | — |
| 2 | 1 | 3, 13, 19, 51 | 3–5 |
| 3 | 1,2 | 6–12,19,29,36 | 4,5 |
| 4 | 1,2 | 13,47,49 | 3,5 |
| 5 | 1 | 6–52 | 2–4 |
| 6 | 3,5 | 8–12,46 | 7,9 |
| 7 | 3,5 | 8–12,19,29 | 6,9 |
| 8 | 6,7 | 11,32,39 | 9,10 |
| 9 | 6,7 | 10–12,16,29 | 8 |
| 10 | 9 | 11,12,50 | 8 |
| 11 | 8–10 | 12,27,45,50 | — |
| 12 | 11 | 36,39 | — |
| 13 | 2,4,6 | 14–18,47 | 19 |
| 14 | 13 | 17,18,30 | 15,16 |
| 15 | 13 | 16,17 | 14 |
| 16 | 9,15 | 17,18,40,46 | 14 |
| 17 | 14–16 | 18,33 | — |
| 18 | 12,16,17 | 36,38,40,46 | — |
| 19 | 3,7 | 20–28,29 | 13 |
| 20 | 19 | 21,24,26–28 | 22,25 |
| 21 | 20 | 25,26,31 | 22,23 |
| 22 | 19 | 23,27,28,42 | 20,25 |
| 23 | 22 | 24,27,28,42 | 21,25,26 |
| 24 | 20,23 | 27,28,31 | 25,26 |
| 25 | 19,21 | 27,28,30 | 22–24,26 |
| 26 | 20,21 | 27,28,30 | 22–25 |
| 27 | 11,20–26 | 28,30–35,41,42 | — |
| 28 | 27 | 31,51 | — |
| 29 | 9,19 | 30–35 | — |
| 30 | 14,25–27,29 | 31,33,34 | — |
| 31 | 21,24,28,30 | 32,34,35 | — |
| 32 | 8,31 | 34,35,43 | 33 |
| 33 | 17,29,30 | 34,43 | 32 |
| 34 | 31–33 | 35,43 | — |
| 35 | 31,32,34 | 43–45 | — |
| 36 | 3,12,18,27,34,35 | 37–44 | — |
| 37 | 4,36 | 38,41,42,47 | — |
| 38 | 18,37 | 39–44 | — |
| 39 | 12,38 | 44 | 40–42 |
| 40 | 18,38 | 44 | 39,41,42 |
| 41 | 27,38 | 43,44 | 39,40 |
| 42 | 22,23,27,38,41 | 43,44 | 39,40 |
| 43 | 34,35,38,41,42 | 44 | — |
| 44 | 35,39–43 | 46,47,51 | — |
| 45 | 11,35 | 50,52 | 46,47 |
| 46 | 6,16,18,44 | 47,48 | 45 |
| 47 | 4,13,37,44,46 | 48,49 | 45 |
| 48 | 46,47 | 49,51 | — |
| 49 | 4,48 | 52 | 50 |
| 50 | 10,27,45 | 51,52 | 49 |
| 51 | 2–50 | 52,F1–F4 | — |
| 52 | 45,49–51 | F1–F4 | — |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Create the isolated v2 workspace and immutable-source receipt
  What to do / Must NOT do: Run from `C:\Users\Kirill\Documents\InputLag`; create and hash an immutable `integrity-policy.json` whose only exclusions are `.omo/`, `.venv/`, `node_modules/`, `.codegraph/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `__pycache__/`, `*.pyc`, `build/` and `dist/`; reject every symlink/junction/reparse entry before traversal; inventory through no-follow opened handles and stream SHA-256 every included file; take matching pre/post path-size-mtime inventories and fail on concurrent mutation. Separately inventory `C:\Users\Kirill\lnt-sessions`; copy the product to `location-network-tester-v2` without only the allowlisted exclusions; verify copy hashes; initialize Git only inside v2 and commit the untouched recovered baseline. Create `scripts/verify_pristine.ps1` in v2 that re-checks both receipts and the policy hash. MUST NOT add ad-hoc transients, follow links, initialize Git in, rename, delete or edit the original or real sessions.
  Parallelization: Wave 0 | Blocked by: none | Blocks: 2–52
  References (executor has NO interview context - be exhaustive): `.omo/drafts/lnt-complete-redesign.md` decisions 2/13–21; `_recovery/RECOVERY.md`; `src/lnt/session_store.py:35-67`; user invariant: all product work belongs in `location-network-tester-v2`.
  Acceptance criteria (agent-executable): `pwsh -File .\scripts\verify_pristine.ps1 -Original ..\location-network-tester -SessionRoot "$HOME\lnt-sessions" -ReceiptDir .\.integrity` exits 0 only when policy hash, no-follow traversal, pre/post inventories and all content hashes agree; `git status --short` in v2 is empty after baseline commit; `git -C ..\location-network-tester status` is not used as evidence.
  QA scenarios (exact tool + invocation): happy—PowerShell copies to a temporary verification directory and compares every included relative path/hash; failure—alter one byte in the temporary copy and assert `verify_pristine.ps1` exits non-zero naming only that file, then delete the temp copy. Evidence `<attemptDir>/task-1-lnt-complete-redesign.json` + `.txt`.
  Commit: YES | `chore(baseline): establish isolated recovered v2 source`

- [ ] 2. Measure and lock the recovered behavioral and performance baseline
  What to do / Must NOT do: In v2 only, sync every extra/dev dependency; run current Python/JS/build/CLI gates; record actual test counts rather than recovery-era claims; add `benchmarks/baseline.py` and fixtures for analyze, compare, session listing and UI health startup; capture OS/CPU/RAM/dependency versions and command exit codes. Open a typed `docs/defect-ledger.md` with reproducible defects only and route each to its owning later todo. MUST NOT “fix while measuring,” compare stale logs or treat skipped tests as passing.
  Parallelization: Wave 0 | Blocked by: 1 | Blocks: 3,13,19,51
  References: `pyproject.toml:1-113`; `tests/`; `tests/js/`; `_recovery/RECOVERY.md`; `src/lnt/cli.py:83-149`; `src/lnt/analysis.py:80-167`; `src/lnt/ui/app.py:38-87`.
  Acceptance criteria: the baseline evidence contains fresh stdout, duration, exit code and environment for all baseline commands; every failing/skip result has a defect-ledger ID and owner todo; `uv run python benchmarks/baseline.py --json <attemptDir>/baseline.json` emits valid non-empty measurements.
  QA scenarios: happy—run all baseline commands and validate JSON against `benchmarks/schema.json`; failure—feed a deliberately failing command to the recorder and assert it cannot emit `status=passed`. Evidence `<attemptDir>/task-2-lnt-complete-redesign/`.
  Commit: YES | `test(baseline): record recovered behavior and performance`

- [ ] 3. Freeze compatibility, storage and architecture contracts before refactoring
  What to do / Must NOT do: Add ADRs for canonical raw sessions, optional `context.json` schema 1, append-only `context.events.jsonl`, `analyses/<artifact-key>/` with separate immutable `recipe_sha256` identity, root legacy analysis projections, experiment storage outside session folders, ID/time/units conventions and error taxonomy. Add byte/semantic fixtures proving manifest v1/v2 remain strict and unchanged. Explicitly specify that legacy schema-v1 sessions without `ch1_setup` remain reason-coded unavailable for input-reference correction. MUST NOT add manifest v3 or hide new fields in the free-form `parameters` map.
  Parallelization: Wave 0 | Blocked by: 1,2 | Blocks: 6–12,19,29,36
  References: `src/lnt/types.py:217-238`; `src/lnt/_manifest_schema.py:78-210`; `tests/test_manifest.py`; `tests/test_ch1_manifest_contract.py`; `src/lnt/analysis.py:129-167`; `src/lnt/input_reference.py:79-106`.
  Acceptance criteria: new contract tests load and round-trip every frozen manifest fixture; old manifests retain identical canonical JSON; an attempted unknown manifest field fails; sidecars can be absent without changing existing behavior; architecture docs define every directory/file owner and atomic-write rule.
  QA scenarios: happy—`uv run pytest tests/test_manifest.py tests/test_ch1_manifest_contract.py tests/test_v2_storage_contract.py -q`; failure—fixture with `schema_version=3` and fixture with an unknown v2 field both fail with typed `InputError`. Evidence `<attemptDir>/task-3-lnt-complete-redesign.txt`.
  Commit: YES | `docs(architecture): freeze v2 compatibility and storage contracts`

- [ ] 4. Pin the private-use dependency, license and build-supply contract
  What to do / Must NOT do: Update locked dev/package dependencies for PyInstaller 6.14.1 and the approved frontend toolchain; retain the exact Hantek commit; inventory every shipped license; add `THIRD_PARTY_NOTICES.md`, `LICENSES/`, hashes/source URLs and a machine-readable dependency manifest. Define this build as owner-internal/private with no conveyance to another person; any transfer or public release triggers a separate GPL-source/license-compliance decision because the Hantek dependency is GPLv3. MUST NOT bundle Zadig, fetch runtime assets, loosen hashes or claim legal advice/public compatibility.
  Parallelization: Wave 0 | Blocked by: 1,2 | Blocks: 13,47,49
  References: `pyproject.toml:11,17-30`; `uv.lock`; upstream Hantek commit `e65d52b0f2536e56eaadbb555e5d7b756409c36e` and its GPLv3 `LICENSE`; PyInstaller 6.14.1 official bundle/data/DLL documentation; draft decision 13.
  Acceptance criteria: `uv lock --check`; license inventory covers every Python wheel/git dependency and every npm production dependency; an allowlist test fails on an unclassified license or unhashed external source; no runtime URL/CDN appears in built assets.
  QA scenarios: happy—`uv run pytest tests/test_dependency_policy.py -q` plus `npm --prefix frontend run licenses:check` once frontend exists; failure—inject a fixture dependency without license metadata and assert policy failure. Evidence `<attemptDir>/task-4-lnt-complete-redesign.json`.
  Commit: YES | `build(deps): pin private portable supply chain`

- [ ] 5. Make pristine-source enforcement a permanent quality gate
  What to do / Must NOT do: Add test/PowerShell wrappers that invoke the immutable receipts before and after every milestone, reject evidence/output inside original/session roots and detect path-normalization/symlink/reparse-point escape. Read the approved plan path/hash from original `.omo/STATE.md`, verify no-follow bytes against that hash, and commit an immutable execution copy as `.integrity/approved-work-plan.md` plus `.integrity/approved-work-plan.sha256` inside v2; all later evidence audits use this committed copy, not a missing v2 `.omo` path. Document safe receipt regeneration only when the user explicitly replaces the original reference. MUST NOT auto-update a receipt/plan copy after mismatch or treat the copied plan as product behavior.
  Parallelization: Wave 0 | Blocked by: 1 | Blocks: 6–52
  References: Todo 1 `integrity-policy.json`/receipts/`scripts/verify_pristine.ps1`; existing `src/lnt/session_store.py:35-67`; `.omo/drafts/lnt-complete-redesign.md` Scope OUT.
  Acceptance criteria: `pwsh -File scripts/verify_pristine.ps1 ...` is called by `scripts/quality.ps1`; reparse/symlink and receipt mismatch fixtures fail closed; `.integrity/approved-work-plan.md` hashes exactly to the approved `.omo/STATE.md` digest and `git diff --exit-code -- .integrity/approved-work-plan*` remains clean; receipt/plan-copy files are read-only inputs to later checkers.
  QA scenarios: happy—run `scripts/quality.ps1 -PristineOnly`; failure—temporary reparse-point fixture aimed outside the test root is rejected without reading/writing its target. Evidence `<attemptDir>/task-5-lnt-complete-redesign.txt`.
  Commit: YES | `test(integrity): enforce pristine original and sessions`

- [ ] 6. Centralize Windows application paths and atomic configuration
  What to do / Must NOT do: Add `src/lnt/app_paths.py` and `src/lnt/config/` with typed paths for `%APPDATA%\LNT\config.json`, disposable `%LOCALAPPDATA%\LNT\catalog.sqlite3`, durable `%LOCALAPPDATA%\LNT\runtime.sqlite3`, cache/log/support directories and the unchanged default `~/lnt-sessions`; support explicit CLI/UI overrides and test-root injection. Write config atomically with schema version and recovery from a corrupt file. MUST NOT store databases/logs beside an arbitrary session root or executable, infer portable-data mode, or depend on current working directory.
  Parallelization: Wave 1 | Blocked by: 3,5 | Blocks: 8–12,46
  References: `src/lnt/cli.py:132-145`; `src/lnt/ui/app.py:38-87`; `src/lnt/session_store.py:35-67`; Python `platformdirs` is not required—use explicit Windows/environment paths with test injection.
  Acceptance criteria: path/config tests cover missing env vars, Unicode/long paths, read-only config, corrupt JSON and explicit root override; defaults preserve `Path.home()/"lnt-sessions"`; atomic failure leaves the previous valid config intact.
  QA scenarios: happy—`uv run pytest tests/test_app_paths.py tests/test_config_store.py -q`; failure—simulate replace failure/read-only parent and assert typed error plus unchanged old bytes. Evidence `<attemptDir>/task-6-lnt-complete-redesign.txt`.
  Commit: YES | `feat(config): add deterministic app paths and settings store`

- [ ] 7. Add versioned typed context sidecars and append-only audit history
  What to do / Must NOT do: Add strict domain/JSON modules for `context.json` schema 1: session ID, revision, typed fields (`string|number|boolean|enum|timestamp`), optional unit/uncertainty, source (`automatic|profile|user|derived`), collection status/reason and captured timestamp; add tags/notes and profile snapshots. Make the hash-chained `context.events.jsonl` canonical: under a per-session writer lock, append one event containing the complete resulting snapshot (or a fully replayable patch), actor, revisions and changed keys, flush it to disk, then atomically replace the derived `context.json` cache. Detect/ignore only a torn final line, reject interior corruption, and deterministically replay a lagging/missing cache at startup without rewriting committed events. MUST NOT claim a two-file atomic commit, mutate manifests/raw files, accept NaN/unknown fields or silently repair an invalid chain.
  Parallelization: Wave 1 | Blocked by: 3,5 | Blocks: 8–12,19,29
  References: manifest strictness patterns in `src/lnt/_manifest_schema.py:149-210`; atomic session pattern `src/lnt/session_store.py:35-67`; JSON value conventions `src/lnt/types.py`; draft decision 5/14.
  Acceptance criteria: strict round-trip/property tests; optimistic revision conflict returns typed conflict; audit chain verifies from genesis; injected crash after flushed event/before cache replace replays the exact new revision; a torn tail is reason-coded/recovered while interior tampering fails; absent sidecar returns an explicit empty context view; malformed sidecar leaves session readable but health=`context_invalid`.
  QA scenarios: happy—`uv run pytest tests/test_context_schema.py tests/test_context_store.py -q`; failure—tamper one JSONL event and assert verification fails without rewriting it. Evidence `<attemptDir>/task-7-lnt-complete-redesign.json`.
  Commit: YES | `feat(context): add audited session context sidecars`

- [ ] 8. Implement profiles and privacy-bounded automatic metadata snapshots
  What to do / Must NOT do: Add versioned location/equipment/front-end/transformer/condition profiles and a metadata collector that snapshots LNT build, frozen/dev mode, OS version/architecture/timezone, device VID/PID/model/firmware/driver diagnostic, sample settings, probe multiplier, range, channel mode, front-end parameters and acquisition telemetry. User profile fields cover location alias, outlet/circuit, equipment, damper state and nearby-load states. Record each unavailable/error reason. MUST NOT collect hostname, username, exact geolocation, running processes, network identity or weather unless a future explicit opt-in integration is designed.
  Parallelization: Wave 1 | Blocked by: 6,7 | Blocks: 11,32,39
  References: `src/lnt/acquire.py:58-155`; `src/lnt/types.py:39-238`; `src/lnt/ui/device.py:37-101`; existing capture argument/model paths `src/lnt/cli.py:83-121`, `src/lnt/ui/models.py` and `src/lnt/ui/job_worker.py`; frontend design state personas/privacy.
  Acceptance criteria: profile CRUD validates IDs/units and preserves old snapshots; collector is deterministic under injected clock/platform/device; forbidden keys are absent; device-offline collection succeeds with reason-coded device fields.
  QA scenarios: happy—`uv run pytest tests/test_profiles.py tests/test_metadata_collector.py -q`; failure—profile with unknown unit/secret-looking forbidden field is rejected and no partial profile file remains. Evidence `<attemptDir>/task-8-lnt-complete-redesign.json`.
  Commit: YES | `feat(metadata): add profiles and safe automatic snapshots`

- [ ] 9. Build the rebuildable SQLite catalog and migration runner
  What to do / Must NOT do: Add `src/lnt/catalog/` with explicit SQL migrations and normalized projection tables for sessions, context fields/tags, artifact recipes, experiments/members and schema migrations. Keep the disposable catalog under LocalAppData, enable `foreign_keys`, WAL and `busy_timeout`; enforce one writer with a process lock while allowing readers; expose transactions/repositories, no ORM. Keep jobs out of this database (Todo 16 owns durable `runtime.sqlite3`). Reindex rebuilds only projection tables, never runtime history. MUST NOT place DB/WAL on session/external media, store raw samples/blobs, or make a catalog row more authoritative than filesystem evidence.
  Parallelization: Wave 1 | Blocked by: 6,7 | Blocks: 10–12,16,29
  References: current O(n) scan `src/lnt/ui/sessions.py:49-105`; app paths Todo 6; canonical-session ADR Todo 3; SQLite stdlib API.
  Acceptance criteria: migrations are ordered/idempotent and downgrade is explicitly unsupported; concurrent reader/single-writer test passes; lock timeout is typed/actionable; deleting/recreating only `catalog.sqlite3` loses no canonical projection data and leaves `runtime.sqlite3` bytes/job history unchanged.
  QA scenarios: happy—`uv run pytest tests/catalog -q`; failure—two writer processes contend and the loser returns `catalog_busy` without corruption; `PRAGMA integrity_check` remains `ok`. Evidence `<attemptDir>/task-9-lnt-complete-redesign.txt`.
  Commit: YES | `feat(catalog): add transactional rebuildable index`

- [ ] 10. Implement incremental reconcile, health classification and reindex/migration tools
  What to do / Must NOT do: Scan immediate session directories safely; fingerprint relevant file names/sizes/mtimes plus canonical hashes; insert/update/delete stale catalog projections transactionally; classify corrupt/missing/partial/duplicate-ID/context-invalid/analysis-invalid states without hiding them. Add `lnt catalog status|reindex|verify` and dry-run sidecar migration/import tools that operate on copied fixtures. MUST NOT follow reparse points outside root, rewrite a manifest or touch raw arrays.
  Parallelization: Wave 1 | Blocked by: 9 | Blocks: 11,12,50
  References: existing `src/lnt/ui/sessions.py:49-105`; pristine/no-follow path contract and checker from Todo 5; `src/lnt/session_store.py:70-131`; existing corrupt-session coverage in `tests/test_ui_sessions.py`; new catalog security tests are created in this todo.
  Acceptance criteria: reindex is idempotent; 10,000-session synthetic reconcile meets documented full/incremental budgets; duplicate IDs and corrupt files remain visible; catalog rebuild after deletion reproduces identical semantic rows.
  QA scenarios: happy—`uv run pytest tests/catalog/test_reconcile.py tests/test_catalog_cli.py -q`; failure—zip-slip/reparse/duplicate fixture is classified and cannot escape/write. Evidence `<attemptDir>/task-10-lnt-complete-redesign.json`.
  Commit: YES | `feat(catalog): reconcile legacy sessions safely`

- [ ] 11. Integrate context/catalog projection with capture, analysis and session storage
  What to do / Must NOT do: Extend capture/simulate completion to snapshot context within the existing partial-directory atomic boundary; index only after final rename; update artifact projection after atomic analysis completion; emit recoverable reconciliation markers if catalog update fails. Keep root legacy `metrics.json`/CSV as replaceable projections of the default recipe for old UI/CLI compatibility. MUST NOT fail a completed raw capture solely because the disposable catalog is unavailable or write half-context into a final session.
  Parallelization: Wave 1 | Blocked by: 8–10 | Blocks: 12,27,45,50
  References: `src/lnt/session_store.py:35-67`; `src/lnt/acquire.py:58-155`; `src/lnt/analysis.py:129-167`; `src/lnt/ui/job_worker.py:81-97`.
  Acceptance criteria: process-crash/failure injection at every write/rename/index boundary leaves either no final session or a checksum-verifiable canonical session plus reconcile-needed marker; startup classifies any power-loss/torn-file corruption rather than promising filesystem durability; legacy loaders/tests remain green; catalog failure is visible but capture result is preserved.
  QA scenarios: happy—`uv run pytest tests/test_capture_context_catalog.py tests/test_analysis_catalog.py -q`; failure—inject SQLite failure after session rename and assert valid session + later successful reindex. Evidence `<attemptDir>/task-11-lnt-complete-redesign.txt`.
  Commit: YES | `feat(storage): project canonical sessions into catalog`

- [ ] 12. Expose catalog/context/profile APIs and CLI contracts
  What to do / Must NOT do: Add split FastAPI routers/Pydantic v2 request-response models for paged/filterable session catalog, health facets, context revisions, tags/notes, profiles and reindex status; add CLI equivalents for automation. Use stable sort/cursor semantics, bounded page sizes, optimistic context revisions and compact Russian errors. MUST NOT return raw filesystem paths by default, accept arbitrary SQL/filter syntax or expose FastAPI online docs.
  Parallelization: Wave 1 | Blocked by: 11 | Blocks: 36,39
  References: `src/lnt/ui/routes_sessions.py`; `src/lnt/ui/models.py`; `src/lnt/ui/errors.py`; `src/lnt/ui/app.py:38-87`; current API tests `tests/test_ui_session_routes.py`.
  Acceptance criteria: route/CLI contract tests cover pagination stability, every filter, corrupt rows, conflict, 404/422/409/503 mapping and 10k-row query budget; OpenAPI/docs remain disabled in production app.
  QA scenarios: happy—`uv run pytest tests/test_catalog_routes.py tests/test_context_routes.py tests/test_profile_routes.py -q`; failure—oversized page, stale revision and traversal-like ID each return the specified Russian typed error. Evidence `<attemptDir>/task-12-lnt-complete-redesign.json`.
  Commit: YES | `feat(api): expose catalog context and profiles`

- [ ] 13. Prove the frozen Hantek/libusb/firmware diagnostic path early
  What to do / Must NOT do: Before full packaging, create a minimal PyInstaller onedir spike using the pinned Hantek extra; trace imports/resources; collect firmware/package data and the actual resolved x64 libusb DLL. Require every non-OS DLL/module/firmware path to resolve inside the bundle. Permit external Windows system DLLs only through a versioned allowlist that verifies canonical path beneath `%SystemRoot%\System32`, x64 PE architecture and valid Microsoft Authenticode signer; record their names/versions/hashes and reject every other external dependency. Run a frozen probe that reports this closure and executes non-invasive `diagnose_device()` for device-present, absent, bootloader/firmware-missing and driver-missing fakes plus the user's real connected device. Emit explicit `go|no_go`: unresolved architecture/dependency/firmware closure blocks Todos 47–49/F3, and unavailable real hardware cannot count as F3 approval. Call the test sanitized-reference-host/process evidence, not clean/sterile VM. MUST NOT start a capture, install/change WinUSB, bundle Zadig, mutate driver state or demand that Windows system DLLs be copied into the bundle.
  Parallelization: Wave 2 | Blocked by: 2,4,6 | Blocks: 14–18,47
  References: Hantek pin `pyproject.toml:20-22`; `src/lnt/hantek_backend.py`; `src/lnt/ui/device.py:37-101`; PyInstaller 6.14.1 `Analysis.binaries`/data and `__file__` behavior; reference host: Windows 10 Home 22H2 x64, Ryzen 7 7800X3D, 31.6 GiB, no Hyper-V/Sandbox.
  Acceptance criteria: `go` requires frozen probe exit 0, bundle-local hashes for all non-OS dependencies/firmware, validated System32/Microsoft/x64 allowlist records for OS DLLs, no-Python sanitized-process import, all fake diagnostic mappings and a non-invasive real-device result; any missing, untrusted external, wrong-architecture or wrongly signed dependency emits `no_go` and prevents package/final approval rather than becoming a warning/skip.
  QA scenarios: happy—`pwsh -File packaging/spike/build-and-probe.ps1 -Evidence <attemptDir>/task-13-lnt-complete-redesign`; failure—remove copied DLL/firmware from a temporary spike and assert a Russian actionable diagnostic names the missing class, not a traceback. Evidence directory includes frozen stdout and dependency inventory.
  Commit: YES | `build(hantek): prove frozen device diagnostic path`
- [ ] 14. Add typed device preflight and post-capture quality diagnostics
  What to do / Must NOT do: Replace booleans with stable device states (backend unavailable, bootloader VID, running VID, handle busy, firmware missing/upload failed, ready); add preflight checks for mode/setup consistency, disk space, duration/sample overflow, writable root, baseline compatibility and safe range/probe choices. Derive post-capture clipping, under-range/LSB usage, callback gaps/short blocks and next-range guidance from telemetry. MUST NOT auto-change hardware settings, auto-recapture, hide raw data or equate “device absent” with “driver absent.”
  Parallelization: Wave 2 | Blocked by: 13 | Blocks: 17,18,30
  References: `src/lnt/ui/device.py:37-101`; `src/lnt/scope_io.py:137-186`; `src/lnt/types.py` acquisition telemetry; `src/lnt/acquire.py:58-155`; prior real-capture clipping/range findings in recovery history.
  Acceptance criteria: exhaustive typed-state tests and request preflight matrix; quality thresholds/version are stored in context/analysis, not magic UI strings; one-/two-channel and line-quality recommendations use correct channel/range semantics.
  QA scenarios: happy—`uv run pytest tests/test_device_diagnostics.py tests/test_capture_preflight.py tests/test_acquisition_quality.py -q`; failure—busy handle, insufficient disk, clipping and weak signal each produce distinct code + recovery action. Evidence `<attemptDir>/task-14-lnt-complete-redesign.json`.
  Commit: YES | `feat(capture): add actionable preflight and quality states`
- [ ] 15. Make hardware acquisition cooperatively cancellable at safe poll boundaries
  What to do / Must NOT do: Define a backend `poll(timeout_ms<=250)` contract and prove the pinned Hantek implementation returns/control-checks within that bound; if upstream cannot honor it, fail this task rather than claim bounded cancellation. Thread a typed cancellation token through `run_capture`/`_stream_capture`; check before setup, between every bounded poll/chunk and between series members; require capture cancellation acknowledgement within 500 ms on the reference host; always call stop, shutdown and close exactly once; preserve telemetry for completed captures and remove partial directories for cancelled incomplete captures. Keep USB exception mapping typed. MUST NOT kill threads/processes, cancel during an atomic final rename or leave a scope handle open.
  Parallelization: Wave 2 | Blocked by: 13 | Blocks: 16,17
  References: `src/lnt/scope_io.py:110-186`; `src/lnt/ui/job_worker.py:81-97`; current cancellation boundary comments; `src/lnt/session_store.py:35-67`.
  Acceptance criteria: fake and pinned-backend latency tests prove poll ≤250 ms and cancel acknowledgement ≤500 ms before start/mid-stream/after requested samples with exact lifecycle call order; timeout/USB errors still close; no partial/final ambiguous session remains.
  QA scenarios: happy—`uv run pytest tests/test_scope_cancellation.py -q`; failure—fake poll raises USB error concurrently with cancellation and test asserts one deterministic terminal result and one close. Evidence `<attemptDir>/task-15-lnt-complete-redesign.txt`.
  Commit: YES | `feat(acquire): add safe cooperative cancellation`
- [ ] 16. Persist jobs, legal transitions and restart recovery
  What to do / Must NOT do: Store job records/events in separate durable `%LOCALAPPDATA%\LNT\runtime.sqlite3` with strict state machine (`queued→running→succeeded|failed|cancelled`, restart turns nonterminal into `interrupted`); keep a bounded worker queue; recover frontend-visible state after server restart; store operation/input/result references, progress and compact errors, not arbitrary tracebacks. Catalog reindex/deletion never opens, clears or migrates runtime tables except through an explicit runtime migration. MUST NOT resume a hardware capture after process death, reuse job IDs or silently discard terminal history.
  Parallelization: Wave 2 | Blocked by: 9,15 | Blocks: 17,18,40,46
  References: in-memory manager `src/lnt/ui/jobs.py:50-240`; state tests `tests/test_ui_job_state.py`; frontend stuck-job regression `tests/js/job-controller.test.mjs`; app lifecycle `src/lnt/ui/app.py:38-87`.
  Acceptance criteria: process-restart integration test marks active job interrupted and accepts the next job without reload; illegal/duplicate transitions fail; retention policy is deterministic and preserves referenced session outcomes.
  QA scenarios: happy—`uv run pytest tests/test_persistent_jobs.py tests/test_job_restart.py -q`; failure—terminate a spawned test server mid-job, restart, assert interrupted status/recovery banner contract and unlocked queue. Evidence `<attemptDir>/task-16-lnt-complete-redesign.json`.
  Commit: YES | `feat(jobs): persist state and recover after restart`
- [ ] 17. Add a single hardware lease and deterministic operation scheduler
  What to do / Must NOT do: Serialize device check/firmware/capture operations under one cross-process lease while allowing bounded CPU analysis jobs in parallel; model capture series progress and cancellation between members; reject double server/device ownership with owner PID/start/build metadata and stale-lease recovery. MUST NOT let Windows `SO_REUSEADDR` create two hardware-owning servers or queue unlimited memory-heavy analyses.
  Parallelization: Wave 2 | Blocked by: 14–16 | Blocks: 18,33
  References: `src/lnt/ui/jobs.py:50-240`; `src/lnt/ui/job_worker.py`; known Windows double-bind/stale-server constraint; current series args in `src/lnt/cli.py:105-121`.
  Acceptance criteria: multi-process tests prove one hardware owner, stale lease is recoverable only after PID/start identity mismatch, CPU concurrency respects configured bound and jobs retain FIFO within class.
  QA scenarios: happy—`uv run pytest tests/test_operation_scheduler.py -q`; failure—launch two test servers and assert second returns owner diagnostics without binding/using device. Evidence `<attemptDir>/task-17-lnt-complete-redesign.txt`.
  Commit: YES | `feat(runtime): serialize hardware and bound analysis work`
- [ ] 18. Harden capture/job APIs, build identity and local security boundary
  What to do / Must NOT do: Split request models/routes; expose preflight, device, durable jobs, cancel and progress/event endpoints; use a per-launch same-origin mutation nonce, strict loopback host validation, request/body/page limits, CSP and security headers. Health/config returns build ID; frontend must detect backend/frontend mismatch. Use hashed static assets with no-store index so stale mixed ES modules cannot recur. MUST NOT enable wildcard CORS, remote bind by default, online docs or trust the old constant CSRF header as authentication.
  Parallelization: Wave 2 | Blocked by: 12,16,17 | Blocks: 36,38,40,46
  References: existing `src/lnt/ui/app.py:38-87` and `tests/test_ui_app.py`; this todo creates new `src/lnt/ui/security.py` plus `tests/test_ui_security_v2.py`; prior stale-cache/server failure; OWASP localhost still requires CSRF/origin discipline.
  Acceptance criteria: route tests cover nonce/origin/build mismatch, limits, restart event replay and all capture modes; index/static cache policy is intentional; server binds one exclusive loopback socket passed to Uvicorn.
  QA scenarios: happy—`uv run pytest tests/test_runtime_routes.py tests/test_ui_security_v2.py -q`; failure—wrong origin/nonce, stale build ID and second bind are rejected with compact Russian errors. Evidence `<attemptDir>/task-18-lnt-complete-redesign.json`.
  Commit: YES | `feat(api): harden local runtime and capture contracts`
- [ ] 19. Create immutable analysis recipes and content-addressed artifact storage
  What to do / Must NOT do: Add immutable strict `AnalysisRecipe` schema 1 covering mode, channels, band/grid, window/segment/overlap/detrend/scaling/average, spectrogram, events, bands, correction and uncertainty settings. Canonical recipe JSON alone yields `recipe_sha256`; edits clone to a new recipe. Separately derive `artifact_key = SHA256(recipe_sha256 + raw hashes + explicitly declared context/profile/calibration dependencies + code/dependency identity)` and write outputs to partial `analyses/<artifact_key>` before atomic rename. `analysis-manifest.json` lists every key input/output and OS/Python/NumPy/SciPy/FFT/BLAS provenance. MUST NOT mutate a recipe, overwrite an existing valid artifact or imply cross-platform bit identity.
  Parallelization: Wave 3 | Blocked by: 3,7 | Blocks: 20–28,29
  References: current fixed dispatch `src/lnt/analysis.py:80-126`; root writers `src/lnt/analysis.py:129-167`; `src/lnt/spectrum.py:53-100`; canonical session/checksum contract Todo 3.
  Acceptance criteria: canonical equivalent recipes hash equally while raw/context/code changes preserve `recipe_sha256` but change `artifact_key`; undeclared context cannot affect an output; clone-on-edit and integrity tests pass; crash leaves no valid partial artifact; same locked environment yields identical bytes/hashes; cross-environment tests use documented numeric tolerance, not same hash claim.
  QA scenarios: happy—`uv run pytest tests/analysis/test_recipe.py tests/analysis/test_artifact_store.py -q`; failure—tampered output/input digest invalidates cache and is never served. Evidence `<attemptDir>/task-19-lnt-complete-redesign.json`.
  Commit: YES | `feat(analysis): add recipe-addressed artifact store`
- [ ] 20. Replace implicit whole-array Welch with an explicit bounded-memory PSD engine
  What to do / Must NOT do: Implement streaming/memmap Welch with explicit periodic Hann window, `nperseg`, 50% overlap, constant detrend, density scaling, mean average, one-sided output and exact frequency grid; preserve the current 50 Hz resolution default and 3 kHz–3 MHz preset while allowing bounded valid bands. Emit linear PSD V²/Hz, ASD V/√Hz, 10·log10 referenced to 1 V²/Hz and integrated band RMS with units. Validate against SciPy on small arrays and synthetic Parseval fixtures. MUST NOT load a 30 s × 8 MHz raw file into float64 RAM or change old default numerics outside declared tolerance.
  Parallelization: Wave 3 | Blocked by: 19 | Blocks: 21,24,26–28
  References: `src/lnt/spectrum.py:53-100`; `src/lnt/analysis.py:80-126`; current spectrum tests `tests/test_signals.py`, `tests/test_analysis.py`; SciPy `signal.welch` contract from locked version.
  Acceptance criteria: chunked vs SciPy relative/absolute tolerances are documented and pass; Parseval integrated power passes; empty/short/NaN/overflow inputs fail typed; on the recorded Ryzen 7 7800X3D host a 30 s × 8 MHz PSD run is ≤120 s, ≤1.5 GiB RSS, checks cancellation at chunks no longer than 250 ms and acknowledges within 500 ms; Todo 2 records baseline but may not silently relax these ceilings.
  QA scenarios: happy—`uv run pytest tests/analysis/test_psd.py tests/analysis/test_psd_properties.py -q`; failure—memory benchmark wrapper fails an intentional whole-array implementation and invalid settings are rejected. Evidence `<attemptDir>/task-20-lnt-complete-redesign.json`.
  Commit: YES | `feat(spectrum): add explicit streaming Welch recipes`
- [ ] 21. Implement honest repeatability and uncertainty semantics
  What to do / Must NOT do: Add uncertainty domain objects/reason codes for named scalar measurands only: band RMS/power, secondary/primary RMS when calibrated, THD and harmonic ratios. For one record report resolution/bin width and within-record spectral variability only. For n≥3 independent capture-level estimates of a mean, Type-A standard uncertainty is `s/sqrt(n)` and the 95% interval uses Student-t with df=n−1; paired effects operate on stored block differences. Convert explicit Type-B profile distributions to standard uncertainties and propagate with named sensitivity coefficients; include covariance only when supplied. Compute ratios/dB from linear-domain propagation or stored deterministic Monte Carlo. Withhold combined/expanded uncertainty if covariance, nonlinear method or any required component is unsupported; name coverage method/factor. MUST NOT call standard deviation or single-record bootstrap “measurement uncertainty,” invent scope specs/default calibration or assume independence silently.
  Parallelization: Wave 3 | Blocked by: 20 | Blocks: 25,26,31
  References: draft decision 18; current line-quality/spectrum metrics `src/lnt/line_quality.py:58-108`, `src/lnt/types.py`; explicit front-end model `FloatingDifferentialRcShunt`; GUM terminology used only as implemented here.
  Acceptance criteria: equation/unit fixtures for every supported measurand, Student-t Type-A and covariance cases agree with analytic/Monte Carlo truth; n<3, missing Type-B/covariance or unsupported nonlinear propagation yields reason-coded partial output without a combined number; intervals are deterministic under stored seed/method.
  QA scenarios: happy—`uv run pytest tests/analysis/test_uncertainty.py -q`; failure—request combined uncertainty with one absent component and assert no numeric combined result is serialized. Evidence `<attemptDir>/task-21-lnt-complete-redesign.json`.
  Commit: YES | `feat(science): add explicit uncertainty budgets`
- [ ] 22. Build bounded multi-resolution spectrogram overview and exact zoom artifacts
  What to do / Must NOT do: Stream STFT from memmap using versioned window/hop/detrend/scaling; aggregate each overview/pyramid cell in linear power with coverage counts before converting to dB; cap stored overview at 2048 time bins × 1024 log-frequency bands as float32 plus axes/coverage; provide on-demand exact interval/band recomputation with strict sample/cell/time limits and cancellation. Store dB reference and floor/ceiling metadata. On the reference host require full overview ≤180 s, ≤1.5 GiB RSS, temporary artifacts ≤8 GiB, exact bounded zoom ≤2 s and cancellation acknowledgement ≤500 ms. MUST NOT average dB values, materialize the full 30 s × 8 MHz cube, smear unavailable bins into zeros or send raw samples to the browser.
  Parallelization: Wave 3 | Blocked by: 19 | Blocks: 23,27,28,42
  References: current bounded payload/decimation patterns `src/lnt/ui/payloads.py:71-141`, `src/lnt/ui/decimation.py:33-69`; recipe/artifact contract Todo 19; UI spectrogram objective.
  Acceptance criteria: tone/chirp/burst fixtures localize expected frequency/time within bin tolerance; linear-power aggregation and coverage match analytic/direct SciPy truth; dimensions/runtime/RSS/temp size meet stated ceilings; zoom values agree with direct SciPy STFT; cancellation/limit paths meet 500 ms and leave no valid partial artifact.
  QA scenarios: happy—`uv run pytest tests/analysis/test_spectrogram.py tests/test_spectrogram_routes.py -q`; failure—oversized zoom and corrupt pyramid return typed errors without allocation spike. Evidence `<attemptDir>/task-22-lnt-complete-redesign.json`.
  Commit: YES | `feat(spectrogram): add bounded overview and exact zoom`
- [ ] 23. Add deterministic transient/event inventory with explicit thresholds
  What to do / Must NOT do: Detect candidate events from versioned robust local noise-floor/MAD and optional compatible baseline, merge by explicit gap, and store start/end/peak/time, polarity, dominant band, excess energy, SNR/qualification and boundary/clipping flags. Provide presets but persist all thresholds. Events are candidates, never causes. MUST NOT use opaque ML, discard clipped events or bridge unqualified gaps.
  Parallelization: Wave 3 | Blocked by: 22 | Blocks: 24,27,28,42
  References: existing peak/correction qualification patterns `src/lnt/input_reference.py:79-106`, `tests/test_ch1_corrected_peaks.py`; spectrogram Todo 22; synthetic signal profiles `src/lnt/signals.py`.
  Acceptance criteria: golden injected impulses/bursts recover precision/recall and timing/frequency tolerances; noise-only false-positive budget is fixed; thresholds/hash appear in artifact; clipping/boundary reason codes survive serialization.
  QA scenarios: happy—`uv run pytest tests/analysis/test_events.py -q`; failure—noise-only and unqualified-baseline fixtures cannot emit “confirmed” events. Evidence `<attemptDir>/task-23-lnt-complete-redesign.json`.
  Commit: YES | `feat(analysis): inventory qualified transient events`
- [ ] 24. Extract versioned bands, noise floor and tracked spectral features
  What to do / Must NOT do: Add built-in and user-defined non-overlapping/overlapping band definitions with units; compute integrated RMS/power, robust floor/percentiles, peak prominence/Q, event rate/duty and peak trajectory across windows/captures. Store estimand direction (`lower|higher|target|descriptive`) so later UI cannot call an unsigned delta improvement. MUST NOT compare dB as linear power or infer Q across unqualified/missing bins.
  Parallelization: Wave 3 | Blocked by: 20,23 | Blocks: 27,28,31
  References: `src/lnt/spectrum.py` peak model; `src/lnt/compare.py:49-56,87-128`; corrected peak tests; recipe Todo 19.
  Acceptance criteria: synthetic band/peak fixtures recover expected integrated power and tracking identity; unit/direction schema rejects ambiguity; missing/NaN qualification propagates explicitly.
  QA scenarios: happy—`uv run pytest tests/analysis/test_features.py -q`; failure—invalid overlapping policy/unknown unit and a disappearing peak produce declared error/unavailable behavior. Evidence `<attemptDir>/task-24-lnt-complete-redesign.json`.
  Commit: YES | `feat(features): derive auditable spectral estimands`
- [ ] 25. Extend transformer line-quality analysis and like-for-like comparison
  What to do / Must NOT do: Version the line-quality recipe; retain frequency, secondary RMS, THD H2–H40, band-limited crest and envelope CV; add time-window drift/intervals and comparison deltas for frequency, secondary RMS, THD, crest, envelope and each harmonic. Estimate primary RMS only when a transformer profile supplies ratio/uncertainty. Compare line-quality only with compatible line-quality recipe/profile, and state this is monitoring—not certified IEC flicker/power quality. MUST NOT compute TDD/current/flicker or calibrated mains voltage without evidence.
  Parallelization: Wave 3 | Blocked by: 19,21 | Blocks: 27,28,30
  References: `src/lnt/line_quality.py:58-108`; current rejection `src/lnt/compare.py:16-22`; line-quality tests; transformer architecture memory.
  Acceptance criteria: old line-quality golden metrics remain within tolerance; new pure/harmonic/drift/calibrated-ratio fixtures pass; HF↔line and incompatible transformer comparisons reject; H2–H40 delta table is complete up to Nyquist.
  QA scenarios: happy—`uv run pytest tests/analysis/test_line_quality_v2.py tests/test_line_quality_compare.py -q`; failure—missing calibration omits primary RMS and cross-type comparison returns typed incompatibility. Evidence `<attemptDir>/task-25-lnt-complete-redesign.json`.
  Commit: YES | `feat(line-quality): add drift uncertainty and comparison`
- [ ] 26. Upgrade input-reference correction without weakening qualification
  What to do / Must NOT do: Move existing RC correction into recipe artifacts; preserve raw scope-plane PSD; subtract compatible baseline excess PSD; retain ≥2× PSD qualification and disconnected-region peak rules; propagate explicit R/C/profile uncertainty only where available; write corrected PSD/ASD/band metrics and model/baseline hashes. Legacy v1/no-setup sessions remain unavailable. MUST NOT correct raw `spectrum.csv`, interpolate across failed bins or compare incompatible setup/baseline grids.
  Parallelization: Wave 3 | Blocked by: 20,21 | Blocks: 27,28,30
  References: `src/lnt/input_reference.py:79-106`; `_input_reference_baseline.py`; `tests/test_ch1_input_reference_*`; defaults R=100 Ω, C1=C2=10 nF; project rules #46/#49.
  Acceptance criteria: all existing correction tests remain green; uncertainty analytic fixtures pass; artifact exposes exact transfer formula/parameters/source; incompatible/noisy/clipped/legacy cases are reason-coded unavailable while raw output remains valid.
  QA scenarios: happy—`uv run pytest tests/test_ch1_input_reference_*.py tests/analysis/test_input_reference_v2.py -q`; failure—tampered baseline hash and sub-2× bin cannot produce corrected numeric output. Evidence `<attemptDir>/task-26-lnt-complete-redesign.json`.
  Commit: YES | `feat(input-reference): version qualified correction artifacts`
- [ ] 27. Orchestrate cancellable analysis, cache validation and bounded plot APIs
  What to do / Must NOT do: Dispatch by session type/immutable recipe; schedule PSD, spectrogram, events, features, line quality and correction in chunks bounded to 250 ms between cancellation checks; persist progress; validate `artifact_key` hashes before reuse; atomically project the chosen default into legacy root files; expose recipe create/list/clone/run/status/artifact/plot/zoom APIs (no in-place update/delete of referenced recipes) with range-aware extrema-preserving decimation and strict limits. MUST NOT serve stale/tampered artifacts, let one failed optional branch invalidate raw capture, conflate default recipe with sole truth or acknowledge cancellation later than 500 ms on the reference host.
  Parallelization: Wave 3 | Blocked by: 11,20–26 | Blocks: 28,30–35,41,42
  References: `src/lnt/analysis.py:80-167`; `src/lnt/ui/payloads.py:71-141`; `src/lnt/ui/decimation.py:33-69`; durable jobs Todo 16; artifact store Todo 19.
  Acceptance criteria: all session types dispatch correctly; rerun same recipe is cache hit only after integrity validation; cancellation recovers; API values match artifacts; max-point/cell/range limits are enforced.
  QA scenarios: happy—`uv run pytest tests/analysis/test_orchestrator.py tests/test_analysis_routes_v2.py -q`; failure—delete/tamper one output, request cache, assert recompute/quarantine rather than stale success. Evidence `<attemptDir>/task-27-lnt-complete-redesign.json`.
  Commit: YES | `feat(analysis): orchestrate reproducible derived artifacts`
- [ ] 28. Establish the scientific truth, regression and performance corpus
  What to do / Must NOT do: Add compact generated fixtures for pure tones, multitone/harmonics, chirps, AM, switching bursts, impulses, clipping, dropout, drift, baseline excess and A/B/A effects; store generators/seeds/truth, not giant raw binaries. Add property/metamorphic tests for scaling, time shift, Parseval, chunk boundaries, sample rate and null data; benchmark 30 s × 8 MHz via generated memmap and record RSS/runtime. MUST NOT tune algorithms to a single fixture or bless outputs without independent analytic truth/tolerance rationale.
  Parallelization: Wave 3 | Blocked by: 27 | Blocks: 31,51
  References: `src/lnt/signals.py`; `tests/test_signals.py`; line-quality fixtures; `tests/ch1_contract_fixtures.py`; baseline/performance Todo 2.
  Acceptance criteria: one command regenerates all fixtures deterministically and verifies truths; mutation checks prove each major algorithm test fails on sign/unit/bin errors; benchmark JSON names host and meets memory/performance budgets or blocks progress.
  QA scenarios: happy—`uv run pytest tests/science -q` and `uv run python benchmarks/scientific.py --json <attemptDir>/task-28-lnt-complete-redesign.json`; failure—run documented mutation fixture and assert the corpus detects it. Evidence JSON + logs.
  Commit: YES | `test(science): add synthetic truth and performance corpus`
- [ ] 29. Model versioned experiments, conditions, members and protocols
  What to do / Must NOT do: Add `src/lnt/experiments/` schemas/repositories for experiment ID/title/question/status, typed factors/conditions, protocol (`ab|aba|repeated_blocks|cohort|longitudinal`), ordered steps, session members/roles, intervention timestamps, primary/secondary estimands, confound checklist and revision history. Every protocol declares sampling unit, site/subject/block/pairing keys, assignment/order, within-unit aggregation, independence assumptions, minimum N and multiplicity policy. Store canonical JSON beside the session root's sibling experiment area and project it into catalog. MUST NOT infer condition from label text, assume sessions from one site/time are independent or require moving a session directory.
  Parallelization: Wave 4 | Blocked by: 9,19 | Blocks: 30–35
  References: current session label/catalog `src/lnt/ui/sessions.py:49-105`; current pair compare model `src/lnt/compare.py:49-56`; context audit Todo 7; recipe Todo 19.
  Acceptance criteria: all five protocols and the protocol-to-estimator contract strict-round-trip; invalid/missing sampling unit, pairing, hierarchy, aggregation, minimum N or independence declaration rejects before analysis; optimistic revisions and append-only events work; deleted/missing member remains visible as broken reference; raw sessions are never rewritten.
  QA scenarios: happy—`uv run pytest tests/experiments/test_models.py tests/experiments/test_store.py -q`; failure—duplicate role/order, unknown session and revision conflict yield typed errors without partial state. Evidence `<attemptDir>/task-29-lnt-complete-redesign.json`.
  Commit: YES | `feat(experiments): model auditable study protocols`

- [ ] 30. Make comparability, QC, inclusion and exclusion explicit
  What to do / Must NOT do: Replace binary compare eligibility with a reason-coded matrix over session type, setup, probe/range/sample rate, recipe/grid, baseline/calibration, acquisition quality and context fields. Persist proposed/included/excluded state, actor/reason/revision and allow undo. Automatic QC may recommend exclusion but never apply it. Define permitted normalization/resampling only where scientifically valid.
  Parallelization: Wave 4 | Blocked by: 14,25–27,29 | Blocks: 31,33,34
  References: current narrow `ensure_comparable`/pair compare `src/lnt/compare.py:16-22,87-128`; baseline compatibility module; quality Todo 14; input/line-quality Todos 25–26.
  Acceptance criteria: exhaustive pair matrix covers legacy/1ch/2ch/self-noise/line-quality; each block/warning includes exact fields; exclusions remain audit-visible; no code path silently drops a member.
  QA scenarios: happy—`uv run pytest tests/experiments/test_comparability.py tests/experiments/test_qc.py -q`; failure—mixed type/grid/front-end and clipped capture cannot produce an unqualified numeric compare. Evidence `<attemptDir>/task-30-lnt-complete-redesign.json`.
  Commit: YES | `feat(compare): expose comparability and QC decisions`

- [ ] 31. Implement repeated-measure, spectral and A/B/A statistics
  What to do / Must NOT do: Implement a locked protocol-to-estimator table. Paired A/B and repeated-block effects use one stored difference per independent block/unit, B−A in linear units (or a ratio converted to dB only after linear estimation), paired mean/median/robust effect and deterministic block bootstrap 95% interval when N≥3. A/B/A uses `B−(A1+A2)/2` plus separate `A2−A1` drift and is always described as a qualified within-run contrast, never causal even when drift is small. Cohort/longitudinal outputs remain descriptive unless declared independent units and a predefined estimator satisfy the protocol contract. Add line-quality harmonic deltas and feature/band tables; exploratory spectra use stored Benjamini–Hochberg plus contiguous-cluster summaries. Show sampling unit, hierarchy, N, missingness, exclusions, estimator and interval method.
  Parallelization: Wave 4 | Blocked by: 21,24,28,30 | Blocks: 32,34,35
  References: current `src/lnt/compare.py:87-128`; uncertainty Todo 21; features Todo 24; scientific corpus Todo 28.
  Acceptance criteria: analytic paired/no-effect/effect/drift/missing/outlier/hierarchical fixtures produce expected estimates/intervals/FDR without pseudoreplication; A/B/A never emits causal wording and high A drift blocks even the pooled within-run contrast; N<3 outputs descriptive deltas only; cohort/longitudinal inference is unavailable when independence/predefinition is absent.
  QA scenarios: happy—`uv run pytest tests/experiments/test_statistics.py -q`; failure—shuffle pairing/units or force A drift and assert test/result blocks invalid inference. Evidence `<attemptDir>/task-31-lnt-complete-redesign.json`.
  Commit: YES | `feat(statistics): compare repeats effects and drift`

- [ ] 32. Add longitudinal/cohort exploration and structured hypothesis records
  What to do / Must NOT do: Build grouped trends by location/condition/time-of-day and available typed metadata; compute descriptive Spearman/lag correlations with N/missingness/intervals, multiple-testing label and explicit confound columns; mark low-N findings exploratory. Add user-authored hypothesis records: statement, expected direction, mechanism, linked experiment/estimands, confounds, evidence-for/evidence-against and status (`draft|testing|consistent_with_observations|not_consistent|inconclusive`). MUST NOT generate theories automatically, use “supported” as causal shorthand or convert correlation into causation.
  Parallelization: Wave 4 | Blocked by: 8,31 | Blocks: 34,35,43
  References: metadata Todo 8; experiment schema Todo 29; draft decisions 7/8/21; user goal to reveal patterns/build theories.
  Acceptance criteria: deterministic longitudinal fixtures handle timezone, missing/duplicate times and lag; every result says descriptive/exploratory and includes N; hypothesis edits are audited and never auto-change status.
  QA scenarios: happy—`uv run pytest tests/experiments/test_longitudinal.py tests/experiments/test_hypotheses.py -q`; failure—N<minimum/constant vectors/confounded fixture returns unavailable/warning, not a coefficient claim. Evidence `<attemptDir>/task-32-lnt-complete-redesign.json`.
  Commit: YES | `feat(research): add trends and hypothesis ledger`

- [ ] 33. Execute guided A/B/A and repeated capture protocols safely
  What to do / Must NOT do: Convert experiment steps into the operation scheduler: preflight, visible requested physical intervention, user-confirmed readiness during real use, simulator auto-confirm for tests, capture/reference assignment, QC and next step. Persist every transition and permit restart at a step boundary. Randomization/block order is generated from stored seed only when protocol requests it. MUST NOT automate a mains wiring change or proceed through a physical intervention without explicit runtime confirmation.
  Parallelization: Wave 4 | Blocked by: 17,29,30 | Blocks: 34,43
  References: operation scheduler Todo 17; existing series capture CLI; safety constraints around RC shunt/transformer; experiment models Todo 29.
  Acceptance criteria: simulator completes A/B/A and repeated-block protocols end-to-end; restart resumes at exact pending boundary; cancellation keeps completed members; real mode exposes but never bypasses confirmation state.
  QA scenarios: happy—`uv run pytest tests/experiments/test_protocol_runner.py -q`; failure—attempt to auto-confirm a physical real-mode intervention and assert hard rejection/no capture. Evidence `<attemptDir>/task-33-lnt-complete-redesign.json`.
  Commit: YES | `feat(experiments): guide safe repeatable protocols`

- [ ] 34. Expose experiment, comparison, trend and hypothesis API/CLI contracts
  What to do / Must NOT do: Add bounded versioned routes/CLI for experiment CRUD/revisions/steps/members, comparability/QC, statistics runs, trend queries, hypotheses and export-ready result retrieval. Use durable jobs for expensive calculations and stable cursor pagination. MUST NOT expose arbitrary expression/SQL execution or return an unlabeled number without units/estimator/N/provenance.
  Parallelization: Wave 4 | Blocked by: 31–33 | Blocks: 35,43
  References: API patterns Todo 12/18; experiment modules Todos 29–33; Pydantic strict models in existing UI.
  Acceptance criteria: JSON contract snapshots and CLI parity cover every protocol/result; malformed filter/revision/estimand maps to stable Russian errors; 10k-member query is bounded.
  QA scenarios: happy—`uv run pytest tests/experiments/test_routes.py tests/experiments/test_cli.py -q`; failure—arbitrary filter/oversize cohort/stale revision is rejected without partial job. Evidence `<attemptDir>/task-34-lnt-complete-redesign.json`.
  Commit: YES | `feat(api): expose experiments and research results`

- [ ] 35. Produce machine-readable and human-readable scientific result models
  What to do / Must NOT do: Define report schema 1 for provenance, setup/context, QC/exclusions, recipes, primary/secondary estimands, intervals, drift/confounds, events, limitations and linked hypotheses; render canonical JSON/CSV tables and escaped offline HTML sections with Russian explanations. Report source/secondary/primary planes separately and show unavailable reasons. MUST NOT call HTML a certificate, embed remote resources or omit exclusions/limitations.
  Parallelization: Wave 4 | Blocked by: 31,32,34 | Blocks: 43–45
  References: current textual renderers `src/lnt/analysis.py`, `src/lnt/compare.py`; artifact manifests Todo 19; stats/hypotheses Todos 31–32.
  Acceptance criteria: report round-trip/schema/golden tests; HTML has no external requests/script execution and print layout; every numeric table includes units/recipe/session/member IDs and N; hostile notes are escaped.
  QA scenarios: happy—`uv run pytest tests/reporting -q`; failure—XSS-like note, missing artifact and unavailable calibration render safe explicit limitation. Evidence `<attemptDir>/task-35-lnt-complete-redesign/`.
  Commit: YES | `feat(reporting): define provenance-rich research reports`

- [ ] 36. Replace the recovered UI contract with the v2 workbench design system
  What to do / Must NOT do: Rewrite `DESIGN.md` for the approved calm data-dense instrument/workbench; define Prepare/Capture/Inspect/Experiments/Reports/Settings information architecture, desktop tri-pane (catalog, plot workspace, context inspector), tablet/mobile focus mode, scroll ownership, IBM Plex Sans/Mono, spacing/type/color/focus/motion tokens, cyan A/amber B plus non-color cues, Russian terminology and every empty/loading/error/interrupt/corrupt state. Build a semantic primitive showcase before product pages. MUST NOT use generic card soup, decorative gradients/glass, hidden essential controls or a separate design planner.
  Parallelization: Wave 5 | Blocked by: 3,12,18,27,34,35 | Blocks: 37–44
  References: partially recovered `DESIGN.md:1-10,134-252,279-304`; `.omo/frontend-design/state.md`; current static HTML/CSS; frontend skills/rules loaded during planning.
  Acceptance criteria: contract names every component/state/breakpoint/accessibility behavior; showcase contains real Russian long-content/error fixtures, theme/forced-color/reduced-motion controls and all chart shells; automated contract tests assert token/semantic/44px/focus rules.
  QA scenarios: happy—Playwright opens `/showcase`, captures 375/768/1280, light/dark/forced-colors/reduced-motion and keyboard traversal; failure—long path/200% zoom/hidden attribute fixture produces no clipped control or page horizontal scroll. Evidence `<attemptDir>/task-36-lnt-complete-redesign/`.
  Commit: YES | `design(ui): define v2 scientific workbench`

- [ ] 37. Bootstrap the offline TypeScript/Vite frontend and app shell
  What to do / Must NOT do: Create `frontend/` with locked npm, TypeScript strict mode, Vite, Vitest, Biome and Playwright; build only local versioned assets into `src/lnt/ui/static/v2/` with a source/build manifest checked for drift; implement semantic shell/navigation/view routing and error boundary. Node/npm are dev-only; committed/release built assets let Python/PyInstaller run offline. Begin the product bundle with uPlot only. In an isolated benchmark entry excluded from product assets, pin modular ECharts and measure 64k/128k/262k/524k/2M heatmap cells, wire size, initial render, zoom and teardown on the reference host; record a hard viewport-cell cap and data format before Todo 42. The dev benchmark may contain ECharts, but the shipped/new product bundle MUST NOT contain ECharts or Plotly here.
  Parallelization: Wave 5 | Blocked by: 4,36 | Blocks: 38,41,42,47
  References: current vanilla modules `src/lnt/ui/static/`; `pyproject.toml` package-data behavior; Vite/TypeScript official build semantics; design contract Todo 36.
  Acceptance criteria: `npm ci/lint/typecheck/test/build/build:check` pass; FastAPI serves hashed app assets offline; a stale source or generated asset fails build:check; browser makes zero non-loopback requests; runtime works with Node removed from PATH; benchmark JSON selects the largest cell count meeting ≤1.5 s initial render, ≤250 ms interaction and ≤512 MiB browser RSS, and fails if no candidate ≥64k works.
  QA scenarios: happy—`npm --prefix frontend run test:e2e -- shell.spec.ts`; failure—alter one built byte/source and assert build:check/build-ID mismatch blocks stale UI. Evidence `<attemptDir>/task-37-lnt-complete-redesign/`.
  Commit: YES | `build(frontend): add typed offline workbench shell`

- [ ] 38. Implement typed API client, URL/state model and accessible shared primitives
  What to do / Must NOT do: Add TypeScript domain guards/API client for stable contracts, abort/stale-request control, build-ID/nonce handling, route/query persistence and explicit loading/error/retry state; implement dialogs, tables, filters, forms, status/progress, split panes and chart shell primitives from DESIGN.md. Preserve keyboard/focus/announcements and Russian error text. MUST NOT use `any`, unsafe innerHTML, color-only state, click-only divs or silently ignore active-job clicks.
  Parallelization: Wave 5 | Blocked by: 18,37 | Blocks: 39–44
  References: current `api.js`, `app-dom.js`, `feedback.js`, `job-controller.js`; stale-chart tests; API contracts Todos 12/18/27/34.
  Acceptance criteria: Vitest contract/state/race tests and axe component tests pass; stale responses cannot overwrite current selection; reload restores safe route/filter but not secrets; every mutation exposes pending/success/failure.
  QA scenarios: happy—`npm --prefix frontend run test -- api state primitives`; failure—out-of-order responses/server restart/wrong build ID produce deterministic recovery and unlocked controls. Evidence `<attemptDir>/task-38-lnt-complete-redesign/`.
  Commit: YES | `feat(frontend): add typed state and accessible primitives`

- [ ] 39. Build the catalog, metadata and profile workspace
  What to do / Must NOT do: Implement virtualized/paged searchable catalog with health/label/type/date/location/setup/tag filters and saved views; detail inspector edits notes/tags/context with source/availability/revision conflict; profile manager previews the exact snapshot that a capture will store. Keep corrupt/missing sessions visible. MUST NOT expose catalog folder vs label ambiguity or overwrite concurrent edits.
  Parallelization: Wave 5 | Blocked by: 12,38 | Blocks: 44
  References: catalog/context/profile APIs Todo 12; current session filter/views tests; project naming distinction Catalog vs Label; design contract Todo 36.
  Acceptance criteria: 10k catalog fixture meets query/render budget; all filters/URL state/revision conflict/empty/corrupt states pass; folder, session ID, label and profile are separately named in Russian.
  QA scenarios: happy—Playwright `catalog.spec.ts` filters, edits and reloads; failure—stale revision/corrupt context/missing folder displays recovery without disappearing. Evidence `<attemptDir>/task-39-lnt-complete-redesign/`.
  Commit: YES | `feat(frontend): build catalog and context workspace`

- [ ] 40. Build the Prepare/Capture/device/job workflow
  What to do / Must NOT do: Implement mode-first setup for RC measurement, terminated self-noise, transformer line-quality and 1/2-channel; always-visible critical settings, optional advanced sections with valid disclosure behavior, profile/context preview, baseline selection, staged preflight/device diagnosis, quality guidance, durable job timeline, cancel/retry/interrupted recovery and series/protocol entry. MUST NOT hide baseline selectors, imply CH labels are metadata, auto-change hardware or silently block clicks.
  Parallelization: Wave 5 | Blocked by: 18,38 | Blocks: 44
  References: current `index.html`, `status-views.js`, `job-controller.js`; baseline/disclosure project rules #24/#31/#32; device/capture APIs Todos 14–18.
  Acceptance criteria: every mode/request maps to backend contract; keyboard/200%/mobile flows complete; device absent/busy/driver missing/firmware missing/clipping/under-range/interrupted all show exact next action; simulator capture creates indexed session.
  QA scenarios: happy—Playwright `capture.spec.ts` completes simulated single/dual/line/self-noise and cancel/retry; failure—invalid setup/baseline/server restart cannot start wrong capture and recovers visibly. Evidence `<attemptDir>/task-40-lnt-complete-redesign/`.
  Commit: YES | `feat(frontend): build trustworthy capture workflow`

- [ ] 41. Replace Plotly 1-D charts with benchmarked uPlot exploration
  What to do / Must NOT do: Implement waveform/spectrum/PSD/ASD/input-reference overlays with uPlot, linked cursor/ranges, log axes, A/B styles, extrema-preserving range fetch, peak/band annotations, selected-value summary and CSV download; pass the measured 200k-point budgets. In the same commit remove Plotly loader/vendor/assets/tests and migrate every 1-D route, so the product has only uPlot before ECharts is introduced. MUST NOT downsample away extrema or retain hidden Plotly fallback.
  Parallelization: Wave 5 | Blocked by: 27,38 | Blocks: 42–44
  References: current Plotly modules/vendor tests; payload/decimation contracts; uPlot official sync/scales examples; draft decision 17.
  Acceptance criteria: numeric/visual parity fixtures, log-safe behavior and linked interaction pass; initial/pan budgets pass; `grep`/asset inventory shows no Plotly runtime or license; accessible summary/table/CSV exists.
  QA scenarios: happy—Playwright `waveform-spectrum.spec.ts` plus `npm --prefix frontend run bench:charts`; failure—spike/log-invalid/stale-request fixture retains spike/filters invalid pairs and cannot show stale series. Evidence `<attemptDir>/task-41-lnt-complete-redesign/`.
  Commit: YES | `feat(charts): replace Plotly with linked uPlot views`

- [ ] 42. Add modular ECharts spectrogram and event exploration
  What to do / Must NOT do: Promote only the benchmarked tree-shaken ECharts Heatmap/Canvas/DataZoom/Tooltip/VisualMap modules into product assets; render a server-selected pyramid tile no larger than Todo 37's viewport-cell cap (the stored 2048×1024 overview is never sent/rendered wholesale), brush/zoom exact tile requests, event markers/list linkage, band/time summaries, perceptually ordered accessible palette and matrix/CSV download. Keep uPlot for 1-D drilldown; total product chart libraries remain exactly two. MUST NOT render millions of cells, exceed the measured cap, import full `echarts` barrel, fetch CDN or call overview pixels exact samples.
  Parallelization: Wave 5 | Blocked by: 22,23,27,38,41 | Blocks: 43,44
  References: spectrogram/event APIs Todos 22/23/27; ECharts official modular registration/dataZoom docs; design accessibility equivalents.
  Acceptance criteria: initial tile respects the benchmarked cap and meets ≤1.5 s render/≤250 ms interaction/≤512 MiB browser RSS; brush exact values match backend fixture; zoom swaps bounded tiles without stale layers; keyboard/event-list navigation and summary/matrix alternatives pass; bundle inventory contains only selected modules and no Plotly. If the cap is <64k or budgets fail, Todo 42 is blocked for redesign rather than relaxing the gate.
  QA scenarios: happy—Playwright `spectrogram.spec.ts` and chart benchmark; failure—oversized/cancelled/corrupt tile shows recoverable state without freezing or stale overlay. Evidence `<attemptDir>/task-42-lnt-complete-redesign/`.
  Commit: YES | `feat(charts): add bounded spectrogram explorer`

- [ ] 43. Build comparison, experiment, trend and hypothesis workspaces
  What to do / Must NOT do: Implement guided experiment creation/protocol timeline, member/QC/exclusion table, A/B/A drift, paired estimates/intervals, spectral/band/harmonic overlays, cohort/longitudinal plots, confound/missingness panels and structured hypothesis editor with evidence links. Every result shows units/N/recipe/plane/limitations and descriptive-vs-inferential status. MUST NOT label correlation causal, hide excluded members or present N=1 as statistical certainty.
  Parallelization: Wave 5 | Blocked by: 32–35,38,41,42 | Blocks: 44
  References: experiment APIs Todo 34; report model Todo 35; stats/hypothesis semantics Todos 31–32; current A/B views.
  Acceptance criteria: synthetic A/B/A and longitudinal journeys reproduce backend goldens; exclusion undo/audit visible; line-quality and HF layouts differ correctly; low-N/drift/confound states are explicit.
  QA scenarios: happy—Playwright `experiments.spec.ts` creates and analyses full synthetic A/B/A; failure—mixed type, high drift, low N and stale revision block/qualify claims exactly. Evidence `<attemptDir>/task-43-lnt-complete-redesign/`.
  Commit: YES | `feat(frontend): build experiment and theory workspaces`

- [ ] 44. Finish reports, settings, diagnostics, responsive and accessibility integration
  What to do / Must NOT do: Build report preview/download, settings/session-root/profile/recipe management, privacy summary, logs/support bundle and first-run/device diagnostics; complete responsive focus mode and all preference states; run full persona journeys and repair every serious/critical accessibility or visual defect. No accepted design debt without explicit affected-user statement/remediation (the plan accepts none).
  Parallelization: Wave 5 | Blocked by: 35,39–43 | Blocks: 46,47,51
  References: report Todo 35; frontend design state personas/verification matrix; DESIGN.md Todo 36; `/visual-qa` skill; current IBM Plex vendor assets.
  Acceptance criteria: all frontend gates, Playwright suites, axe and visual snapshots pass at specified sizes/themes/preferences; no non-loopback requests/console errors; Lighthouse applicable local categories target 100 with documented localhost-only exclusions.
  QA scenarios: happy—`npm --prefix frontend run test:e2e` then invoke `/visual-qa` against fresh build; failure—offline, corrupt config, unwritable root, missing device and long Russian content remain usable. Evidence `<attemptDir>/task-44-lnt-complete-redesign/`.
  Commit: YES | `feat(frontend): complete accessible offline workbench`

- [ ] 45. Add checksum-verified export, archive, backup and restore
  What to do / Must NOT do: Add explicit versioned exports for selected sessions/contexts/analyses/experiments/reports; create ZIP with manifest, relative safe paths, sizes/SHA-256 and provenance. Stream extraction into one new staging root on the destination volume while enforcing compressed/expanded bytes, file count and per-file limits; reject case-fold collisions, duplicate paths, `..`, absolute/UNC/device paths, drive/ADS colons, reserved Windows names, trailing dots/spaces and every symlink/hardlink/reparse entry before materialization. Validate checksums/schema/IDs, then rename the single staged archive root to one nonexistent destination; catalog is omitted/rebuilt. Imported HTML is download-only or opened under a sandboxed opaque origin, never served beneath the app origin. Add dry-run/list/verify CLI and UI jobs. MUST NOT claim multi-session atomicity, include secrets/logs by default, overwrite existing raw sessions or trust ZIP metadata.
  Parallelization: Wave 6 | Blocked by: 11,35 | Blocks: 50,52
  References: session atomic writes `src/lnt/session_store.py:35-67`; security path helpers; canonical/report contracts Todos 3/35; OWASP zip-slip/decompression limits.
  Acceptance criteria: backup→delete copied working root→restore→reindex yields identical per-file hashes and semantic report/catalog rows; every hostile Windows path/link/collision/ADS/bomb fixture fails before final destination creation; injected crash leaves only a named staging quarantine; imported HTML cannot execute under/read the LNT application origin.
  QA scenarios: happy—`uv run pytest tests/archive -q` and PowerShell round-trip fixture; failure—`../`, absolute, duplicate, wrong hash and expansion-limit archives all fail closed. Evidence `<attemptDir>/task-45-lnt-complete-redesign/`.
  Commit: YES | `feat(archive): add verified backup and restore`

- [ ] 46. Add production logging, support bundles and single-instance launcher
  What to do / Must NOT do: Add structured rotating local logs with correlation/job/session IDs and privacy redaction; support bundle selects config schema/device diagnostic/build/dependency/job tail without raw captures/private notes unless explicitly selected. Create launcher that acquires instance lock, pre-binds exclusive 127.0.0.1 socket (preferred 8765, deterministic next-free fallback), starts Uvicorn, waits for health/build ID and opens browser; second launch focuses/opens current URL. MUST NOT log raw samples, exact private metadata by default, reuse stale lock or allow double-bind.
  Parallelization: Wave 6 | Blocked by: 6,16,18,44 | Blocks: 47,48
  References: stale/double-server constraint #40; `src/lnt/ui/app.py`; app paths Todo 6; jobs Todo 16; privacy requirements.
  Acceptance criteria: redaction/rotation/lock/PID-start-identity tests pass; two processes yield one server; stale lock recovers; crash writes support code/log and nonzero exit without console traceback in GUI mode.
  QA scenarios: happy—`uv run pytest tests/test_logging.py tests/test_launcher.py tests/test_support_bundle.py -q`; failure—two launchers, stale PID reuse and secret fixture prove focus/recovery/redaction. Evidence `<attemptDir>/task-46-lnt-complete-redesign/`.
  Commit: YES | `feat(runtime): add private diagnostics and launcher`

- [ ] 47. Build the complete PyInstaller one-folder private-use distribution
  What to do / Must NOT do: Turn Todo 13's `go` spike into `packaging/lnt.spec`/`build.ps1`; include Python runtime, locked app/deps, NumPy/SciPy data/DLLs, Hantek firmware/libusb, IBM Plex, built v2 assets, licenses/notices and version/icon; exclude tests/caches/dev frontend/node. Verify every non-OS runtime DLL/firmware/module remains bundle-local and every external OS DLL satisfies Todo 13's canonical System32/x64/Microsoft-signer allowlist. Use one-folder, no UPX/one-file; generate ZIP and file-hash manifest; fail on missing/extra/untrusted-external/unclassified binary/data/license. Label the ZIP owner-internal/no-conveyance; any transfer requires a separate GPL compliance decision. MUST NOT copy system DLLs indiscriminately, bundle Zadig or call the bundle an installer/public release.
  Parallelization: Wave 6 | Blocked by: 4,13,37,44,46 | Blocks: 48,49
  References: Todo 13 spike; PyInstaller 6.14.1 official docs; `pyproject.toml`; frontend build manifest Todo 37; licensing Todo 4.
  Acceptance criteria: clean `build.ps1` produces deterministic inventory, ≤600 MiB unzipped, no Node/dev/test/Plotly files, all runtime data/DLLs classified, ZIP/hash manifest and private-use README present.
  QA scenarios: happy—`pwsh -File packaging/build.ps1 -Clean -Evidence <attemptDir>/task-47-lnt-complete-redesign`; failure—remove required DLL/font/static/license in staging and assert build validation fails before ZIP. Evidence directory includes size/dependency/license manifests.
  Commit: YES | `build(windows): package private one-folder LNT`

- [ ] 48. Verify the frozen runtime on a sanitized non-elevated reference host
  What to do / Must NOT do: Add `packaging/smoke-portable.ps1` that copies ZIP to a fresh temp path, constructs fresh temp HOME/APPDATA/LOCALAPPDATA/session root, removes project Python/uv/Node from PATH/PYTHON* variables, verifies bundle-local non-OS dependencies plus Todo 13's trusted System32 DLL allowlist, runs `LNT.exe selftest`, starts UI, checks health/build/assets/API/offline requests, exercises synthetic capture→analysis→experiment→report→backup/restore and non-invasive device diagnosis, then tears down every process. Record current host as Windows 10 Home 22H2 x64 and label this evidence only `sanitized-reference-host-verified`. Make the same unattended script usable on a genuinely fresh external Windows PC later, but MUST NOT label the local result sterile, clean-VM, universal or externally verified.
  Parallelization: Wave 6 | Blocked by: 46,47 | Blocks: 49,51
  References: launcher Todo 46; full package Todo 47; no Hyper-V/Sandbox environment finding; CLI/UI selftest paths; Must-NOT false portability claims.
  Acceptance criteria: script is unattended/non-elevated, leaves no process/temp state, cold health ≤15 s and all workflow checks pass without external Python/Node/network; device absent/ready is a valid typed diagnostic, not a skipped import test.
  QA scenarios: happy—`pwsh -File packaging/smoke-portable.ps1 -Zip dist/LNT-*.zip -Evidence <attemptDir>/task-48-lnt-complete-redesign`; failure—alter ZIP hash/remove DLL/occupy 8765/block device and assert integrity/fallback/diagnostic behavior. Evidence complete smoke transcript/HTTP/asset/process inventory.
  Commit: YES | `test(portable): verify frozen offline workflow`

- [ ] 49. Make builds reproducible and emit provenance, SBOM and checksums
  What to do / Must NOT do: Add `scripts/quality.ps1`, deterministic frontend/Python/package order, lock checks, timestamp normalization where supported, CycloneDX-style SBOM/source/dependency/license manifests and SHA-256 checksums. Add a Windows CI workflow definition for future private repository use, but keep local script authoritative and do not publish/upload. Compare two clean builds; classify allowed binary nondeterminism rather than falsely claiming bit reproducibility.
  Parallelization: Wave 6 | Blocked by: 4,48 | Blocks: 52
  References: lock/license Todo 4; package Todo 47; reproducibility decision 16; no public release guardrail.
  Acceptance criteria: two clean builds have identical logical file inventory, versions/config/assets/licenses and documented allowed PyInstaller byte differences; every ZIP file checksum is covered; local quality script fails stale lock/assets/SBOM.
  QA scenarios: happy—run two `build.ps1 -Clean` directories and `compare-builds.ps1`; failure—inject stale frontend/dependency/license and assert quality failure. Evidence `<attemptDir>/task-49-lnt-complete-redesign/`.
  Commit: YES | `build(release): add reproducible provenance and SBOM`

- [ ] 50. Rehearse legacy import/reanalysis on read-only copies of real sessions
  What to do / Must NOT do: Verify the pristine real-session receipt, copy representative v1/v2 single/dual/self-noise/line-quality/corrupt sessions into an evidence temp root, reindex, inspect, run old-default and new recipes, compare old metrics within documented tolerance, create sidecars/experiments only on copies, then delete temp root. Produce compatibility matrix and reason-coded gaps (especially schema-v1 input reference). MUST NOT point write-capable v2 commands at `C:\Users\Kirill\lnt-sessions`.
  Parallelization: Wave 6 | Blocked by: 10,27,45 | Blocks: 51,52
  References: real sessions root project memory; manifest/correction contract Todo 3; catalog reindex Todo 10; archive Todo 45; original hash guard Todos 1/5.
  Acceptance criteria: pre/post real-session SHA-256 receipt identical; copied session types remain readable; expected legacy numeric tolerances pass; corrupt sessions remain visible; no v1 correction is fabricated.
  QA scenarios: happy—`pwsh -File scripts/rehearse-legacy.ps1 -Source "$HOME\lnt-sessions" -Evidence <attemptDir>/task-50-lnt-complete-redesign`; failure—write attempt under real root is blocked by guard and recorded. Evidence compatibility JSON + hashes.
  Commit: YES | `test(migration): prove read-only legacy compatibility`

- [ ] 51. Close the defect, security, quality, size and performance ledger
  What to do / Must NOT do: Re-run baseline/defect ledger, `aft_inspect`, all diagnostics/gates/benchmarks; reproduce each open defect before fixing in its owning module; remove dead `getHealth`, test duplication and stale legacy assets; split new/changed production modules above 250 pure LOC (generated/vendor excluded with explicit test); audit archive/XSS/CSRF/path/process/DLL loading, memory/resource cleanup and error redaction. Add `scripts/audit-plan-evidence.ps1` (Todo 1–52 row, commit/command/exit-code/freshness/schema/skip/pristine checks) and `scripts/audit-scope.ps1` (seven user outcomes + every Must Have/Must NOT Have mapped to live evidence and immutable receipts), each emitting strict JSON and nonzero on any missing/unknown row. MUST NOT delete reachable/type-only code from scanner hints without proof or perform behavior-changing cleanup without regression test.
  Parallelization: Wave 6 | Blocked by: 2–50 | Blocks: 52,F1–F4
  References: Todo 2 ledger/baselines; latest AFT findings (1 dead/unused export, 5 duplicate groups, 0 diagnostics); quality project rule; security routes/archive/package tasks.
  Acceptance criteria: defect ledger has reproduction+fix+evidence or explicit environment-blocked status (no “unknown fixed”); unified gates pass; zero new dead/unused exports; clone policy and module-size test pass; all performance ceilings and security corpus pass.
  QA scenarios: happy—`pwsh -File scripts/quality.ps1 -Full -Evidence <attemptDir>/task-51-lnt-complete-redesign`; failure—documented mutation suite proves gates catch stale asset, path escape, XSS, unit error, memory leak and oversized module. Evidence directory + final AFT report.
  Commit: YES | `fix(quality): close v2 defect and hardening ledger`

- [ ] 52. Finish operator, scientific, safety, recovery and package documentation
  What to do / Must NOT do: Rewrite README/quick start/full Russian UI guide; document modes/front-ends/baseline/correction, metadata/privacy, recipes/units/uncertainty, experiment design/interpretation/limitations, archives, portable ZIP, WinUSB/Zadig steps (link/instructions only), diagnostics/support, backup/restore and disaster recovery. Add architecture/schema/API/developer/build/release docs and a generated in-app help set. End by rerunning pristine receipts and recording no product/session changes. MUST NOT claim public release, certified measurement, clean-VM validation or driver-free portability.
  Parallelization: Wave 6 | Blocked by: 45,49–51 | Blocks: F1–F4
  References: current `README.md`; `_recovery/RECOVERY.md`; `DESIGN.md`; all finalized contracts/evidence; safety constraint #35; owner-internal/GPL and sanitized-reference-host decisions.
  Acceptance criteria: docs link/code/schema examples are tested; Russian help covers every screen/error path; package contains matching offline docs/licenses; final original/session hash receipts equal Todo 1; no stale command/UI label remains.
  QA scenarios: happy—`uv run pytest tests/test_docs.py -q` plus link/CLI-snippet checker and packaged-help Playwright smoke; failure—stale command/broken anchor/forbidden claim fixture fails lint. Evidence `<attemptDir>/task-52-lnt-complete-redesign/`.
  Commit: YES | `docs(lnt): complete operator and scientific handbook`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance and evidence audit
  First verify `.integrity/approved-work-plan.md` against `.integrity/approved-work-plan.sha256` and the approved digest recorded in original read-only `.omo/STATE.md`; then run `pwsh -File scripts/audit-plan-evidence.ps1 -Plan .integrity/approved-work-plan.md -Commit HEAD -EvidenceRoot <attemptDir> -Output <attemptDir>/final-F1-plan-compliance.json` and `scripts/verify_pristine.ps1` against the original and real sessions. The script must enumerate exactly Todos 1–52, verify each acceptance/QA artifact against the live commit, exit codes/freshness/schema/no-skips, dependency/milestone gates and recomputed receipts. Expected: exit 0, `todos_total=52`, `unmet=[]`, `skipped=[]`, `stale=[]`, `outside_v2_writes=[]`, plan and both receipts match. Any absent/unknown/malformed row or nonzero command is FAIL; APPROVE only on those exact values.

- [ ] F2. Code, scientific-integrity, security and packaging review
  Run `/review-work` and independent focused inspection of Python/TypeScript types, error/resource paths, recipe/provenance/cache determinism, units/uncertainty/statistics/causal language, SQLite/archive/local-web boundary, DLL/license/SBOM and module-size rules. Re-run unified gates and mutation/security/science suites. Output `<attemptDir>/final-F2-quality.json`; APPROVE only with no critical/high issue and no unproven scientific claim.

- [ ] F3. Real packaged-workflow and visual QA
  From a fresh ZIP under the sanitized non-elevated reference-host environment, execute synthetic prepare→capture→inspect→A/B/A→report→backup/restore plus the user's real non-invasive Hantek diagnostic; use Playwright and `/visual-qa` on 375/768/1280, 200%, keyboard, light/dark/system/forced-colors/reduced-motion, long Russian/error/interrupted states; record screenshots/traces/console/network/process teardown and performance. No automated mains capture. Physical hardware unavailable/not ready is environment-blocked and cannot APPROVE F3. Output `<attemptDir>/final-F3-manual-qa.json`; APPROVE only if all owner journeys and the real diagnostic work and no serious visual/accessibility defect remains.

- [ ] F4. Scope fidelity, compatibility and pristine-source audit
  Verify the committed approved-plan digest as in F1, then run `pwsh -File scripts/audit-scope.ps1 -Plan .integrity/approved-work-plan.md -Commit HEAD -EvidenceRoot <attemptDir> -Output <attemptDir>/final-F4-scope.json`. It must map exactly the original seven outcomes and every Must Have/Must NOT Have to live tests/artifacts, run legacy copied-session matrix and final original/session no-follow receipts, and inventory manifests/raw writes, network/telemetry, chart assets, Plotly, Node runtime, conveyance/certification claims. Expected: exit 0, `requested_outcomes=7`, `missing=[]`, `unauthorized=[]`, `manifest_v3=[]`, `raw_mutations=[]`, `forbidden_runtime=[]`, `receipt_drift=[]`; any plan-digest mismatch or unknown/unmapped row is FAIL. APPROVE only on those exact values.

## Commit strategy
- Repository begins with Todo 1's untouched recovered-baseline commit in `location-network-tester-v2`; original remains non-Git and hash-protected.
- Each todo creates exactly the listed conventional commit after its focused tests/evidence pass; never mix unrelated todos or commit `.omo/evidence`, raw captures, local catalog/config/logs, `.venv`, `node_modules` or package output.
- Generated frontend assets are committed only together with their source/build-manifest change and must pass `build:check`; generated scientific fixtures are parameter definitions, not giant arrays.
- Wave milestone tags are local annotated tags `v2-wave0-baseline` through `v2-wave6-rc`; no remote push/public release.
- Any failed task leaves its working changes uncommitted or is reverted to the last passing atomic commit; use checkpoints before schema/migration/bulk frontend/package operations.

## Success criteria
- `location-network-tester-v2` is the only modified product tree, has clean local Git history, and final SHA-256 inventories prove the original code and `C:\Users\Kirill\lnt-sessions` equal the Todo 1 receipts.
- Every current LNT mode/CLI/UI behavior and manifest v1/v2 fixture remains compatible; new sessions still use strict known manifests, while optional sidecars/artifacts add context, recipes and experiments without raw mutation.
- Context/profile metadata is privacy-bounded and auditable; SQLite is disposable/rebuildable; durable jobs recover from restart; device/preflight/quality/cancellation states are actionable and tested.
- Scientific outputs are unit-correct, recipe/provenance-addressed, bounded-memory and validated against analytic truth; uncertainty and causal limitations are explicit; line-quality and HF comparisons never mix domains.
- A/B, A/B/A, repeated, cohort and longitudinal workflows expose members/QC/exclusions/N/estimands/intervals/drift/confounds and link to user-authored hypotheses; no opaque ML or automatic causal claim exists.
- The Russian-first workbench completes every owner journey at all required breakpoints/preferences with zero serious/critical accessibility violation, no console/non-loopback network error and all stated chart/catalog/performance gates.
- Plotly is absent; committed/runtime product contains exactly uPlot and modular ECharts, locally built with no runtime Node/CDN.
- Versioned reports/archives round-trip with checksums and hostile archives/HTML fail closed; logs/support bundles are redacted; docs describe recovery and limitations accurately.
- The owner-internal one-folder ZIP passes sanitized-reference-host non-elevated selftest/UI/synthetic workflow and the user's real non-invasive device diagnostic without Python/Node, stays ≤600 MiB unzipped and ≤15 s cold health on recorded Windows 10 Home. It is labelled `sanitized-reference-host-verified`, never sterile/clean-VM/universal/external/public-release certified; any conveyance requires a separate GPL compliance decision.
- Unified Python/frontend/browser/build/package gates pass; defect ledger is closed or explicitly environment-blocked; F1–F4 all return APPROVE and their evidence is surfaced for the user's explicit completion okay.
