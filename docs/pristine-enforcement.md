# Pristine-Source Enforcement Gate

## Purpose

The pristine-enforcement gate ensures that the **original reference source**
(`location-network-tester`) and the **real sessions root** (`~\lnt-sessions`)
remain **immutable snapshots** — unmodified, untampered, and unescaped-into —
for the duration of the v2 redesign.

Any modification to the original source invalidates the integrity receipts,
which is a **must-fail** signal: the gate reports the mismatch but **never
auto-updates** receipts. Safe receipt regeneration requires explicit user
action to replace the original reference.

## Components

### 1. `scripts/Assert-Pristine.ps1` — integrity receipt check

Invokes `verify_pristine.ps1` with the correct parameters:

- Verifies `integrity-policy.sha256` matches `integrity-policy.json`
- Re-inventories the original source tree and sessions root
- Re-hashes every file against `receipt-original.json` and `receipt-sessions.json`
- Detects: new files, missing files, size/mtime changes, hash mismatches,
  reparse-point escapes, and concurrent mutations
- Exit 0 = pristine; exit 1 = failure

**Usage:**
```powershell
.\scripts\Assert-Pristine.ps1 `
    -Original C:\path\to\location-network-tester `
    -SessionRoot C:\Users\Kirill\lnt-sessions
```

### 2. `scripts/Assert-EvidencePaths.ps1` — evidence-path guard

Given a list of output/evidence paths, fails if any path normalises into the
original source tree or the real sessions root.  Catches:

- `..\` traversal
- Forward-slash / back-slash mixing
- Reparse-point escape (symlinks, junctions) — every path component is checked
- Case variations on a case-insensitive filesystem

**Usage:**
```powershell
.\scripts\Assert-EvidencePaths.ps1 `
    -Paths @("C:\out\report.pdf") `
    -Original C:\path\to\location-network-tester `
    -SessionRoot C:\Users\Kirill\lnt-sessions
```

### 3. `.integrity/approved-work-plan.md` + `.integrity/approved-work-plan.sha256`

A **byte-identical frozen copy** of the approved plan file at execution time.
The live plan file (`location-network-tester\.omo\plans\lnt-complete-redesign.md`)
legitimately changes as the orchestrator marks checkboxes.  This copy freezes
the exact content that was approved.

### 4. `scripts/Verify-ApprovedPlan.ps1` — committed-copy hash check

Re-hashes `approved-work-plan.md` against the pinned `.sha256` file.  Detects
if the committed copy itself was modified.  Does **not** check the live plan file.

**Usage:**
```powershell
.\scripts\Verify-ApprovedPlan.ps1
```

### 5. `tests/test_pristine_gate.py` — pytest integration

Marked with `@pytest.mark.pristine` so it can run standalone:

```bash
uv run pytest tests/test_pristine_gate.py -q -m pristine
```

Or the whole suite:

```bash
uv run pytest tests/test_pristine_gate.py -q
```

Tests cover:
- Happy path: Assert-Pristine.ps1 exits 0 on pristine source
- Missing receipt dir: exits non-zero
- Safe evidence path: passes
- Path inside original tree: rejected
- Path traversal `..\`: rejected
- Path inside sessions root: rejected
- Forward/back slash mixing: rejected
- Verify-ApprovedPlan: exits 0 on intact committed copy

## When Does the Gate Run?

- **Before every milestone**: verify the original reference is still pristine
- **After every milestone**: verify nothing leaked back into the original tree
- **On CI/CD**: as part of the quality gate pipeline
- **Before any destructive operation**: e.g., regenerating receipts

## Safe Receipt Regeneration

If the original reference genuinely needs to change (e.g., user applies an
upstream patch), regeneration is an **explicit manual step**:

1. Run `.\scripts\verify_pristine.ps1` — expect failure
2. Investigate and confirm the change is legitimate
3. Delete the old receipt in `.integrity/`
4. Re-run the receipt-creation workflow
5. Update `integrity-policy.sha256` if the policy changed
6. Run `Assert-Pristine.ps1` to confirm green

The gate will **never auto-update** receipts after mismatch.

## MUST-FAIL Semantics

- If the original source has changed → `Assert-Pristine.ps1` exits 1
- If an evidence path escapes into protected trees → `Assert-EvidencePaths.ps1` exits 1
- If the approved-plan committed copy is modified → `Verify-ApprovedPlan.ps1` exits 1

In all cases the script **reports only** — no auto-fix, no auto-update.
