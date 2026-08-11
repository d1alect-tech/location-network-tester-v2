#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$SessionRoot = (Join-Path $HOME 'lnt-sessions'),
    [string]$Original = '',
    [string]$EvidenceDir = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $RepoRoot
if ([string]::IsNullOrWhiteSpace($Original)) {
    $Original = Join-Path $WorkspaceRoot 'location-network-tester'
}
if ([string]::IsNullOrWhiteSpace($EvidenceDir)) {
    $EvidenceDir = Join-Path $WorkspaceRoot '.omo\start-work\evidence\task-50-lnt-complete-redesign'
}
$ReceiptDir = Join-Path $RepoRoot '.integrity'
$ReceiptPath = Join-Path $ReceiptDir 'receipt-sessions.json'
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('lnt-legacy-rehearsal-' + [guid]::NewGuid().ToString('N'))
$Catalog = Join-Path $TempRoot 'catalog.sqlite3'
$Transcript = Join-Path $EvidenceDir 'script-transcript.txt'
$MatrixPath = Join-Path $EvidenceDir 'compatibility-matrix.json'
$Tolerance = 1e-9
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Invoke-LoggedCommand {
    param([string]$Program, [string[]]$Arguments)
    Write-Output ('RUN: {0} {1}' -f $Program, ($Arguments -join ' '))
    & $Program @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw ('command failed with exit {0}: {1}' -f $code, $Program) }
}

function Invoke-PristineCheck {
    param([string]$OutputPath)
    $arguments = @(
        '-NoProfile', '-File', (Join-Path $PSScriptRoot 'verify_pristine.ps1'),
        '-Original', $Original, '-SessionRoot', $SessionRoot, '-ReceiptDir', $ReceiptDir
    )
    $output = & powershell.exe @arguments 2>&1
    $code = $LASTEXITCODE
    $output | Out-File -LiteralPath $OutputPath -Encoding ascii
    Write-Host ('Pristine receipt exit: {0}' -f $code)
    if ($code -ne 0) { throw ('pristine receipt failed with exit {0}' -f $code) }
    return $code
}

function Copy-ReadOnlyTree {
    param([string]$Source, [string]$Destination)
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $prefix = $Source.TrimEnd('\').Length + 1
    foreach ($file in Get-ChildItem -LiteralPath $Source -File -Recurse) {
        $relative = $file.FullName.Substring($prefix)
        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        $input = New-Object System.IO.FileStream(
            $file.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        try {
            $output = New-Object System.IO.FileStream(
                $target, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            try { $input.CopyTo($output) } finally { $output.Dispose() }
        } finally { $input.Dispose() }
    }
}

function Assert-RehearsalWritePath {
    param([string]$Path)
    $real = [System.IO.Path]::GetFullPath($SessionRoot).TrimEnd('\')
    $candidate = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($candidate.Equals($real, [System.StringComparison]::OrdinalIgnoreCase) -or
        $candidate.StartsWith($real + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'write_guard_real_session_root'
    }
}

function Get-RelativeDelta {
    param([double]$Old, [double]$New)
    if ($Old -eq $New) { return 0.0 }
    if ($Old -eq 0.0) { return [math]::Abs($New) }
    return [math]::Abs(($New - $Old) / $Old)
}

function Add-MetricComparison {
    param(
        [System.Collections.ArrayList]$Rows,
        [string]$Session,
        [string]$Metric,
        [double]$Old,
        [double]$New
    )
    $relative = Get-RelativeDelta -Old $Old -New $New
    [void]$Rows.Add([ordered]@{
        session = $Session; metric = $Metric; old = $Old; recomputed = $New
        absolute_delta = [math]::Abs($New - $Old); relative_delta = $relative
        tolerance = $Tolerance; passed = ($relative -le $Tolerance)
    })
}

function Compare-Metrics {
    param([string]$Name, $Old, $New, [System.Collections.ArrayList]$Rows)
    $oldNames = $Old.PSObject.Properties.Name
    $newNames = $New.PSObject.Properties.Name
    if ($oldNames -contains 'needle' -and $newNames -contains 'needle' -and $null -ne $Old.needle -and $null -ne $New.needle) {
        Add-MetricComparison $Rows $Name 'mu_pk' $Old.needle.needle_mean_v $New.needle.needle_mean_v
        Add-MetricComparison $Rows $Name 'sigma_over_mu' $Old.needle.needle_sigma_ratio $New.needle.needle_sigma_ratio
    }
    if ($oldNames -contains 'spectrum' -and $newNames -contains 'spectrum' -and $null -ne $Old.spectrum -and $null -ne $New.spectrum) {
        $count = [math]::Min($Old.spectrum.peaks.Count, $New.spectrum.peaks.Count)
        for ($index = 0; $index -lt $count; $index++) {
            Add-MetricComparison $Rows $Name ('spectrum_peak_{0}_frequency_hz' -f $index) $Old.spectrum.peaks[$index].frequency_hz $New.spectrum.peaks[$index].frequency_hz
            Add-MetricComparison $Rows $Name ('spectrum_peak_{0}_level_db' -f $index) $Old.spectrum.peaks[$index].level_db $New.spectrum.peaks[$index].level_db
        }
    }
    if ($oldNames -contains 'line_quality' -and $newNames -contains 'line_quality' -and $null -ne $Old.line_quality -and $null -ne $New.line_quality) {
        foreach ($field in @('fundamental_hz', 'fundamental_rms_v', 'total_rms_v', 'thd_ratio')) {
            Add-MetricComparison $Rows $Name ('line_quality_' + $field) $Old.line_quality.$field $New.line_quality.$field
        }
    }
}

function Invoke-AnalysisRehearsal {
    param([string]$SessionPath, [System.Collections.ArrayList]$Gaps)
    Write-Host ('RUN: uv run lnt analyze {0}' -f $SessionPath)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $output = & uv run lnt analyze $SessionPath 2>&1 } finally { $ErrorActionPreference = $previousPreference }
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) {
        [void]$Gaps.Add([ordered]@{
            session = [System.IO.Path]::GetFileName($SessionPath)
            reason_code = 'legacy_analysis_exit_nonzero'
            exit_code = $code
            detail = ($output -join [Environment]::NewLine)
        })
        return $false
    }
    return $true
}

New-Item -ItemType Directory -Path $EvidenceDir -Force | Out-Null
if (Test-Path -LiteralPath $Transcript) { Remove-Item -LiteralPath $Transcript -Force }
Start-Transcript -LiteralPath $Transcript -Force | Out-Null
$preExit = -1
$postExit = -1
$writeGuard = $null
$matrix = $null
try {
    Write-Output 'LNT legacy rehearsal started'
    $receiptHashPre = (Get-FileHash -LiteralPath $ReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $preExit = Invoke-PristineCheck (Join-Path $EvidenceDir 'receipt-pre.txt')

    New-Item -ItemType Directory -Path $TempRoot | Out-Null
    $selection = @(
        [ordered]@{ name = 'first-capture'; type = 'dual-channel'; expected_schema = 2 },
        [ordered]@{ name = 'single-ch-test'; type = 'single-channel'; expected_schema = 2 },
        [ordered]@{ name = 'cap-20260805-192920'; type = 'self-noise'; expected_schema = 2 },
        [ordered]@{ name = 'qa-line-quality'; type = 'line-quality'; expected_schema = 2 }
    )
    foreach ($item in $selection) {
        $source = Join-Path $SessionRoot $item.name
        $destination = Join-Path $TempRoot $item.name
        Copy-ReadOnlyTree -Source $source -Destination $destination
        Write-Output ('Copied real session: {0} ({1})' -f $item.name, $item.type)
    }

    $legacyCopy = Join-Path $TempRoot 'single-ch-test-schema-v1'
    Copy-ReadOnlyTree -Source (Join-Path $SessionRoot 'single-ch-test') -Destination $legacyCopy
    $legacyManifestPath = Join-Path $legacyCopy 'manifest.json'
    $legacyManifest = Get-Content -LiteralPath $legacyManifestPath -Raw | ConvertFrom-Json
    $legacyManifest.schema_version = 1
    $legacyManifest.session_id = 'rehearsal-single-ch-test-schema-v1'
    $legacyManifest.PSObject.Properties.Remove('ch1_setup')
    [System.IO.File]::WriteAllText($legacyManifestPath, ($legacyManifest | ConvertTo-Json -Depth 100), $Utf8NoBom)
    foreach ($derived in @('metrics.json', 'spectrum.csv', 'spectrum_input_referred.csv')) {
        $derivedPath = Join-Path $legacyCopy $derived
        if (Test-Path -LiteralPath $derivedPath) { Remove-Item -LiteralPath $derivedPath -Force }
    }

    $byteFlip = Join-Path $TempRoot 'corrupt-byte-flip'
    Copy-ReadOnlyTree -Source (Join-Path $SessionRoot 'single-ch-test') -Destination $byteFlip
    $byteManifestPath = Join-Path $byteFlip 'manifest.json'
    $byteManifest = Get-Content -LiteralPath $byteManifestPath -Raw | ConvertFrom-Json
    $byteManifest.session_id = 'rehearsal-corrupt-byte-flip'
    [System.IO.File]::WriteAllText($byteManifestPath, ($byteManifest | ConvertTo-Json -Depth 100), $Utf8NoBom)
    foreach ($derived in @('metrics.json', 'spectrum.csv', 'spectrum_input_referred.csv')) {
        $derivedPath = Join-Path $byteFlip $derived
        if (Test-Path -LiteralPath $derivedPath) { Remove-Item -LiteralPath $derivedPath -Force }
    }
    $bytePath = Join-Path $byteFlip 'ch1.npy'
    $stream = New-Object System.IO.FileStream($bytePath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
    try {
        $stream.Seek(-1, [System.IO.SeekOrigin]::End) | Out-Null
        $oldByte = $stream.ReadByte()
        $stream.Seek(-1, [System.IO.SeekOrigin]::End) | Out-Null
        $stream.WriteByte($oldByte -bxor 1)
    } finally { $stream.Dispose() }

    $truncated = Join-Path $TempRoot 'corrupt-truncated-manifest'
    Copy-ReadOnlyTree -Source (Join-Path $SessionRoot 'qa-line-quality') -Destination $truncated
    [System.IO.File]::WriteAllText((Join-Path $truncated 'manifest.json'), '{"schema_version":', [System.Text.Encoding]::ASCII)

    try {
        Assert-RehearsalWritePath -Path $SessionRoot
        Invoke-LoggedCommand 'uv' @('run', 'lnt', 'context', 'set', 'blocked', '--expected-revision', '0')
        throw 'write guard unexpectedly allowed real root'
    } catch {
        if ($_.Exception.Message -ne 'write_guard_real_session_root') { throw }
        $writeGuard = [ordered]@{
            blocked = $true; requested_root = $SessionRoot; command = 'lnt context set'
            guard = 'scripts/rehearse-legacy.ps1 Assert-RehearsalWritePath'
            reason_code = 'write_guard_real_session_root'
        }
        Write-Output 'Write guard blocked real session root before CLI invocation'
    }

    Invoke-LoggedCommand 'uv' @('run', 'lnt', 'catalog', 'reindex', '--root', $TempRoot, '--database', $Catalog, '--json')
    $statusJson = & uv run lnt catalog status --database $Catalog --json
    if ($LASTEXITCODE -ne 0) { throw 'catalog status failed' }
    $status = $statusJson | ConvertFrom-Json
    Write-Output ('Catalog status: {0}' -f $statusJson)

    $rowsCode = "import sqlite3,json; c=sqlite3.connect(r'$Catalog'); print(json.dumps([dict(zip(('storage_path','health','manifest_schema','session_type','channels'),r)) for r in c.execute('select storage_path,health,manifest_schema,session_type,channels from catalog_sessions order by storage_path')]))"
    $catalogRowsJson = & uv run python -c $rowsCode
    if ($LASTEXITCODE -ne 0) { throw 'catalog row query failed' }
    $catalogRows = @($catalogRowsJson | ConvertFrom-Json)

    $metricRows = New-Object System.Collections.ArrayList
    $analysisGaps = New-Object System.Collections.ArrayList
    foreach ($item in $selection) {
        $copy = Join-Path $TempRoot $item.name
        $metricsPath = Join-Path $copy 'metrics.json'
        $old = if (Test-Path -LiteralPath $metricsPath) { Get-Content -LiteralPath $metricsPath -Raw | ConvertFrom-Json } else { $null }
        $analyzed = Invoke-AnalysisRehearsal -SessionPath $copy -Gaps $analysisGaps
        if ($analyzed) {
            $new = Get-Content -LiteralPath $metricsPath -Raw | ConvertFrom-Json
            if ($null -ne $old) { Compare-Metrics -Name $item.name -Old $old -New $new -Rows $metricRows }
        }
    }
    if (-not (Invoke-AnalysisRehearsal -SessionPath $legacyCopy -Gaps $analysisGaps)) {
        throw 'schema-v1 rehearsal copy must remain analyzable'
    }
    $legacyMetrics = Get-Content -LiteralPath (Join-Path $legacyCopy 'metrics.json') -Raw | ConvertFrom-Json

    $v2ScriptPath = Join-Path $TempRoot 'run-v2-recipe.py'
    $v2Code = @'
import json
import sys
from pathlib import Path
from lnt.analysis_store import AnalysisRecipe
from lnt.analysis_v2 import AnalysisOrchestrator, DefaultAnalysisEngine

recipe = AnalysisRecipe.from_mapping(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
result = AnalysisOrchestrator(engine=DefaultAnalysisEngine()).run(
    Path(sys.argv[1]), recipe, project_legacy=False
)
print(json.dumps({
    "artifact_key": result.artifact_key,
    "artifact_dir": str(result.artifact_dir),
    "failures": [
        {"branch": item.branch, "error_type": item.error_type, "message": item.message}
        for item in result.failures
    ],
}, sort_keys=True))
'@
    [System.IO.File]::WriteAllText($v2ScriptPath, $v2Code, $Utf8NoBom)
    $v2Recipe = [ordered]@{
        schema_version = 1; mode = 'legacy-rehearsal-v2'; channels = @('ch1')
        band_grid = [ordered]@{ low_hz = 10.0; high_hz = 400.0; grid_hz = 1.0 }
        welch = [ordered]@{ window = 'hann_periodic'; segment_samples = 64; overlap_fraction = 0.5; detrend = 'constant'; scaling = 'density'; average = 'mean' }
        spectrogram = [ordered]@{ enabled = $true; segment_samples = 64; overlap_fraction = 0.5 }
        events = [ordered]@{ enabled = $true; threshold_sigma = 5.0 }
        bands = [ordered]@{ edges_hz = @(10.0, 100.0, 400.0) }
        correction = [ordered]@{ method = 'none' }
        uncertainty = [ordered]@{ enabled = $false; confidence_level = 0.95; bootstrap_samples = 0 }
    }
    $v2RecipePath = Join-Path $TempRoot 'v2-recipe.json'
    [System.IO.File]::WriteAllText($v2RecipePath, ($v2Recipe | ConvertTo-Json -Compress -Depth 20), $Utf8NoBom)
    $v2Json = & uv run python $v2ScriptPath (Join-Path $TempRoot 'qa-line-quality') $v2RecipePath
    if ($LASTEXITCODE -ne 0) { throw 'v2 recipe rehearsal failed' }
    $v2Result = $v2Json | ConvertFrom-Json
    Write-Output ('V2 recipe result: {0}' -f $v2Json)

    $contextFixture = Join-Path $legacyCopy 'context.legacy.json'
    [System.IO.File]::WriteAllText($contextFixture, '{"notes":"rehearsal copy only"}', $Utf8NoBom)
    Invoke-LoggedCommand 'uv' @('run', 'lnt', 'catalog', 'import-context', $legacyCopy, '--dry-run', '--json')

    $failedMetrics = @($metricRows | Where-Object { -not $_.passed })
    $corruptRows = @($catalogRows | Where-Object { [System.IO.Path]::GetFileName($_.storage_path).StartsWith('corrupt-') })
    $analysesCreated = Test-Path -LiteralPath (Join-Path (Join-Path $TempRoot 'qa-line-quality') 'analyses')
    $matrix = [ordered]@{
        schema_version = 1
        tolerance = [ordered]@{ relative = $Tolerance; absolute = 0.0; policy = 'exact expected; rel <= 1e-9 accepted' }
        receipt = [ordered]@{ expected_file_count = 92; pre_exit = $preExit; receipt_sha256_pre = $receiptHashPre }
        sessions = $selection
        schema_v1 = [ordered]@{
            real_receipt_candidate_found = $false
            reason_code = 'no_real_schema_v1_in_receipt'
            rehearsed_copy = 'single-ch-test-schema-v1'
            input_reference_status = $legacyMetrics.ch1_input_reference.status
            input_reference_reason_code = $legacyMetrics.ch1_input_reference.reason_code
            correction_model = $legacyMetrics.ch1_input_reference.model
        }
        catalog = [ordered]@{ status = $status; rows = $catalogRows; corrupt_rows = $corruptRows }
        corrupt_artifact_gap = [ordered]@{
            reason_code = 'catalog_artifact_content_not_validated'
            detail = 'byte-flipped NPY remains visible with health ok; truncated manifest is corrupt_manifest'
        }
        metrics = @($metricRows)
        metric_failures = $failedMetrics
        analysis_gaps = @($analysisGaps)
        old_default_command = 'uv run lnt analyze <copy>'
        new_v2_projection = [ordered]@{
            created = $analysesCreated; path_scope = 'temp copy analyses/'
            recipe_mode = 'legacy-rehearsal-v2'; session = 'qa-line-quality'
            artifact_key = $v2Result.artifact_key; failures = $v2Result.failures
        }
        sidecars = [ordered]@{ context_legacy_created_under_temp = $true; import_dry_run = $true }
        write_guard = $writeGuard
        temp_root_deleted = $false
    }
    if ($failedMetrics.Count -gt 0) { throw ('metric tolerance failures: {0}' -f $failedMetrics.Count) }
} finally {
    if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
    $postExit = Invoke-PristineCheck (Join-Path $EvidenceDir 'receipt-post.txt')
    $receiptHashPost = (Get-FileHash -LiteralPath $ReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($null -ne $matrix) {
        $matrix.receipt.post_exit = $postExit
        $matrix.receipt.receipt_sha256_post = $receiptHashPost
        $matrix.receipt.hashes_match = ($matrix.receipt.receipt_sha256_pre -eq $receiptHashPost)
        $matrix.temp_root_deleted = $true
        [System.IO.File]::WriteAllText($MatrixPath, ($matrix | ConvertTo-Json -Depth 100), $Utf8NoBom)
    }
    Stop-Transcript | Out-Null
}

Write-Output ('Compatibility matrix: {0}' -f $MatrixPath)
Write-Output 'LNT legacy rehearsal passed'
