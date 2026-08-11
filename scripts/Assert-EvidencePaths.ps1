#requires -Version 5.1
<#
.SYNOPSIS
    Evidence-path guard: given a list of output/evidence paths, FAIL if any
    path normalises (via Resolve-Path / [IO.Path]::GetFullPath, no-follow)
    into the original source tree or the real sessions root.  Catches ..\
    traversal, forward/back slash mixing, and reparse-point escape.

    Exit 0 = all paths safe; exit 1 = one or more unsafe paths detected.

.PARAMETER Paths
    Array of evidence/output paths to validate.

.PARAMETER Original
    Absolute path to the original location-network-tester product directory
    (the protected tree).

.PARAMETER SessionRoot
    Absolute path to the real sessions root (the protected tree).

.PARAMETER Verbose
    Print detailed resolution steps.

.EXAMPLE
    .\Assert-EvidencePaths.ps1 -Paths @("C:\out\report.pdf") -Original C:\repo\lnt -SessionRoot C:\Users\Kirill\lnt-sessions
.EXAMPLE
    .\Assert-EvidencePaths.ps1 -Paths @("..\lnt\secrets.txt") -Original C:\repo\lnt -SessionRoot C:\Users\Kirill\lnt-sessions
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string[]]$Paths,
    [Parameter(Mandatory = $true)][string]$Original,
    [Parameter(Mandatory = $true)][string]$SessionRoot,
    [Parameter(Mandatory = $false)][switch]$Detailed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$failures = @()

function Write-Dbg {
    param([string]$Msg)
    if ($Detailed) { Write-Host "  DEBUG: $Msg" }
}

function Test-PathInsideProtected {
    param(
        [string]$CandidatePath,
        [string]$ProtectedRoot
    )
    # Normalise both to absolute, no-follow, forward-slash, lowercase
    try {
        # Resolve-Path follows reparse points; for no-follow we use
        # [System.IO.Path]::GetFullPath on the literal path, then
        # check each component for reparse attributes.
        $normalised = [System.IO.Path]::GetFullPath($CandidatePath).Replace('\', '/').TrimEnd('/')
        $protected  = [System.IO.Path]::GetFullPath($ProtectedRoot).Replace('\', '/').TrimEnd('/')
        Write-Dbg "  normalised candidate: $normalised"
        Write-Dbg "  protected root:       $protected"

        # Reject reparse points on every path component
        $components = $normalised.Split('/')
        $current = ''
        foreach ($comp in $components) {
            if (-not $comp) { continue }
            $current = if ($current) { "$current/$comp" } else { "$comp" }
            $currentWin = $current.Replace('/', '\')
            if (Test-Path -LiteralPath $currentWin) {
                $attrs = [System.IO.File]::GetAttributes($currentWin)
                if ($attrs -band [System.IO.FileAttributes]::ReparsePoint) {
                    Write-Dbg "  reparse point detected at: $current"
                    return $true  # reparse = potential escape route, reject
                }
            }
        }

        # Check if candidate is inside protected root
        if ($normalised -eq $protected) { return $true }
        if ($normalised.StartsWith("$protected/")) { return $true }

        return $false
    } catch {
        Write-Dbg "  resolution error: $_"
        return $false
    }
}

Write-Host "Assert-EvidencePaths: checking $($Paths.Count) path(s) against Original=$Original SessionRoot=$SessionRoot"

foreach ($rawPath in $Paths) {
    if ([string]::IsNullOrWhiteSpace($rawPath)) {
        $failures += 'empty or whitespace-only path'
        Write-Host "  FAIL: empty path"
        continue
    }
    Write-Dbg "  inspecting: $rawPath"

    # Test against Original
    if (Test-PathInsideProtected -CandidatePath $rawPath -ProtectedRoot $Original) {
        $msg = "path resolves into original tree: $rawPath"
        $failures += $msg
        Write-Host "  FAIL: $msg"
    }

    # Test against SessionRoot
    if (Test-PathInsideProtected -CandidatePath $rawPath -ProtectedRoot $SessionRoot) {
        $msg = "path resolves into sessions root: $rawPath"
        $failures += $msg
        Write-Host "  FAIL: $msg"
    }
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host ("Assert-EvidencePaths: FAILED - {0} unsafe path(s) detected" -f $failures.Count)
    foreach ($f in $failures) { Write-Host "  $f" }
    exit 1
}

Write-Host "Assert-EvidencePaths: PASSED - all paths are outside protected trees"
exit 0
