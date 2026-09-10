# Build script for the public GPL-3.0-only one-folder LNT Windows distribution.

# Usage:
#   powershell -File packaging/build.ps1 -Clean -Evidence <dir>
# Extracted Corresponding Source archive:
#   powershell -File project/packaging/build.ps1 -Clean -Evidence evidence -SourceArchive
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
    [switch]$SourceArchive,
    [string]$StageFrom,
    [string]$HantekSource
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
$hantekCommit = "e65d52b0f2536e56eaadbb555e5d7b756409c36e"
$hantekFirmwareSha256 = "7773d886de861e2a95b159f103135b06391a6433adf0727d3d1e23aec9e65cfd"
$hantekRuntimeHashes = [ordered]@{
    "PyHT6022/Firmware/__init__.py" = "eb3065de8608ee4a48f1d3a79f97d04bee91eb7af4ac0867b82fa73580731916"
    "PyHT6022/LibUsbScope.py" = "2c257ea5097cadbf581119fa74128e8da00f32f05c3f9fb8abb7c3b20f235fc9"
}
$hantekPatched = Join-Path $root "build\hantek-6022be"
$hantekPatch = Join-Path $PSScriptRoot "hantek-6022be.patch"
$sourceNotice = Join-Path $PSScriptRoot "SOURCE.txt"

if (-not $SourceArchive) {
    Push-Location $root
    try {
        $gitHead = git rev-parse HEAD 2>$null
        $gitHeadExit = $LASTEXITCODE
        $gitWorktreeState = @(git status --porcelain=v1 --untracked-files=all 2>$null)
        $gitWorktreeExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
if (-not $SourceArchive) {
    New-Item -ItemType Directory -Force -Path $outDist | Out-Null
}

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

function Get-NormalizedTextSha256 {
    param([string]$Path)
    $text = [System.IO.File]::ReadAllText($Path).Replace("`r`n", "`n").Replace("`r", "`n")
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha256.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha256.Dispose()
    }
}

function Get-SourceArchiveProjectFiles {
    param([string]$ProjectRoot)
    $files = New-Object System.Collections.Generic.List[System.IO.FileInfo]
    $directories = New-Object System.Collections.Generic.Queue[System.IO.DirectoryInfo]
    $prunedDirectories = @(
        ".venv",
        "build",
        "dist",
        "frontend/node_modules",
        "frontend/test-results",
        "frontend/playwright-report",
        "frontend/dist"
    )
    $projectItem = Get-Item -LiteralPath $ProjectRoot -Force
    if (($projectItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "project/ is a reparse point"
    }
    $directories.Enqueue($projectItem)
    while ($directories.Count -gt 0) {
        $directory = $directories.Dequeue()
        foreach ($item in (Get-ChildItem -LiteralPath $directory.FullName -Force)) {
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw ("reparse/symlink-like project entry rejected: " + $item.FullName)
            }
            if ($item.PSIsContainer) {
                $relativeDirectory = $item.FullName.Substring($ProjectRoot.Length + 1).Replace("\", "/")
                if (($item.Name -ceq "__pycache__") -or ($prunedDirectories -ccontains $relativeDirectory)) {
                    continue
                }
                $directories.Enqueue($item)
            } else {
                $files.Add($item)
            }
        }
    }
    return @($files)
}

function Assert-SourceArchiveIntegrity {
    if ($SkipBuild) { throw "-SourceArchive cannot be combined with -SkipBuild" }
    if (Test-Path -LiteralPath (Join-Path $root ".git")) {
        throw "-SourceArchive is forbidden when project/.git exists"
    }

    $gitProbeExit = 127
    $gitProbe = @()
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $gitProbe = @(& git -C $root rev-parse --is-inside-work-tree 2>$null)
        $gitProbeExit = $LASTEXITCODE
    } catch {
        $gitProbeExit = 127
    } finally {
        $ErrorActionPreference = $previousEap
    }
    if (($gitProbeExit -eq 0) -and (($gitProbe -join "").Trim() -eq "true")) {
        throw "-SourceArchive is forbidden inside a Git worktree"
    }

    $archiveRoot = Split-Path -Parent $root
    $manifestPath = Join-Path $archiveRoot "SOURCE-MANIFEST.json"
    $sumsPath = Join-Path $archiveRoot "SHA256SUMS"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "source archive requires SOURCE-MANIFEST.json beside project/"
    }
    if (-not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) {
        throw "source archive requires SHA256SUMS beside project/"
    }

    try {
        $manifestText = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
        $manifest = $manifestText | ConvertFrom-Json
    } catch {
        throw ("invalid SOURCE-MANIFEST.json: " + $_.Exception.Message)
    }
    $schemaTokens = @([regex]::Matches($manifestText, '"schema_version"\s*:\s*1(?=\s*[,}])'))
    if (($null -eq $manifest) -or -not ($manifest.PSObject.Properties.Name -ccontains "schema_version") -or
        ($manifest.schema_version -ne 1) -or ($schemaTokens.Count -ne 1)) {
        throw "SOURCE-MANIFEST.json schema_version must be 1"
    }
    if (-not ($manifest.PSObject.Properties.Name -ccontains "project") -or ($null -eq $manifest.project)) {
        throw "SOURCE-MANIFEST.json project must be an object"
    }
    $project = $manifest.project
    foreach ($field in @("path", "version", "commit")) {
        if (-not ($project.PSObject.Properties.Name -ccontains $field)) {
            throw "SOURCE-MANIFEST.json project.$field is required"
        }
    }
    if (($project.path -isnot [string]) -or ($project.path -cne "project/")) {
        throw "SOURCE-MANIFEST.json project.path must be exactly project/"
    }
    $manifestProjectPath = (Resolve-Path -LiteralPath (Join-Path $archiveRoot "project")).Path
    if (-not [string]::Equals($manifestProjectPath, $root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "SOURCE-MANIFEST.json project.path does not identify this project root"
    }
    if (($project.version -isnot [string]) -or [string]::IsNullOrWhiteSpace($project.version)) {
        throw "SOURCE-MANIFEST.json project.version must be a non-empty string"
    }
    if (($project.commit -isnot [string]) -or ($project.commit -cnotmatch '^[0-9a-f]{40}$')) {
        throw "SOURCE-MANIFEST.json project.commit must be 40 lowercase hexadecimal characters"
    }

    $pyprojectPath = Join-Path $root "pyproject.toml"
    if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
        throw "project/pyproject.toml is missing"
    }
    $pyprojectText = Get-Content -LiteralPath $pyprojectPath -Raw -Encoding UTF8
    if ($pyprojectText -notmatch '(?ms)^\[project\]\s*(.*?)(?=^\[|\z)') {
        throw "project/pyproject.toml has no [project] table"
    }
    $projectTable = $Matches[1]
    if (($projectTable -notmatch '(?m)^\s*version\s*=\s*"([^"]+)"\s*$') -or
        ($Matches[1] -cne $project.version)) {
        throw "SOURCE-MANIFEST.json project.version does not match project/pyproject.toml"
    }

    $listedPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $listedPathsIgnoreCase = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $projectListed = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $sumLines = @(Get-Content -LiteralPath $sumsPath -Encoding ASCII)
    if ($sumLines.Count -eq 0) { throw "SHA256SUMS is empty" }
    foreach ($line in $sumLines) {
        if ($line -cnotmatch '^([0-9a-f]{64})  (.+)$') {
            throw ("malformed SHA256SUMS row: " + $line)
        }
        $expectedHash = $Matches[1]
        $relativePath = $Matches[2]
        if ($relativePath.StartsWith("/") -or $relativePath.Contains("\") -or
            $relativePath.Contains(":") -or [System.IO.Path]::IsPathRooted($relativePath)) {
            throw ("unsafe SHA256SUMS path: " + $relativePath)
        }
        $parts = @($relativePath.Split('/'))
        if (($parts.Count -eq 0) -or @($parts | Where-Object { $_ -in @("", ".", "..") }).Count -gt 0) {
            throw ("unsafe SHA256SUMS path: " + $relativePath)
        }
        if (-not $listedPathsIgnoreCase.Add($relativePath)) {
            throw ("duplicate or case-colliding SHA256SUMS path: " + $relativePath)
        }
        [void]$listedPaths.Add($relativePath)
        $fullPath = Join-Path $archiveRoot ($relativePath.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            throw ("SHA256SUMS file is missing: " + $relativePath)
        }
        $item = Get-Item -LiteralPath $fullPath -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw ("reparse/symlink-like archive entry rejected: " + $relativePath)
        }
        $actualHash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -cne $expectedHash) {
            throw ("SHA-256 mismatch: " + $relativePath)
        }
        if ($relativePath.StartsWith("project/", [System.StringComparison]::Ordinal)) {
            [void]$projectListed.Add($relativePath)
        }
    }

    foreach ($requiredPath in @(
        "SOURCE-MANIFEST.json",
        "project/packaging/build.ps1",
        "project/packaging/hantek-6022be.patch",
        "project/pyproject.toml",
        "project/release-source-inputs.json"
    )) {
        if (-not $listedPaths.Contains($requiredPath)) {
            throw ("SHA256SUMS omits required file: " + $requiredPath)
        }
    }
    foreach ($file in (Get-SourceArchiveProjectFiles -ProjectRoot $root)) {
        $relativePath = "project/" + $file.FullName.Substring($root.Length + 1).Replace("\", "/")
        if (-not $projectListed.Contains($relativePath)) {
            throw ("unlisted project file: " + $relativePath)
        }
    }
    return $project.commit
}

Log "=== LNT public GPL-3.0-only packaging build ==="
Log ("params: Clean={0} SkipBuild={1} SourceArchive={2} Evidence={3}" -f `
    [bool]$Clean, [bool]$SkipBuild, [bool]$SourceArchive, $evidenceRoot)

# --- Step 1: provenance header -------------------------------------------------
if ($SourceArchive) {
    try {
        $gitHead = Assert-SourceArchiveIntegrity
    } catch {
        Record "source-archive-integrity" 10 $_.Exception.Message
        Fail 10 ("source archive integrity failed: " + $_.Exception.Message)
    }
    Record "source-archive-integrity" 0 ("manifest-commit=" + $gitHead)
    Record "git-head" 0 ("manifest-commit=" + $gitHead)
    Record "git-worktree-clean" 0 "not-enforced-for-SourceArchive"
} else {
    Record "git-head" $gitHeadExit ([string]$gitHead)
    if ($SkipBuild) {
        Record "git-worktree-clean" 0 ("not-enforced-for-SkipBuild; tracked-and-untracked-changes={0}" -f $gitWorktreeState.Count)
    } else {
        Record "git-worktree-clean" $(if (($gitWorktreeExit -eq 0) -and ($gitWorktreeState.Count -eq 0)) { 0 } else { 10 }) `
            ("tracked-and-untracked-changes={0}" -f $gitWorktreeState.Count)
    }
}

if (-not $SkipBuild) {
    if (-not $SourceArchive) {
        if ($gitHeadExit -ne 0) { Fail 10 "cannot resolve committed HEAD" }
        if ($gitWorktreeExit -ne 0) { Fail 10 "cannot inspect tracked and untracked worktree state" }
        if ($gitWorktreeState.Count -ne 0) {
            Fail 10 "release build requires a clean tracked and untracked worktree"
        }
    }
    if (-not (Test-Path -LiteralPath $sourceNotice)) {
        Fail 10 "public build requires packaging/SOURCE.txt"
    }
    if ($SourceArchive) {
        New-Item -ItemType Directory -Force -Path $outDist | Out-Null
    }
    # --- Step 2: -Clean really cleans (stale_state defense) --------------------
    if ($Clean) {
        $stalePaths = @(
            $pyiRoot,
            (Join-Path $outDist "LNT-*-win64.zip"),
            (Join-Path $outDist "LNT-*-win64.zip.sha256"),
            (Join-Path $outDist "LNT-*-win64.zip.sbom.cdx.json")
        )
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
        Record "clean" 0 ("removed-and-verified-absent: build/pyinstaller, dist/LNT-*-win64.zip{,.sha256,.sbom.cdx.json}")
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

    # --- Step 4: isolated pinned Hantek source ---------------------------------
    if (Test-Path -LiteralPath $hantekPatched) {
        Remove-Item -LiteralPath $hantekPatched -Recurse -Force
    }
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $cloneSource = "https://github.com/Ho-Ro/Hantek6022API.git"
    if ($HantekSource) {
        $cloneSource = [System.IO.Path]::GetFullPath($HantekSource)
        if (-not (Test-Path -LiteralPath $cloneSource)) {
            Fail 10 "prefetched Hantek source/cache does not exist: $cloneSource"
        }
        $prefetchedCommit = [string](& git -C $cloneSource rev-parse ($hantekCommit + "^{commit}") 2>$null)
        $prefetchedCommit = $prefetchedCommit.Trim()
        if (($LASTEXITCODE -ne 0) -or ($prefetchedCommit -ne $hantekCommit)) {
            Fail 10 "prefetched Hantek source/cache does not contain commit $hantekCommit"
        }
    }
    $cloneOutput = & git clone --no-checkout -- $cloneSource $hantekPatched 2>&1
    $cloneExit = $LASTEXITCODE
    $cloneOutput | ForEach-Object { Log ("hantek-clone| " + $_) }
    if ($cloneExit -ne 0) { Fail 10 "failed to clone isolated Hantek source" }
    $checkoutOutput = & git -C $hantekPatched checkout --detach $hantekCommit 2>&1
    $checkoutExit = $LASTEXITCODE
    $checkoutOutput | ForEach-Object { Log ("hantek-checkout| " + $_) }
    if ($checkoutExit -ne 0) { Fail 10 "failed to check out pinned Hantek commit" }
    $hantekHead = (& git -C $hantekPatched rev-parse HEAD).Trim()
    $revParseExit = $LASTEXITCODE
    if (($revParseExit -ne 0) -or ($hantekHead -ne $hantekCommit)) {
        Fail 10 "isolated Hantek checkout is not pinned commit $hantekCommit"
    }
    Record "hantek-pinned-source" 0 $hantekHead

    $patchCheckOutput = & git -C $hantekPatched apply --check $hantekPatch 2>&1
    $patchCheckExit = $LASTEXITCODE
    $patchCheckOutput | ForEach-Object { Log ("hantek-patch-check| " + $_) }
    if ($patchCheckExit -ne 0) { Fail 10 "Hantek 6022BE patch does not apply cleanly" }
    $patchOutput = & git -C $hantekPatched apply $hantekPatch 2>&1
    $patchExit = $LASTEXITCODE
    $patchOutput | ForEach-Object { Log ("hantek-patch| " + $_) }
    if ($patchExit -ne 0) { Fail 10 "failed to apply Hantek 6022BE patch" }
    $ErrorActionPreference = $previousEap

    $firmwareDir = Join-Path $hantekPatched "PyHT6022\Firmware\HEX"
    $firmwarePath = Join-Path $firmwareDir "dso6022be-firmware.hex"
    $firmwareBytes = [System.IO.File]::ReadAllBytes($firmwarePath)
    $firmwareText = [System.Text.Encoding]::ASCII.GetString($firmwareBytes).Replace("`r`n", "`n")
    [System.IO.File]::WriteAllBytes($firmwarePath, [System.Text.Encoding]::ASCII.GetBytes($firmwareText))
    Get-ChildItem -LiteralPath $firmwareDir -File |
        Where-Object { $_.Name -ne "dso6022be-firmware.hex" } |
        Remove-Item -Force
    $firmwareFiles = @(Get-ChildItem -LiteralPath $firmwareDir -File)
    $firmwareHash = (Get-FileHash -LiteralPath $firmwarePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if (($firmwareFiles.Count -ne 1) -or ($firmwareHash -ne $hantekFirmwareSha256)) {
        Fail 10 "isolated Hantek tree does not contain exactly the approved 6022BE firmware"
    }
    $runtimeAttestation = @()
    foreach ($relativePath in $hantekRuntimeHashes.Keys) {
        $runtimePath = Join-Path $hantekPatched ($relativePath.Replace("/", "\"))
        if (-not (Test-Path -LiteralPath $runtimePath)) {
            Fail 10 "patched Hantek runtime file missing: $relativePath"
        }
        $runtimeHash = Get-NormalizedTextSha256 -Path $runtimePath
        if ($runtimeHash -ne $hantekRuntimeHashes[$relativePath]) {
            Fail 10 "patched Hantek runtime content is not approved: $relativePath"
        }
        $runtimeAttestation += ($relativePath + "=" + $runtimeHash)
    }
    if (Test-Path -LiteralPath (Join-Path $hantekPatched "PyHT6022\upload_firmware.py")) {
        Fail 10 "generic Hantek firmware uploader survived patch"
    }
    Record "hantek-6022be-profile" 0 `
        ((@("firmware_sha256=" + $firmwareHash) + $runtimeAttestation) -join "; ")

    # --- Step 4.1: deterministic staging via PyInstaller ------------------------
    if (Test-Path -LiteralPath $stageDefault) {
        Remove-Item -LiteralPath $stageDefault -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $pyiDist | Out-Null
    Push-Location $root
    try {
        $previousPythonPath = $env:PYTHONPATH
        $previousHantekSource = $env:LNT_HANTEK_SOURCE
        $env:PYTHONPATH = $hantekPatched
        $env:LNT_HANTEK_SOURCE = $hantekPatched
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
            $env:PYTHONPATH = $previousPythonPath
            $env:LNT_HANTEK_SOURCE = $previousHantekSource
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
# PyInstaller places all datas under _internal; source instructions, license
# texts and provenance manifest belong beside the executable. Move (not copy)
# so every file exists exactly once.
if (-not $SkipBuild) {
    $internalDir = Join-Path $stage "_internal"
    foreach ($doc in @("LICENSE", "THIRD_PARTY_NOTICES.md", "distribution-policy.md", "SOURCE.txt", "dependency-manifest.json")) {
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
Record "stage-documents" 0 "LICENSE/notices/policy/licenses/manifest moved beside LNT.exe"

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
$zipName = "LNT-$projectVersion-win64.zip"
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
    "LICENSE", "THIRD_PARTY_NOTICES.md", "distribution-policy.md", "SOURCE.txt", "dependency-manifest.json",
    "lnt/ui/static/fonts/OFL.txt", "lnt/ui/static/fonts/manifest.json"
)
@{
    schema_version = 1
    policy = "public GPL-3.0-only binary distribution with corresponding-source instructions"
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
