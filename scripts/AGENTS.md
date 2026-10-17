# scripts — local gate + release tooling

## OVERVIEW

15 files: PowerShell 5.1 gate scripts (`quality.ps1` is the local gate authority) + 4 Python release/vendor tools.

## WHERE TO LOOK

| Task | Script |
|---|---|
| Authoritative local gate | `quality.ps1 -Evidence <dir> [-Full]` |
| Two-clean-build compare | `compare-builds.ps1 -Evidence <dir>` → `compare-verdict.json` (0 PASS / 1 FAIL / 10 harness) |
| Scope audit (MNH gates) | `audit-scope.ps1 -EvidenceRoot <dir> -Output <json>` — forbidden deps/claims/packaging features |
| Plan/evidence audit | `audit-plan-evidence.ps1` — full pytest + ruff + basedpyright + vitest + pristine, `-n auto` |
| Pristine / integrity | `Assert-Pristine.ps1`, `verify_pristine.ps1`, `Assert-EvidencePaths.ps1`, `Verify-ApprovedPlan.ps1` — all dot-source `Integrity.Common.ps1` |
| Corresponding source | `release_sources.py` — deterministic archive from committed HEAD |
| Pin verification | `release_lockcheck.py` (0 verified / 1 semantic mismatch / 2 malformed) |
| Vendoring | `pin_vendor.py` (read-only), `vendor_ibm_plex.py` (fetch + verify IBM Plex WOFF2) |
| Legacy rehearsal | `rehearse-legacy.ps1` |

## CONVENTIONS

- PowerShell 5.1 only (pwsh is not installed on the host); every script opens with `Set-StrictMode -Version Latest` + `$ErrorActionPreference = "Stop"`.
- `quality.ps1` exit codes: 0 ok; 10 preflight; 20 stale package-lock.json; 21 stale uv.lock; 22 dependency-manifest; 23 stale frontend assets; 30 frontend not byte-stable; 31 wheel/sdist; 32 package; 33 Corresponding Source; 40 SBOM; 50 checksums; 60 ledger gate. `-Full` adds the Todo-51 ledger gates after the reproducibility gates; every mode runs all reproducibility gates.
- One canonical `STEP <name> EXIT_CODE=<n>` line per gate step — adversarial contract: artifact state is asserted separately, exit codes alone are not trusted; strict JSON verdicts are re-parsed before success.
- UTC-stamped transcript written into the `-Evidence` dir.
- `Log` writes via `[Console]::WriteLine`, never `Write-Output` (pipeline pollution).
- Python tools run under `uv run --python 3.12`; tests invoke them as subprocesses by path (`tests/test_release_lockcheck.py`, `tests/test_release_sources.py`).

## ANTI-PATTERNS

- `quality.ps1` stays the single authoritative gate — CI (`.github/workflows/build.yml`) only replays it and uploads nothing.
- `pin_vendor.py` mismatch means investigate — never silently rewrite frozen golden pins.
- Full pytest and ruff are NOT inside `quality.ps1` — run them separately.
- Integrity scripts are report-only (MUST-FAIL semantics): they never auto-fix, receipts regenerate explicitly.
