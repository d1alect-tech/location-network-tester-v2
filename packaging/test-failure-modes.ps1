# Failure-mode proof harness for the LNT private-use distribution (Todo 47 QA).

# Proves the adversarial requirement: removing a required DLL / font / static
# asset / license from a staged bundle makes validation FAIL BEFORE any ZIP is
# written. Runs build.ps1 in its internal -SkipBuild mode against corrupted
# bundle copies and asserts BOTH the nonzero exit AND that no new ZIP appeared
# in the repository dist/ directory.
# Exit codes: 0 all scenarios proven; 5 control scenario unexpectedly failed;
# 6 a removal scenario unexpectedly validated OK; 7 zip appeared despite failure.
# PowerShell 5.1 compatible (pwsh is not installed on this host).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Stage,
    [Parameter(Mandatory = $true)][string]$Evidence
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$packagingDir = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $packagingDir "..")).Path
$stageFull = (Resolve-Path -LiteralPath $Stage).Path.TrimEnd("\")
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$workRoot = Join-Path $evidenceRoot "work"
if (Test-Path -LiteralPath $workRoot) { Remove-Item -LiteralPath $workRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $workRoot | Out-Null

$transcriptPath = Join-Path $evidenceRoot "failure-modes-transcript.txt"
function Log {
    param([string]$Line)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Write-Output "[$stamp] $Line"
    Add-Content -LiteralPath $transcriptPath -Value "[$stamp] $Line" -Encoding UTF8
}

Log "=== LNT packaging failure-mode proof ==="
Log ("stage={0}" -f $stageFull)

# --- Fresh working copy of the staged bundle ------------------------------------
$bundleCopy = Join-Path $workRoot "bundle"
robocopy $stageFull $bundleCopy /MIR /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit $LASTEXITCODE" }
Log "working-copy ready (robocopy /MIR)"

# --- Control scenario: pristine copy must validate ------------------------------
. (Join-Path $packagingDir "validate-bundle.ps1")
$controlReport = Join-Path $workRoot "control-classification.json"
$controlOk = Test-BundleValidation -Bundle $bundleCopy `
    -Allowlist (Join-Path $packagingDir "system32-allowlist.v2.json") `
    -ReportPath $controlReport
Log ("CONTROL pristine-validation EXIT_CODE={0}" -f $(if ($controlOk) { 0 } else { 5 }))
if (-not $controlOk) {
    $summary = @("CONTROL FAILED EXIT_CODE=5", "pristine bundle must validate")
    $summary | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
    exit 5
}
Move-Item -LiteralPath $controlReport -Destination (Join-Path $evidenceRoot "control-classification.json") -Force

# --- Scenarios: one required file removed at a time ------------------------------
function Resolve-ScenarioTarget {
    param([string]$Bundle, [string[]]$Patterns)
    foreach ($pattern in $Patterns) {
        $hit = Get-ChildItem -LiteralPath (Join-Path $Bundle "_internal") -File -Filter $pattern -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $hit) { return $hit.FullName.Substring($Bundle.Length + 1) }
    }
    throw ("scenario target not found; tried: " + ($Patterns -join ", "))
}

$scenarios = @(
    @{ name = "removed-required-dll"; rel = (Resolve-ScenarioTarget -Bundle $bundleCopy -Patterns @("libscipy_openblas*.dll", "libopenblas*.dll", "VCRUNTIME140.dll")) },
    @{ name = "removed-required-font"; rel = "_internal/lnt/ui/static/fonts/IBMPlexSans-Regular.woff2" },
    @{ name = "removed-required-static"; rel = "_internal/lnt/ui/static/v2/index.html" },
    @{ name = "removed-required-license"; rel = "licenses/MIT.txt" }
)

$results = @()
foreach ($scenario in $scenarios) {
    $target = Join-Path $bundleCopy ($scenario.rel.Replace("/", "\"))
    if (-not (Test-Path -LiteralPath $target)) { throw "scenario target missing: $($scenario.rel)" }
    # Backup OUTSIDE the bundle: a leftover file inside would fail validation
    # for the wrong reason; the removal itself must be the cause.
    $backup = Join-Path $workRoot ($scenario.name + ".proof-backup")
    Move-Item -LiteralPath $target -Destination $backup -Force
    Log ("SCENARIO {0} :: removed {1}" -f $scenario.name, $scenario.rel)

    $zipBefore = @(Get-Item (Join-Path $repoRoot "dist\LNT-*.zip") -ErrorAction SilentlyContinue)
    $scenarioEvidence = Join-Path $evidenceRoot $scenario.name
    New-Item -ItemType Directory -Force -Path $scenarioEvidence | Out-Null

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & powershell -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $packagingDir "build.ps1") `
            -SkipBuild -StageFrom $bundleCopy -Evidence $scenarioEvidence 2>&1
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $buildExit = $LASTEXITCODE
    $output | ForEach-Object { Log ("build| " + $_) }
    Log ("SCENARIO {0} EXIT_CODE={1}" -f $scenario.name, $buildExit)

    $zipAfter = @(Get-Item (Join-Path $repoRoot "dist\LNT-*.zip") -ErrorAction SilentlyContinue)
    $noZipWritten = ($zipAfter.Count -eq $zipBefore.Count) -and
        (@(Compare-Object -ReferenceObject @($zipBefore | ForEach-Object FullName) `
                -DifferenceObject @($zipAfter | ForEach-Object FullName)).Count -eq 0)

    $validationFailed = ($buildExit -ne 0)
    if (-not $validationFailed) {
        Log ("VERDICT {0}=UNEXPECTED-PASS" -f $scenario.name)
        $results += [ordered]@{ scenario = $scenario.name; removed = $scenario.rel; expected = "fail"; observed = "pass"; exit_code = $buildExit; proof = $false }
    } elseif (-not $noZipWritten) {
        Log ("VERDICT {0}=ZIP-WRITTEN-DESPITE-FAILURE" -f $scenario.name)
        $results += [ordered]@{ scenario = $scenario.name; removed = $scenario.rel; expected = "fail"; observed = "fail-but-zip-written"; exit_code = $buildExit; proof = $false }
    } else {
        Log ("VERDICT {0}=PROVEN fail-before-zip" -f $scenario.name)
        $results += [ordered]@{
            scenario = $scenario.name
            removed = $scenario.rel
            expected = "fail"
            observed = "fail-before-zip"
            exit_code = $buildExit
            proof = $true
        }
    }

    Move-Item -LiteralPath $backup -Destination $target -Force
}

$allProven = @($results | Where-Object { $_.proof -ne $true }).Count -eq 0
$finalExit = $(if ($allProven) { 0 } else { 6 })
@{
    schema_version = 1
    stage = $stageFull
    control_validation_passed = [bool]$controlOk
    scenarios = $results
    verdict = $(if ($allProven) { "proven: every staged-removal fails validation BEFORE any ZIP" } else { "FAILED: unexpected validation outcome" })
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidenceRoot "failure-modes-verdict.json") -Encoding UTF8

$summary = New-Object System.Collections.Generic.List[string]
$summary.Add("CONTROL pristine-validation EXIT_CODE=0")
foreach ($result in $results) {
    $summary.Add(("SCENARIO {0} EXIT_CODE={1} removed={2} proof={3}" -f $result.scenario, $result.exit_code, $result.removed, $result.proof))
}
$summary.Add(("FAILURE-MODES EXIT_CODE={0}" -f $finalExit))
$summary | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
Log ("FAILURE-MODES EXIT_CODE={0}" -f $finalExit)
exit $finalExit
