# tests/science — AGENTS.md

OVERVIEW: Analytic truth corpus + verifier, engine-derived truth forbidden.

## WHERE TO LOOK

- `corpus.py`: 11 seeded fixtures, RATE 16384 / COUNT 16384 / SEED 20260811.
- `corpus.py`: exposes `AnalyticTruth` + `tolerance_rationale` per fixture.
- `corpus.py`: seeds fixed, regenerate only via explicit seed change.
- `truth.py`: `verify_scalar` requires non-empty rationale.
- `truth.py`: raises `TruthMismatchError` on tolerance breach.
- `truth.py`: verifier is dumb comparator, no math of its own.
- `test_corpus.py`: inventory check, all 11 fixtures present.
- `test_corpus.py`: digest check, byte-stable corpus identity.
- `test_corpus.py`: RMS check, analytic value vs tight tolerance.
- `test_corpus.py`: ABA pattern, A/B branches share one truth.
- `test_truth_verifier.py`: mutation rejection, perturbed value fails.
- `test_truth_verifier.py`: rationale gate, empty rationale fails.
- `test_truth_verifier.py`: boundary probe, just-outside-tolerance fails.

## CONVENTIONS

- Comment blocks: Given / When / Then.
- Given: fixture name + analytic expectation.
- When: engine call under test.
- Then: `verify_scalar` assertion.
- Golden values fixed before prod edits.
- Prod code changes to match goldens, not reverse.
- Fix green baseline before refactor.
- New math needs new fixture + rationale first.
- Rationales cite source: closed form, textbook, derivation.
- Tolerances numeric + justified, never bare epsilon.

## ANTI-PATTERNS

- Never engine-derived truth.
- Never copy engine output into corpus.
- Never silent golden updates.
- Never widen tolerance to make red pass.
- Never empty or placeholder rationale.
- Never skip digest check after corpus edit.
- Corpus is source for frontend MockLntBackend goldens (roadmap C2).
- Frontend goldens mirror corpus, never diverge.
- If corpus changes, update MockLntBackend in same commit.
