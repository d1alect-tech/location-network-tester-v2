# testkit/ — e2e mock backend + fixtures

## OVERVIEW

Test-only infrastructure: unified mock backend, canned goldens, fixture
generators. Never imported by product code. Earned by score 9:
`installMockBackend` has 29 spec importers.

## WHERE TO LOOK

- `mockBackend.ts`: `installMockBackend`, `MockLntBackend` — unified e2e
  backend, merged from three diverged mocks (jobs+SSE pump,
  catalog/context/profiles, research). SSE pace is driven by the spec via
  `pump()`/`pumpAll()`.
- `mockGolden.ts`: canned golden numbers; source of truth is
  `tests/science/corpus.py` — aba semantics are NOT duplicated in TS.
- `catalogFixture.ts` (~700 LOC, exempt from the 250-LOC module gate):
  `generateSessions`, `worstCaseSessions`, `corpusRows`, `CORPUS_*` fixture
  dirs; deterministic seeds via `mulberry32`.
- `mockCatalogStore.ts` / `mockDevice.ts` / `mockJobStore.ts` /
  `mockResearchStore.ts` / `mockHttp.ts`: per-domain stores;
  `mockCatalogStore` reuses `views/inspect/sessionAlias`.
- `axe.ts`: `injectAxe` + `seriousAxeViolations` for a11y specs.
- `*.test.ts`: unit pins for the mocks themselves (aliases, stores,
  goldens); no `*.spec.ts` lives here — specs sit beside the views they
  exercise.

## CONVENTIONS

- Specs: `installMockBackend` first, then `pumpAll()` to flush SSE — never
  sleep.
- Deterministic only: fixed seeds, fixed snapshots; no wall-clock, no
  unseeded randomness.
- Mutations require the nonce from `/api/config`; the mock serves it.
- Route matching `startsWith("/api/")` only — glob `**/api/**` broke vite
  module splitting.

## ANTI-PATTERNS

- NEVER import testkit from product modules — the `main.ts` graph must stay
  clean.
- Golden numbers never diverge from the science corpus; no interval is
  computed from an input-set signature.
- The product backend contract never changes to satisfy a mock.
