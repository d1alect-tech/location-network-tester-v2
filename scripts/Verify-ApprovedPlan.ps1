#requires -Version 5.1
<#
.SYNOPSIS
    Verify that the committed approved-plan copy in .integrity matches its
    pinned SHA-256 hash.  This verifies the COMMITTED COPY, not the live
    plan file (which legitimately changes as checkboxes get marked).

    Exit 0 = hash matches; exit 1 = mismatch or missing file.

.PARAMETER IntegrityDir
    Absolute path to the .integrity directory.  Defaults to
    <script-root>\..\.integrity.

.EXAMPLE
    .\Verify-ApprovedPlan.ps1
.EXAMPLE
    .\Verify-ApprovedPlan.ps1 -IntegrityDir C:\repo\v2\.integrity
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][string]$IntegrityDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $IntegrityDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $v2Root = Split-Path -Parent $scriptDir
    $IntegrityDir = Join-Path $v2Root '.integrity'
}

$planCopy   = Join-Path $IntegrityDir 'approved-work-plan.md'
$sha256File = Join-Path $IntegrityDir 'approved-work-plan.sha256'

$failures = @()

# --- Check files exist ---
if (-not (Test-Path -LiteralPath $planCopy)) {
    $failures += "missing approved-plan copy: $planCopy"
    Write-Host "FAIL: $($failures[-1])"
} else {
    Write-Host "  found approved-plan copy: $planCopy"
}

if (-not (Test-Path -LiteralPath $sha256File)) {
    $failures += "missing SHA-256 file: $sha256File"
    Write-Host "FAIL: $($failures[-1])"
} else {
    Write-Host "  found SHA-256 file: $sha256File"
}

if ($failures.Count -gt 0) {
    Write-Host "`nAPPROVED PLAN VERIFY FAILED: $($failures.Count) problem(s)"
    exit 1
}

# --- Load expected hash ---
$raw = (Get-Content -LiteralPath $sha256File -Raw).Trim()
$expectedHash = ($raw -split '\s+')[0].ToLowerInvariant()
Write-Host "  expected hash: $expectedHash"

# --- Compute actual hash of committed copy ---
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'Integrity.Common.ps1')

$actualHash = Get-StreamingSha256 -LiteralPath $planCopy
Write-Host "  actual hash:   $actualHash"

if ($actualHash -ne $expectedHash) {
    Write-Host "FAIL: approved-plan copy hash mismatch"
    Write-Host "  The committed plan copy has been modified since it was pinned."
    Write-Host "  To re-pin (only on explicit user replacement of the plan):"
    Write-Host "    (Get-FileHash -LiteralPath '$planCopy' -Algorithm SHA256).Hash.ToLowerInvariant()"
    Write-Host "    # update approved-work-plan.sha256 with the new hash"
    exit 1
}

Write-Host "`nAPPROVED PLAN VERIFY PASSED - committed copy matches pinned hash"
exit 0
