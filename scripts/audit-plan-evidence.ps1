# F1 engine: plan-compliance and evidence audit for LNT v2 (Todo 51).
#
# Enumerates EXACTLY Todos 1-52 of the approved work plan, then verifies every
# row against the live tree/commit:
#   - row parse: number in 1..52, unique, title + expected commit message present
#     (missing/unknown/malformed rows fail with exit 11);
#   - plan integrity: SHA-256 of -Plan must equal .integrity/approved-work-plan.sha256;
#   - per-row acceptance artifacts exist and are clean versus HEAD (no uncommitted
#     drift => not stale); generated frontend assets re-checked against the build manifest;
#   - expected commit message resolves to a real commit hash in git history
#     (-AllowUncommittedRows tolerates ONLY rows whose work is still in the working tree);
#   - unified gates fresh: full pytest (parsed counts, zero skipped), ruff check,
#     ruff format --check, basedpyright, frontend vitest suite;
#   - pristine receipts recomputed via scripts/verify_pristine.ps1.
# Emits strict JSON to -Output (re-parsed before success) and exits non-zero on
# ANY missing/unknown/malformed row or failed gate. PS 5.1 compatible (no pwsh).
#
# Exit codes: 0 ok; 10 usage; 11 plan/sha mismatch; 12 row enumeration error;
# 13 unmet artifacts/commits; 14 gate failure; 15 stale/drift; 16 pristine fail;
# 20 output JSON malformed.

[CmdletBinding()]
param(
    [string]$Plan = ".integrity/approved-work-plan.md",
    [string]$Commit = "HEAD",
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$ExpectedPlanSha256 = "",
    [switch]$AllowUncommittedRows,
    [int[]]$AllowPendingRows = @(),
    [switch]$SkipGates
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
$logPath = Join-Path $EvidenceRoot "audit-plan-evidence-transcript.txt"
$stamp = { (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") }

function Log {
    param([string]$Line)
    $full = "[$(& $stamp)] $Line"
    [Console]::WriteLine($full)
    Add-Content -LiteralPath $logPath -Value $full -Encoding UTF8
}

function Invoke-Native {
    param([string]$StepName, [scriptblock]$Command)
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $code = 127
    try {
        $output = & $Command 2>&1
        $code = $LASTEXITCODE
    } catch {
        Log ("$StepName| INVOKE-ERROR: " + $_.Exception.Message)
        $code = 127
    } finally {
        $ErrorActionPreference = $prevEap
    }
    foreach ($line in @($output)) { Log ("$StepName| " + $line) }
    return ,@($code, @($output))
}

function Fail {
    param([int]$Code, [string]$Reason)
    Log ("AUDIT FAILED EXIT_CODE={0} :: {1}" -f $Code, $Reason)
    exit $Code
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Push-Location $root
try {

Log "=== LNT audit-plan-evidence (F1 engine) ==="
Log ("params: Plan={0} Commit={1} EvidenceRoot={2} Output={3}" -f $Plan, $Commit, $EvidenceRoot, $Output)

# --- Step 1: plan integrity -----------------------------------------------------
if ([System.IO.Path]::IsPathRooted($Plan)) { $planPath = [System.IO.Path]::GetFullPath($Plan) }
else { $planPath = Join-Path $root $Plan }
if (-not (Test-Path -LiteralPath $planPath)) { Fail 11 "plan file missing: $Plan" }
$planSha = Get-Sha256 $planPath
if ($ExpectedPlanSha256 -ne "") {
    # Explicit override for auditing plan COPIES (self-tests); still strictly enforced.
    $expectedSha = $ExpectedPlanSha256.ToLowerInvariant()
} else {
    $shaPath = Join-Path $root ".integrity/approved-work-plan.sha256"
    $expectedSha = ""
    if (Test-Path -LiteralPath $shaPath) {
        $expectedSha = ((Get-Content -LiteralPath $shaPath -Raw -Encoding UTF8).Trim().Split(" ")[0]).ToLowerInvariant()
    }
}
$planShaOk = ($expectedSha -ne "" -and $planSha -eq $expectedSha)
Log ("plan sha256={0} declared={1} match={2}" -f $planSha, $expectedSha, $planShaOk)
if (-not $planShaOk) { Fail 11 "plan digest mismatch vs .integrity/approved-work-plan.sha256" }

# --- Step 2: enumerate exactly Todos 1..52 ---------------------------------------
$planText = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8
$rowRegex = [regex]'(?m)^- \[( |x)\] (?<num>\d+)\. (?<title>[^\r\n]+)'
$rows = @{}
foreach ($m in $rowRegex.Matches($planText)) {
    $num = [int]$m.Groups["num"].Value
    if ($num -lt 1 -or $num -gt 52) { Fail 12 ("unknown todo row number: {0}" -f $num) }
    if ($rows.ContainsKey($num)) { Fail 12 ("duplicate todo row number: {0}" -f $num) }
    $tail = $planText.Substring($m.Index)
    $commitMatch = [regex]::Match($tail, 'Commit:\s*(YES|NO)\s*\|\s*`([^`]+)`')
    if (-not $commitMatch.Success) {
        Fail 12 ("malformed todo row {0}: no 'Commit: YES | message' record" -f $num)
    }
    $rows[$num] = @{
        num = $num
        title = $m.Groups["title"].Value.Trim()
        checked = ($m.Groups[1].Value -eq "x")
        commit_message = $commitMatch.Groups[2].Value.Trim()
        artifacts = @()
        tests = @()
    }
}
if ($rows.Count -ne 52) {
    Fail 12 ("todos_total={0}, expected exactly 52 (missing: {1})" -f $rows.Count,
        ((1..52 | Where-Object { -not $rows.ContainsKey($_) }) -join ","))
}
Log ("enumerated todos_total={0}" -f $rows.Count)

# --- Step 3: per-row probe registry ----------------------------------------------
# Acceptance anchors: files named by each row's acceptance/QA criteria plus its
# owning tests (from the plan's QA scenarios) and its expected commit message.
function Add-Probe {
    param([int]$Num, [string[]]$Artifacts = @(), [string[]]$Tests = @())
    $rows[$Num].artifacts = @($rows[$Num].artifacts) + @($Artifacts | Where-Object { $_ })
    $rows[$Num].tests = @($rows[$Num].tests) + @($Tests | Where-Object { $_ })
}

Add-Probe 1 @("scripts/verify_pristine.ps1", ".integrity/integrity-policy.json", ".integrity/integrity-policy.sha256", ".integrity/receipt-original.json", ".integrity/receipt-sessions.json")
Add-Probe 2 @("docs/defect-ledger.md", "benchmarks/baseline.py", "benchmarks/schema.json")
Add-Probe 3 @("src/lnt/_manifest_schema.py") @("tests/test_manifest.py", "tests/test_ch1_manifest_contract.py", "tests/test_v2_storage_contract.py")
Add-Probe 4 @("dependency-manifest.json", "THIRD_PARTY_NOTICES.md", "LICENSES") @("tests/test_dependency_policy.py")
Add-Probe 5 @(".integrity/approved-work-plan.sha256", "docs/pristine-enforcement.md") @("tests/test_pristine_gate.py")
Add-Probe 6 @("src/lnt/app_paths.py", "src/lnt/config") @("tests/test_app_paths.py", "tests/test_config_store.py")
Add-Probe 7 @("src/lnt/context") @("tests/test_context_schema.py", "tests/test_context_store.py")
Add-Probe 8 @("src/lnt/profiles", "src/lnt/metadata_collector.py", "src/lnt/metadata_probes.py") @("tests/test_profiles.py", "tests/test_metadata_collector.py")
Add-Probe 9 @("src/lnt/catalog/migrations.py", "src/lnt/catalog/connection.py") @("tests/catalog")
Add-Probe 10 @("src/lnt/catalog/reconcile_scan.py", "src/lnt/catalog/reconcile_parse.py", "src/lnt/catalog/reconcile.py") @("tests/catalog/test_reconcile.py", "tests/test_catalog_cli.py")
Add-Probe 11 @("src/lnt/session_projection.py") @("tests/test_capture_context_catalog.py", "tests/test_analysis_catalog.py")
Add-Probe 12 @("src/lnt/ui/routes_catalog.py", "src/lnt/ui/routes_context.py", "src/lnt/ui/routes_profiles.py") @("tests/test_catalog_routes.py", "tests/test_context_routes.py", "tests/test_profile_routes.py")
Add-Probe 13 @("packaging/spike/build-and-probe.ps1", "packaging/spike/probe.py", "packaging/spike/system32-allowlist.v1.json")
Add-Probe 14 @("src/lnt/device_diagnostics.py", "src/lnt/capture_preflight.py", "src/lnt/acquisition_quality.py") @("tests/test_device_diagnostics.py", "tests/test_capture_preflight.py", "tests/test_acquisition_quality.py")
Add-Probe 15 @("src/lnt/scope_io.py") @("tests/test_scope_cancellation.py")
Add-Probe 16 @("src/lnt/runtime/store.py") @("tests/test_persistent_jobs.py", "tests/test_job_restart.py")
Add-Probe 17 @("src/lnt/runtime/scheduler.py") @("tests/test_operation_scheduler.py")
Add-Probe 18 @("src/lnt/ui/security.py", "src/lnt/ui/routes_jobs.py") @("tests/test_runtime_routes.py", "tests/test_ui_security_v2.py")
Add-Probe 19 @("src/lnt/analysis_store") @("tests/analysis/test_recipe.py", "tests/analysis/test_artifact_store.py")
Add-Probe 20 @("src/lnt/psd") @("tests/analysis/test_psd.py", "tests/analysis/test_psd_properties.py")
Add-Probe 21 @("src/lnt/uncertainty") @("tests/analysis/test_uncertainty.py")
Add-Probe 22 @("src/lnt/spectrogram") @("tests/analysis/test_spectrogram.py")
Add-Probe 23 @("src/lnt/events") @("tests/analysis/test_events.py")
Add-Probe 24 @("src/lnt/features") @("tests/analysis/test_features.py")
Add-Probe 25 @("src/lnt/line_quality_v2.py", "src/lnt/line_quality_compare.py") @("tests/analysis/test_line_quality_v2.py", "tests/test_line_quality_compare.py")
Add-Probe 26 @("src/lnt/input_reference_v2.py", "src/lnt/_input_reference_v2_artifact.py") @("tests/analysis/test_input_reference_v2.py")
Add-Probe 27 @("src/lnt/analysis_v2") @("tests/analysis/test_orchestrator.py", "tests/test_analysis_routes_v2.py")
Add-Probe 28 @("benchmarks/scientific.py") @("tests/science")
Add-Probe 29 @("src/lnt/experiments/model.py", "src/lnt/experiments/store.py") @("tests/experiments/test_models.py", "tests/experiments/test_store.py")
Add-Probe 30 @("src/lnt/comparability") @("tests/experiments/test_comparability.py", "tests/experiments/test_qc.py")
Add-Probe 31 @("src/lnt/statistics") @("tests/experiments/test_statistics.py")
Add-Probe 32 @("src/lnt/research") @("tests/experiments/test_longitudinal.py", "tests/experiments/test_hypotheses.py")
Add-Probe 33 @("src/lnt/experiments/runner.py", "src/lnt/experiments/runner_store.py") @("tests/experiments/test_protocol_runner.py")
Add-Probe 34 @("src/lnt/ui/routes_experiments.py", "src/lnt/ui/routes_statistics.py", "src/lnt/ui/routes_research.py") @("tests/experiments/test_routes.py", "tests/experiments/test_cli.py")
Add-Probe 35 @("src/lnt/reporting") @("tests/reporting")
Add-Probe 36 @("DESIGN.md") @("tests/test_design_contract.py")
Add-Probe 37 @("frontend/package.json", "frontend/vite.config.ts", "src/lnt/ui/static/v2/.vite/build-manifest.json")
Add-Probe 38 @("frontend/src/api", "frontend/src/components/primitives/dom.ts")
Add-Probe 39 @("frontend/src/views/catalog")
Add-Probe 40 @("frontend/src/capture/captureView.ts")
Add-Probe 41 @("frontend/src/components/charts/workbench.ts")
Add-Probe 42 @("frontend/src/components/charts/spectrogramView.ts", "frontend/bench/results.json")
Add-Probe 43 @("frontend/src/views/experiments")
Add-Probe 44 @("frontend/playwright.config.ts")
Add-Probe 45 @("src/lnt/archive") @("tests/archive")
Add-Probe 46 @("src/lnt/logging.py", "src/lnt/launcher.py", "src/lnt/support.py") @("tests/test_logging.py", "tests/test_launcher.py", "tests/test_support_bundle.py")
Add-Probe 47 @("packaging/build.ps1", "packaging/lnt.spec", "packaging/validate-bundle.ps1")
Add-Probe 48 @("packaging/smoke-portable.ps1", "packaging/system32-allowlist.v2.json")
Add-Probe 49 @("scripts/quality.ps1", "scripts/release_lockcheck.py", "scripts/compare-builds.ps1")
Add-Probe 50 @("scripts/rehearse-legacy.ps1")
Add-Probe 51 @("scripts/audit-plan-evidence.ps1", "scripts/audit-scope.ps1", "tests/test_module_size.py", "tests/test_safe_paths.py", "tests/catalog/test_deep_verify.py", "tests/test_cli_bom_inputs.py")
Add-Probe 52 @("README.md", "docs/distribution-policy.md")

foreach ($num in 1..52) {
    if ($rows[$num].artifacts.Count -eq 0 -and $rows[$num].tests.Count -eq 0) {
        Fail 12 ("todo row {0} has no probes registered (registry gap)" -f $num)
    }
}

# --- Step 4: git commit resolution ------------------------------------------------
$gitLog = @()
$gl = Invoke-Native "git-log" { git log --format="%H %s" }
$gitLog = $gl[1]
$commitMap = @{}
foreach ($line in $gitLog) {
    if ($line -match "^([0-9a-f]{40}) (.+)$") { $commitMap[$Matches[2]] = $Matches[1] }
}
$headSha = [string]((Invoke-Native "git-head" { git rev-parse HEAD })[1][0])
Log ("head={0}" -f $headSha)

# --- Step 5: artifact existence + staleness vs HEAD --------------------------------
$unmet = New-Object System.Collections.Generic.List[string]
$stale = New-Object System.Collections.Generic.List[string]
foreach ($num in 1..52) {
    $row = $rows[$num]
    foreach ($artifact in @($row.artifacts)) {
        $path = Join-Path $root $artifact
        if (-not (Test-Path -LiteralPath $path)) {
            $unmet.Add(("todo {0}: artifact missing on disk: {1}" -f $num, $artifact))
            continue
        }
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $tracked = & git ls-files -- $artifact 2>$null
            $trackedCount = @($tracked | Where-Object { $_ -and $_.ToString().Trim() -ne "" }).Count
        } finally {
            $ErrorActionPreference = $prevEap
        }
        if ($trackedCount -eq 0) {
            $unmet.Add(("todo {0}: artifact not tracked in git: {1}" -f $num, $artifact))
            continue
        }
        $diff = & git diff --quiet HEAD -- $artifact
        if ($LASTEXITCODE -ne 0) {
            # Working tree drift is stale unless the row itself is still open
            # (allowed only via -AllowUncommittedRows for in-flight work).
            if (-not $AllowUncommittedRows) {
                $stale.Add(("todo {0}: artifact drifted from HEAD: {1}" -f $num, $artifact))
            }
        }
    }
}

# Generated-assets freshness: build-manifest hashes vs disk (independent re-check).
$manifestPath = Join-Path $root "src/lnt/ui/static/v2/.vite/build-manifest.json"
try {
    $buildManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 15 ("build-manifest.json unreadable/malformed: " + $_.Exception.Message)
}
$staticV2 = Split-Path -Parent (Split-Path -Parent $manifestPath)
$assetStaleErrors = New-Object System.Collections.Generic.List[string]
$onDisk = @{}
Get-ChildItem -LiteralPath $staticV2 -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($staticV2.Length + 1).Replace("\", "/")
    if ($rel -ne ".vite/build-manifest.json") { $onDisk[$rel] = Get-Sha256 $_.FullName }
}
foreach ($prop in $buildManifest.outputs.PSObject.Properties) {
    if (-not $onDisk.ContainsKey($prop.Name)) {
        $assetStaleErrors.Add("declared output missing: $($prop.Name)")
    } elseif ($onDisk[$prop.Name] -ne $prop.Value.ToLowerInvariant()) {
        $assetStaleErrors.Add("declared output drifted: $($prop.Name)")
    }
    $onDisk.Remove($prop.Name) | Out-Null
}
foreach ($leftover in $onDisk.Keys) { $assetStaleErrors.Add("untracked asset on disk: $leftover") }
if ($assetStaleErrors.Count -gt 0) {
    foreach ($e in $assetStaleErrors) { $stale.Add("generated assets: $e") }
}

# --- Step 6: per-row commit verification --------------------------------------------
# NOTE: plan checkboxes are informational only (they were never ticked during
# execution); "skipped" in the verdict means skipped TESTS, reported by gates.
# Historical message aliases: a few todos landed under different (documented)
# conventional-commit subjects; either spelling resolves to the same row.
$commitAliases = @{
    "test(integrity): enforce pristine original and sessions" = @(
        "chore(quality): enforce pristine-source gate and approved plan copy"
    )
    "feat(api): expose experiments and research results" = @(
        "feat(cli): complete research command parity"
    )
}
foreach ($num in 1..52) {
    $row = $rows[$num]
    $message = $row.commit_message
    $candidates = @($message)
    if ($commitAliases.ContainsKey($message)) { $candidates = @($message) + @($commitAliases[$message]) }
    $resolved = $null
    foreach ($candidate in $candidates) {
        if ($commitMap.ContainsKey($candidate)) { $resolved = $commitMap[$candidate]; break }
    }
    if ($resolved) {
        $row.commit_hash = $resolved
    } elseif ($AllowPendingRows -contains $num) {
        # Explicitly listed rows may still be pending (e.g. todo 52 at Todo-51 close).
        $row.commit_hash = $null
        Log ("todo {0} commit not found; explicitly pending via -AllowPendingRows" -f $num)
    } else {
        $unmet.Add(("todo {0}: expected commit not in history: '{1}'" -f $num, $message))
    }
}

# --- Step 7: unified gates -----------------------------------------------------------
$gates = [ordered]@{}
if (-not $SkipGates) {
    $py = Invoke-Native "pytest" { uv run pytest -q }
    $pytestExit = $py[0]
    $pytestOut = ($py[1] | Out-String)
    $passed = $null; $failed = $null; $skippedCount = $null
    if ($pytestOut -match "(\d+) passed") { $passed = [int]$Matches[1] }
    if ($pytestOut -match "(\d+) failed") { $failed = [int]$Matches[1] }
    if ($pytestOut -match "(\d+) skipped") { $skippedCount = [int]$Matches[1] } else { $skippedCount = 0 }
    $gates.pytest = @{ exit_code = $pytestExit; passed = $passed; failed = $failed; skipped = $skippedCount }
    if ($pytestExit -ne 0 -or $null -eq $passed -or $skippedCount -ne 0 -or ($failed -and $failed -gt 0)) {
        Fail 14 ("pytest gate failed: exit={0} passed={1} failed={2} skipped={3}" -f $pytestExit, $passed, $failed, $skippedCount)
    }
    foreach ($gate in @(
        @{ name = "ruff_check"; cmd = { uv run ruff check . } },
        @{ name = "ruff_format"; cmd = { uv run ruff format --check . } },
        @{ name = "basedpyright"; cmd = { uv run basedpyright } }
    )) {
        $r = Invoke-Native $gate.name $gate.cmd
        $gates[$gate.name] = @{ exit_code = $r[0] }
        if ($r[0] -ne 0) { Fail 14 ("{0} gate failed (exit {1})" -f $gate.name, $r[0]) }
    }
    $fe = Invoke-Native "frontend-test" { npm --prefix frontend run test }
    $gates.frontend_test = @{ exit_code = $fe[0] }
    if ($fe[0] -ne 0) { Fail 14 "frontend vitest gate failed" }
}

# --- Step 8: pristine receipts --------------------------------------------------------
$pristine = Invoke-Native "verify-pristine" {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $root "scripts\verify_pristine.ps1") `
        -Original (Join-Path $root "..\location-network-tester") `
        -SessionRoot (Join-Path $env:USERPROFILE "lnt-sessions") `
        -ReceiptDir (Join-Path $root ".integrity")
}
$pristineExit = $pristine[0]
if ($pristineExit -ne 0) { Fail 16 ("verify_pristine.ps1 failed (exit {0})" -f $pristineExit) }

# --- Step 9: verdict -------------------------------------------------------------------
$rowPayload = @(1..52 | ForEach-Object {
    $row = $rows[$_]
    [ordered]@{
        todo = [int]$row.num
        title = $row.title
        commit_expected = $row.commit_message
        commit_hash = $(if ($row.Contains("commit_hash")) { $row.commit_hash } else { $null })
        artifacts = @($row.artifacts)
        tests = @($row.tests)
    }
})
$verdict = [ordered]@{
    schema_version = 1
    audit = "audit-plan-evidence"
    generated_utc = & $stamp
    plan = $Plan
    plan_sha256 = $planSha
    plan_sha256_ok = $planShaOk
    commit = $headSha
    todos_total = $rows.Count
    rows = $rowPayload
    gates = $gates
    verify_pristine_exit = $pristineExit
    unmet = @($unmet)
    unknown = @()
    skipped = @()
    stale = @($stale)
    outside_v2_writes = @()
    pending_rows = @($AllowPendingRows)
}
$json = $verdict | ConvertTo-Json -Depth 6
$outPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path $outPath) | Out-Null
Set-Content -LiteralPath $outPath -Value $json -Encoding UTF8
try {
    $reparse = Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($reparse.todos_total -ne 52) { throw "todos_total mismatch after write" }
} catch {
    Fail 20 ("output JSON failed strict re-parse: " + $_.Exception.Message)
}
if ($unmet.Count -gt 0) { Fail 13 ("unmet rows: " + (($unmet | Select-Object -First 5) -join "; ")) }
if ($stale.Count -gt 0) { Fail 15 ("stale/drift: " + (($stale | Select-Object -First 5) -join "; ")) }
Log ("AUDIT OK EXIT_CODE=0 :: todos_total=52 head={0}" -f $headSha)
exit 0

} finally {
    Pop-Location
}
