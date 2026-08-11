[CmdletBinding()]
param([Parameter(Mandatory = $true)][string]$Evidence)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
$dist = Join-Path $PSScriptRoot "dist"
$build = Join-Path $PSScriptRoot "build"
$bundle = Join-Path $dist "hantek-diagnostic"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null

Push-Location $root
try {
    uv run pyinstaller --noconfirm --clean --distpath $dist --workpath $build (Join-Path $PSScriptRoot "hantek-diagnostic.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
    & (Join-Path $PSScriptRoot "Test-DependencyClosure.ps1") -Bundle $bundle -Evidence $evidenceRoot -Allowlist (Join-Path $PSScriptRoot "system32-allowlist.v1.json")
    $closureExit = $LASTEXITCODE

    $oldPath = $env:PATH; $oldPythonPath = $env:PYTHONPATH; $oldPythonHome = $env:PYTHONHOME
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
        $env:LNT_SPIKE_OUTPUT = Join-Path $evidenceRoot "probe-report.json"
        & (Join-Path $bundle "hantek-diagnostic.exe") 2>&1 | Tee-Object -FilePath (Join-Path $evidenceRoot "frozen-stdout.txt")
        $probeExit = $LASTEXITCODE
    } finally {
        $env:PATH = $oldPath
        if ($null -eq $oldPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $oldPythonPath }
        if ($null -eq $oldPythonHome) { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue } else { $env:PYTHONHOME = $oldPythonHome }
        Remove-Item Env:LNT_SPIKE_OUTPUT -ErrorAction SilentlyContinue
    }

    $probe = Get-Content -LiteralPath (Join-Path $evidenceRoot "probe-report.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $inventory = Get-Content -LiteralPath (Join-Path $evidenceRoot "dependency-inventory.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $fakeOk = $probe.fakes.'device-present'.device_opened -and
        (-not $probe.fakes.absent.device_opened) -and
        $probe.fakes.bootloader.device_opened -and (-not $probe.fakes.bootloader.firmware_present) -and
        $probe.fakes.'firmware-missing'.device_opened -and (-not $probe.fakes.'firmware-missing'.firmware_present) -and
        (-not $probe.fakes.'driver-missing'.driver_installed)
    $dependencyGo = ($closureExit -eq 0) -and ($probeExit -eq 0) -and $probe.frozen -and $fakeOk -and ($inventory.errors.Count -eq 0)
    $hardwareAvailable = [bool]$probe.real_device.device_opened
    $verdict = [ordered]@{
        schema_version = 1; verdict = if ($dependencyGo) { "go" } else { "no_go" }
        dependency_closure_go = $dependencyGo; f3_hardware_approval_available = $hardwareAvailable
        real_device = $probe.real_device; fake_mappings_correct = $fakeOk
        sanitized_process = [ordered]@{ pythonpath_removed = $true; pythonhome_removed = $true; path = "%SystemRoot%\System32;%SystemRoot%"; label = "sanitized-reference-host/process evidence; not a clean or sterile VM" }
        blockers = if ($dependencyGo) { @() } else { @("Todos 47-49/F3 blocked: frozen dependency, architecture, firmware, or fake closure failed") }
        f3_note = if ($hardwareAvailable) { "real non-invasive diagnosis recorded" } else { "real hardware unavailable; cannot count as F3 approval" }
    }
    $verdict | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceRoot "verdict.json") -Encoding UTF8
    Write-Output "go|no_go: $($verdict.verdict)"
    if (-not $dependencyGo) { exit 2 }
} finally {
    Pop-Location
}
exit 0
