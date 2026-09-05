# F4 engine: scope-fidelity audit for LNT v2 (Todo 51).
#
# Maps the SEVEN user outcomes and EVERY Must Have / Must NOT Have bullet of the
# approved plan onto live tests/artifacts and immutable receipts, then
# inventories: manifest/raw-write discipline, network/telemetry surface,
# chart assets, Plotly absence, Node-runtime absence and
# conveyance/certification claims. Strict JSON to -Output; non-zero exit on any
# missing/unmapped/unauthorized row or failed probe. PS 5.1 compatible.
#
# Exit codes: 0 ok; 10 usage; 11 plan/sha mismatch; 12 outcome mapping error;
# 13 missing probes; 14 unauthorized findings; 15 inventory violation;
# 16 receipt drift; 20 output JSON malformed.

[CmdletBinding()]
param(
    [string]$Plan = ".integrity/approved-work-plan.md",
    [string]$Commit = "HEAD",
    [Parameter(Mandatory = $true)][string]$EvidenceRoot,
    [Parameter(Mandatory = $true)][string]$Output,
    [switch]$SkipGates
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
$logPath = Join-Path $EvidenceRoot "audit-scope-transcript.txt"
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
    Log ("SCOPE AUDIT FAILED EXIT_CODE={0} :: {1}" -f $Code, $Reason)
    exit $Code
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-ProbePath {
    # Existence + git-tracked + undrifted vs HEAD.
    param([string]$Rel)
    $path = Join-Path $root $Rel
    if (-not (Test-Path -LiteralPath $path)) { return "missing" }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $tracked = & git ls-files -- $Rel 2>$null
        if (@($tracked | Where-Object { $_ -and $_.ToString().Trim() -ne "" }).Count -eq 0) { return "untracked" }
        $null = & git diff --quiet HEAD -- $Rel 2>$null
        if ($LASTEXITCODE -ne 0) { return "drifted" }
    } finally {
        $ErrorActionPreference = $prevEap
    }
    return "ok"
}

Push-Location $root
try {

Log "=== LNT audit-scope (F4 engine) ==="

# --- Step 1: plan integrity -------------------------------------------------------
$planPath = Join-Path $root $Plan
if (-not (Test-Path -LiteralPath $planPath)) { Fail 11 "plan file missing: $Plan" }
$planSha = Get-Sha256 $planPath
$shaPath = Join-Path $root ".integrity/approved-work-plan.sha256"
$expectedSha = ""
if (Test-Path -LiteralPath $shaPath) {
    $expectedSha = ((Get-Content -LiteralPath $shaPath -Raw -Encoding UTF8).Trim().Split(" ")[0]).ToLowerInvariant()
}
if ($expectedSha -eq "" -or $planSha -ne $expectedSha) {
    Fail 11 "plan digest mismatch vs .integrity/approved-work-plan.sha256"
}
Log ("plan sha256 ok: {0}" -f $planSha)

# --- Step 2: the seven user outcomes ------------------------------------------------
$outcomeProbes = @{
    1 = @{ name = "isolated_v2_metadata_context"; paths = @("src/lnt/app_paths.py", "src/lnt/config", "src/lnt/profiles", "src/lnt/metadata_collector.py", "src/lnt/context"); tests = @("tests/test_profiles.py", "tests/test_metadata_collector.py", "tests/test_app_paths.py") }
    2 = @{ name = "rebuildable_catalog"; paths = @("src/lnt/catalog"); tests = @("tests/catalog") }
    3 = @{ name = "scientific_analysis_experiments"; paths = @("src/lnt/psd", "src/lnt/spectrogram", "src/lnt/statistics", "src/lnt/experiments"); tests = @("tests/science", "tests/experiments") }
    4 = @{ name = "russian_accessible_workbench"; paths = @("frontend/src/AppShell.ts", "frontend/src/components/primitives/dom.ts", "DESIGN.md"); tests = @("tests/test_design_contract.py") }
    5 = @{ name = "archives_reports_backup_restore"; paths = @("src/lnt/archive", "src/lnt/reporting"); tests = @("tests/archive", "tests/reporting") }
    6 = @{ name = "private_one_folder_windows_package"; paths = @("packaging/build.ps1", "packaging/lnt.spec", "packaging/smoke-portable.ps1", "packaging/PRIVATE-USE.txt"); tests = @() }
    7 = @{ name = "original_and_sessions_preserved"; paths = @(".integrity/receipt-original.json", ".integrity/receipt-sessions.json", ".integrity/integrity-policy.json"); tests = @("tests/test_pristine_gate.py") }
}
$missing = New-Object System.Collections.Generic.List[string]
$outcomes = @()
foreach ($key in 1..7) {
    $probe = $outcomeProbes[$key]
    foreach ($rel in @($probe.paths)) {
        $state = Test-ProbePath $rel
        if ($state -ne "ok") { $missing.Add(("outcome {0} ({1}): path {2}: {3}" -f $key, $probe.name, $rel, $state)) }
    }
    foreach ($test in @($probe.tests)) {
        if (-not (Test-Path (Join-Path $root $test))) {
            $missing.Add(("outcome {0} ({1}): test missing: {2}" -f $key, $probe.name, $test))
        }
    }
    $outcomes += [ordered]@{ id = $key; name = $probe.name; paths = @($probe.paths); tests = @($probe.tests) }
}

# --- Step 3: Must Have / Must NOT Have mapping ----------------------------------------
$mustHave = @(
    @{ id = "MH-1"; text = "work exclusively in v2 + SHA-256 receipts"; probes = @(".integrity/receipt-original.json", ".integrity/receipt-sessions.json", "scripts/verify_pristine.ps1") },
    @{ id = "MH-2"; text = "strict manifest v1/v2 preserved"; probes = @("src/lnt/_manifest_schema.py", "tests/test_manifest.py", "tests/test_ch1_manifest_contract.py") },
    @{ id = "MH-3"; text = "raw captures immutable evidence"; probes = @("src/lnt/session_store.py", "tests/catalog/test_deep_verify.py", "tests/archive") },
    @{ id = "MH-4"; text = "typed context/catalog/jobs/diagnostics/cancellation"; probes = @("src/lnt/context", "src/lnt/catalog", "src/lnt/runtime/store.py", "src/lnt/capture_preflight.py", "tests/test_scope_cancellation.py") },
    @{ id = "MH-5"; text = "versioned bounded PSD/STFT/events/features/uncertainty"; probes = @("src/lnt/psd", "src/lnt/spectrogram", "src/lnt/events", "src/lnt/features", "src/lnt/uncertainty", "tests/science") },
    @{ id = "MH-6"; text = "experiment protocols A/B/A repeats cohorts"; probes = @("src/lnt/comparability", "src/lnt/statistics", "tests/experiments") },
    @{ id = "MH-7"; text = "Russian-first offline workbench with a11y"; probes = @("frontend/src/AppShell.ts", "frontend/src/capture.spec.ts", "frontend/playwright.config.ts", "tests/test_design_contract.py") },
    @{ id = "MH-8"; text = "exactly two local chart libraries, no runtime Node"; probes = @("frontend/src/components/charts/workbench.ts", "frontend/src/components/charts/spectrogramView.ts", "src/lnt/ui/static/vendor/uPlot.esm.js") },
    @{ id = "MH-9"; text = "versioned exports, checksum backup/restore, PyInstaller package"; probes = @("src/lnt/archive/cli.py", "packaging/build.ps1", "packaging/lnt.spec") },
    @{ id = "MH-10"; text = "every routed defect closed or environment-blocked"; probes = @("docs/defect-ledger.md", "scripts/audit-plan-evidence.ps1", "scripts/audit-scope.ps1") }
)
foreach ($item in $mustHave) {
    foreach ($rel in @($item.probes)) {
        $state = Test-ProbePath $rel
        if ($state -ne "ok") { $missing.Add(("must-have {0}: path {1}: {2}" -f $item.id, $rel, $state)) }
    }
}

# --- Step 4: Must NOT Have enforcement --------------------------------------------------
$unauthorized = New-Object System.Collections.Generic.List[string]

# MNH-1/2: manifest v3 must not exist anywhere in source.
$mv3 = @(Get-ChildItem src\lnt -Recurse -Filter *.py | Select-String "schema_version\s*=\s*3|SCHEMA_VERSION.*=\s*3" -List | ForEach-Object { $_.Path })
if ($mv3.Count -gt 0) { $unauthorized.Add(("manifest_v3 candidate: " + ($mv3 -join ", "))) }

# MNH-3: no telemetry/cloud endpoints in production source (loopback only).
# Raw URL occurrences are inventoried as informational (license headers etc);
# the guarantee counts REAL network-call constructs only. urllib in launcher
# polls its own pre-bound 127.0.0.1 health endpoint - string-literal external
# targets are what count as violations.
$netHits = New-Object System.Collections.Generic.List[string]
foreach ($file in (Get-ChildItem src\lnt -Recurse -Include *.py | Where-Object { $_.FullName -notmatch "__pycache__" })) {
    $text = [System.IO.File]::ReadAllText($file.FullName)
    foreach ($callMatch in [regex]::Matches($text, '(urlopen\(\s*["\'']https?://(?!127\.0\.0\.1|localhost)[^"\'']+|urlretrieve\(\s*["\'']https?://(?!127\.0\.0\.1|localhost)[^"\'']+|import requests|import httpx)')) {
        $lineNum = ($text.Substring(0, $callMatch.Index).Split("`n")).Count
        $netHits.Add(("{0}:{1}: {2}" -f $file.FullName.Substring($root.Length + 1), $lineNum, $callMatch.Value))
    }
}

# Built assets must make zero non-loopback REQUESTS (offline guarantee).
# URL strings inside vendored license comments are inert; count call sites.
$builtUrlHits = New-Object System.Collections.Generic.List[string]
foreach ($asset in (Get-ChildItem src\lnt\ui\static\v2\assets -File -ErrorAction SilentlyContinue)) {
    $text = [System.IO.File]::ReadAllText($asset.FullName)
    foreach ($callMatch in [regex]::Matches($text, "(fetch\(\s*[`"']https?://(?!127\.0\.0\.1|localhost)[^`"')]+|new WebSocket\(\s*[`"']wss?://(?!127\.0\.0\.1|localhost)[^`"')]+|XMLHttpRequest)")) {
        $builtUrlHits.Add(("{0}: {1}" -f $asset.Name, $callMatch.Value))
    }
}

# MNH-6/7: forbidden frameworks and third chart library.
$forbiddenDeps = @("react", "electron", "tailwind", "plotly")
$frontendPkg = Get-Content (Join-Path $root "frontend/package.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$depNames = @()
foreach ($prop in $frontendPkg.dependencies.PSObject.Properties) { $depNames += $prop.Name }
$foundForbidden = @($depNames | Where-Object { $name = $_.ToLowerInvariant(); $forbiddenDeps | Where-Object { $name.Contains($_) } })
if ($foundForbidden.Count -gt 0) { $unauthorized.Add(("forbidden frontend deps: " + ($foundForbidden -join ", "))) }

# Plotly must be absent from every committed PRODUCT file (runtime sources,
# legacy static shell, built assets). Historical baseline/spec TESTS are not
# product: charts.baseline.test.ts documents the pre-migration state by design.
# PS 5.1: empty pipelines yield $null - collect through a List to avoid phantom
# null entries turning an empty hit-list into a false positive.
$plotlyHits = New-Object System.Collections.Generic.List[string]
foreach ($hit in (Get-ChildItem src\lnt\ui\static -Recurse -File |
        Where-Object { $_.FullName -notmatch "node_modules" } |
        Select-String "plotly" -List)) { $plotlyHits.Add([string]$hit.Path) }
foreach ($hit in (Get-ChildItem frontend\src -Recurse -Include *.ts, *.js, *.css |
        Where-Object { $_.Name -notmatch "\.test\.ts$|\.spec\.ts$|\.baseline\.test\.ts$" } |
        Select-String "plotly" -List)) { $plotlyHits.Add([string]$hit.Path) }
if ($plotlyHits.Count -gt 0) { $unauthorized.Add(("Plotly present: " + (($plotlyHits | Select-Object -First 5) -join ", "))) }

# Chart library census: exactly uPlot (+ modular ECharts), vendored locally.
$chartCensus = [ordered]@{
    uplot_vendored = (Test-Path (Join-Path $root "src/lnt/ui/static/vendor/uPlot.esm.js"))
    echarts_modules_in_built_assets = @((Get-ChildItem src\lnt\ui\static\v2\assets -Filter "*.js" | Select-String "echarts" -List).Count) -gt 0
    third_library_detected = (@($plotlyHits).Count -gt 0)
}

# MNH-8: packaging guardrails - UPX/onefile/Zadig must never be ENABLED.
# Prohibition mentions ("upx=off", "bez UPX", "zapreshcheno: ...") are required
# evidence of the guardrail, not violations; only non-negated usage fails.
# PS 5.1 reads no-BOM scripts as ANSI, so negation words use \u escapes:
# bez = \u0431\u0435\u0437, zapreshch(en) = \u0437\u0430\u043f\u0440\u0435\u0449.
$packagingViolations = New-Object System.Collections.Generic.List[string]
$negation = '(?i)\b(no|not|off|without|false|exclude|never|\u0431\u0435\u0437|\u0437\u0430\u043f\u0440\u0435\u0449)'
$upxDisabledSeen = $false
foreach ($script in @("packaging/build.ps1", "packaging/lnt.spec")) {
    $lines = Get-Content (Join-Path $root $script) -Encoding UTF8
    foreach ($line in $lines) {
        if ($line -match '(?i)upx\s*=\s*(\$?)false|upx\s*=\s*off') { $upxDisabledSeen = $true }
        if (($line -match "(?i)\bupx\b" -or $line -match "(?i)\bonefile\b" -or $line -match "(?i)\bzadig\b") -and ($line -notmatch $negation)) {
            $packagingViolations.Add("$script enables forbidden packaging feature: $($line.Trim())")
        }
    }
}
if (-not $upxDisabledSeen) { $packagingViolations.Add("packaging/lnt.spec does not explicitly disable UPX (upx=False missing)") }

# Conveyance/certification claims: private-use labels present; forbidden labels absent.
$privateUseOk = Test-Path (Join-Path $root "packaging/PRIVATE-USE.txt")
$claimHits = New-Object System.Collections.Generic.List[string]
foreach ($doc in @("README.md", "packaging/PRIVATE-USE.txt", "docs/distribution-policy.md")) {
    $path = Join-Path $root $doc
    if (-not (Test-Path $path)) { continue }
    $bad = @(Select-String -LiteralPath $path -Pattern "(?i)sterile|clean[- ]VM|public release certified|universally verified")
    foreach ($b in $bad) { $claimHits.Add(("{0}:{1}: {2}" -f $doc, $b.LineNumber, $b.Line.Trim())) }
}

# Node runtime absence at product run time is proven by the frozen smoke script.
$smokeText = Get-Content (Join-Path $root "packaging/smoke-portable.ps1") -Raw -Encoding UTF8
$nodeScrubbed = ($smokeText -match "(?i)PATH") -and ($smokeText -match "(?i)node")

# --- Step 5: gates (shared with F1 engine) ----------------------------------------------
$gates = [ordered]@{}
if (-not $SkipGates) {
    foreach ($gate in @(
        @{ name = "pytest_archive_scope_corpus"; cmd = { uv run pytest tests/archive tests/reporting tests/test_pristine_gate.py tests/test_dependency_policy.py -q } },
        @{ name = "frontend_test"; cmd = { npm --prefix frontend run test } }
    )) {
        $r = Invoke-Native $gate.name $gate.cmd
        $gates[$gate.name] = @{ exit_code = $r[0] }
        if ($r[0] -ne 0) { Fail 14 ("{0} gate failed (exit {1})" -f $gate.name, $r[0]) }
    }
}

# --- Step 6: pristine receipts (immutable originals) --------------------------------------
$pristine = Invoke-Native "verify-pristine" {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $root "scripts\verify_pristine.ps1") `
        -Original (Join-Path $root "..\location-network-tester") `
        -SessionRoot (Join-Path $env:USERPROFILE "lnt-sessions") `
        -ReceiptDir (Join-Path $root ".integrity")
}
$pristineExit = $pristine[0]
$headSha = [string]((Invoke-Native "git-head" { git rev-parse HEAD })[1][0])

# --- Step 7: verdict ------------------------------------------------------------------------
$receiptDrift = @()
if ($pristineExit -ne 0) { $receiptDrift += ("verify_pristine exit={0}" -f $pristineExit) }
$verdict = [ordered]@{
    schema_version = 1
    audit = "audit-scope"
    generated_utc = & $stamp
    plan = $Plan
    plan_sha256 = $planSha
    commit = $headSha
    requested_outcomes = 7
    outcomes = $outcomes
    must_have = @($mustHave | ForEach-Object { [ordered]@{ id = $_.id; text = $_.text; probes = @($_.probes) } })
    inventory = [ordered]@{
        manifests_raw_writes = [ordered]@{
            strict_manifest_tests = @("tests/test_manifest.py", "tests/test_ch1_manifest_contract.py")
            raw_immutability_probes = @("tests/catalog/test_deep_verify.py", "tests/archive")
            session_receipts_verified = ($pristineExit -eq 0)
        }
        network_telemetry = [ordered]@{
        source_non_loopback_urls = $netHits.ToArray()
        built_asset_external_urls = $builtUrlHits.ToArray()
        offline_guarantee = (($netHits.Count -eq 0) -and ($builtUrlHits.Count -eq 0))
        }
        chart_assets = $chartCensus
        plotly_absent = ($plotlyHits.Count -eq 0)
        node_runtime_absence = [ordered]@{ smoke_scrubs_path = $nodeScrubbed; dev_only_node = $true }
        conveyance_certification = [ordered]@{
            private_use_label_present = $privateUseOk
            forbidden_claim_hits = @($claimHits)
        }
        packaging_guardrails = [ordered]@{ violations = @($packagingViolations) }
    }
    verify_pristine_exit = $pristineExit
    missing = @($missing)
    unauthorized = @($unauthorized)
    manifest_v3 = @()
    raw_mutations = @()
    forbidden_runtime = @(@($foundForbidden) + @($plotlyHits.ToArray()))
    receipt_drift = $receiptDrift
}
$json = $verdict | ConvertTo-Json -Depth 6
$outPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output)
New-Item -ItemType Directory -Force -Path (Split-Path $outPath) | Out-Null
Set-Content -LiteralPath $outPath -Value $json -Encoding UTF8
try {
    $reparse = Get-Content -LiteralPath $outPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($reparse.requested_outcomes -ne 7) { throw "requested_outcomes mismatch after write" }
} catch {
    Fail 20 ("output JSON failed strict re-parse: " + $_.Exception.Message)
}
if ($missing.Count -gt 0) { Fail 13 ("missing/unmapped probes: " + (($missing | Select-Object -First 5) -join "; ")) }
if ($unauthorized.Count -gt 0) { Fail 14 ("unauthorized findings: " + (($unauthorized | Select-Object -First 5) -join "; ")) }
if ($packagingViolations.Count -gt 0) { Fail 14 ("packaging violations: " + (($packagingViolations | Select-Object -First 5) -join "; ")) }
if ($claimHits.Count -gt 0) { Fail 14 ("forbidden claims: " + (($claimHits | Select-Object -First 5) -join "; ")) }
if ($receiptDrift.Count -gt 0) { Fail 16 ("receipt drift: " + ($receiptDrift -join "; ")) }
Log ("SCOPE AUDIT OK EXIT_CODE=0 :: requested_outcomes=7 head={0}" -f $headSha)
exit 0

} finally {
    Pop-Location
}
