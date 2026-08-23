# Bundle classification/validation library for the private LNT distribution.

# Dot-sourced by packaging/build.ps1 and packaging/test-failure-modes.ps1.
# Every file in a candidate bundle MUST be classified into an allowed class;
# anything unclassified, forbidden, missing-but-required, externally untrusted
# or over the size cap makes Test-BundleValidation return $false BEFORE any ZIP
# is written. PowerShell 5.1 compatible (pwsh is not installed on this host).

Set-StrictMode -Version Latest

$script:SIZE_LIMIT_BYTES = 600 * 1024 * 1024 # <=600 MiB unzipped
$script:FIRMWARE_EXPECTED_COUNT = 7
$script:MACHINE_X64 = 0x8664
$script:CORE_LICENSES = @(
    "OFL-1.1.txt", "GPL-3.0.txt", "LGPL-2.1.txt", "MIT.txt",
    "BSD-2-Clause.txt", "BSD-3-Clause.txt", "Apache-2.0.txt", "README.md"
)
$script:METADATA_PACKAGES = @("lnt", "numpy", "scipy", "fastapi", "uvicorn")
$script:REQUIRED_FONTS_EXTRA = @("OFL.txt", "manifest.json")

function Get-PeMachine {
    # Copied from packaging/spike/Test-DependencyClosure.ps1 (Todo 13 evidence tooling).
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $reader = New-Object System.IO.BinaryReader($stream)
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        $stream.Position = $peOffset + 4
        return $reader.ReadUInt16()
    } finally {
        $stream.Dispose()
    }
}

function Get-ForbiddenHit {
    # Hard-fail patterns: Node/dev/test/cache/Plotly artifacts must never ship.
    param([string]$RelPath)
    $lower = $RelPath.ToLowerInvariant()
    $patterns = @(
        "node_modules", "/.vite/", ".vite/", "plotly", "vitest", "playwright",
        "jest", "__pycache__", "_pytest", "pytest_cache", "ruff_cache",
        "package.json", "package-lock.json", "node.exe", "npm.cmd", "npx.cmd",
        "tsconfig", "biome.json", "vite.config", "vitest.config",
        "/setuptools/", "/frontend/", "/bench/", "/test-results/"
    )
    foreach ($pattern in $patterns) {
        if ($lower.Contains($pattern)) { return $pattern }
    }
    # Extension-boundary checks: .pyd must NOT trip the .py rule.
    if ($lower.EndsWith(".py") -or $lower.EndsWith(".pyc") -or $lower.EndsWith(".map")) {
        return "python-source-or-dev-map"
    }
    if ($lower.StartsWith("tests/") -or $lower.StartsWith("test/")) { return "test-tree" }
    return $null
}

function Get-BundleClass {
    # Classification table; $null means UNCLASSIFIED (hard failure upstream).
    # PyInstaller onedir layout: everything except LNT.exe lives under _internal/.
    param([string]$RelPath)
    $lower = $RelPath.ToLowerInvariant().Replace("\", "/")
    if ($lower -eq "lnt.exe" -or $lower -eq "lnt-cli.exe") { return "app-bootloader" }
    if ($lower -match "^_internal/python3\d+\.dll$") { return "python-runtime" }
    if ($lower -match "^_internal/(base_library\.zip|[^/]+\.pyz)$") { return "python-runtime" }
    if ($lower.EndsWith(".pyd")) { return "python-extension" }
    if ($lower -eq "_internal/usb1/libusb-1.0.dll") { return "libusb-driver" }
    if ($lower.EndsWith(".hex") -or $lower.EndsWith(".ihex")) { return "firmware" }
    if ($lower.StartsWith("_internal/") -and $lower.EndsWith(".dll")) { return "bundled-binary" }
    if ($lower.StartsWith("_internal/lnt/ui/static/")) { return "ui-static-assets" }
    if ($lower.StartsWith("_internal/dateutil/zoneinfo/")) { return "dependency-data" }
    if ($lower.Contains(".dist-info/")) { return "package-metadata" }
    if ($lower.StartsWith("licenses/")) { return "license-document" }
    if ($lower -in @("third_party_notices.md", "private-use-policy.md", "private-use.txt")) {
        return "license-document"
    }
    if ($lower -eq "dependency-manifest.json") { return "provenance-manifest" }
    return $null
}

function Test-RequiredEntries {
    param(
        [string]$Bundle,
        [System.Collections.Generic.HashSet[string]]$RelativePaths,
        [hashtable]$FirmwareByExtension,
        [ref]$Errors
    )
    function Require([string]$rel) {
        if (-not $RelativePaths.Contains($rel.Replace("\", "/").ToLowerInvariant())) {
            $Errors.Value.Add("отсутствует обязательный элемент: $rel")
        }
    }
    Require "LNT.exe"
    Require "LNT-cli.exe"
    Require "_internal/usb1/libusb-1.0.dll"
    Require "_internal/lnt/ui/static/v2/index.html"
    Require "_internal/lnt/ui/static/vendor/uPlot.esm.js"
    Require "_internal/lnt/ui/static/vendor/uPlot.min.css"
    Require "THIRD_PARTY_NOTICES.md"
    Require "PRIVATE-USE.txt"
    Require "private-use-policy.md"
    Require "dependency-manifest.json"

    if (-not ($RelativePaths | Where-Object { $_ -match "^_internal/python3\d+\.dll$" })) {
        $Errors.Value.Add("отсутствует обязательный элемент: _internal/python3xx.dll")
    }

    $firmwareCount = $FirmwareByExtension["firmware"].Count
    if ($firmwareCount -ne $script:FIRMWARE_EXPECTED_COUNT) {
        $Errors.Value.Add(
            "неполный класс firmware: ожидалось $($script:FIRMWARE_EXPECTED_COUNT), найдено $firmwareCount"
        )
    }

    # Fonts: каждый файл, заявленный в комплектном fonts/manifest.json, плюс OFL.
    $fontsManifestRel = "_internal/lnt/ui/static/fonts/manifest.json"
    if ($RelativePaths.Contains($fontsManifestRel)) {
        $fontsManifest = Get-Content -LiteralPath (Join-Path $Bundle "_internal\lnt\ui\static\fonts\manifest.json") `
            -Raw -Encoding UTF8 | ConvertFrom-Json
        $declared = @($fontsManifest.files.PSObject.Properties.Name)
        foreach ($font in $declared + $script:REQUIRED_FONTS_EXTRA) {
            Require ("_internal/lnt/ui/static/fonts/" + $font)
        }
    } else {
        $Errors.Value.Add("отсутствует обязательный элемент: $fontsManifestRel")
    }

    foreach ($license in $script:CORE_LICENSES) {
        Require ("licenses/" + $license)
    }

    foreach ($package in $script:METADATA_PACKAGES) {
        $found = $false
        foreach ($path in $RelativePaths) {
            if ($path -match ("(^|/)" + [regex]::Escape($package) + "-[\d.]+\.dist-info/metadata$")) {
                $found = $true
                break
            }
        }
        if (-not $found) {
            $Errors.Value.Add("отсутствуют метаданные пакета для importlib.metadata: $package")
        }
    }
}

function Test-ExternalClosure {
    # Validates Todo 13's trusted-external policy: every OS-resolved import must be
    # canonical System32, x64 PE, Microsoft Authenticode-valid AND allowlisted.
    param(
        [string]$Bundle,
        [string]$Allowlist,
        [string]$PeReportPath,
        [ref]$Errors
    )
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
    Push-Location $repoRoot
    try {
        uv run python (Join-Path $PSScriptRoot "spike\pe_imports.py") $Bundle $PeReportPath
    } finally {
        Pop-Location
    }
    $peExit = $LASTEXITCODE
    if ($peExit -ne 0) {
        $Errors.Value.Add("неразрешимые импорты вне бандла и System32; см. $PeReportPath")
    }
    $raw = Get-Content -LiteralPath $PeReportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $policy = Get-Content -LiteralPath $Allowlist -Raw -Encoding UTF8 | ConvertFrom-Json
    $allowed = @{}
    foreach ($name in $policy.allowed_names) { $allowed[$name.ToLowerInvariant()] = $true }
    $system32 = (Resolve-Path -LiteralPath (Join-Path $env:SystemRoot "System32")).Path.TrimEnd("\")

    $records = @()
    $osImports = @($raw.imports | Where-Object location -eq "system32" | Sort-Object resolved_path -Unique)
    foreach ($import in $osImports) {
        $name = [System.IO.Path]::GetFileName([string]$import.resolved_path)
        $lower = $name.ToLowerInvariant()
        $path = [System.IO.Path]::GetFullPath([string]$import.resolved_path)
        if (-not $allowed.ContainsKey($lower)) { $Errors.Value.Add("внешняя DLL не в allowlist: $name") }
        if (-not $path.StartsWith($system32 + '\', [StringComparison]::OrdinalIgnoreCase)) {
            $Errors.Value.Add("DLL вне canonical System32: $path")
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        $subject = if ($null -eq $signature.SignerCertificate) { "" } else { $signature.SignerCertificate.Subject }
        if (($signature.Status -ne "Valid") -or ($subject -notmatch "Microsoft")) {
            $Errors.Value.Add("нет валидной Microsoft Authenticode подписи: $path")
        }
        if ((Get-PeMachine $path) -ne $script:MACHINE_X64) { $Errors.Value.Add("DLL не x64: $path") }
        $item = Get-Item -LiteralPath $path
        $records += [ordered]@{
            name = $name
            requested_name = $import.dependency
            requested_by = @($raw.imports | Where-Object { $_.location -eq "system32" -and $_.resolved_path -eq $import.resolved_path } | ForEach-Object source | Sort-Object -Unique)
            path = $path
            version = $item.VersionInfo.FileVersion
            sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
            signer = $subject
            signature_status = [string]$signature.Status
            machine = "0x8664"
        }
    }
    return ,$records
}

function Test-BundleValidation {
    <#
    .SYNOPSIS
    Полная проверка staged-бандла LNT перед упаковкой в ZIP.
    .OUTPUTS
    $true при успехе; иначе $false. Отчёт всегда пишется в $ReportPath.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Bundle,
        [Parameter(Mandatory = $true)][string]$Allowlist,
        [Parameter(Mandatory = $true)][string]$ReportPath,
        [string]$PeReportPath
    )
    $errors = New-Object System.Collections.Generic.List[string]
    $warnings = New-Object System.Collections.Generic.List[string]
    if (-not $PeReportPath) { $PeReportPath = "$ReportPath.pe-imports.raw.json" }

    if (-not (Test-Path -LiteralPath (Join-Path $Bundle "LNT.exe"))) {
        $errors.Add("бандл неполон: нет LNT.exe (стейджинг не собран?)")
    }
    if (-not (Test-Path -LiteralPath $Bundle)) {
        $errors.Add("каталог бандла не существует: $Bundle")
        Write-ClassificationReport -ReportPath $ReportPath -Bundle $Bundle `
            -Classes @{} -Required @() -External @() -Errors $errors -Warnings $warnings
        return $false
    }

    $classes = @{}
    $firmwareByExtension = @{ firmware = New-Object System.Collections.Generic.List[string] }
    $allFiles = @(Get-ChildItem -LiteralPath $Bundle -Recurse -File)
    $totalBytes = 0L
    $relativePaths = New-Object System.Collections.Generic.HashSet[string]

    foreach ($file in $allFiles) {
        $rel = $file.FullName.Substring($Bundle.Length + 1).Replace("\", "/")
        $null = $relativePaths.Add($rel.ToLowerInvariant())
        $totalBytes += $file.Length
        $forbidden = Get-ForbiddenHit $rel
        if ($null -ne $forbidden) {
            $errors.Add("запрещённый артефакт '$forbidden' в бандле: $rel")
            continue
        }
        $class = Get-BundleClass $rel
        if ($null -eq $class) {
            $errors.Add("неклассифицированный файл: $rel")
            continue
        }
        if ($class -eq "firmware") { $firmwareByExtension["firmware"].Add($rel) }
        if (-not $classes.ContainsKey($class)) { $classes[$class] = New-Object System.Collections.Generic.List[object] }
        $classes[$class].Add(@{
            path = $rel
            bytes = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        })
    }

    if ($totalBytes -gt $script:SIZE_LIMIT_BYTES) {
        $errors.Add(
            ("размер бандла {0:N0} байт превышает лимит {1:N0} байт (600 MiB)" -f $totalBytes, $script:SIZE_LIMIT_BYTES)
        )
    }

    $requiredRef = [ref]$errors
    Test-RequiredEntries -Bundle $Bundle -RelativePaths $relativePaths `
        -FirmwareByExtension $firmwareByExtension -Errors $requiredRef

    $external = @()
    if (Test-Path -LiteralPath (Join-Path $Bundle "LNT.exe")) {
        $external = Test-ExternalClosure -Bundle $Bundle -Allowlist $Allowlist `
            -PeReportPath $PeReportPath -Errors $requiredRef
    }

    Write-ClassificationReport -ReportPath $ReportPath -Bundle $Bundle -Classes $classes `
        -Required @() -External $external -Errors $errors -Warnings $warnings -TotalBytes $totalBytes

    foreach ($message in $errors) {
        [Console]::Error.WriteLine("ОШИБКА ВАЛИДАЦИИ: $message")
    }
    return ($errors.Count -eq 0)
}

function Write-ClassificationReport {
    param(
        [string]$ReportPath,
        [string]$Bundle,
        [hashtable]$Classes,
        [array]$Required,
        [array]$External,
        [System.Collections.Generic.List[string]]$Errors,
        [System.Collections.Generic.List[string]]$Warnings,
        [long]$TotalBytes = 0
    )
    $reportDirectory = Split-Path -Parent $ReportPath
    if ($reportDirectory) { New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null }
    $payload = [ordered]@{
        schema_version = 1
        bundle = (Resolve-Path -LiteralPath $Bundle -ErrorAction SilentlyContinue).Path
        policy = "private-use one-folder distribution; every file classified; external OS DLLs allowlisted (Todo 13)"
        file_count = ($Classes.Values | ForEach-Object Count | Measure-Object -Sum).Sum
        total_bytes = $TotalBytes
        size_limit_bytes = $script:SIZE_LIMIT_BYTES
        classes = $Classes
        required = $Required
        external_system32 = $External
        errors = @($Errors)
        warnings = @($Warnings)
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReportPath -Encoding UTF8
}
