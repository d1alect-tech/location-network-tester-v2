# src/lnt/ui — FastAPI + SSE job server

## OVERVIEW
FastAPI app serving Vite build + JSON/SSE API, single-job 409.

## WHERE TO LOOK
- `app.py` — StaticFiles `/static/v2` + `/` mounts, `/legacy` panel, app factory only
- `routes_*.py` + `models_*.py` — one pair per group: jobs/sessions/device/catalog/context/profiles/quality/statistics/experiments/analysis_v2/research
- `models.py` — shared envelopes; group files own their schemas
- `job_worker.py` / `job_state.py` — threading + SSE progress, dual truth: in-memory registry + on-disk store
- `jobs.py` / `operations.py` / `sessions.py` / `device.py` — job lifecycle ops, session fs, device chain
- `security.py` — launch nonce gate, `build_id` mixing, immutable hashed assets
- `decimation.py` — min/max downsample, display-only: spectrum ≤5000 pts, waveform ≤4000 pts
- `analysis_v2_wire.py` — exception-to-job-failure boundary for analysis engine
- `dependencies.py` / `api_support.py` / `payloads.py` — DI, error envelope, payload helpers
- `launcher.py` — bind/ready/browser-open, port picking

## CONVENTIONS
- Mutating requests need launch nonce: `security.py` issues per-boot, client sends header, mismatch → 403
- Bind `127.0.0.1` only; Swagger/ReDoc/OpenAPI off
- One job at a time: second launch → 409, cancel finishes current session first
- SSE streams stage + series position `i/N`; store is durable truth, registry is live view
- Decimation never touches session files; raw `spectrum.csv` / `ch*.npy` untouched
- `index.html` = `no-store`; hashed JS/CSS = `immutable`
- Compare deltas `B - A`; session write `.partial-*` + rename

## ANTI-PATTERNS
- `static/v2/` built output committed — never hand-edit; rebuild via `npm run build`, byte-stable, `build-check.js` fails on drift
- Never `raise` into job path — route through `analysis_v2_wire.py`, exceptions become job failure payloads
- No lost wakeup: `clear → check → wait` order on job events, never `wait` before re-check
- No second truth source: don't cache job/session state outside registry+store
- No absolute URLs to backend; no external CDN/font/fetch — offline bundle only
- No untrusted `innerHTML`; no new endpoints without `routes_*` + `models_*` pair
