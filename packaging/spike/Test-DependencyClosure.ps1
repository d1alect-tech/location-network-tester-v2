[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [Parameter(Mandatory = $true)][string]$Evidence,
    [Parameter(Mandatory = $true)][string]$Allowlist
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PeMachine([string]$Path) {
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

$bundleRoot = (Resolve-Path -LiteralPath $Bundle).Path.TrimEnd('\')
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$rawPath = Join-Path $evidenceRoot "pe-imports.raw.json"
uv run python (Join-Path $PSScriptRoot "pe_imports.py") $bundleRoot $rawPath
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("ОШИБКА ЗАВИСИМОСТИ: неразрешимый импорт DLL; см. pe-imports.raw.json")
    exit 2
}

$raw = Get-Content -LiteralPath $rawPath -Raw -Encoding UTF8 | ConvertFrom-Json
$policy = Get-Content -LiteralPath $Allowlist -Raw -Encoding UTF8 | ConvertFrom-Json
$allowed = @{}
foreach ($name in $policy.allowed_names) { $allowed[$name.ToLowerInvariant()] = $true }
$system32 = (Resolve-Path -LiteralPath (Join-Path $env:SystemRoot "System32")).Path.TrimEnd('\')
$osImports = @($raw.imports | Where-Object location -eq "system32" | Sort-Object resolved_path -Unique)
$osFiles = @()
$errors = New-Object System.Collections.Generic.List[string]
foreach ($import in $osImports) {
    $name = [System.IO.Path]::GetFileName([string]$import.resolved_path)
    $lower = $name.ToLowerInvariant()
    $path = [System.IO.Path]::GetFullPath([string]$import.resolved_path)
    if (-not $allowed.ContainsKey($lower)) { $errors.Add("внешняя DLL не в allowlist: $name") }
    if (-not $path.StartsWith($system32 + '\', [StringComparison]::OrdinalIgnoreCase)) {
        $errors.Add("DLL вне canonical System32: $path")
    }
    if ((Get-PeMachine $path) -ne 0x8664) { $errors.Add("DLL не x64: $path") }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    $subject = if ($null -eq $signature.SignerCertificate) { "" } else { $signature.SignerCertificate.Subject }
    if (($signature.Status -ne "Valid") -or ($subject -notmatch "Microsoft")) {
        $errors.Add("нет валидной Microsoft Authenticode подписи: $path")
    }
    $item = Get-Item -LiteralPath $path
    $osFiles += [ordered]@{
        name = $name; requested_name = $import.dependency; path = $path; version = $item.VersionInfo.FileVersion
        sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        signer = $subject; signature_status = [string]$signature.Status; machine = "0x8664"
    }
}

$bundleFiles = @()
Get-ChildItem -LiteralPath $bundleRoot -Recurse -File | Where-Object {
    $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".pyd", ".hex", ".ihex")
} | ForEach-Object {
    $bundleFiles += [ordered]@{
        path = $_.FullName.Substring($bundleRoot.Length + 1)
        class = if ($_.Extension -in @(".hex", ".ihex")) { "firmware" } else { "binary" }
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$firmwareCount = @($bundleFiles | Where-Object class -eq "firmware").Count
if ($firmwareCount -ne 7) { $errors.Add("неполный класс firmware: ожидалось 7, найдено $firmwareCount") }
$inventory = [ordered]@{
    schema_version = 1; bundle = $bundleRoot; binary_count = $raw.binary_count
    bundle_local_files = $bundleFiles; allowlisted_system32 = $osFiles
    imports = $raw.imports; errors = @($errors)
}
$inventory | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot "dependency-inventory.json") -Encoding UTF8
if ($errors.Count -gt 0) {
    foreach ($message in $errors) { [Console]::Error.WriteLine("ОШИБКА ЗАВИСИМОСТИ: $message") }
    exit 2
}
Write-Output "dependency closure: bundle=$($bundleFiles.Count), system32=$($osFiles.Count), firmware=$firmwareCount"
exit 0
