# Build script for the private-use one-folder LNT Windows distribution (Todo 47).

# Usage:
#   powershell -File packaging/build.ps1 -Clean -Evidence <dir>
# Internal harness hooks (failure-mode proofs, Todo 47 QA):
#   -SkipBuild [-StageFrom <bundle-dir>] — validate an existing staged bundle only.
# Exit codes: 0 ok; 2 bundle validation failed (before ANY ZIP); 3 artifact
# assertion failed; 4 zip/hash/manifest stage failed; 10 clean/preflight failed.
# PowerShell 5.1 compatible (pwsh is not installed on this host); every gate
# command appends an EXIT_CODE line to the evidence transcript.

[CmdletBinding()]
param(
    [switch]$Clean,
    [Parameter(Mandatory = $true)][string]$Evidence,
    [switch]$SkipBuild,
    [string]$StageFrom
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
$pyiRoot = Join-Path $root "build\pyinstaller"
$pyiDist = Join-Path $pyiRoot "dist"
$pyiWork = Join-Path $pyiRoot "work"
$stageDefault = Join-Path $pyiDist "LNT"
$outDist = Join-Path $root "dist"
$allowlist = Join-Path $PSScriptRoot "system32-allowlist.v2.json"
$specPath = Join-Path $PSScriptRoot "lnt.spec"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
New-Item -ItemType Directory -Force -Path $outDist | Out-Null

$transcriptPath = Join-Path $evidenceRoot "build-transcript.txt"
$summaryLines = New-Object System.Collections.Generic.List[string]

function Log {
    param([string]$Line)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $full = "[$stamp] $Line"
    Write-Output $full
    Add-Content -LiteralPath $transcriptPath -Value $full -Encoding UTF8
}

function Record {
    # One canonical EXIT_CODE line per gate command (adversarial contract:
    # assert artifact state separately — exit codes alone are not trusted).
    param([string]$Step, [int]$ExitCode, [string]$Detail = "")
    $suffix = ""
    if ($Detail) { $suffix = " :: $Detail" }
    Log ("STEP {0} EXIT_CODE={1}{2}" -f $Step, $ExitCode, $suffix)
    $summaryLines.Add(("STEP {0} EXIT_CODE={1} {2}" -f $Step, $ExitCode, $Detail))
}

function Fail {
    param([int]$ExitCode, [string]$Reason)
    Log ("BUILD FAILED EXIT_CODE={0} :: {1}" -f $ExitCode, $Reason)
    $summaryLines.Add(("BUILD FAILED EXIT_CODE={0} :: {1}" -f $ExitCode, $Reason))
    $summaryLines | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
    exit $ExitCode
}

Log "=== LNT private-use packaging build ==="
Log ("params: Clean={0} SkipBuild={1} Evidence={2}" -f [bool]$Clean, [bool]$SkipBuild, $evidenceRoot)

# --- Step 1: provenance header -------------------------------------------------
Push-Location $root
try {
    $gitHead = git rev-parse HEAD 2>$null
    Record "git-head" $LASTEXITCODE ([string]$gitHead)
} finally {
    Pop-Location
}

if (-not $SkipBuild) {
    # --- Step 2: -Clean really cleans (stale_state defense) --------------------
    if ($Clean) {
        $stalePaths = @($pyiRoot, (Join-Path $outDist "LNT-*.zip"), (Join-Path $outDist "LNT-*.sha256"))
        foreach ($stale in $stalePaths) {
            $found = @(Get-Item $stale -ErrorAction SilentlyContinue)
            foreach ($item in $found) {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force
            }
        }
        $stillThere = @()
        foreach ($stale in $stalePaths) { $stillThere += @(Get-Item $stale -ErrorAction SilentlyContinue) }
        if ($stillThere.Count -gt 0) {
            Fail 10 ("-Clean did not remove: " + (($stillThere | ForEach-Object FullName) -join "; "))
        }
        Record "clean" 0 ("removed-and-verified-absent: build/pyinstaller, dist/LNT-*.zip, dist/LNT-*.sha256")
    }

    # --- Step 3: frontend freshness (read-only strict manifest check) ----------
    $npmExit = $null
    Push-Location $root
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & npm --prefix frontend run build:check 2>&1 |
                ForEach-Object { Log ("npm:build:check| " + $_) }
            $npmExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
    } catch {
        Log ("npm:build:check| INVOKE-ERROR: " + $_.Exception.Message)
        if ($null -eq $npmExit) { $npmExit = 127 }
    } finally {
        Pop-Location
    }
    Record "frontend-build-check" $npmExit "strict built-assets manifest check"
    if ($npmExit -ne 0) { Fail 20 "frontend build:check failed; built v2 assets are stale" }

    # --- Step 4: deterministic staging via PyInstaller --------------------------
    if (Test-Path -LiteralPath $stageDefault) {
        Remove-Item -LiteralPath $stageDefault -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $pyiDist | Out-Null
    Push-Location $root
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            & uv run pyinstaller --noconfirm --clean `
                --distpath $pyiDist --workpath $pyiWork `
                $specPath 2>&1 |
                ForEach-Object { Log ("pyinstaller| " + $_) }
            $pyiExit = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
    } catch {
        Log ("pyinstaller| INVOKE-ERROR: " + $_.Exception.Message)
        if ($null -eq $pyiExit) { $pyiExit = 127 }
    } finally {
        Pop-Location
    }
    Record "pyinstaller-onefolder" $pyiExit "onefolder, upx=off, console=off (GUI launcher)"
    if ($pyiExit -ne 0) { Fail 30 "PyInstaller failed" }
    $stage = $stageDefault
} else {
    if (-not $StageFrom) { Fail 10 "-SkipBuild requires -StageFrom <bundle-dir>" }
    $stage = [System.IO.Path]::GetFullPath($StageFrom)
}
Record "artifact-stage-exists" $(if (Test-Path -LiteralPath (Join-Path $stage "LNT.exe")) { 0 } else { 3 }) $stage
if (-not (Test-Path -LiteralPath (Join-Path $stage "LNT.exe"))) {
    Fail 3 "staged LNT.exe missing after build; refusing validation theater"
}

# --- Step 4.5: stage user-facing documents next to LNT.exe ---------------------
# PyInstaller places all datas under _internal; the private-use notice, license
# texts and provenance manifest belong beside the executable where the owner
# sees them. Move (not copy) so every file exists exactly once.
if (-not $SkipBuild) {
    $internalDir = Join-Path $stage "_internal"
    foreach ($doc in @("THIRD_PARTY_NOTICES.md", "distribution-policy.md", "PRIVATE-USE.txt", "dependency-manifest.json")) {
        $source = Join-Path $internalDir $doc
        $target = Join-Path $stage $doc
        if (-not (Test-Path -LiteralPath $source)) { Fail 3 "expected PyInstaller data missing: _internal/$doc" }
        Move-Item -LiteralPath $source -Destination $target -Force
        if (-not (Test-Path -LiteralPath $target)) { Fail 3 "document staging failed: $doc" }
    }
    Move-Item -LiteralPath (Join-Path $internalDir "licenses") -Destination (Join-Path $stage "licenses") -Force
    if (-not (Test-Path -LiteralPath (Join-Path $stage "licenses\MIT.txt"))) {
        Fail 3 "license directory staging failed"
    }
}
Record "stage-documents" 0 "notices/policy/licenses/manifest moved beside LNT.exe"

# --- Step 5: classify + validate BEFORE any ZIP --------------------------------
. (Join-Path $PSScriptRoot "validate-bundle.ps1")
$classificationReport = Join-Path $evidenceRoot "classification-report.json"
$validated = Test-BundleValidation -Bundle $stage -Allowlist $allowlist -ReportPath $classificationReport
Record "bundle-validation" $(if ($validated) { 0 } else { 2 }) "every file classified; external OS DLLs allowlisted; <=600 MiB"
if (-not $validated) {
    Fail 2 "bundle validation failed; no ZIP was written (see classification-report.json)"
}

# --- Step 6: deterministic ZIP --------------------------------------------------
Add-Type -AssemblyName System.IO.Compression | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null

$projectVersion = "0.0.0"
$pyprojectText = Get-Content -LiteralPath (Join-Path $root "pyproject.toml") -Raw -Encoding UTF8
if ($pyprojectText -match '(?m)^\s*version\s*=\s*"([^"]+)"') { $projectVersion = $Matches[1] }
$zipName = "LNT-$projectVersion-win64-private-use.zip"
$zipPath = Join-Path $outDist $zipName
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }

function New-DeterministicZip {
    # Sorted entries, forward slashes, fixed 1980 timestamp: byte-stable layout.
    param([string]$SourceDir, [string]$ZipTarget)
    $sourceFull = (Resolve-Path -LiteralPath $SourceDir).Path.TrimEnd("\")
    $fileStream = [System.IO.File]::Open($ZipTarget, [System.IO.FileMode]::CreateNew)
    $archive = New-Object System.IO.Compression.ZipArchive($fileStream, [System.IO.Compression.ZipArchiveMode]::Create)
    try {
        $files = @(Get-ChildItem -LiteralPath $sourceFull -Recurse -File | Sort-Object FullName)
        $fixedTime = [DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [TimeSpan]::Zero)
        foreach ($file in $files) {
            $entryName = $file.FullName.Substring($sourceFull.Length + 1).Replace("\", "/")
            $entry = $archive.CreateEntry($entryName, [System.IO.Compression.CompressionLevel]::Optimal)
            $entry.LastWriteTime = $fixedTime
            $entryStream = $entry.Open()
            try {
                $bytes = [System.IO.File]::ReadAllBytes($file.FullName)
                $entryStream.Write($bytes, 0, $bytes.Length)
            } finally {
                $entryStream.Dispose()
            }
        }
        return $files.Count
    } finally {
        $archive.Dispose()
        $fileStream.Dispose()
    }
}

try {
    $stagedCount = @(Get-ChildItem -LiteralPath $stage -Recurse -File).Count
    $zippedCount = New-DeterministicZip -SourceDir $stage -ZipTarget $zipPath
} catch {
    Fail 4 ("zip creation failed: " + $_.Exception.Message)
}
if (-not (Test-Path -LiteralPath $zipPath)) { Fail 4 "ZIP missing after creation" }
if ($zippedCount -ne $stagedCount) {
    Fail 4 ("ZIP members {0} != staged files {1}" -f $zippedCount, $stagedCount)
}
Record "deterministic-zip" 0 ("{0}; members={1}" -f $zipName, $zippedCount)

# --- Step 7: hashes --------------------------------------------------------------
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$zipSize = (Get-Item -LiteralPath $zipPath).Length
$sidecar = Join-Path $outDist ($zipName + ".sha256")
Set-Content -LiteralPath $sidecar -Value ("{0}  {1}" -f $zipHash, $zipName) -Encoding ASCII
Set-Content -LiteralPath (Join-Path $evidenceRoot "zip-hash.txt") `
    -Value ("zip_sha256={0}`nzip_bytes={1}`nzip_name={2}" -f $zipHash, $zipSize, $zipName) -Encoding ASCII
Record "sha256-sidecar" 0 ("{0}.sha256" -f $zipName)
if ((Get-Item -LiteralPath $sidecar).Length -eq 0) { Fail 4 "empty sha256 sidecar" }

# --- Step 8: size / license manifests -------------------------------------------
$sizeManifest = foreach ($file in (Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName)) {
    [ordered]@{
        path = $file.FullName.Substring($stage.Length + 1).Replace("\", "/")
        bytes = $file.Length
    }
}
$totalBytes = ($sizeManifest | ForEach-Object bytes | Measure-Object -Sum).Sum
@{
    schema_version = 1
    bundle = $stage
    file_count = @($sizeManifest).Count
    total_bytes = $totalBytes
    size_limit_bytes = 629145600
    zip_name = $zipName
    zip_sha256 = $zipHash
    files = @($sizeManifest)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidenceRoot "size-manifest.json") -Encoding UTF8
Record "size-manifest" 0 ("files={0} total_bytes={1}" -f @($sizeManifest).Count, $totalBytes)

# License manifest: runtime packages from the locked dependency manifest plus
# vendored assets plus the license documents actually shipped in the bundle.
$repoDependencyManifest = Get-Content -LiteralPath (Join-Path $root "dependency-manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$runtimePackages = @($repoDependencyManifest | Where-Object scope -eq "runtime" | ForEach-Object {
    [ordered]@{ name = $_.name; version = $_.version; license = $_.license; source_url = $_.source_url; hash = $_.hash }
})
$fontsManifest = Get-Content -LiteralPath (Join-Path $stage "_internal\lnt\ui\static\fonts\manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$vendoredAssets = @(
    [ordered]@{ name = "uplot"; version = "1.6.32"; license = "MIT"; source_url = "https://registry.npmjs.org/uplot/-/uplot-1.6.32.tgz" },
    [ordered]@{ name = "@ibm/plex-sans"; version = $fontsManifest.packages[0].version; license = "OFL-1.1"; source_url = $fontsManifest.packages[0].source },
    [ordered]@{ name = "@ibm/plex-mono"; version = $fontsManifest.packages[1].version; license = "OFL-1.1"; source_url = $fontsManifest.packages[1].source }
)
$bundledLicenseDocs = @(
    Get-ChildItem -LiteralPath (Join-Path $stage "licenses") -File | ForEach-Object { "licenses/" + $_.Name }
    "THIRD_PARTY_NOTICES.md", "distribution-policy.md", "PRIVATE-USE.txt", "dependency-manifest.json",
    "lnt/ui/static/fonts/OFL.txt", "lnt/ui/static/fonts/manifest.json"
)
@{
    schema_version = 1
    policy = "owner-internal/no-conveyance; transfer requires separate GPL compliance decision"
    runtime_packages = $runtimePackages
    vendored_assets = $vendoredAssets
    bundled_license_documents = @($bundledLicenseDocs)
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidenceRoot "license-manifest.json") -Encoding UTF8
Copy-Item -LiteralPath (Join-Path $evidenceRoot "classification-report.json") `
    -Destination (Join-Path $evidenceRoot "dependency-manifest.json") -Force
Record "license-manifest" 0 ("runtime_packages={0} vendored_assets={1}" -f $runtimePackages.Count, $vendoredAssets.Count)

# --- Step 9: summary -------------------------------------------------------------
$summaryLines.Add(("STEP artifact-stage-exists EXIT_CODE=0 {0}" -f $stage))
$summaryLines.Add("BUILD OK EXIT_CODE=0")
$summaryLines.Add(("ZIP {0}" -f $zipPath))
$summaryLines.Add(("ZIP_SHA256 {0}" -f $zipHash))
$summaryLines | Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Encoding UTF8
Log ("BUILD OK EXIT_CODE=0 :: zip={0} sha256={1}" -f $zipPath, $zipHash)
exit 0
