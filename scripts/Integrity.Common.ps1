#requires -Version 5.1
# Integrity.Common.ps1 - shared library for immutable-source integrity receipts.
# Dot-source this file: . .\Integrity.Common.ps1
# Exports: Normalize-RelPath, Test-ReparseAttrs, Test-ExcludedPath,
#          Get-Inventory, Compare-Inventories, Get-StreamingSha256,
#          Get-PolicyExclusions, Assert-PolicyHash,
#          Write-JsonNoBom, Read-JsonReceipt

Set-StrictMode -Version Latest
$script:ItemErrorAction = 'Stop'

# ------------------------------------------------------------ path utils ----

<#
.SYNOPSIS
    Normalize a relative path segment: backslash -> forward slash, no leading slash.
    For path-based matching, use the forward-slash form everywhere.
#>
function Normalize-RelPath {
    param([string]$RelPath)
    if (-not $RelPath) { return '' }
    $p = $RelPath.Replace('\', '/').TrimStart('/')
    return $p
}

<#
.SYNOPSIS
    Check whether a file-system item is a reparse point (symlink, junction, mount point).
#>
function Test-ReparseAttrs {
    param([System.IO.FileAttributes]$Attributes)
    return [bool]($Attributes -band [System.IO.FileAttributes]::ReparsePoint)
}

# --------------------------------------------------------- exclusion rules ----

<#
.SYNOPSIS
    Test a relative path against the exclusion rule set.
    Directory rules end with / and match any path component.
    *.pyc matches file names only.
    Matching is case-insensitive on normalized forward-slash paths.
#>
function Test-ExcludedPath {
    param(
        [string]$RelPath,
        [bool]$IsDirectory,
        $Rules
    )
    $p = Normalize-RelPath $RelPath
    foreach ($rule in $Rules) {
        if ($rule.EndsWith('/')) {
            $seg = $rule.TrimEnd('/')
            if ($p -match "(^|/)$([regex]::Escape($seg))(/|$)") { return $true }
        } elseif ($rule.StartsWith('*.')) {
            if (-not $IsDirectory -and $p -like "*$rule") { return $true }
        } elseif ($p -eq $rule) {
            return $true
        }
    }
    return $false
}

<#
.SYNOPSIS
    Return the canonical 11-entry exclusion rule array.
#>
function Get-PolicyExclusions {
    return @(
        '.omo/', '.venv/', 'node_modules/', '.codegraph/',
        '.pytest_cache/', '.ruff_cache/', '.mypy_cache/',
        '__pycache__/', '*.pyc', 'build/', 'dist/'
    )
}

# -------------------------------------------------------- policy hash -------

<#
.SYNOPSIS
    Read integrity-policy.json, hash it with SHA-256, compare to expected,
    return $true on match. Writes failure messages via Write-Host.
#>
function Assert-PolicyHash {
    param(
        [string]$PolicyPath,
        [string]$ExpectedHash
    )
    if (-not (Test-Path -LiteralPath $PolicyPath)) {
        Write-Host "FAIL: policy file missing: $PolicyPath"
        return $false
    }
    $actual = (Get-FileHash -LiteralPath $PolicyPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $expected = $ExpectedHash.Trim().ToLowerInvariant()
    if ($actual -ne $expected) {
        Write-Host "FAIL: policy hash mismatch - expected $expected, got $actual"
        return $false
    }
    Write-Host "OK: policy hash $actual"
    return $true
}

<#
.SYNOPSIS
    Read integrity-policy.json and return its parsed exclusions.
#>
function Read-PolicyExclusions {
    param([string]$PolicyPath)
    $raw = [System.IO.File]::ReadAllText($PolicyPath)
    $parsed = $raw | ConvertFrom-Json
    return @($parsed.exclusions | ForEach-Object { [string]$_ })
}

# -------------------------------------------------------- streaming hash ----

<#
.SYNOPSIS
    Compute SHA-256 of a file through a read-only FileStream (no FileShare write
    so concurrent mutation is detectable). Returns lowercase hex string.
#>
function Get-StreamingSha256 {
    param([string]$LiteralPath)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $fs = $null
    try {
        # Open with Read sharing - blocks writers; fails if another process holds
        # a write lock, which is precisely the concurrent-mutation signal we want.
        $fs = [System.IO.File]::Open($LiteralPath, [System.IO.FileMode]::Open,
                                     [System.IO.FileAccess]::Read,
                                     [System.IO.FileShare]::Read)
        $buffer = New-Object byte[] (4MB)
        while (($read = $fs.Read($buffer, 0, $buffer.Length)) -gt 0) {
            [void]$sha.TransformBlock($buffer, 0, $read, $buffer, 0)
        }
        [void]$sha.TransformFinalBlock($buffer, 0, 0)
        return ([BitConverter]::ToString($sha.Hash)).Replace('-', '').ToLowerInvariant()
    } finally {
        if ($fs) { $fs.Close(); $fs.Dispose() }
        $sha.Dispose()
    }
}

# ------------------------------------------------------------ inventory -----

<#
.SYNOPSIS
    Walk a directory tree with strict no-follow reparse detection on every
    component. Returns ordered list of inventory entries:
      { path, size, mtime_utc } - sorted by path.
    Concurrency-catches by opening files with Read sharing (blocks writers).
#>
function Get-Inventory {
    param(
        [string]$Root,
        $Exclusions
    )
    $items = @()
    $problems = @()
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Root)

    while ($stack.Count -gt 0) {
        $dir = $stack.Pop()
        # --- reject reparse on directory entry itself ---
        $dirAttr = [System.IO.File]::GetAttributes($dir)
        if (Test-ReparseAttrs $dirAttr) {
            $problems += [pscustomobject]@{ path = $dir; problem = 'reparse_point_directory' }
            continue
        }
        # Relative path prefix for this directory
        $rel = ''
        if ($dir.Length -gt $Root.Length) {
            $rel = $dir.Substring($Root.Length).TrimStart('\')
        }
        # Enumerate children
        $children = $null
        try {
            $children = [System.IO.Directory]::EnumerateFileSystemEntries($dir)
        } catch {
            $problems += [pscustomobject]@{ path = $dir; problem = ('enumerate: ' + $_.Exception.Message) }
            continue
        }
        foreach ($child in $children) {
            $name = [System.IO.Path]::GetFileName($child)
            $childRel = if ($rel) { "$rel\$name" } else { $name }
            $attr = [System.IO.File]::GetAttributes($child)
            # --- reject reparse on every child ---
            if (Test-ReparseAttrs $attr) {
                $problems += [pscustomobject]@{ path = $childRel.Replace('\', '/'); problem = 'reparse_point' }
                continue
            }
            $isDir = [bool]($attr -band [System.IO.FileAttributes]::Directory)
            if (Test-ExcludedPath $childRel $isDir $Exclusions) { continue }
            if ($isDir) {
                $stack.Push($child)
            } else {
                try {
                    # Open with Read sharing - write holders cause sharing violation
                    $fs = [System.IO.File]::Open($child, 'Open', 'Read', 'Read')
                    $len = $fs.Length
                    $fs.Close(); $fs.Dispose()
                    $fi = Get-Item -LiteralPath $child -Force
                    $items += [pscustomobject]@{
                        path      = $childRel.Replace('\', '/')
                        size      = $len
                        mtime_utc = $fi.LastWriteTimeUtc.ToString('o')
                    }
                } catch {
                    $problems += [pscustomobject]@{ path = $childRel.Replace('\', '/'); problem = ('open: ' + $_.Exception.Message) }
                }
            }
        }
    }

    # Return deterministic ordering by relative path
    $sorted = $items | Sort-Object -Property path
    return [pscustomobject]@{
        items    = @($sorted)
        problems = @($problems)
    }
}

<#
.SYNOPSIS
    Compare two inventory item arrays. Returns array of human-readable
    difference strings; empty = identical.
#>
function Compare-Inventories {
    param(
        $PreItems,
        $PostItems
    )
    $diffs = @()
    $hpre = @{}; foreach ($i in $PreItems)  { $hpre[$i.path] = $i }
    $hpost = @{}; foreach ($i in $PostItems) { $hpost[$i.path] = $i }

    foreach ($k in $hpre.Keys) {
        if (-not $hpost.ContainsKey($k)) {
            $diffs += "missing: $k"
        } else {
            $a = $hpre[$k]; $b = $hpost[$k]
            if ($a.size -ne $b.size -or $a.mtime_utc -ne $b.mtime_utc) {
                $diffs += "mutated: $k  (size $($a.size)->$($b.size)  mtime $($a.mtime_utc)->$($b.mtime_utc))"
            }
        }
    }
    foreach ($k in $hpost.Keys) {
        if (-not $hpre.ContainsKey($k)) {
            $diffs += "added: $k"
        }
    }
    # PowerShell strips empty arrays from functions (produces null).
    # Use comma-prefix trick to preserve empty array on the pipeline.
    return , $diffs
}

# ----------------------------------------------------------- JSON helpers ----

<#
.SYNOPSIS
    Write JSON to a file with UTF8 encoding and NO BOM.  The object is
    serialised via ConvertTo-Json then written through .NET IO.
#>
function Write-JsonNoBom {
    param(
        [object]$InputObject,
        [string]$LiteralPath,
        [int]$Depth = 4
    )
    $json = $InputObject | ConvertTo-Json -Depth $Depth
    [System.IO.File]::WriteAllText($LiteralPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

<#
.SYNOPSIS
    Read a JSON receipt file and return the parsed PSObject.
    Uses .NET IO to handle arbitrary encodings.
#>
function Read-JsonReceipt {
    param([string]$LiteralPath)
    $raw = [System.IO.File]::ReadAllText($LiteralPath)
    try {
        return ($raw | ConvertFrom-Json)
    } catch {
        return $null
    }
}

# --------------------------------------------------------- receipt hashing ----

<#
.SYNOPSIS
    Given an inventory + root, hash every included file and write a receipt JSON.
    Returns @{ errors = <count>; receiptPath = <string> }.
#>
function New-Receipt {
    param(
        [string]$Root,
        [object[]]$InventoryItems,
        [string]$OutputPath,
        [string]$Label = ''
    )
    $rows = @()
    $errors = @()
    $n = 0
    $total = $InventoryItems.Count

    foreach ($item in $InventoryItems) {
        $n++
        if ($Label -and ($n % 2000 -eq 0)) {
            Write-Host ("  [{0}] hashed {1}/{2}" -f $Label, $n, $total)
        }
        $full = Join-Path $Root ($item.path.Replace('/', '\'))
        try {
            $h = Get-StreamingSha256 -LiteralPath $full
            $rows += [pscustomobject]@{
                path   = $item.path
                size   = $item.size
                mtime  = $item.mtime_utc
                sha256 = $h
            }
        } catch {
            $errors += [pscustomobject]@{ path = $item.path; problem = ('hash: ' + $_.Exception.Message) }
        }
    }

    $receipt = [ordered]@{
        version   = 1
        root      = $Root
        created   = (Get-Date).ToUniversalTime().ToString('o')
        algorithm = 'sha256'
        count     = $rows.Count
        files     = @($rows)
        errors    = @($errors)
    }
    Write-JsonNoBom -InputObject $receipt -LiteralPath $OutputPath -Depth 4
    Write-Host ("  receipt {0}: {1} files, {2} errors" -f $OutputPath, $rows.Count, $errors.Count)
    return @{ errors = $errors.Count; receiptPath = $OutputPath }
}

Write-Host "Integrity.Common.ps1 loaded - $(Get-Date -Format o)"
