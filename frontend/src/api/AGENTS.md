# api/ — typed backend clients

## OVERVIEW

24 typed clients, one per backend route group; types-* declare shapes, guards-* narrow them, client-* fetch them.

## WHERE TO LOOK

- `client.ts`: shared fetch wrapper, base headers, error mapping; start here.
- `client-jobs.ts`: job launch / status / cancel, single-job 409 path, nonce attach.
- `client-analysis.ts`: analyze / reanalyze triggers, branch selection, result polling.
- `types-plots.ts` + `guards-plots.ts`: `SpectrumPayload` / `InputReferredSpectrumPayload` shapes + narrowing.
- `spectrumInputReferred`: input-referred excess PSD resolution; pairs with plot types/guards above.
- `client-research.ts`: thin facade (45 LOC) over `client-research-*.ts` leaves; add new research calls to a leaf.
- `client-device.ts`, `client-profiles.ts`, `client-statistics.ts`: device / profile / stats groups.
- `types-jobs.ts`, `types-analysis.ts`, `types-device.ts`, `types-research.ts`: per-group payloads.
- `guards-jobs.ts`, `guards-analysis.ts`, `guards-device.ts`, `guards.ts`: per-group predicates.
- `errors.ts`, `types.ts`: shared error kinds + common aliases.
- `*.test.ts`: contract examples per client/guard pair.

## CONVENTIONS

- Route check: exact `pathname.startsWith(/api/)` predicate only.
- Glob/regex route match breaks vite dev/prod split, don't use.
- Mutations: send + verify `x-lnt-mutation-nonce` header each call.
- SSE in specs: `installMockBackend` then `pumpAll` to flush events.
- Narrow first: guard before access, never trust raw JSON shape.
- `df` derives only from payload `resolution_hz` field.
- Keep types-*/guards-*/client-* triple in sync per group.

## ANTI-PATTERNS

- No `as any`, `@ts-ignore` in clients or guards.
- No `df` constants, no back-calc from bins or span.
- No silent fallbacks; every default branch logs or returns explicit unavailable.
- No cross-group imports (jobs client never imports research types).
- No hand-rolled fetch outside `client.ts` wrapper.
- No unchecked `response.json()` without guard.
