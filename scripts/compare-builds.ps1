# Two-clean-build reproducibility comparison for the LNT private distribution
# (Todo 49). Runs packaging/build.ps1 -Clean TWICE into fresh separate evidence
# directories, preserves each production, then compares honestly:
#   - logical file inventory must be identical (paths AND sizes),
#   - versions/config/assets/licenses must be identical,
#   - every ZIP member of BOTH builds is SHA-256 hashed (coverage assertion),
#   - byte differences are allowed ONLY for the documented PyInstaller
#     bootloader/base_library timestamp classes (decision 16: no false
#     bit-for-bit reproducibility claim); anything else fails the verdict.
#
# Usage:
#   powershell -File scripts/compare-builds.ps1 -Evidence <dir>
# Exit codes: 0 verdict PASS; 1 verdict FAIL; 10 harness/precondition failure.
# Output: strict JSON verdict at <Evidence>\compare-verdict.json.
# PowerShell 5.1 compatible (pwsh is not installed on this host).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Evidence
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$transcriptPath = Join-Path $evidenceRoot "compare-transcript.txt"
$failures = New-Object System.Collections.Generic.List[string]

function Log {
    param([string]$Line)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $full = "[$stamp] $Line"
    # Console (not Write-Output): Log must never pollute a function's pipeline.
    [Console]::WriteLine($full)
    Add-Content -LiteralPath $transcriptPath -Value $full -Encoding UTF8
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-ZipEntryHashes {
    # SHA-256 of EVERY entry inside a ZIP (misleading-success defense: content,
    # not just counts; the coverage assertion needs per-member hashes of BOTH
    # builds, not only the aggregate archive hash). Returns hashtable
    # name -> @{sha256; bytes}; throws on structural surprises so callers can
    # classify them as harness failures.
    param([string]$ZipPath)
    Add-Type -AssemblyName System.IO.Compression | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    $result = @{}
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.EndsWith("/")) {
                throw "unexpected directory entry in ZIP: $($entry.FullName)"
            }
            $sha = [System.Security.Cryptography.SHA256]::Create()
            try {
                $stream = $entry.Open()
                try {
                    $bytes = $sha.ComputeHash($stream)
                } finally {
                    $stream.Dispose()
                }
            } finally {
                $sha.Dispose()
            }
            # PS 5.1 quirk: materialize into a plain hashtable BEFORE any
            # [ordered] literal ever sees a generic-collection value.
            $row = @{}
            $row["sha256"] = ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
            $row["bytes"] = $entry.Length
            $result[$entry.FullName] = $row
        }
    } finally {
        $zip.Dispose()
    }
    return $result
}

function Read-JsonFile {
    # Strict JSON load for harness inputs; throws with context on malformed
    # input (malformed_input defense) instead of dying without a verdict.
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label missing: $Path"
    }
    try {
        return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "$Label is not valid JSON: $($_.Exception.Message)"
    }
}

function Test-JsonContainer {
    # True for parsed-JSON objects and arrays (everything else compares as scalar).
    param([object]$Value)
    if ($null -eq $Value) { return $false }
    if ($Value -is [System.Management.Automation.PSCustomObject]) { return $true }
    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string] -and $Value -isnot [byte[]]) {
        return $true
    }
    return $false
}

function Compare-Deep {
    # Structural equality of parsed JSON with a human-readable difference path.
    param(
        [object]$A,
        [object]$B,
        [string]$Path,
        [System.Collections.Generic.List[string]]$Diffs
    )
    if ($null -eq $A -and $null -eq $B) { return }
    if (($null -eq $A) -ne ($null -eq $B)) {
        $Diffs.Add("$Path = [$A] vs [$B]")
        return
    }
    if (-not (Test-JsonContainer $A) -or -not (Test-JsonContainer $B)) {
        if ([string]$A -cne [string]$B) { $Diffs.Add("$Path = [$A] vs [$B]") }
        return
    }
    if ($A -is [System.Collections.IEnumerable] -or $B -is [System.Collections.IEnumerable]) {
        if (($A -is [System.Collections.IEnumerable]) -ne ($B -is [System.Collections.IEnumerable])) {
            $Diffs.Add("$Path container kind differs")
            return
        }
        $listA = @($A)
        $listB = @($B)
        if ($listA.Count -ne $listB.Count) { $Diffs.Add("$Path length $($listA.Count) vs $($listB.Count)") }
        $max = [Math]::Max($listA.Count, $listB.Count)
        for ($i = 0; $i -lt $max; $i++) {
            $va = $null
            $vb = $null
            if ($i -lt $listA.Count) { $va = $listA[$i] }
            if ($i -lt $listB.Count) { $vb = $listB[$i] }
            Compare-Deep -A $va -B $vb -Path "$Path[$i]" -Diffs $Diffs
        }
        return
    }
    $namesA = @($A.PSObject.Properties.Name | Sort-Object)
    $namesB = @($B.PSObject.Properties.Name | Sort-Object)
    foreach ($name in $namesA) {
        if ($namesB -notcontains $name) {
            $Diffs.Add("$Path.$name missing in B")
            continue
        }
        Compare-Deep -A $A.$name -B $B.$name -Path "$Path.$name" -Diffs $Diffs
    }
    foreach ($name in $namesB) {
        if ($namesA -notcontains $name) { $Diffs.Add("$Path.$name missing in A") }
    }
}

# Documented allowed binary nondeterminism (decision 16): PyInstaller embeds
# the build timestamp in the CArchive cookie of each launcher and stdlib
# base_library.zip keeps member timestamps. NOTHING else may differ.
$allowedPatterns = @(
    @{ pattern = "^LNT(-cli)?\.exe$"; reason = "PyInstaller CArchive cookie embeds the build timestamp (bootloader)" },
    @{ pattern = "^_internal/base_library\.zip$"; reason = "stdlib zip archive carries embedded member timestamps" }
)

Log "=== LNT two-clean-build comparison ==="
Log ("params: Evidence={0}" -f $evidenceRoot)

$runs = @(
    @{ id = "a"; buildDir = Join-Path $evidenceRoot "build-a"; artifactsDir = Join-Path $evidenceRoot "artifacts-a"; data = $null },
    @{ id = "b"; buildDir = Join-Path $evidenceRoot "build-b"; artifactsDir = Join-Path $evidenceRoot "artifacts-b"; data = $null }
)

foreach ($run in $runs) {
    # stale_state defense: fresh directories, asserted empty before building.
    foreach ($dir in @($run.buildDir, $run.artifactsDir)) {
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        if (@(Get-ChildItem -LiteralPath $dir -Force).Count -ne 0) {
            Log ("HARNESS FAIL EXIT_CODE=10 :: dir not empty after reset: $dir")
            exit 10
        }
    }
    Log "--- clean build $($run.id) ---"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $root "packaging\build.ps1") `
            -Clean -Evidence $run.buildDir 2>&1 |
            ForEach-Object { Log ("build-$($run.id)| " + $_) }
        $exitCode = $LASTEXITCODE
    } catch {
        Log ("build-$($run.id)| INVOKE-ERROR: " + $_.Exception.Message)
        $exitCode = 127
    } finally {
        $ErrorActionPreference = $prevEap
    }
    Log ("BUILD $($run.id) EXIT_CODE=$exitCode")
    if ($exitCode -ne 0) {
        $failures.Add("clean build $($run.id) failed with exit $exitCode")
        continue
    }
    $transcript = Join-Path $run.buildDir "build-transcript.txt"
    if (-not (Select-String -LiteralPath $transcript -Pattern "BUILD OK EXIT_CODE=0" -Quiet)) {
        $failures.Add("build $($run.id) transcript lacks BUILD OK EXIT_CODE=0")
        continue
    }
    # Move the production aside so run b starts from a genuinely clean dist/.
    $zips = @(Get-ChildItem -LiteralPath (Join-Path $root "dist") -Filter "LNT-*.zip" -File -ErrorAction SilentlyContinue)
    if ($zips.Count -ne 1) {
        $failures.Add("expected exactly one release ZIP after build $($run.id), found $($zips.Count)")
        continue
    }
    Move-Item -LiteralPath $zips[0].FullName -Destination (Join-Path $run.artifactsDir $zips[0].Name) -Force
    $sidecarSource = "$($zips[0].FullName).sha256"
    $sidecarMoved = Join-Path $run.artifactsDir "$($zips[0].Name).sha256"
    if (Test-Path -LiteralPath $sidecarSource) {
        Move-Item -LiteralPath $sidecarSource -Destination $sidecarMoved -Force
    }
    $zipPath = Join-Path $run.artifactsDir $zips[0].Name
    $actualHash = Get-Sha256 $zipPath
    $sidecarOk = $false
    if (Test-Path -LiteralPath $sidecarMoved) {
        $sidecarText = (Get-Content -LiteralPath $sidecarMoved -Raw -Encoding ASCII).Trim()
        $sidecarOk = $sidecarText.StartsWith($actualHash)
    }
    if (-not $sidecarOk) { $failures.Add("build $($run.id): sha256 sidecar does not match ZIP bytes") }

    try {
        $classification = Read-JsonFile -Path (Join-Path $run.buildDir "classification-report.json") -Label "classification-report.json (build $($run.id))"
        $licenseManifest = Read-JsonFile -Path (Join-Path $run.buildDir "license-manifest.json") -Label "license-manifest.json (build $($run.id))"
        $sizeManifest = Read-JsonFile -Path (Join-Path $run.buildDir "size-manifest.json") -Label "size-manifest.json (build $($run.id))"
        $entries = Get-ZipEntryHashes -ZipPath $zipPath
    } catch {
        $failures.Add("build $($run.id): harness input unreadable: $($_.Exception.Message)")
        continue
    }

    $staged = @{}
    foreach ($classProp in $classification.classes.PSObject.Properties) {
        foreach ($item in @($classProp.Value)) { $staged[$item.path] = $item.sha256 }
    }
    foreach ($name in $entries.Keys) {
        if (-not $staged.ContainsKey($name)) {
            $failures.Add("build $($run.id): ZIP member not covered by staged checksums: $name")
        } elseif ($staged[$name] -ne $entries[$name].sha256) {
            $failures.Add("build $($run.id): ZIP member hash differs from staged file: $name")
        }
    }
    foreach ($name in $staged.Keys) {
        if (-not $entries.ContainsKey($name)) {
            $failures.Add("build $($run.id): staged file missing from ZIP: $name")
        }
    }

    # PS 5.1 quirk fix: materialize the collection into a plain variable
    # BEFORE this literal is constructed; never embed @($collection)
    # inline as an [ordered] value.
    $stagedPathsArray = @($staged.Keys | Sort-Object)
    $run.data = [ordered]@{
        zip_name = $zips[0].Name
        zip_sha256 = $actualHash
        zip_bytes = (Get-Item -LiteralPath $zipPath).Length
        sidecar_verified = $sidecarOk
        entries = $entries
        staged_paths = $stagedPathsArray
        license_manifest = $licenseManifest
        size_manifest = $sizeManifest
        build_evidence = $run.buildDir
    }
}

foreach ($run in $runs) {
    if ($null -eq $run.data) {
        $run.data = [ordered]@{
            zip_name = ""
            zip_sha256 = ""
            zip_bytes = 0
            sidecar_verified = $false
            entries = @{}
            staged_paths = @()
            license_manifest = $null
            size_manifest = [pscustomobject]@{ file_count = 0 }
            build_evidence = $run.buildDir
        }
    }
}

$inventoryIdentical = $false
$licensesIdentical = $false
$sizesIdentical = $false
$coverageComplete = ($failures.Count -eq 0)
$identical = 0
$differing = New-Object System.Collections.Generic.List[object]

if ($failures.Count -eq 0) {
    # --- logical inventory -------------------------------------------------------
    $setA = $runs[0].data.staged_paths
    $setB = $runs[1].data.staged_paths
    $onlyA = @($setA | Where-Object { $setB -notcontains $_ })
    $onlyB = @($setB | Where-Object { $setA -notcontains $_ })
    $inventoryIdentical = ($onlyA.Count -eq 0 -and $onlyB.Count -eq 0)
    if (-not $inventoryIdentical) {
        $failures.Add(("logical inventory differs: only-in-A=[{0}] only-in-B=[{1}]" -f ($onlyA -join ","), ($onlyB -join ",")))
    }
    # --- versions/config/assets/licenses ------------------------------------------
    $licenseDiffs = New-Object System.Collections.Generic.List[string]
    Compare-Deep -A $runs[0].data.license_manifest -B $runs[1].data.license_manifest `
        -Path "license-manifest" -Diffs $licenseDiffs
    $licensesIdentical = ($licenseDiffs.Count -eq 0)
    if (-not $licensesIdentical) {
        $failures.Add("versions/licenses differ between builds: " + ($licenseDiffs -join "; "))
    }
    $sizeDiffs = New-Object System.Collections.Generic.List[string]
    Compare-Deep -A $runs[0].data.size_manifest.files -B $runs[1].data.size_manifest.files `
        -Path "size-manifest.files" -Diffs $sizeDiffs
    $sizesIdentical = ($sizeDiffs.Count -eq 0)
    if (-not $sizesIdentical) {
        $failures.Add("per-file sizes differ between builds: " + ($sizeDiffs -join "; "))
    }
    if ($runs[0].data.zip_name -ne $runs[1].data.zip_name) {
        $failures.Add("ZIP names differ: $($runs[0].data.zip_name) vs $($runs[1].data.zip_name)")
    }
    # --- per-member content comparison ---------------------------------------------
    foreach ($name in $runs[0].data.entries.Keys) {
        if (-not $runs[1].data.entries.ContainsKey($name)) { continue }
        $hashA = $runs[0].data.entries[$name].sha256
        $hashB = $runs[1].data.entries[$name].sha256
        if ($hashA -eq $hashB) {
            $identical++
            continue
        }
        $allowed = $null
        foreach ($rule in $allowedPatterns) {
            if ($name -match $rule.pattern) { $allowed = $rule.reason; break }
        }
        if ($null -eq $allowed) {
            $failures.Add("UNEXPLAINED byte difference between builds: $name")
        } else {
            $differing.Add([ordered]@{ path = $name; reason = $allowed })
        }
    }
    Log ("content: identical={0} documented-different={1} total={2}" -f $identical, $differing.Count, $runs[0].data.entries.Count)
}

$differingArray = $differing.ToArray()
$policyArray = @($allowedPatterns | ForEach-Object { "{0} -> {1}" -f $_.pattern, $_.reason })
$verdictValue = "PASS"
if ($failures.Count -gt 0) { $verdictValue = "FAIL" }
$verdict = [ordered]@{
    schema_version = 1
    verdict = $verdictValue
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    method = "two independent packaging/build.ps1 -Clean productions compared by logical inventory, versions/config/licenses, and per-member SHA-256"
    reproducibility_claim = "decision 16: deterministic LOGICAL builds; bit-level determinism guaranteed only for the locked Windows x64 dependency build minus documented bootloader timestamp drift"
    build_a = [ordered]@{
        evidence_dir = $runs[0].data.build_evidence
        zip_name = $runs[0].data.zip_name
        zip_sha256 = $runs[0].data.zip_sha256
        zip_bytes = $runs[0].data.zip_bytes
        files = $runs[0].data.size_manifest.file_count
    }
    build_b = [ordered]@{
        evidence_dir = $runs[1].data.build_evidence
        zip_name = $runs[1].data.zip_name
        zip_sha256 = $runs[1].data.zip_sha256
        zip_bytes = $runs[1].data.zip_bytes
        files = $runs[1].data.size_manifest.file_count
    }
    checks = [ordered]@{
        logical_inventory_identical = $inventoryIdentical
        versions_config_assets_licenses_identical = ($licensesIdentical -and $sizesIdentical)
        zip_checksum_coverage_complete = $coverageComplete
        sidecars_match_zip_bytes = ($runs[0].data.sidecar_verified -and $runs[1].data.sidecar_verified)
    }
    content_comparison = [ordered]@{
        identical_files = $identical
        differing_files = $differingArray
        allowed_differences_policy = $policyArray
    }
    failures = $failures.ToArray()
}
$verdict | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot "compare-verdict.json") -Encoding UTF8
$finalExit = 1
if ($verdictValue -eq "PASS") { $finalExit = 0 }
Log ("COMPARE VERDICT={0} EXIT_CODE={1}" -f $verdictValue, $finalExit)
foreach ($failure in $failures) { Log ("FAILURE: " + $failure) }
exit $finalExit
