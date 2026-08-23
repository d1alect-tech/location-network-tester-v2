# Authoritative local quality gate for reproducible LNT releases (Todo 49).
#
# Runs the deterministic build pipeline in fixed order and fails hard BEFORE
# declaring any release artifact good:
#   preflight -> lock freshness (uv.lock / package-lock.json) ->
#   dependency-manifest cross-check -> stale-asset detection ->
#   frontend build (must be byte-stable) -> python wheel/sdist
#   (SOURCE_DATE_EPOCH normalized) -> PyInstaller package via
#   packaging/build.ps1 -Clean -> CycloneDX-style SBOM emission + cross-check
#   -> per-file ZIP checksum coverage.
#
# Reproducibility policy = project decision 16 ("define reproducibility
# honestly"): bit-level determinism is guaranteed only for the locked Windows
# x64 dependency build; PyInstaller bootloader/base_library timestamp drift is
# documented allowed nondeterminism (see scripts/compare-builds.ps1).
#
# Usage:
#   powershell -File scripts/quality.ps1 -Evidence <dir> [-Full]
# -Full additionally runs the Todo-51 ledger gates (defect/security/size
# regressions + basedpyright) AFTER the reproducibility gates.
# Every mode runs all reproducibility gates.
# Exit codes: 0 ok; 10 preflight; 20 stale package-lock.json; 21 stale uv.lock;
# 22 dependency-manifest invalid/stale; 23 stale frontend assets;
# 30 frontend build not byte-stable; 31 python wheel/sdist failed;
# 32 package build failed; 40 SBOM failed; 50 checksum coverage failed;
# 60 Todo-51 ledger gate failed.
# PowerShell 5.1 compatible (pwsh is not installed on this host); every gate
# command appends an EXIT_CODE line to the evidence transcript.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Evidence,
    [switch]$Full
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$transcriptPath = Join-Path $evidenceRoot "quality-transcript.txt"
$summaryLines = New-Object System.Collections.Generic.List[string]

function Log {
    param([string]$Line)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $full = "[$stamp] $Line"
    # Console (not Write-Output): Log must never pollute a function's pipeline.
    [Console]::WriteLine($full)
    Add-Content -LiteralPath $transcriptPath -Value $full -Encoding UTF8
}

function Record {
    # One canonical EXIT_CODE line per gate step (adversarial contract: assert
    # artifact state separately - exit codes alone are not trusted).
    param([string]$Step, [int]$ExitCode, [string]$Detail = "")
    $suffix = ""
    if ($Detail) { $suffix = " :: $Detail" }
    Log ("STEP {0} EXIT_CODE={1}{2}" -f $Step, $ExitCode, $suffix)
    $summaryLines.Add(("STEP {0} EXIT_CODE={1} {2}" -f $Step, $ExitCode, $Detail))
}

function Fail {
    param([int]$ExitCode, [string]$Reason)
    Log ("QUALITY FAILED EXIT_CODE={0} :: {1}" -f $ExitCode, $Reason)
    $summaryLines.Add(("QUALITY FAILED EXIT_CODE={0} :: {1}" -f $ExitCode, $Reason))
    $summaryLines | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
    exit $ExitCode
}

function Invoke-Native {
    # Run a native command, tee its output into the transcript, return exit code.
    # Output is CAPTURED first so Log's Write-Output never pollutes the return.
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
    return $code
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-Uuid5 {
    # RFC 4122 name-based UUID (SHA-1, version 5) for a deterministic SBOM serial.
    param([byte[]]$NamespaceBytes, [string]$Name)
    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    try {
        $nameBytes = [System.Text.Encoding]::UTF8.GetBytes($Name)
        $all = New-Object byte[] ($NamespaceBytes.Length + $nameBytes.Length)
        [Array]::Copy($NamespaceBytes, 0, $all, 0, $NamespaceBytes.Length)
        [Array]::Copy($nameBytes, 0, $all, $NamespaceBytes.Length, $nameBytes.Length)
        $hash = $sha1.ComputeHash($all)
        $hash[6] = [byte](($hash[6] -band 0x0F) -bor 0x50)
        $hash[8] = [byte](($hash[8] -band 0x3F) -bor 0x80)
        $hex = [BitConverter]::ToString($hash[0..15]).Replace("-", "").ToLowerInvariant()
        return "{0}-{1}-{2}-{3}-{4}" -f $hex.Substring(0, 8), $hex.Substring(8, 4),
            $hex.Substring(12, 4), $hex.Substring(16, 4), $hex.Substring(20, 12)
    } finally {
        $sha1.Dispose()
    }
}

function Get-ZipEntryHashes {
    # SHA-256 of EVERY entry inside a ZIP (misleading-success defense: content,
    # not just counts). Returns hashtable name -> @{sha256; bytes}.
    param([string]$ZipPath)
    Add-Type -AssemblyName System.IO.Compression | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    $result = @{}
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.FullName.EndsWith("/")) {
                Fail 50 ("unexpected directory entry in ZIP: " + $entry.FullName)
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
            $result[$entry.FullName] = @{
                sha256 = ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
                bytes = $entry.Length
            }
        }
    } finally {
        $zip.Dispose()
    }
    return $result
}

Log "=== LNT reproducible-release quality gate ==="
Log ("params: Evidence={0} Full={1}" -f $evidenceRoot, [bool]$Full)

# --- Step 1: preflight --------------------------------------------------------
$gitHead = ""
$gitExit = 1
Push-Location $root
try {
    $gitOutput = git rev-parse HEAD
    $gitExit = $LASTEXITCODE
} finally {
    Pop-Location
}
$gitHead = [string](@($gitOutput) | Select-Object -First 1)
Record "git-head" $gitExit ([string]$gitHead)
foreach ($tool in @("git", "uv", "node", "npm")) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue
    if ($null -eq $found) { Fail 10 "required tool missing: $tool" }
}
Record "preflight-tools" 0 "git/uv/node/npm present"

# --- Step 2: lock freshness ----------------------------------------------------
# uv.lock must be up-to-date versus pyproject.toml.
$uvCheckExit = Invoke-Native "uv-lock-check" { uv lock --check }
Record "lock-uv-fresh" $uvCheckExit "uv lock --check"
if ($uvCheckExit -ne 0) { Fail 21 "uv.lock is stale versus pyproject.toml (run: uv lock)" }

# package-lock.json must equal a freshly regenerated lock for the same
# package.json (compared canonically, not byte-wise: formatting may differ).
$npmRegenDir = Join-Path $evidenceRoot "npm-lock-regen"
Remove-Item -LiteralPath $npmRegenDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $npmRegenDir | Out-Null
Copy-Item -LiteralPath (Join-Path $root "frontend\package.json") -Destination $npmRegenDir -Force
Copy-Item -LiteralPath (Join-Path $root "frontend\package-lock.json") -Destination $npmRegenDir -Force
$npmLockExit = Invoke-Native "npm-lock-regen" {
    Push-Location $npmRegenDir
    try {
        npm install --package-lock-only --ignore-scripts --no-audit --no-fund
    } finally {
        Pop-Location
    }
}
Record "lock-npm-regenerate" $npmLockExit "regenerated lock copy in evidence work dir"
if ($npmLockExit -ne 0) { Fail 20 "npm could not regenerate package-lock.json for comparison" }

# --- Step 3: dependency-manifest cross-check -----------------------------------
$lockcheckOut = Join-Path $evidenceRoot "lockcheck.json"
$lockcheckExit = Invoke-Native "release-lockcheck" {
    Push-Location $root
    try {
        uv run python (Join-Path $PSScriptRoot "release_lockcheck.py") `
            --root $root --out $lockcheckOut --npm-regen-dir $npmRegenDir
    } finally {
        Pop-Location
    }
}
Record "dependency-manifest-crosscheck" $lockcheckExit "manifest vs uv.lock/package-lock/fonts hashes"
if (-not (Test-Path -LiteralPath $lockcheckOut)) {
    Fail 22 "lockcheck produced no verdict JSON (malformed input?)"
}
$lockcheck = $null
try {
    $lockcheck = Get-Content -LiteralPath $lockcheckOut -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 22 ("lockcheck verdict unreadable/malformed: " + $_.Exception.Message)
}
if ($lockcheckExit -eq 2) { Fail 22 "dependency-manifest.json or a lock file is malformed" }
if ($lockcheckExit -ne 0 -or $lockcheck.ok -ne $true) {
    $reasons = @($lockcheck.errors) -join "; "
    Fail 22 ("dependency manifest/locks inconsistent: " + $reasons)
}
Record "locks-verified" 0 ("runtime={0} dev={1} vendored={2}" -f
    $lockcheck.checked.runtime, $lockcheck.checked.dev, $lockcheck.checked.vendored)

# --- Step 4: stale-asset detection ---------------------------------------------
# Independent re-verification of the strict built-assets manifest against disk
# (build-manifest.json outputs vs src/lnt/ui/static/v2 on-disk), then the
# Todo 37 gate as second opinion.
$staticV2 = Join-Path $root "src\lnt\ui\static\v2"
$buildManifestPath = Join-Path $staticV2 ".vite\build-manifest.json"
if (-not (Test-Path -LiteralPath $buildManifestPath)) { Fail 23 "build-manifest.json missing" }
$buildManifest = $null
try {
    $buildManifest = Get-Content -LiteralPath $buildManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 23 ("build-manifest.json malformed (corrupt manifest must fail hard): " + $_.Exception.Message)
}
$staleErrors = New-Object System.Collections.Generic.List[string]
$onDisk = @{}
Get-ChildItem -LiteralPath $staticV2 -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($staticV2.Length + 1).Replace("\", "/")
    if ($rel -ne ".vite/build-manifest.json") { $onDisk[$rel] = (Get-Sha256 $_.FullName) }
}
foreach ($prop in $buildManifest.outputs.PSObject.Properties) {
    $rel = $prop.Name
    $declared = $prop.Value.ToLowerInvariant()
    if (-not $onDisk.ContainsKey($rel)) {
        $staleErrors.Add("declared output missing on disk: $rel")
    } elseif ($onDisk[$rel] -ne $declared) {
        $staleErrors.Add("declared output drifted on disk: $rel")
    }
    $onDisk.Remove($rel)
}
foreach ($leftover in $onDisk.Keys) {
    $staleErrors.Add("on-disk asset not tracked by build-manifest: $leftover")
}
Record "stale-assets-independent" $(if ($staleErrors.Count -eq 0) { 0 } else { 23 })
if ($staleErrors.Count -gt 0) {
    Fail 23 ("stale frontend assets: " + (($staleErrors | Select-Object -First 5) -join "; "))
}
$bcExit = Invoke-Native "frontend-build-check" {
    Push-Location $root
    try {
        npm --prefix frontend run build:check
    } finally {
        Pop-Location
    }
}
Record "frontend-build-check" $bcExit "strict todo-37 manifest check"
if ($bcExit -ne 0) { Fail 23 "frontend build:check failed; built v2 assets are stale" }

# --- Step 5: deterministic frontend build (byte-stable proof) -------------------
$snapshotBefore = @{}
Get-ChildItem -LiteralPath $staticV2 -Recurse -File | ForEach-Object {
    $snapshotBefore[$_.FullName] = (Get-Sha256 $_.FullName)
}
$fbExit = Invoke-Native "frontend-build" {
    Push-Location $root
    try {
        npm --prefix frontend run build
    } finally {
        Pop-Location
    }
}
Record "frontend-build" $fbExit "vite build + build-manifest regeneration"
if ($fbExit -ne 0) { Fail 30 "frontend build failed" }
$drift = @()
Get-ChildItem -LiteralPath $staticV2 -Recurse -File | ForEach-Object {
    $h = (Get-Sha256 $_.FullName)
    if (-not $snapshotBefore.ContainsKey($_.FullName) -or $snapshotBefore[$_.FullName] -ne $h) {
        $drift += $_.FullName.Substring($root.Length + 1)
    }
}
Record "frontend-build-byte-stable" $(if ($drift.Count -eq 0) { 0 } else { 30 }) ("files={0}" -f $snapshotBefore.Count)
if ($drift.Count -gt 0) {
    Fail 30 ("frontend build output NOT byte-stable across rebuilds: " + ($drift -join "; "))
}

# --- Step 6: python wheel/sdist with normalized timestamps ----------------------
$epoch = [int](git -C $root log -1 --format=%ct)
$commitTime = [DateTimeOffset]::FromUnixTimeSeconds($epoch).UtcDateTime
$env:SOURCE_DATE_EPOCH = [string]$epoch
$env:PYTHONHASHSEED = "0"
$pythonDist = Join-Path $evidenceRoot "python-dist"
New-Item -ItemType Directory -Force -Path $pythonDist | Out-Null
$pbExit = Invoke-Native "python-dist-build" {
    Push-Location $root
    try {
        uv build --out-dir $pythonDist
    } finally {
        Pop-Location
    }
}
Record "python-dist-build" $pbExit ("SOURCE_DATE_EPOCH={0} PYTHONHASHSEED=0" -f $epoch)
if ($pbExit -ne 0) { Fail 31 "uv build (wheel/sdist) failed" }
$wheel = Get-ChildItem -LiteralPath $pythonDist -Filter "*.whl" | Select-Object -First 1
$sdist = Get-ChildItem -LiteralPath $pythonDist -Filter "*.tar.gz" | Select-Object -First 1
if ($null -eq $wheel -or $null -eq $sdist) { Fail 31 "wheel or sdist missing after uv build" }
Record "python-dist-artifacts" 0 ("wheel={0} sdist={1}" -f $wheel.Name, $sdist.Name)

# --- Step 7: PyInstaller package via authoritative packaging/build.ps1 ----------
$packageEvidence = Join-Path $evidenceRoot "package"
$pkgExit = Invoke-Native "package-build" {
    powershell -NoProfile -ExecutionPolicy Bypass `
        -File (Join-Path $root "packaging\build.ps1") `
        -Clean -Evidence $packageEvidence
}
Record "package-build" $pkgExit "packaging/build.ps1 -Clean (validation before ZIP)"
if ($pkgExit -ne 0) { Fail 32 "packaging/build.ps1 failed" }
$pkgTranscript = Join-Path $packageEvidence "build-transcript.txt"
if (-not (Test-Path -LiteralPath $pkgTranscript) -or
    (Select-String -LiteralPath $pkgTranscript -Pattern "BUILD OK EXIT_CODE=0" -Quiet) -ne $true) {
    Fail 32 "packaging transcript lacks BUILD OK EXIT_CODE=0 (misleading success defense)"
}
$projectVersion = "0.0.0"
$pyprojectText = Get-Content -LiteralPath (Join-Path $root "pyproject.toml") -Raw -Encoding UTF8
if ($pyprojectText -match '(?m)^\s*version\s*=\s*"([^"]+)"') { $projectVersion = $Matches[1] }
$zipName = "LNT-$projectVersion-win64-private-use.zip"
$zipPath = Join-Path $root "dist\$zipName"
if (-not (Test-Path -LiteralPath $zipPath)) { Fail 32 "expected release ZIP missing: $zipName" }
$zipSha256 = Get-Sha256 $zipPath
$sidecarPath = "$zipPath.sha256"
if (-not (Test-Path -LiteralPath $sidecarPath)) { Fail 32 "ZIP sha256 sidecar missing" }
$sidecarText = (Get-Content -LiteralPath $sidecarPath -Raw -Encoding ASCII).Trim()
if (-not $sidecarText.StartsWith($zipSha256)) {
    Fail 32 "sidecar hash does not match actual ZIP bytes"
}
Record "release-zip" 0 ("{0} sha256={1}" -f $zipName, $zipSha256)

# --- Step 8: CycloneDX-style SBOM emission + cross-check -------------------------
$licenseManifestPath = Join-Path $packageEvidence "license-manifest.json"
if (-not (Test-Path -LiteralPath $licenseManifestPath)) { Fail 40 "license-manifest.json missing from package evidence" }
$licenseManifest = $null
try {
    $licenseManifest = Get-Content -LiteralPath $licenseManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 40 ("license-manifest.json malformed: " + $_.Exception.Message)
}

$recipeInput = [ordered]@{
    build_ps1 = Get-Sha256 (Join-Path $root "packaging\build.ps1")
    lnt_spec = Get-Sha256 (Join-Path $root "packaging\lnt.spec")
    quality_ps1 = Get-Sha256 (Join-Path $PSScriptRoot "quality.ps1")
    release_lockcheck_py = Get-Sha256 (Join-Path $PSScriptRoot "release_lockcheck.py")
    pyproject_toml = Get-Sha256 (Join-Path $root "pyproject.toml")
    npm_lock_fingerprint = $lockcheck.npm_lock_fingerprint
}
$recipeJson = $recipeInput | ConvertTo-Json -Depth 4 -Compress
$recipeSha256 = [BitConverter]::ToString(
    [System.Security.Cryptography.SHA256]::Create().ComputeHash(
        [System.Text.Encoding]::UTF8.GetBytes($recipeJson))).Replace("-", "").ToLowerInvariant()
$artifactKeyInput = "$recipeSha256|$gitHead|" + (Get-Sha256 $buildManifestPath) + "|" +
    (Get-Sha256 (Join-Path $root "dependency-manifest.json"))
$artifactKey = [BitConverter]::ToString(
    [System.Security.Cryptography.SHA256]::Create().ComputeHash(
        [System.Text.Encoding]::UTF8.GetBytes($artifactKeyInput))).Replace("-", "").ToLowerInvariant()

$components = New-Object System.Collections.Generic.List[object]
$components.Add([ordered]@{
    type = "application"
    name = "lnt"
    version = $projectVersion
    purl = "pkg:pypi/lnt@$projectVersion"
    licenses = @(@{ license = @{ id = "MIT" } })
    hashes = @(@{ alg = "SHA-256"; content = (Get-Sha256 $wheel.FullName) })
    properties = @(@{ name = "lnt:role"; value = "application-under-test" })
})
foreach ($entry in $lockcheck.entries) {
    if ($entry.scope -eq "runtime") {
        $hashArray = @()
        $extraProps = @()
        if ($entry.hash.StartsWith("sha256:")) {
            $hashArray = @(@{ alg = "SHA-256"; content = $entry.hash.Substring(7) })
        }
        if ($entry.hash.StartsWith("git-commit:")) {
            # Git direct-reference dependency: no PyPI artifact hash exists;
            # record the pinned commit as provenance instead of faking a digest.
            $extraProps = @(@{ name = "lnt:vcs_commit"; value = $entry.hash.Substring(11) })
        }
        $components.Add([ordered]@{
            type = "library"
            name = $entry.name
            version = $entry.version
            purl = "pkg:pypi/$($entry.name)@$($entry.version)"
            licenses = @(@{ license = @{ id = $entry.license } })
            hashes = $hashArray
            properties = @(
                @{ name = "lnt:source_url"; value = $entry.source_url },
                @{ name = "lnt:scope"; value = "runtime" }
            ) + $extraProps
        })
    }
}
$components.Add([ordered]@{
    type = "library"
    name = "uplot"
    version = $lockcheck.uplot_version
    purl = "pkg:npm/uplot@$($lockcheck.uplot_version)"
    licenses = @(@{ license = @{ id = "MIT" } })
    properties = @(@{ name = "lnt:scope"; value = "vendored" })
})
foreach ($entry in $lockcheck.entries) {
    if ($entry.scope -eq "vendored" -and $entry.name -like "ibm-plex-*") {
        # "ibm-plex-<family>-<weight>" -> shipped IBMPlex<Family>-<Weight>.woff2
        $famMap = @{ sans = "Sans"; mono = "Mono" }
        $wtMap = @{ regular = "Regular"; medium = "Medium"; semibold = "SemiBold" }
        $parts = $entry.name.Substring("ibm-plex-".Length).Split("-")
        $fileLabel = "IBMPlex" + $famMap[$parts[0]] + "-" + $wtMap[$parts[1]] + ".woff2"
        $components.Add([ordered]@{
            type = "file"
            name = $entry.name
            version = $entry.version
            licenses = @(@{ license = @{ id = $entry.license } })
            hashes = @(@{ alg = "SHA-256"; content = $entry.hash.Substring("sha256:".Length) })
            properties = @(
                @{ name = "lnt:file"; value = "lnt/ui/static/fonts/$fileLabel" },
                @{ name = "lnt:scope"; value = "vendored" }
            )
        })
    }
}
$serial = Get-Uuid5 -NamespaceBytes ([byte[]](0x6b, 0xa7, 0xb8, 0x11, 0x9d, 0xad, 0x11, 0xd1,
    0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8)) -Name "lnt:sbom:$artifactKey"
# PS 5.1: a generic List embedded via @(...) inside an [ordered] literal throws
# "Argument types do not match" - materialize to a plain array FIRST.
$componentsArray = $components.ToArray()
$sbom = [ordered]@{
    bomFormat = "CycloneDX"
    specVersion = "1.5"
    serialNumber = "urn:uuid:$serial"
    version = 1
    metadata = [ordered]@{
        # Deterministic per-commit timestamp: SBOM bytes must not depend on wall clock.
        timestamp = $commitTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        tools = @{ components = @(@{ type = "application"; name = "lnt-quality-gate"; version = "1.0.0" }) }
        properties = @(
            @{ name = "lnt:git_commit"; value = [string]$gitHead },
            @{ name = "lnt:recipe_sha256"; value = $recipeSha256 },
            @{ name = "lnt:artifact_key_sha256"; value = $artifactKey },
            @{ name = "lnt:source_date_epoch"; value = [string]$epoch },
            @{ name = "lnt:scope"; value = "bundle runtime components only (dev deps do not ship)" },
            @{ name = "lnt:reproducibility_policy"; value =
                "decision 16: bit-level determinism guaranteed only for the locked Windows x64 dependency build; PyInstaller bootloader/base_library timestamp drift is documented allowed nondeterminism" }
        )
    }
    components = $componentsArray
}
$sbomPath = Join-Path $root "dist\$zipName.sbom.cdx.json"
$sbom | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $sbomPath -Encoding UTF8
Copy-Item -LiteralPath $sbomPath -Destination (Join-Path $evidenceRoot "sbom.cdx.json") -Force

# Self-validation: re-parse and cross-check against the license manifest.
$sbomCheck = $null
try {
    $sbomCheck = Get-Content -LiteralPath $sbomPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 40 ("emitted SBOM failed re-parse: " + $_.Exception.Message)
}
$sbomErrors = New-Object System.Collections.Generic.List[string]
# StrictMode-safe: vendored font "file" components carry no purl, so a
# bare $_.purl access throws PropertyNotFoundStrict under Set-StrictMode.
$pypiComponents = @($sbomCheck.components | Where-Object {
    ($null -ne $_.PSObject.Properties["purl"]) -and
    ($_.purl -like "pkg:pypi/*") -and
    ($_.type -eq "library")
})
$runtimePackages = @($licenseManifest.runtime_packages)
if ($pypiComponents.Count -ne $runtimePackages.Count) {
    $sbomErrors.Add("SBOM pypi components $($pypiComponents.Count) != license manifest runtime packages $($runtimePackages.Count)")
}
foreach ($pkg in $runtimePackages) {
    $hit = @($pypiComponents | Where-Object { $_.name -eq $pkg.name -and $_.version -eq $pkg.version -and $_.licenses[0].license.id -eq $pkg.license })
    if ($hit.Count -ne 1) { $sbomErrors.Add("SBOM/runtime mismatch for $($pkg.name)@$($pkg.version)") }
}
# StrictMode-safe vendored detection: never index properties by position
# ([1] throws under Set-StrictMode Latest for single-property components).
$vendoredSbom = @($sbomCheck.components | Where-Object {
    @($_.properties | Where-Object { $_.name -eq "lnt:scope" -and $_.value -eq "vendored" }).Count -gt 0
})
foreach ($asset in @($licenseManifest.vendored_assets)) {
    if ($asset.name -eq "uplot") {
        $hit = @($vendoredSbom | Where-Object {
            $_.name -eq $asset.name -and $_.version -eq $asset.version
        })
    } elseif ($asset.name -like "@ibm/plex-*") {
        # The npm font package ships as per-font FILE components:
        # "@ibm/plex-sans" -> "ibm-plex-sans-<weight>".
        $family = $asset.name.Substring("@ibm/plex-".Length)
        $hit = @($vendoredSbom | Where-Object {
            $_.name -like "ibm-plex-$family-*" -and
            $_.version -eq $asset.version -and
            $_.licenses[0].license.id -eq $asset.license
        })
    } else {
        $hit = @()
    }
    if ($hit.Count -lt 1) { $sbomErrors.Add("SBOM missing vendored asset $($asset.name)@$($asset.version)") }
}
$sbomComponentCount = @($sbomCheck.components).Count
Record "sbom-emitted" $(if ($sbomErrors.Count -eq 0) { 0 } else { 40 }) ("components={0} serial={1}" -f $sbomComponentCount, $sbomCheck.serialNumber)
if ($sbomErrors.Count -gt 0) {
    Fail 40 ("SBOM cross-check failed: " + (($sbomErrors | Select-Object -First 5) -join "; "))
}

# --- Step 9: ZIP checksum coverage ----------------------------------------------
$entryHashes = Get-ZipEntryHashes -ZipPath $zipPath
$classificationPath = Join-Path $packageEvidence "classification-report.json"
if (-not (Test-Path -LiteralPath $classificationPath)) {
    Fail 50 "classification-report.json missing from package evidence"
}
$classification = $null
try {
    $classification = Get-Content -LiteralPath $classificationPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Fail 50 ("classification-report.json malformed: " + $_.Exception.Message)
}
$stagedHashes = @{}
foreach ($classProp in $classification.classes.PSObject.Properties) {
    foreach ($item in @($classProp.Value)) {
        $stagedHashes[$item.path] = $item.sha256
    }
}
$coverageErrors = New-Object System.Collections.Generic.List[string]
$members = New-Object System.Collections.Generic.List[object]
foreach ($entryName in $entryHashes.Keys) {
    $members.Add([ordered]@{ path = $entryName; bytes = $entryHashes[$entryName].bytes; sha256 = $entryHashes[$entryName].sha256 })
    if (-not $stagedHashes.ContainsKey($entryName)) {
        $coverageErrors.Add("ZIP member not covered by staged classification: $entryName")
    } elseif ($stagedHashes[$entryName] -ne $entryHashes[$entryName].sha256) {
        $coverageErrors.Add("ZIP member hash differs from staged file: $entryName")
    }
}
foreach ($stagedName in $stagedHashes.Keys) {
    if (-not $entryHashes.ContainsKey($stagedName)) {
        $coverageErrors.Add("staged file missing from ZIP: $stagedName")
    }
}
$memberCount = @($entryHashes.Keys).Count
$memberArray = @($members | Sort-Object { $_.path })
$checksumManifest = [ordered]@{
    schema_version = 1
    zip_name = $zipName
    zip_sha256 = $zipSha256
    zip_bytes = (Get-Item -LiteralPath $zipPath).Length
    member_count = $memberCount
    coverage_complete = ($coverageErrors.Count -eq 0)
    verified_against_staging = $true
    members = $memberArray
}
$checksumManifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $evidenceRoot "checksum-manifest.json") -Encoding UTF8
Record "checksum-coverage" $(if ($coverageErrors.Count -eq 0) { 0 } else { 50 }) ("members={0}" -f $memberCount)
if ($coverageErrors.Count -gt 0) {
    Fail 50 ("checksum coverage incomplete: " + (($coverageErrors | Select-Object -First 5) -join "; "))
}

# --- Step 10: Todo-51 ledger gates (-Full only) ---------------------------------
if ($Full) {
    $ledgerExit = Invoke-Native "ledger-regressions" {
        Push-Location $root
        try {
            uv run pytest tests/test_module_size.py tests/test_safe_paths.py `
                tests/catalog/test_deep_verify.py tests/test_cli_bom_inputs.py `
                tests/archive tests/test_ui_security_v2.py -q
        } finally {
            Pop-Location
        }
    }
    Record "ledger-regressions" $ledgerExit "defect/security/size corpus"
    if ($ledgerExit -ne 0) { Fail 60 "Todo-51 ledger regression corpus failed" }

    $bpExit = Invoke-Native "basedpyright" {
        Push-Location $root
        try {
            uv run basedpyright
        } finally {
            Pop-Location
        }
    }
    Record "basedpyright" $bpExit "strict types"
    if ($bpExit -ne 0) { Fail 60 "basedpyright failed" }

    foreach ($auditScript in @("scripts\audit-plan-evidence.ps1", "scripts\audit-scope.ps1")) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $auditScript))) { Fail 60 ("audit engine missing: " + $auditScript) }
    }
    Record "audit-engines-present" 0 "F1/F4 engines available"
}

# --- Step 11: verdict -------------------------------------------------------------
$verdict = [ordered]@{
    schema_version = 1
    verdict = "PASS"
    git_head = [string]$gitHead
    gates = [ordered]@{
        lock_uv_fresh = $true
        lock_npm_fresh = $true
        dependency_manifest_crosscheck = $true
        stale_assets = $true
        frontend_build_byte_stable = $true
        python_dist_source_date_epoch = $epoch
        package_build = $true
        sbom_crosschecked = $true
        checksum_coverage_complete = $true
        todo51_ledger_gates = [bool]$Full
    }
    artifacts = [ordered]@{
        zip_name = $zipName
        zip_sha256 = $zipSha256
        sbom = "dist/$zipName.sbom.cdx.json"
        wheel = $wheel.Name
        sdist = $sdist.Name
    }
    sbom_components = $sbomComponentCount
    recipe_sha256 = $recipeSha256
    artifact_key_sha256 = $artifactKey
}
$verdict | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidenceRoot "quality-verdict.json") -Encoding UTF8
$summaryLines.Add("QUALITY OK EXIT_CODE=0")
$summaryLines.Add("ZIP $zipName")
$summaryLines.Add("ZIP_SHA256 $zipSha256")
$summaryLines | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
Log ("QUALITY OK EXIT_CODE=0 :: zip={0} sha256={1} sbom_components={2}" -f $zipName, $zipSha256, $sbomComponentCount)
exit 0
