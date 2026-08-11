#requires -Version 5.1
<#
.SYNOPSIS
    Assert that the original source + sessions root remain pristine against
    their integrity receipts.  Intended to run before/after every milestone.
    Exit 0 = pristine; exit 1 = one or more failures.

.PARAMETER Original
    Absolute path to the original location-network-tester product directory.

.PARAMETER SessionRoot
    Absolute path to the sessions root (e.g. C:\Users\Kirill\lnt-sessions).

.PARAMETER ReceiptDir
    Absolute path to the .integrity directory containing receipts and policy.
    Defaults to <v2-root>\.integrity where v2-root is derived from this script's
    own location: <v2-root>\scripts\Assert-Pristine.ps1 -> <v2-root>\.integrity.

.EXAMPLE
    .\Assert-Pristine.ps1 -Original C:\repo\location-network-tester -SessionRoot C:\Users\Kirill\lnt-sessions
.EXAMPLE
    .\Assert-Pristine.ps1 -Original C:\repo\location-network-tester -SessionRoot C:\Users\Kirill\lnt-sessions -ReceiptDir C:\repo\location-network-tester-v2\.integrity
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Original,
    [Parameter(Mandatory = $true)][string]$SessionRoot,
    [Parameter(Mandatory = $false)][string]$ReceiptDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Derive ReceiptDir from script location if not provided
if (-not $ReceiptDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $v2Root = Split-Path -Parent $scriptDir
    $ReceiptDir = Join-Path $v2Root '.integrity'
}

Write-Host "Assert-Pristine: Original=$Original SessionRoot=$SessionRoot ReceiptDir=$ReceiptDir"

# Delegate to verify_pristine.ps1
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$verifyScript = Join-Path $scriptDir 'verify_pristine.ps1'

if (-not (Test-Path -LiteralPath $verifyScript)) {
    Write-Host "FAIL: verify_pristine.ps1 not found at $verifyScript"
    exit 1
}

$output = & $verifyScript -Original $Original -SessionRoot $SessionRoot -ReceiptDir $ReceiptDir 2>&1
$exitCode = $LASTEXITCODE

# Print output regardless
$output | ForEach-Object { Write-Host "$_" }

if ($exitCode -ne 0) {
    Write-Host "Assert-Pristine: FAILED (exit $exitCode)"
    exit 1
}

Write-Host "Assert-Pristine: PASSED"
exit 0
