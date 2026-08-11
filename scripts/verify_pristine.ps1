#requires -Version 5.1
<#
.SYNOPSIS
    Verify that a previously receipted source tree remains pristine:
    policy hash matches, both receipts (original + sessions) re-hash
    every file and detect any change. Reports only differing relative paths.
    Exit 0 = pristine; exit 1 = one or more failures.

.PARAMETER Original
    Absolute path to the original location-network-tester product directory.

.PARAMETER SessionRoot
    Absolute path to the sessions root (e.g. C:\Users\Kirill\lnt-sessions).

.PARAMETER ReceiptDir
    Absolute path to the .integrity directory containing receipts and policy.

.EXAMPLE
    .\verify_pristine.ps1 -Original C:\repo\location-network-tester -SessionRoot C:\Users\Kirill\lnt-sessions -ReceiptDir C:\repo\.integrity
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Original,
    [Parameter(Mandatory = $true)][string]$SessionRoot,
    [Parameter(Mandatory = $true)][string]$ReceiptDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Load common library
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir 'Integrity.Common.ps1')

$failures = @()
$resolvedReceiptDir = Resolve-Path -LiteralPath $ReceiptDir -ErrorAction Stop

function Add-Fail([string]$Msg) {
    $script:failures += $Msg
    Write-Host "FAIL: $Msg"
}

# ------------------------------------------------------- 1. Policy hash ----
$policyPath = Join-Path $resolvedReceiptDir 'integrity-policy.json'
$policyShaPath = Join-Path $resolvedReceiptDir 'integrity-policy.sha256'

if (-not (Test-Path -LiteralPath $policyShaPath)) {
    Add-Fail "missing policy hash file: $policyShaPath"
} else {
    $expectedHash = ((Get-Content -LiteralPath $policyShaPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    if (-not (Assert-PolicyHash -PolicyPath $policyPath -ExpectedHash $expectedHash)) {
        Add-Fail "policy hash validation failed"
    }
}

# Read exclusions for inventory (skip if policy file is missing)
$exclusions = @()
if (Test-Path -LiteralPath $policyPath) {
    $exclusions = Read-PolicyExclusions -PolicyPath $policyPath
}

# ------------------------------------------------------- 2. Verify source ----
function Test-Receipt {
    param(
        [string]$Root,
        [string]$ReceiptPath,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $ReceiptPath)) {
        Add-Fail "missing receipt: $ReceiptPath"
        return
    }
    if (-not (Test-Path -LiteralPath $Root)) {
        Add-Fail "$Label root missing: $Root"
        return
    }

    $receipt = Read-JsonReceipt -LiteralPath $ReceiptPath
    if (-not $receipt) {
        Add-Fail ("malformed receipt: {0}" -f [System.IO.Path]::GetFileName($ReceiptPath))
        return
    }
    # Validate receipt schema
    $hasValidSchema = $true
    if (-not ($receipt.PSObject.Properties.Name -contains 'version')) { $hasValidSchema = $false }
    if (-not ($receipt.PSObject.Properties.Name -contains 'algorithm')) { $hasValidSchema = $false }
    if (-not ($receipt.PSObject.Properties.Name -contains 'count') -or -not ($receipt.count -is [int])) { $hasValidSchema = $false }
    if (-not ($receipt.PSObject.Properties.Name -contains 'files') -or -not ($receipt.files -is [array])) { $hasValidSchema = $false }
    if ($hasValidSchema -and $receipt.count -ne $receipt.files.Count) { $hasValidSchema = $false }
    if (-not $hasValidSchema) {
        Add-Fail ("invalid receipt schema: {0}" -f [System.IO.Path]::GetFileName($ReceiptPath))
        return
    }
    Write-Host ("  {0}: receipt claims {1} files" -f $Label, $receipt.count)

    # Build receipt path -> entry map for O(1) lookup
    $receiptMap = @{}
    foreach ($f in $receipt.files) { $receiptMap[$f.path] = $f }

    # Live inventory
    $inventory = Get-Inventory -Root $Root -Exclusions $exclusions
    if ($inventory.problems.Count -gt 0) {
        Add-Fail "$Label inventory problems: $($inventory.problems.Count) issues"
        foreach ($p in $inventory.problems) { Write-Host "    problem: $($p.path) - $($p.problem)" }
    }
    $liveItems = $inventory.items

    # --- Check file coverage ---
    foreach ($live in $liveItems) {
        if (-not $receiptMap.ContainsKey($live.path)) {
            Add-Fail "$Label untracked file present: $($live.path)"
        }
    }
    foreach ($receiptPathKey in $receiptMap.Keys) {
        $found = $false
        foreach ($live in $liveItems) {
            if ($live.path -eq $receiptPathKey) { $found = $true; break }
        }
        if (-not $found) {
            Add-Fail "$Label receipt file missing: $receiptPathKey"
        }
    }

    # --- Check each file: size, mtime, then hash ---
    $n = 0
    foreach ($live in $liveItems) {
        $pathKey = $live.path
        if (-not $receiptMap.ContainsKey($pathKey)) { continue }
        $rec = $receiptMap[$pathKey]

        # Quick metadata check first
        if ($live.size -ne $rec.size -or $live.mtime_utc -ne $rec.mtime) {
            Add-Fail "$Label $pathKey - metadata changed"
            continue
        }

        # Full content hash
        $fullPath = Join-Path $Root ($pathKey.Replace('/', '\'))
        $h = Get-StreamingSha256 -LiteralPath $fullPath
        if ($h -ne $rec.sha256) {
            Add-Fail "$Label $pathKey - hash mismatch"
        }
        $n++
        if ($n % 2000 -eq 0) { Write-Host "    $Label re-checked $n files..." }
    }

    # --- Concurrent mutation check: re-inventory and compare ---
    Write-Host "    $Label concurrent-mutation check (re-inventory)..."
    $postInventory = Get-Inventory -Root $Root -Exclusions $exclusions
    $diffs = Compare-Inventories -PreItems $liveItems -PostItems $postInventory.items
    if ($diffs.Count -gt 0) {
        Add-Fail "$Label concurrent mutation detected"
        foreach ($d in $diffs) { Write-Host "    $d" }
    }

    Write-Host ("  OK: {0} checked ({1} files re-hashed)" -f $Label, $n)
}

$originalReceiptPath = Join-Path $resolvedReceiptDir 'receipt-original.json'
$sessionsReceiptPath = Join-Path $resolvedReceiptDir 'receipt-sessions.json'

Test-Receipt -Root $Original -ReceiptPath $originalReceiptPath -Label 'original'
Test-Receipt -Root $SessionRoot -ReceiptPath $sessionsReceiptPath -Label 'sessions'

# ------------------------------------------------------- 3. Verdict ----
Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host ("PRISTINE CHECK FAILED: {0} problem(s)" -f $failures.Count)
    $failures | Sort-Object | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host "PRISTINE CHECK PASSED - all receipts match current state"
exit 0
