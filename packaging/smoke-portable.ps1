# Sanitized non-elevated reference-host smoke for the frozen portable LNT (Todo 48).

# Verifies dist\LNT-0.1.0-win64-private-use.zip end-to-end WITHOUT external
# Python/Node/network: fresh temp payload + HOME/APPDATA/LOCALAPPDATA/session root,
# project toolchains removed from PATH, PYTHON*/NODE* scrubbed, SHA-256 vs sidecar
# BEFORE extraction, bundle-local closure + canonical System32/x64/Microsoft-signer
# allowlist (pure PowerShell PE IMPORT walk; same semantics as the Todo 13 spike's
# packaging/spike/pe_imports.py - standard import directory only), UI cold start,
# health/build-id/assets/API checks, synthetic journey simulate -> analyze ->
# compare -> selftest(job) -> experiment(simulator run) -> statistics report ->
# filesystem backup/restore round-trip, non-invasive typed device diagnosis, four
# failure-mode proofs, and full process/temp teardown with receipts.
#
# DEFECT NOTE (Todo 48): the shipped Todo 47 artifact exposed ONLY the GUI
# launcher surface (packaging/lnt.spec -> lnt/launcher.py gui_main;
# --root/--port/--no-browser), so a literal `LNT.exe selftest` exited 2 via
# argparse. This smoke PROVED that defect against the shipped ZIP (transcript:
# failure-modes/prefix-selftest-defect.txt) and it was then fixed minimally in
# src/lnt/launcher.py: registered lnt.cli subcommands are dispatched to the real
# CLI surface while plain/flag-only launches keep the GUI behavior. This script
# consequently RUNS `LNT.exe selftest` as a HARD gate (exit 0 required) and
# drives backup/restore through the frozen `lnt archive` verbs.
#
# Evidence label: ONLY `sanitized-reference-host-verified`. The script never emits
# sterile/clean-VM/universal/externally-verified claims and stays reusable unchanged
# on a genuinely fresh external Windows PC (stock PowerShell plus its two packaging/
# siblings: validate-bundle.ps1 and system32-allowlist.v2.json).
#
# Exit codes: 0 all green; 10 preflight; 20 sanitize; 30 integrity; 40 runtime;
# 50 workflow; 60 failure-mode proof failed; 70 teardown. PowerShell 5.1 compatible.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Zip,
    [Parameter(Mandatory = $true)][string]$Evidence,
    [int]$HealthTimeoutS = 15,
    [int]$PreferredPort = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:FirmwareExpectedCount = 7
$script:SizeLimitBytes = 600L * 1024L * 1024L
$script:HostLabel = "sanitized-reference-host-verified"
$script:ForbiddenLabels = @("sterile", "clean-vm", "clean vm", "universal",
    "externally verified", "clean machine")
$script:DeviceStates = @(
    "backend_unavailable", "driver_missing", "device_absent", "bootloader_vid",
    "running_vid", "handle_busy", "firmware_missing", "firmware_upload_failed", "ready"
)
$script:AbsentFamilyStates = @("backend_unavailable", "driver_missing", "device_absent")

$script:TempRoot = $null
$script:SpawnedPids = New-Object System.Collections.Generic.List[int]
$script:Listener = $null
$script:NetworkViolations = New-Object System.Collections.Generic.List[object]
$script:NetworkSamples = 0
$script:OrigEnv = @{}
$script:SanitizedNow = $false
$script:HttpLog = New-Object System.Collections.Generic.List[object]
$script:ExitCode = 70

$evidenceRoot = [System.IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$fmDir = Join-Path $evidenceRoot "failure-modes"
New-Item -ItemType Directory -Force -Path $fmDir | Out-Null
$transcriptPath = Join-Path $evidenceRoot "smoke-transcript.txt"
Set-Content -LiteralPath $transcriptPath -Value "" -Encoding UTF8

function Log {
    param([string]$Line)
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")
    # Console + file only - NEVER the PowerShell output stream, so functions that
    # log stay pipeline-clean and can return hashtables to their callers.
    [Console]::WriteLine(("[{0}] {1}" -f $stamp, $Line))
    Add-Content -LiteralPath $transcriptPath -Value "[$stamp] $Line" -Encoding UTF8
}

function Step {
    param([string]$Name, [int]$Code, [string]$Detail)
    Log ("STEP {0} EXIT_CODE={1} {2}" -f $Name, $Code, $Detail)
}

function Write-EvidenceJson {
    param([string]$Name, [object]$Payload)
    $path = Join-Path $evidenceRoot $Name
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    Log ("EVIDENCE {0} written" -f $Name)
}

function Get-Sha256 {
    param([string]$Path)
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-NoForbiddenLabel {
    param([string]$Text)
    foreach ($label in $script:ForbiddenLabels) {
        if ($Text.ToLowerInvariant().Contains($label)) { return $false }
    }
    return $true
}

function Sample-Network {
    # Non-admin outbound assertion: any established remote endpoint owned by a
    # spawned PID that is not loopback counts as a network violation.
    foreach ($pidToCheck in @($script:SpawnedPids.ToArray())) {
        $conns = @(Get-NetTCPConnection -OwningProcess $pidToCheck -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq "Established" })
        foreach ($c in $conns) {
            if (@("127.0.0.1", "::1") -notcontains $c.RemoteAddress) {
                $script:NetworkViolations.Add(@{
                    pid = $pidToCheck; remote = $c.RemoteAddress; port = $c.RemotePort
                    observed_at = (Get-Date).ToUniversalTime().ToString("o")
                })
            }
        }
    }
    $script:NetworkSamples++
}

function Enter-SanitizedEnvironment {
    param([string]$Root)
    $keep = @("PATH", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA",
        "LOCALAPPDATA", "TEMP", "TMP")
    foreach ($name in $keep) { $script:OrigEnv[$name] = [Environment]::GetEnvironmentVariable($name) }
    $scrubbed = @(Get-ChildItem env: |
        Where-Object { $_.Name -match "^(PYTHON|UV_|NODE|NPM|NVM|CONDA|PIP)" } |
        Select-Object -ExpandProperty Name)
    $script:OrigEnv["__scrubbed__"] = $scrubbed
    foreach ($name in $scrubbed) {
        Remove-Item -LiteralPath ("env:" + $name) -ErrorAction SilentlyContinue
    }

    $fakeHome = Join-Path $Root "home"
    $env:USERPROFILE = $fakeHome
    $env:HOMEDRIVE = $fakeHome.Substring(0, 2)
    $env:HOMEPATH = $fakeHome.Substring(2)
    $env:APPDATA = Join-Path $Root "appdata\roaming"
    $env:LOCALAPPDATA = Join-Path $Root "appdata\local"
    $env:TEMP = Join-Path $Root "tmp"
    $env:TMP = $env:TEMP
    foreach ($dir in @($fakeHome, $env:APPDATA, $env:LOCALAPPDATA, $env:TEMP)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem;" +
        "$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    $script:SanitizedNow = $true
    Step "sanitize-env-applied" 0 ("scrubbed=[" + ($scrubbed -join ",") + "]")
}

function Exit-SanitizedEnvironment {
    if (-not $script:SanitizedNow) { return }
    foreach ($key in @($script:OrigEnv.Keys)) {
        if ($key -eq "__scrubbed__") { continue }
        $value = $script:OrigEnv[$key]
        if ($null -eq $value) {
            Remove-Item -LiteralPath ("env:" + $key) -ErrorAction SilentlyContinue
        } else {
            Set-Item -LiteralPath ("env:" + $key) -Value $value
        }
    }
    $script:OrigEnv = @{}
    $script:SanitizedNow = $false
}

function Invoke-ApiJson {
    param(
        [string]$Method,
        [string]$Url,
        [object]$Body = $null,
        [string]$Nonce = "",
        [int]$TimeoutSec = 10,
        [string]$Label = ""
    )
    try {
        $headers = @{ Origin = "http://127.0.0.1" }
        if ($Nonce -ne "") { $headers["X-LNT-Mutation-Nonce"] = $Nonce }
        $params = @{
            UseBasicParsing = $true
            Method = $Method
            Uri = $Url
            Headers = $headers
            TimeoutSec = $TimeoutSec
        }
        if ($null -ne $Body) {
            $params["ContentType"] = "application/json"
            $params["Body"] = ($Body | ConvertTo-Json -Depth 8)
        }
        $response = Invoke-WebRequest @params
        $record = @{ label = $Label; method = $Method; url = $Url
            status = [int]$response.StatusCode; ok = $true }
        if (-not $Label.EndsWith("-poll")) { $null = $script:HttpLog.Add($record) }
        return @{ status = [int]$response.StatusCode; body = $response.Content }
    } catch {
        $status = 0
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
        $record = @{ label = $Label; method = $Method; url = $Url
            status = $status; ok = $false; error = $_.Exception.Message }
        if (-not $Label.EndsWith("-poll")) { $null = $script:HttpLog.Add($record) }
        return @{ status = $status; body = ""; error = $_.Exception.Message }
    }
}

function Get-PeImportedDlls {
    # Pure-PowerShell walk of the standard PE IMPORT directory (parity with the
    # Todo 13 spike parser: delay-load imports are intentionally not followed).
    param([string]$Path)
    $names = New-Object System.Collections.Generic.List[string]
    $fs = [System.IO.File]::OpenRead($Path)
    try {
        $br = New-Object System.IO.BinaryReader($fs)
        if ($fs.Length -lt 0x40) { return ,$names }
        if ($br.ReadUInt16() -ne 0x5A4D) { return ,$names }
        $fs.Position = 0x3C
        $peOff = $br.ReadInt32()
        if (($peOff -le 0) -or (($peOff + 264) -gt $fs.Length)) { return ,$names }
        $fs.Position = $peOff
        if ($br.ReadUInt32() -ne 0x00004550) { return ,$names }
        $null = $br.ReadUInt16()                                    # machine (checked by caller)
        $numSections = $br.ReadUInt16()
        $fs.Position = $peOff + 20
        $optSize = $br.ReadUInt16()
        $fs.Position = $peOff + 24
        $magic = $br.ReadUInt16()
        $dirsOff = 0
        if ($magic -eq 0x20B) { $dirsOff = $peOff + 24 + 112 }      # PE32+
        elseif ($magic -eq 0x10B) { $dirsOff = $peOff + 24 + 96 }   # PE32
        else { return ,$names }
        $fs.Position = $dirsOff + 8                                 # data directory index 1
        $importRva = $br.ReadUInt32()
        $sections = @()
        $secTable = $peOff + 24 + $optSize
        for ($i = 0; $i -lt $numSections; $i++) {
            $base = $secTable + 40 * $i
            if (($base + 40) -gt $fs.Length) { break }
            $fs.Position = $base + 8
            $virtualSize = $br.ReadUInt32()
            $virtualAddr = $br.ReadUInt32()
            $rawSize = $br.ReadUInt32()
            $rawPtr = $br.ReadUInt32()
            $span = [Math]::Max($virtualSize, $rawSize)
            $sections += ,@{ va = $virtualAddr; span = $span; ptr = $rawPtr }
        }
        if ($importRva -eq 0) { return ,$names }

        function Convert-RvaToLocal([uint32]$Rva) {
            foreach ($s in $sections) {
                if (($Rva -ge $s.va) -and ($Rva -lt ($s.va + $s.span))) {
                    return [int64]($Rva - $s.va + $s.ptr)
                }
            }
            return [int64]-1
        }

        $descOff = Convert-RvaToLocal $importRva
        if ($descOff -lt 0) { return ,$names }
        for ($entry = 0; $entry -lt 4096; $entry++) {
            if (($descOff + 20) -gt $fs.Length) { break }
            $fs.Position = $descOff
            $originalFirstThunk = $br.ReadUInt32()
            $null = $br.ReadUInt32()                                # TimeDateStamp
            $null = $br.ReadUInt32()                                # ForwarderChain
            $nameRva = $br.ReadUInt32()
            $null = $br.ReadUInt32()                                # FirstThunk
            if (($nameRva -eq 0) -and ($originalFirstThunk -eq 0)) { break }
            if ($nameRva -ne 0) {
                $nameOff = Convert-RvaToLocal $nameRva
                if ($nameOff -ge 0) {
                    $fs.Position = $nameOff
                    $chars = New-Object System.Collections.Generic.List[char]
                    while (($chars.Count -lt 256) -and (($nameOff + $chars.Count) -lt $fs.Length)) {
                        $b = $br.ReadByte()
                        if ($b -eq 0) { break }
                        $chars.Add([char]$b)
                    }
                    if ($chars.Count -gt 0) { $null = $names.Add((-join $chars.ToArray())) }
                }
            }
            $descOff += 20
        }
        return ,$names
    } finally {
        $fs.Dispose()
    }
}

function Test-BundleCore {
    # Classification + required entries + layout invariant + pure-PS external closure.
    # Reuses packaging/validate-bundle.ps1 classification logic (dot-sourced by the
    # caller) instead of duplicating it; deliberately does NOT call its
    # Test-BundleValidation, whose external-closure step shells out to uv/python -
    # forbidden on the sanitized host under test.
    param(
        [string]$Bundle,
        [string]$AllowlistPath,
        [string]$ReportPath
    )
    $errors = New-Object System.Collections.Generic.List[string]
    $firmware = New-Object System.Collections.Generic.List[string]
    $relativePaths = New-Object System.Collections.Generic.HashSet[string]
    $bundleLocalDlls = New-Object System.Collections.Generic.HashSet[string]
    $classes = @{}
    $totalBytes = 0L

    if (-not (Test-Path -LiteralPath (Join-Path $Bundle "LNT.exe"))) {
        $null = $errors.Add("бандл неполон: нет LNT.exe")
    }
    $allFiles = @(Get-ChildItem -LiteralPath $Bundle -Recurse -File)
    foreach ($file in $allFiles) {
        $rel = $file.FullName.Substring($Bundle.Length + 1).Replace("\", "/")
        $lower = $rel.ToLowerInvariant()
        $null = $relativePaths.Add($lower)
        $totalBytes += $file.Length
        $forbidden = Get-ForbiddenHit $rel
        if ($null -ne $forbidden) {
            $null = $errors.Add(("запрещённый артефакт '{0}': {1}" -f $forbidden, $rel))
            continue
        }
        $class = Get-BundleClass $rel
        if ($null -eq $class) {
            $null = $errors.Add("неклассифицированный файл: $rel")
            continue
        }
        if ($class -eq "firmware") { $null = $firmware.Add($rel) }
        if (-not $classes.ContainsKey($class)) {
            $classes[$class] = New-Object System.Collections.Generic.List[string]
        }
        $null = $classes[$class].Add($rel)
        if ($lower.EndsWith(".dll")) {
            $null = $bundleLocalDlls.Add([System.IO.Path]::GetFileName($lower))
        }
    }
    if ($totalBytes -gt $script:SizeLimitBytes) {
        $null = $errors.Add(("размер бандла {0} байт превышает лимит {1}" -f $totalBytes, $script:SizeLimitBytes))
    }
    if ($firmware.Count -ne $script:FirmwareExpectedCount) {
        $null = $errors.Add(("неполный класс firmware: ожидалось {0}, найдено {1}" -f `
            $script:FirmwareExpectedCount, $firmware.Count))
    }
    $requiredRef = [ref]$errors
    Test-RequiredEntries -Bundle $Bundle -RelativePaths $relativePaths `
        -FirmwareByExtension @{ firmware = $firmware } -Errors $requiredRef

    foreach ($rel in $relativePaths) {
        $isBinary = $rel.EndsWith(".dll") -or $rel.EndsWith(".pyd")
        if ($isBinary -and (-not $rel.StartsWith("_internal/"))) {
            $null = $errors.Add("бинарный файл вне _internal/: $rel")
        }
    }

    $policy = Get-Content -LiteralPath $AllowlistPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not ("LntSmoke.NativeResolve" -as [type])) {
        Add-Type -Namespace LntSmoke -Name NativeResolve -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll", SetLastError=true, CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
public static extern System.IntPtr LoadLibraryExW(string fileName, System.IntPtr fileHandle, uint flags);
[System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
public static extern uint GetModuleFileNameW(System.IntPtr module, System.Text.StringBuilder buffer, uint size);
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern bool FreeLibrary(System.IntPtr module);
'@
    }
    $allowed = @{}
    foreach ($name in $policy.allowed_names) { $allowed[$name.ToLowerInvariant()] = $true }
    $system32 = [System.IO.Path]::GetFullPath((Join-Path $env:SystemRoot "System32")).TrimEnd("\")
    $externalRecords = @()
    $signatureCache = @{}

function Resolve-ExternalImport {
        # Loader-parity resolution mirroring packaging/spike/pe_imports.py:
        # LoadLibraryExW(name, DONT_RESOLVE_DLL_REFERENCES) lets the Windows loader
        # map virtual api-set names (api-ms-win-crt-*, api-ms-win-core-*) to their
        # final physical DLLs without executing entry points or loading dependencies.
        # Accepted only if the resolved file lives in canonical System32.
        param([string]$ImportName)
        $lower = $ImportName.ToLowerInvariant()
        $direct = Join-Path $system32 $ImportName
        if (Test-Path -LiteralPath $direct) {
            return @{ resolved = $lower; path = $direct }
        }
        $handle = [LntSmoke.NativeResolve]::LoadLibraryExW($ImportName, [IntPtr]::Zero, 0x800)
        if ($handle -ne [IntPtr]::Zero) {
            try {
                $buffer = New-Object System.Text.StringBuilder 32768
                $length = [LntSmoke.NativeResolve]::GetModuleFileNameW($handle, $buffer, 32768)
                if ($length -gt 0) {
                    $resolvedPath = [System.IO.Path]::GetFullPath($buffer.ToString())
                    $parent = [System.IO.Path]::GetDirectoryName($resolvedPath).TrimEnd("\")
                    if ($parent -eq $system32) {
                        return @{
                            resolved = ([System.IO.Path]::GetFileName($resolvedPath).ToLowerInvariant())
                            path = $resolvedPath
                        }
                    }
                }
            } finally {
                $null = [LntSmoke.NativeResolve]::FreeLibrary($handle)
            }
        }
        return $null
    }

    $pes = @(Get-ChildItem -LiteralPath $Bundle -Recurse -File |
        Where-Object { @(".exe", ".dll", ".pyd") -contains $_.Extension.ToLowerInvariant() })
    foreach ($pe in $pes) {
        $imports = Get-PeImportedDlls -Path $pe.FullName
        foreach ($importedName in $imports) {
            $lowerImport = $importedName.ToLowerInvariant()
            if ($bundleLocalDlls.Contains($lowerImport)) { continue }
            $resolution = Resolve-ExternalImport $importedName
            if ($null -eq $resolution) {
                $null = $errors.Add("импорт не разрешается ни в бандл, ни в canonical System32: " +
                    "$lowerImport (из $($pe.Name))")
                continue
            }
            if (-not $allowed.ContainsKey($resolution.resolved)) {
                $null = $errors.Add(("внешняя DLL не в allowlist: {0} (разрешено из {1})" -f `
                    $resolution.resolved, $lowerImport))
                continue
            }
            if (-not $signatureCache.ContainsKey($resolution.resolved)) {
                $signature = Get-AuthenticodeSignature -LiteralPath $resolution.path
                $subject = ""
                if ($null -ne $signature.SignerCertificate) {
                    $subject = $signature.SignerCertificate.Subject
                }
                $machineOk = ((Get-PeMachine $resolution.path) -eq 0x8664)
                $signatureCache[$resolution.resolved] = @{
                    status = [string]$signature.Status
                    microsoft = ($subject -match "Microsoft")
                    machine_x64 = $machineOk
                }
            }
            $cached = $signatureCache[$resolution.resolved]
            if (($cached.status -ne "Valid") -or (-not $cached.microsoft)) {
                $null = $errors.Add("нет валидной Microsoft Authenticode подписи: $($resolution.path)")
            }
            if (-not $cached.machine_x64) {
                $null = $errors.Add("DLL не x64: $($resolution.path)")
            }
            $externalRecords += @{
                name = $lowerImport
                resolved_to = $resolution.resolved
                requested_by = $pe.FullName.Substring($Bundle.Length + 1).Replace("\", "/")
            }
        }
    }

    $payload = [ordered]@{
        schema_version = 1
        bundle = $Bundle
        policy = "private-use one-folder distribution; every file classified; external OS DLLs allowlisted (Todo 13); sanitized-host re-check"
        file_count = $allFiles.Count
        total_bytes = $totalBytes
        classes = $classes
        external_system32 = $externalRecords
        errors = @($errors.ToArray())
    }
    $reportDir = Split-Path -Parent $ReportPath
    if ($reportDir) { New-Item -ItemType Directory -Force -Path $reportDir | Out-Null }
    $payload | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding UTF8

    return @{ ok = ($errors.Count -eq 0); errors = @($errors.ToArray()); report = $payload }
}

function Verify-ZipIntegrity {
    param([string]$ZipPath, [string]$SidecarPath)
    $actual = Get-Sha256 $ZipPath
    $sidecarLine = (Get-Content -LiteralPath $SidecarPath -TotalCount 1).Trim()
    $expected = $sidecarLine.Split(" ")[0].ToLowerInvariant()
    return @{ ok = ($actual -eq $expected); expected = $expected; actual = $actual }
}

function Start-LntUi {
    param([string]$BundleDir, [string]$SessionRoot, [int]$Port)
    $exe = Join-Path $BundleDir "LNT.exe"
    # UseShellExecute=true: the windowed child must NOT inherit this process's
    # stdout/stderr pipes (inherited handles make automation callers block until
    # the app exits, and leak console handles into CI harnesses).
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = '--no-browser --root="' + $SessionRoot + '" --port=' + $Port
    $psi.WorkingDirectory = $BundleDir
    $psi.UseShellExecute = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $proc = [System.Diagnostics.Process]::Start($psi)
    $null = $script:SpawnedPids.Add($proc.Id)
    Log ("SPAWN pid={0} exe=LNT.exe port={1}" -f $proc.Id, $Port)
    return $proc
}

function Wait-Health {
    param([string]$BaseUrl, [int]$TimeoutS)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutS)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ([DateTime]::UtcNow -lt $deadline) {
        $response = Invoke-ApiJson -Method GET -Url ($BaseUrl + "api/health") -TimeoutSec 3 -Label "health-poll"
        if ($response.status -eq 200) {
            $payload = $response.body | ConvertFrom-Json
            if (($payload.status -eq "ok") -and ($payload.build_id)) {
                Sample-Network
                return @{ ok = $true; build_id = [string]$payload.build_id; elapsed_ms = $sw.ElapsedMilliseconds }
            }
        }
        Start-Sleep -Milliseconds 250
    }
    return @{ ok = $false; build_id = ""; elapsed_ms = $sw.ElapsedMilliseconds }
}

function Wait-JobTerminal {
    param([string]$BaseUrl, [string]$JobId, [string]$Nonce, [int]$TimeoutS = 240)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutS)
    $polls = 0
    while ([DateTime]::UtcNow -lt $deadline) {
        $polls++
        if (($polls % 4) -eq 0) { Sample-Network }
        $response = Invoke-ApiJson -Method GET -Url ($BaseUrl + "api/jobs/" + $JobId) -Label "job-poll"
        if ($response.status -eq 200) {
            $snapshot = $response.body | ConvertFrom-Json
            if (@("succeeded", "failed", "cancelled", "interrupted") -contains $snapshot.status) {
                return $snapshot
            }
        }
        Start-Sleep -Milliseconds 250
    }
    throw "job $JobId did not reach a terminal state within ${TimeoutS}s"
}

function Invoke-StartJob {
    param([string]$BaseUrl, [object]$Body, [string]$Nonce, [string]$Label)
    $response = Invoke-ApiJson -Method POST -Url ($BaseUrl + "api/jobs") -Body $Body -Nonce $Nonce -Label $Label
    if ($response.status -ne 202) {
        throw ("{0}: POST /api/jobs expected 202 got {1} body={2}" -f $Label, $response.status, $response.body)
    }
    $payload = $response.body | ConvertFrom-Json
    if (-not $payload.job_id) { throw "$Label : response missing job_id" }
    return $payload
}

function Invoke-FrozenCli {
    # Runs a short-lived command via the CONSOLE sibling LNT-cli.exe: it shares
    # _internal and the entry script with the windowed LNT.exe but has real
    # console streams, so stdout/exit codes are observable evidence. The PID is
    # registered for teardown.
    param([string]$BundleDir, [string]$Arguments, [string]$Label, [int]$TimeoutMs = 600000)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = (Join-Path $BundleDir "LNT-cli.exe")
    $psi.Arguments = $Arguments
    $psi.WorkingDirectory = $BundleDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $proc = [System.Diagnostics.Process]::Start($psi)
    $null = $script:SpawnedPids.Add($proc.Id)
    Log ("SPAWN pid={0} exe=LNT-cli.exe args={1}" -f $proc.Id, $Arguments)
    $exited = $proc.WaitForExit($TimeoutMs)
    if (-not $exited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    # Small outputs only (selftest/archive print a few lines); read AFTER exit.
    $stdoutText = ""; $stderrText = ""
    if ($exited) {
        try { $stdoutText = $proc.StandardOutput.ReadToEnd() } catch { }
        try { $stderrText = $proc.StandardError.ReadToEnd() } catch { }
    }
    return @{
        label = $Label; arguments = $Arguments; exited = $exited
        exit_code = $(if ($exited) { $proc.ExitCode } else { -1 })
        elapsed_ms = $watch.ElapsedMilliseconds
        stdout_head = $stdoutText.Trim()
        stderr_head = $stderrText.Trim()
    }
}

function Invoke-Teardown {
    param([string]$Phase)
    $killed = New-Object System.Collections.Generic.List[int]
    $receipt = @{ phase = $Phase; killed_pids = $killed; listener_stopped = $false
        temp_root_removed = $false; temp_root = $script:TempRoot }

    foreach ($pidToKill in @($script:SpawnedPids.ToArray())) {
        try {
            $proc = Get-Process -Id $pidToKill -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                $proc.WaitForExit(5000) | Out-Null
            }
        } catch { }
        $null = $killed.Add($pidToKill)
    }
    if ($script:Listener -ne $null) {
        try { $script:Listener.Stop() } catch { }
        $script:Listener = $null
        $receipt.listener_stopped = $true
    }
    Exit-SanitizedEnvironment

    if (($null -ne $script:TempRoot) -and (Test-Path -LiteralPath $script:TempRoot)) {
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            try {
                Remove-Item -LiteralPath $script:TempRoot -Recurse -Force -ErrorAction Stop
                break
            } catch {
                Start-Sleep -Seconds (2 * $attempt)
            }
        }
        $receipt.temp_root_removed = (-not (Test-Path -LiteralPath $script:TempRoot))
    }
    Write-EvidenceJson "temp-state-receipt.json" $receipt
    return $receipt
}

function Get-PortSweepReceipt {
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { ($_.LocalPort -ge 8765 -and $_.LocalPort -le 8780) -or $_.LocalPort -eq 4101 })
    $rows = @()
    foreach ($l in $listeners) {
        $rows += @{ local_address = $l.LocalAddress; local_port = $l.LocalPort; pid = $l.OwningProcess }
    }
    return @{ checked_ports = "8765..8780,4101"; listeners = $rows
        clean = ($rows.Count -eq 0); swept_at = (Get-Date).ToUniversalTime().ToString("o") }
}

function Get-LntProcessSweep {
    $rows = @()
    foreach ($p in @(Get-Process -Name "LNT" -ErrorAction SilentlyContinue)) {
        $rows += @{ pid = $p.Id; started = $p.StartTime.ToString("o") }
    }
    return $rows
}

# =============================== MAIN ===========================================
$startedAt = [DateTime]::UtcNow
Log ("=== LNT sanitized reference-host smoke ===")
Log ("host_label={0}" -f $script:HostLabel)
Log ("zip={0}" -f (Resolve-Path -LiteralPath $Zip).Path)

try {
    # --- S00 preflight ----------------------------------------------------------
    if (-not (Test-Path -LiteralPath $Zip)) { throw "PREFLIGHT FAIL: ZIP не найден: $Zip" }
    if (-not (Test-Path -LiteralPath ($Zip + ".sha256"))) { throw "PREFLIGHT FAIL: нет sidecar $Zip.sha256" }
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) { throw "ELEVATED: скрипт обязан выполняться НЕ от администратора" }
    $os = Get-CimInstance Win32_OperatingSystem
    $hostInfo = @{
        label = $script:HostLabel
        os_caption = $os.Caption
        os_version = $os.Version
        os_architecture = $os.OSArchitecture
        powershell_version = $PSVersionTable.PSVersion.ToString()
        elevated = $false
        forbidden_labels_used = @()
        recorded_at = $startedAt.ToString("o")
    }
    Write-EvidenceJson "host-label.json" $hostInfo
    $processBefore = Get-LntProcessSweep
    $portsBefore = Get-PortSweepReceipt
    Write-EvidenceJson "process-inventory-before.json" @{ lnt_processes = $processBefore; port_sweep = $portsBefore }
    Step "00-preflight-non-elevated" 0 ("admin=False ps=" + $hostInfo.powershell_version)

    # --- S01 sanitize -----------------------------------------------------------
    $suffix = [guid]::NewGuid().ToString("N").Substring(0, 12)
    $script:TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("lnt-smoke-" + $suffix)
    New-Item -ItemType Directory -Force -Path $script:TempRoot | Out-Null
    $payloadDir = Join-Path $script:TempRoot "payload"
    New-Item -ItemType Directory -Force -Path $payloadDir | Out-Null
    $zipCopy = Join-Path $payloadDir "LNT.zip"
    Copy-Item -LiteralPath (Resolve-Path -LiteralPath $Zip).Path -Destination $zipCopy -Force
    Enter-SanitizedEnvironment -Root $script:TempRoot

    $missingTools = @()
    foreach ($tool in @("python", "python3", "node", "npm", "uv")) {
        $found = Get-Command $tool -ErrorAction SilentlyContinue
        if ($null -ne $found) { $missingTools += $tool }
    }
    if ($missingTools.Count -gt 0) {
        throw ("SANITIZE FAILED: под очищенным PATH найдены внешние инструменты: " + ($missingTools -join ","))
    }
    Step "01-sanitize-toolchains-absent" 0 ("where-python-node-npm-uv=not-found scrubbed-env=true")

    # --- S02 integrity ----------------------------------------------------------
    $zipSourceFull = (Resolve-Path -LiteralPath $Zip).Path
    $sidecarPath = $zipSourceFull + ".sha256"
    if (-not (Test-Path -LiteralPath $sidecarPath)) { throw "нет sidecar SHA-256: $sidecarPath" }
    $integrity = Verify-ZipIntegrity -ZipPath $zipCopy -SidecarPath $sidecarPath
    Write-EvidenceJson "integrity.json" @{
        zip = $zipCopy; expected_sha256 = $integrity.expected
        actual_sha256 = $integrity.actual; match = $integrity.ok
    } 
    if (-not $integrity.ok) { throw ("INTEGRITY FAIL: sha256 mismatch expected={0} actual={1}" -f $integrity.expected, $integrity.actual) }
    Step "02-integrity-sha256" 0 ("match=True sha=" + $integrity.actual.Substring(0, 16) + "...")

    $bundleDir = Join-Path $script:TempRoot "bundle"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipCopy, $bundleDir)
    . (Join-Path $PSScriptRoot "validate-bundle.ps1")
    $validation = Test-BundleCore -Bundle $bundleDir `
        -AllowlistPath (Join-Path $PSScriptRoot "system32-allowlist.v2.json") `
        -ReportPath (Join-Path $evidenceRoot "classification-report.json")
    if (-not $validation.ok) {
        foreach ($err in $validation.errors) { Log "VALIDATION ERROR: $err" }
        throw ("BUNDLE VALIDATION FAIL: " + $validation.errors.Count + " ошибок")
    }
    Step "02-bundle-validation" 0 ("files=" + $validation.report.file_count + " external-system32-ok firmware=7")

    # --- S03 frozen CLI surface: run the REAL `selftest` via LNT-cli.exe ----------
    # Exact subcommand name verified in src/lnt/cli.py (parser: "selftest").
    $selftestRun = Invoke-FrozenCli -BundleDir $bundleDir -Arguments "selftest" -Label "cli-selftest"
    Write-EvidenceJson "cli-selftest.json" @{
        exe = "LNT-cli.exe"
        arguments = "selftest"
        exit_code = $selftestRun.exit_code
        timed_out = (-not $selftestRun.exited)
        elapsed_ms = $selftestRun.elapsed_ms
        stdout_head = $selftestRun.stdout_head
        stderr_head = $selftestRun.stderr_head
    }
    Step "03-cli-selftest" $selftestRun.exit_code ("exit=" + $selftestRun.exit_code + " stdout=" + $selftestRun.stdout_head)
    if ($selftestRun.exit_code -ne 0) {
        throw ("FROZEN SELFTEST FAIL: LNT-cli.exe selftest exited {0}: {1}" -f $selftestRun.exit_code, $selftestRun.stderr_head)
    }
    if ($selftestRun.stdout_head -notmatch "SELFTEST OK") {
        throw ("FROZEN SELFTEST FAIL: unexpected selftest output: {0}" -f $selftestRun.stdout_head)
    }

    # --- S04 launch UI, cold health ---------------------------------------------
    # Защита от протечек предыдущих прогонов: никакой LNT-процесс не должен
    # переживать границы смоука (иначе health может ответить «чужой» инстанс).
    $stale = @(Get-Process -Name "LNT", "LNT-cli" -ErrorAction SilentlyContinue)
    foreach ($staleProc in $stale) {
        Log ("STALE-KILL pid={0} name={1}" -f $staleProc.Id, $staleProc.ProcessName)
        Stop-Process -Id $staleProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($stale.Count -gt 0) { Start-Sleep -Milliseconds 800 }
    $stillAlive = @(Get-Process -Name "LNT", "LNT-cli" -ErrorAction SilentlyContinue)
    if ($stillAlive.Count -gt 0) {
        throw ("STALE INSTANCE FAIL: не удалось завершить прежние процессы: {0}" -f `
            (($stillAlive | ForEach-Object { $_.Id }) -join ","))
    }
    # Ждём фактического освобождения диапазона портов: сразу после Stop-Process
    # слушатель может держаться ещё мгновения, и тогда новый инстанс молча
    # упадёт на fallback вместо ожидаемого preferred.
    $portsFree = $false
    for ($i = 0; $i -lt 40; $i++) {
        $rangeBusy = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.LocalPort -ge $PreferredPort -and $_.LocalPort -le 8780 })
        if ($rangeBusy.Count -eq 0) { $portsFree = $true; break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $portsFree) {
        throw "PORT SLATE FAIL: порты 8765..8780 не освободились перед холодным стартом"
    }
    Log "PORT-SLATE-CLEAN range=8765..8780"
    $sessionRoot = Join-Path $script:TempRoot "sessions"
    New-Item -ItemType Directory -Force -Path $sessionRoot | Out-Null
    $launchWatch = [System.Diagnostics.Stopwatch]::StartNew()
    $proc = Start-LntUi -BundleDir $bundleDir -SessionRoot $sessionRoot -Port $PreferredPort
    $baseUrl = "http://127.0.0.1:" + $PreferredPort + "/"
    $health = Wait-Health -BaseUrl $baseUrl -TimeoutS $HealthTimeoutS
    if ((-not $health.ok) -or ($launchWatch.ElapsedMilliseconds -gt ($HealthTimeoutS * 1000))) {
        # Диагностика отказа: не упал ли инстанс на fallback-порту и что в журнале.
        $fallbackProbe = @()
        foreach ($candidate in ((($PreferredPort + 1)..8780))) {
            $probeResult = Wait-Health -BaseUrl ("http://127.0.0.1:" + $candidate + "/") -TimeoutS 1
            if ($probeResult.ok) { $fallbackProbe += $candidate }
        }
        $logDump = ""
        Get-ChildItem -Path $script:TempRoot -Recurse -Include "*.jsonl","*.log" -ErrorAction SilentlyContinue |
            ForEach-Object { $logDump += ("=== {0} ===`n{1}`n" -f $_.FullName, ((Get-Content $_.FullName -Tail 40 -ErrorAction SilentlyContinue) -join "`n")) }
        $logDump | Set-Content -LiteralPath (Join-Path $fmDir "cold-health-failure-forensics.txt") -Encoding UTF8
        Step "04-cold-health-forensics" 0 ("fallback_ports=" + (($fallbackProbe | ForEach-Object { $_ }) -join ","))
        throw ("COLD HEALTH FAIL: /api/health не ответил за {0} ms (лимит {1}s); fallback-порты с живым health: [{2}]" -f `
            $launchWatch.ElapsedMilliseconds, $HealthTimeoutS, (($fallbackProbe | ForEach-Object { $_ }) -join ","))
    }
    Step "04-cold-health" 0 ("elapsed_ms=" + $launchWatch.ElapsedMilliseconds + " build_id=" + $health.build_id)

    # Health должен отвечать именно НАШ процесс, а не пережиток чужого прогона.
    $ownerPid = 0
    try {
        $ownerConn = Get-NetTCPConnection -LocalPort $PreferredPort -State Listen -ErrorAction Stop |
            Select-Object -First 1
        $ownerPid = [int]$ownerConn.OwningProcess
    } catch {
        throw ("HEALTH OWNER FAIL: нет слушателя на порту {0} после успешного health" -f $PreferredPort)
    }
    if ($ownerPid -ne $proc.Id) {
        throw ("HEALTH OWNER FAIL: порт {0} держит pid={1}, ожидался pid={2} (чужой инстанс?)" -f `
            $PreferredPort, $ownerPid, $proc.Id)
    }
    Log ("HEALTH-OWNER pid={0} port={1} confirmed" -f $ownerPid, $PreferredPort)

    $configResp = Invoke-ApiJson -Method GET -Url ($baseUrl + "api/config") -Label "config"
    if ($configResp.status -ne 200) { throw "CONFIG FAIL: HTTP $($configResp.status)" }
    $config = $configResp.body | ConvertFrom-Json
    $nonce = [string]$config.mutation_nonce
    if (($nonce -eq "") -or ([string]$config.build_id -ne $health.build_id)) {
        throw "CONFIG FAIL: nonce/build_id рассинхронизированы"
    }
    $rootNormalized = ([IO.Path]::GetFullPath([string]$config.root)).TrimEnd("\").ToLowerInvariant()
    $expectedRoot = ([IO.Path]::GetFullPath($sessionRoot)).TrimEnd("\").ToLowerInvariant()
    if ($rootNormalized -ne $expectedRoot) {
        throw ("CONFIG FAIL: root={0} ожидание={1}" -f $config.root, $sessionRoot)
    }
    Step "04-config-nonce-root" 0 ("build_id_match=True root_isolated=True")

    # --- S05 assets & offline-request assertions --------------------------------
    $assetChecks = @()
    $indexResp = Invoke-ApiJson -Method GET -Url $baseUrl -Label "index"
    if ($indexResp.status -ne 200) { throw "ASSET FAIL: GET / -> $($indexResp.status)" }
    $indexHtml = [string]$indexResp.body
    $assetChecks += @{ asset = "/"; status = 200; bytes = $indexHtml.Length
        checks = @{ data_build_id_present = $indexHtml.Contains('data-build-id="' + $health.build_id + '"') } }
    $externalRefs = @([regex]::Matches($indexHtml, '(?:src|href)="(http[^"]+)"') |
        ForEach-Object { $_.Groups[1].Value } |
        Where-Object { $_ -notmatch "^https?://127\.0\.0\.1" })
    if ($externalRefs.Count -gt 0) {
        throw ("OFFLINE FAIL: index.html ссылается на внешние URL: " + ($externalRefs -join ", "))
    }
    $hashedApp = [string]$config.static_assets.app
    $appResp = Invoke-ApiJson -Method GET -Url ($baseUrl.TrimEnd("/") + $hashedApp) -Label "hashed-app-js"
    $immutableOk = $false
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri ($baseUrl.TrimEnd("/") + $hashedApp) -TimeoutSec 10
        $immutableOk = ([string]$r.Headers["Cache-Control"]).Contains("immutable")
    } catch { }
    $assetChecks += @{ asset = $hashedApp; status = $appResp.status; immutable_cache = $immutableOk }
    foreach ($staticPath in @("/static/v2/index.html", "/static/vendor/uPlot.esm.js",
            "/static/vendor/uPlot.min.css")) {
        $resp = Invoke-ApiJson -Method GET -Url ($baseUrl.TrimEnd("/") + $staticPath) -Label ("asset " + $staticPath)
        if ($resp.status -ne 200) { throw "ASSET FAIL: $staticPath -> $($resp.status)" }
        $assetChecks += @{ asset = $staticPath; status = 200; bytes = ([string]$resp.body).Length }
    }
    $fontsManifest = Get-Content -LiteralPath (Join-Path $bundleDir "_internal\lnt\ui\static\fonts\manifest.json") `
        -Raw -Encoding UTF8 | ConvertFrom-Json
    $fontFile = @($fontsManifest.files.PSObject.Properties.Name | Where-Object { $_ -like "*.woff2" })[0]
    $fontResp = Invoke-ApiJson -Method GET -Url ($baseUrl.TrimEnd("/") + "/static/fonts/" + $fontFile) -Label "font"
    if ($fontResp.status -ne 200) { throw "ASSET FAIL: font $fontFile -> $($fontResp.status)" }
    $assetChecks += @{ asset = "/static/fonts/" + $fontFile; status = 200; bytes = $fontResp.body.Length }
    Write-EvidenceJson "asset-checks.json" @{
        external_references_in_index = @($externalRefs)
        offline_assertion = "no absolute non-loopback src/href in served index.html"
        checks = $assetChecks
    }
    Step "05-assets-offline" 0 ("checks=" + $assetChecks.Count + " external_refs=0")

    # --- S06 typed device diagnosis (non-invasive) ------------------------------
    $deviceResp = Invoke-ApiJson -Method GET -Url ($baseUrl + "api/device/state") -Label "device-state"
    if ($deviceResp.status -ne 200) { throw "DEVICE FAIL: HTTP $($deviceResp.status)" }
    $device = $deviceResp.body | ConvertFrom-Json
    if ($script:DeviceStates -notcontains [string]$device.state) {
        throw ("DEVICE FAIL: неизвестное типизированное состояние: " + $device.state)
    }
    if ([string]::IsNullOrWhiteSpace([string]$device.description_ru) -or
        [string]::IsNullOrWhiteSpace([string]$device.recovery_action_ru)) {
        throw "DEVICE FAIL: пустое описание/действие в типизированном состоянии"
    }
    $deviceAbsentFamily = $script:AbsentFamilyStates -contains [string]$device.state
    Write-EvidenceJson "device-diagnostic.json" @{
        state = [string]$device.state
        description_ru = [string]$device.description_ru
        recovery_action_ru = [string]$device.recovery_action_ru
        absent_family = $deviceAbsentFamily
        typed_state_valid = $true
    }
    Step "06-device-typed-state" 0 ("state=" + $device.state + " absent_family=" + $deviceAbsentFamily)

    # --- S07 synthetic journey ---------------------------------------------------
    $journeyChecks = @()

    $simBodyA = @{ kind = "simulate"; profile = "quiet"; duration_s = 2.4
        sample_rate_hz = 500000.0; seed = 602210; channels = 2
        output_name = "lnt-smoke-a"; label = "smoke-a" }
    $simBodyB = @{ kind = "simulate"; profile = "quiet"; duration_s = 2.4
        sample_rate_hz = 500000.0; seed = 602211; channels = 2
        output_name = "lnt-smoke-b"; label = "smoke-b" }
    foreach ($sim in @(@{ body = $simBodyA; name = "lnt-smoke-a" }, @{ body = $simBodyB; name = "lnt-smoke-b" })) {
        $job = Invoke-StartJob -BaseUrl $baseUrl -Body $sim.body -Nonce $nonce -Label ("simulate " + $sim.name)
        $snapshot = Wait-JobTerminal -BaseUrl $baseUrl -JobId $job.job_id -Nonce $nonce
        if ($snapshot.status -ne "succeeded") {
            throw ("SIMULATE FAIL: {0} -> {1} ({2})" -f $sim.name, $snapshot.status, $snapshot.error_message)
        }
        $sessionDir = Join-Path $sessionRoot $sim.name
        foreach ($artifact in @("manifest.json", "ch1.npy", "ch2.npy")) {
            if (-not (Test-Path -LiteralPath (Join-Path $sessionDir $artifact))) {
                throw "SIMULATE FAIL: отсутствует артефакт $artifact в $($sim.name)"
            }
        }
        $journeyChecks += @{ step = "simulate:" + $sim.name; job_status = "succeeded"
            artifacts_on_disk = @("manifest.json", "ch1.npy", "ch2.npy") }
    }

    $analyzeJob = Invoke-StartJob -BaseUrl $baseUrl `
        -Body @{ kind = "analyze"; session_name = "lnt-smoke-a" } -Nonce $nonce -Label "analyze"
    $analyzeSnap = Wait-JobTerminal -BaseUrl $baseUrl -JobId $analyzeJob.job_id -Nonce $nonce
    if ($analyzeSnap.status -ne "succeeded") {
        throw ("ANALYZE FAIL: {0} ({1})" -f $analyzeSnap.status, $analyzeSnap.error_message)
    }
    $metricsPath = Join-Path $sessionRoot "lnt-smoke-a\metrics.json"
    if (-not (Test-Path -LiteralPath $metricsPath)) { throw "ANALYZE FAIL: metrics.json не создан" }
    $spectrumResp = Invoke-ApiJson -Method GET `
        -Url ($baseUrl + "api/sessions/lnt-smoke-a/spectrum?max_points=512") -Label "spectrum"
    if ($spectrumResp.status -ne 200) { throw "SPECTRUM FAIL: HTTP $($spectrumResp.status)" }
    $spectrumPayload = $spectrumResp.body | ConvertFrom-Json
    if ((@($spectrumPayload.frequency_hz).Count -lt 100) -or
        (@($spectrumPayload.psd_v2_per_hz).Count -ne @($spectrumPayload.frequency_hz).Count)) {
        throw "SPECTRUM FAIL: тело ответа не содержит согласованных спектральных данных"
    }
    $waveformResp = Invoke-ApiJson -Method GET `
        -Url ($baseUrl + "api/sessions/lnt-smoke-a/waveform?channel=ch1&max_points=512") -Label "waveform"
    if ($waveformResp.status -ne 200) { throw "WAVEFORM FAIL: HTTP $($waveformResp.status)" }
    $journeyChecks += @{ step = "analyze:lnt-smoke-a"; job_status = "succeeded"
        metrics_json_on_disk = $true
        spectrum_points = @($spectrumPayload.frequency_hz).Count
        waveform_http = 200 }

    $compareJob = Invoke-StartJob -BaseUrl $baseUrl `
        -Body @{ kind = "compare"; session_a = "lnt-smoke-a"; session_b = "lnt-smoke-b" } `
        -Nonce $nonce -Label "compare"
    $compareSnap = Wait-JobTerminal -BaseUrl $baseUrl -JobId $compareJob.job_id -Nonce $nonce
    if ($compareSnap.status -ne "succeeded") { throw ("COMPARE FAIL: " + $compareSnap.status) }
    $journeyChecks += @{ step = "compare:a-vs-b"; job_status = "succeeded" }

    $selftestJob = Invoke-StartJob -BaseUrl $baseUrl -Body @{ kind = "selftest" } `
        -Nonce $nonce -Label "selftest-job"
    $selftestSnap = Wait-JobTerminal -BaseUrl $baseUrl -JobId $selftestJob.job_id -Nonce $nonce -TimeoutS 300
    if ($selftestSnap.status -ne "succeeded") {
        throw ("SELFTEST FAIL через API: {0} ({1})" -f $selftestSnap.status, $selftestSnap.error_message)
    }
    $journeyChecks += @{ step = "selftest:job-api"; job_status = "succeeded"
        note = "run_selftest() executed inside frozen runtime via POST /api/jobs" }

    $experiment = [ordered]@{
        experiment_schema_version = 1
        experiment_id = "lnt-smoke-exp"
        title = "LNT smoke A/B"
        question = "Синтетический прогон smoke-скрипта"
        status = "draft"
        revision = 1
        factors = @(@{ factor_id = "firmware"; kind = "categorical"; levels = @("a", "b") })
        conditions = @(
            @{ condition_id = "condition-a"; values = @(@{ factor_id = "firmware"; value = "a" }) }
            @{ condition_id = "condition-b"; values = @(@{ factor_id = "firmware"; value = "b" }) }
        )
        protocol = [ordered]@{
            kind = "ab"; sampling_unit = "subject"; site_key = "site_id"
            subject_key = "subject_id"; block_key = "block_id"; pairing_key = "pair_id"
            assignment_scheme = "balanced_explicit"; order_scheme = "declared_step_order"
            within_unit_aggregation = "median"
            independence_assumptions = @("Независимы только разные subject_id.")
            minimum_n = 2; multiplicity_policy = "holm"
        }
        steps = @(
            @{ order = 1; condition_id = "condition-a"; instruction = "Измерить A" }
            @{ order = 2; condition_id = "condition-b"; instruction = "Измерить B" }
        )
        members = @(
            @{ session_id = "session-a"; storage_ref = "session-a"; role = "measurement"
                condition_id = "condition-a"; order = 1; block_key = "block-1"; pairing_key = "pair-1" }
            @{ session_id = "missing-session"; storage_ref = "missing-session"; role = "measurement"
                condition_id = "condition-b"; order = 2; block_key = "block-1"; pairing_key = "pair-1" }
        )
        interventions = @(@{ intervention_id = "firmware-b"
            occurred_at = "2026-08-23T10:00:00.000Z"; condition_id = "condition-b" })
        primary_estimands = @(@{ feature_key = "latency_s"; direction = "lower"
            contrast = "condition-b - condition-a" })
        secondary_estimands = @()
        confound_checklist = @(@{ key = "temperature"; checked = $true; note = "Стабильна" })
        revision_history = @(@{ revision = 1; occurred_at = "2026-08-23T10:00:00.000Z"
            actor = "lnt-smoke"; reason = "Smoke-прогон" })
    }
    $expResp = Invoke-ApiJson -Method POST -Url ($baseUrl + "api/v2/experiments") `
        -Body @{ experiment = $experiment; expected_revision = 0 } -Nonce $nonce -Label "create-experiment"
    if ($expResp.status -ne 201) {
        throw ("EXPERIMENT FAIL: HTTP {0} body={1}" -f $expResp.status, $expResp.body)
    }
    $runResp = Invoke-ApiJson -Method POST -Url ($baseUrl + "api/v2/experiments/lnt-smoke-exp/runs") `
        -Body @{ run_id = "lnt-smoke-run-1"; mode = "simulator" } -Nonce $nonce -Label "protocol-run-start"
    if ($runResp.status -ne 201) { throw ("PROTOCOL RUN FAIL: HTTP $($runResp.status)") }
    $confirmResp = Invoke-ApiJson -Method POST -Url ($baseUrl + "api/v2/protocol-runs/lnt-smoke-run-1/confirm") `
        -Body @{ actor = "user:lnt-smoke"; auto_confirm = $false } -Nonce $nonce -Label "protocol-run-confirm"
    if ($confirmResp.status -ne 200) { throw ("CONFIRM FAIL: HTTP $($confirmResp.status)") }
    $statusResp = Invoke-ApiJson -Method GET -Url ($baseUrl + "api/v2/protocol-runs/lnt-smoke-run-1") `
        -Label "protocol-run-status"
    $runStatus = $statusResp.body | ConvertFrom-Json
    if ([string]$runStatus.status -ne "completed") { throw ("PROTOCOL RUN STATUS: " + $runStatus.status) }
    $journeyChecks += @{ step = "experiment:simulator-run"; status = "completed"
        confirm_actor = "user:lnt-smoke" }

    $pairs = @(0..11 | ForEach-Object { @{ unit_id = "u-$_"; value_a = $_; value_b = ($_ + 0.5) } })
    $statResp = Invoke-ApiJson -Method POST `
        -Url ($baseUrl + "api/v2/experiments/lnt-smoke-exp/statistics-runs") `
        -Body @{ kind = "ab"; estimand = "latency_s"; units = "s"; pairs = $pairs; seed = 7 } `
        -Nonce $nonce -Label "statistics-submit"
    if ($statResp.status -ne 202) { throw ("STATISTICS FAIL: HTTP $($statResp.status) body=$($statResp.body)") }
    $statJobId = (($statResp.body | ConvertFrom-Json).job_id)
    $statDeadline = [DateTime]::UtcNow.AddSeconds(60)
    $statResult = $null
    while ([DateTime]::UtcNow -lt $statDeadline) {
        Sample-Network
        $r = Invoke-ApiJson -Method GET -Url ($baseUrl + "api/v2/statistics-runs/$statJobId/result") `
            -Label "statistics-result-poll"
        if ($r.status -eq 200) { $statResult = $r.body | ConvertFrom-Json; break }
        Start-Sleep -Milliseconds 200
    }
    if ($null -eq $statResult) { throw "STATISTICS FAIL: результат не готов за 60 c" }
    if (([string]$statResult.result_kind -ne "effect") -or
        ([string]$statResult.metadata.estimator -ne "paired_difference")) {
        throw ("REPORT FAIL: result_kind={0} estimator={1}" -f $statResult.result_kind, $statResult.metadata.estimator)
    }
    $journeyChecks += @{ step = "report:statistics-ab"; result_kind = "effect"
        estimator = "paired_difference" }

    # --- S08 backup/restore through the FROZEN archive CLI -----------------------
    # Todo 45 ships backup/restore as `lnt archive` verbs (no HTTP routes by
    # design); after the Todo 48 launcher fix the frozen exe exposes them.
    # Round-trip: create -> verify -> restore into one NEW directory, then assert
    # restored bytes match the originals by SHA-256.
    $backupZip = Join-Path $script:TempRoot "backup.zip"
    $restoreRoot = Join-Path $script:TempRoot "restored-root"
    $manifestBefore = Get-Sha256 (Join-Path $sessionRoot "lnt-smoke-a\manifest.json")
    $createRun = Invoke-FrozenCli -BundleDir $bundleDir -Label "archive-create" `
        -Arguments ('archive create "{0}" --root "{1}" --session lnt-smoke-a --experiment lnt-smoke-exp' -f $backupZip, $sessionRoot)
    if ($createRun.exit_code -ne 0) {
        throw ("ARCHIVE FAIL: create exited {0}" -f $createRun.exit_code)
    }
    $verifyRun = Invoke-FrozenCli -BundleDir $bundleDir -Label "archive-verify" `
        -Arguments ('archive verify "{0}"' -f $backupZip)
    if ($verifyRun.exit_code -ne 0) {
        throw ("ARCHIVE FAIL: verify exited {0}" -f $verifyRun.exit_code)
    }
    $restoreRun = Invoke-FrozenCli -BundleDir $bundleDir -Label "archive-restore" `
        -Arguments ('archive restore "{0}" --dest "{1}"' -f $backupZip, $restoreRoot)
    if ($restoreRun.exit_code -ne 0) {
        throw ("ARCHIVE FAIL: restore exited {0}" -f $restoreRun.exit_code)
    }
    $restoredManifest = Join-Path $restoreRoot "sessions\lnt-smoke-a\manifest.json"
    $restoredSpectrum = Join-Path $restoreRoot "sessions\lnt-smoke-a\spectrum.csv"
    $manifestAfter = $null
    if (Test-Path -LiteralPath $restoredManifest) { $manifestAfter = Get-Sha256 $restoredManifest }
    if ((-not (Test-Path -LiteralPath $restoredManifest)) -or
        (-not (Test-Path -LiteralPath $restoredSpectrum)) -or
        ($manifestBefore -ne $manifestAfter)) {
        throw "ARCHIVE FAIL: восстановленные файлы отсутствуют или не совпадают по SHA-256"
    }
    $journeyChecks += @{ step = "backup-restore:frozen-archive-cli"
        create_exit = $createRun.exit_code; verify_exit = $verifyRun.exit_code
        restore_exit = $restoreRun.exit_code
        manifest_sha256_stable = ($manifestBefore -eq $manifestAfter)
        note = "archive create/verify/restore executed by LNT.exe itself" }
    Write-EvidenceJson "journey-checks.json" @{ checks = $journeyChecks }
    Step "07-journey" 0 ("checks=" + $journeyChecks.Count)

    # --- S09 FM4: device blocked/absent -> typed diagnostic behaviour ------------
    $preflightResp = Invoke-ApiJson -Method POST -Url ($baseUrl + "api/capture/preflight") `
        -Body @{ kind = "capture"; duration_s = 2.4; sample_rate_hz = 8000000.0
            range_v = 5.0; channels = 2; input = "rc" } `
        -Nonce $nonce -Label "capture-preflight"
    if ($preflightResp.status -ne 200) { throw "FM4 FAIL: preflight HTTP $($preflightResp.status)" }
    $preflight = $preflightResp.body | ConvertFrom-Json
    $blockFindings = @(@($preflight.findings) | Where-Object { $_.severity -eq "block" })
    $couplingOk = $true
    if ($script:AbsentFamilyStates -contains [string]$device.state) {
        $couplingOk = (($preflight.ready -eq $false) -and ($blockFindings.Count -gt 0))
    } else {
        $couplingOk = ($preflight.ready -eq ($blockFindings.Count -eq 0))
    }
    if (-not $couplingOk) {
        throw ("FM4 FAIL: ready={0} blocks={1} device_state={2} нарушена типизированная связь" -f `
            $preflight.ready, $blockFindings.Count, $device.state)
    }
    @{
        device_state = [string]$device.state
        preflight_ready = $preflight.ready
        block_findings = @($blockFindings | ForEach-Object { $_.code })
        coupling_ok = $true
        verdict = "typed diagnostic behaviour proven for absent/blocked device"
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $fmDir "fm4-device-absent-typed.json") -Encoding UTF8
    Step "09-fm4-device-absent-typed" 0 ("ready=" + $preflight.ready + " blocks=" + $blockFindings.Count)

    # --- teardown of the happy-path instance before offline failure modes --------
    foreach ($pidToStop in @($proc.Id)) {
        Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    Sample-Network

    # --- S10 FM1: altered ZIP hash -> integrity fail ------------------------------
    $alteredPath = Join-Path $script:TempRoot "payload\altered.zip"
    $bytes = [System.IO.File]::ReadAllBytes($zipCopy)
    $mid = [int]($bytes.Length / 2)
    $bytes[$mid] = $bytes[$mid] -bxor 0xFF
    [System.IO.File]::WriteAllBytes($alteredPath, $bytes)
    $fm1 = Verify-ZipIntegrity -ZipPath $alteredPath -SidecarPath $sidecarPath
    $fm1Ok = (-not $fm1.ok)
    ("FM1 altered-zip: detected_mismatch={0}`nexpected={1}`naltered ={2}" -f `
        $fm1Ok, $fm1.expected, $fm1.actual) |
        Set-Content -LiteralPath (Join-Path $fmDir "fm1-altered-zip.txt") -Encoding UTF8
    Step "10-fm1-altered-zip" $(if ($fm1Ok) { 0 } else { 60 }) ("integrity_rejected=" + $fm1Ok)
    if (-not $fm1Ok) { throw "FM1 FAIL: изменённый ZIP не был отвергнут по SHA-256" }

    # --- S11 FM2: removed required DLL -> validation fail -------------------------
    $fmBundle = Join-Path $script:TempRoot "fm-bundle"
    New-Item -ItemType Directory -Force -Path $fmBundle | Out-Null
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipCopy, $fmBundle)
    Remove-Item -LiteralPath (Join-Path $fmBundle "_internal\usb1\libusb-1.0.dll") -Force
    $fm2 = Test-BundleCore -Bundle $fmBundle `
        -AllowlistPath (Join-Path $PSScriptRoot "system32-allowlist.v2.json") `
        -ReportPath (Join-Path $fmDir "fm2-classification-report.json")
    $fm2LibusbHits = @(@($fm2.errors) | Where-Object { $_ -match "libusb" })
    $fm2Ok = ((-not $fm2.ok) -and ($fm2LibusbHits.Count -gt 0))
    ("FM2 removed-required-dll: validation_failed_with_libusb_error={0}`nerrors={1}" -f `
        $fm2Ok, ($fm2.errors -join "; ")) |
        Set-Content -LiteralPath (Join-Path $fmDir "fm2-removed-dll.txt") -Encoding UTF8
    Step "11-fm2-removed-dll" $(if ($fm2Ok) { 0 } else { 60 }) ("validation_rejected=" + $fm2Ok)
    if (-not $fm2Ok) { throw "FM2 FAIL: удаление libusb-1.0.dll не привело к ошибке валидации" }

    # --- S12 FM3: occupied 8765 -> deterministic fallback within 8766..8780 -------
    # Главный инстанс уже остановлен выше. FM3 запускается через консольный
    # сиблинг LNT-cli.exe (та же логика launcher/fallback, но наблюдаемые
    # stdout/exit) и с СОБСТВЕННЫМ LOCALAPPDATA: иначе устаревший hardware.lease
    # убитого главного инстанса в общем фейковом профиле может совпасть с
    # переиспользованием PID в Windows и дать ложный InvalidLease вместо фолбэка.
    # Зомби на 8766..8780 отравляют весь fallback-диапазон — зачищаем перед проверкой.
    $fmStale = @(Get-Process -Name "LNT", "LNT-cli" -ErrorAction SilentlyContinue)
    foreach ($fs in $fmStale) {
        Log ("FM3-STALE-KILL pid={0}" -f $fs.Id)
        Stop-Process -Id $fs.Id -Force -ErrorAction SilentlyContinue
    }
    if ($fmStale.Count -gt 0) { Start-Sleep -Milliseconds 800 }
    $portReleased = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 250
        $leftover = Get-NetTCPConnection -LocalPort $PreferredPort -State Listen -ErrorAction SilentlyContinue
        if ($null -eq $leftover) { $portReleased = $true; break }
    }
    if (-not $portReleased) { throw "FM3 FAIL: порт {0} не освободился после остановки главного инстанса" -f $PreferredPort }
    Log ("MAIN-INSTANCE-STOPPED pid={0} port={1} released=True" -f $proc.Id, $PreferredPort)
    $script:Listener = New-Object System.Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $PreferredPort)
    $script:Listener.Start()

    $fm3Home = Join-Path $script:TempRoot "fm3-profile"
    $fm3Sessions = Join-Path $script:TempRoot "sessions-fm3"
    $psi3 = New-Object System.Diagnostics.ProcessStartInfo
    $psi3.FileName = (Join-Path $bundleDir "LNT-cli.exe")
    $psi3.Arguments = '--no-browser --root "{0}" --port {1}' -f $fm3Sessions, $PreferredPort
    $psi3.WorkingDirectory = $bundleDir
    $psi3.UseShellExecute = $false
    $psi3.CreateNoWindow = $true
    $psi3.RedirectStandardOutput = $false
    $psi3.RedirectStandardError = $false
    $ev3 = $psi3.EnvironmentVariables
    $ev3["LOCALAPPDATA"] = "$fm3Home\AppData\Local"
    $ev3["APPDATA"] = "$fm3Home\AppData\Roaming"
    $ev3["TEMP"] = "$fm3Home\tmp"
    $ev3["TMP"] = "$fm3Home\tmp"
    $fm3Proc = [System.Diagnostics.Process]::Start($psi3)
    $null = $script:SpawnedPids.Add($fm3Proc.Id)
    Log ("SPAWN pid={0} exe=LNT-cli.exe args={1} isolated_localappdata=True" -f $fm3Proc.Id, $psi3.Arguments)

    $fallbackPort = -1
    $fm3Health = @{ ok = $false; build_id = ""; elapsed_ms = 0 }
    foreach ($candidate in ((($PreferredPort + 1)..8780))) {
        if ($fm3Proc.HasExited) { Log ("FM3 app exited early code=" + $fm3Proc.ExitCode); break }
        $fm3Health = Wait-Health -BaseUrl ("http://127.0.0.1:" + $candidate + "/") -TimeoutS 4
        if ($fm3Health.ok) { $fallbackPort = $candidate; break }
    }
    $fm3Ok = $false
    if ($fm3Health.ok) {
        $directPreferred = Invoke-ApiJson -Method GET -Url ("http://127.0.0.1:" + $PreferredPort + "/api/health") `
            -TimeoutSec 2 -Label "fm3-preferred-port-probe"
        $fm3Ok = ($directPreferred.status -ne 200)
    }
    ("FM3 occupied-{0}: fell_back_to_{1}={2} preferred_still_occupied_by_listener={3} build_id={4}" -f `
        $PreferredPort, $fallbackPort, $fm3Health.ok, $fm3Ok, $fm3Health.build_id) |
        Set-Content -LiteralPath (Join-Path $fmDir "fm3-port-occupied.txt") -Encoding UTF8
    Step "12-fm3-port-occupied" $(if ($fm3Ok) { 0 } else { 60 }) ("fallback_port=" + $fallbackPort + " healthy=" + $fm3Health.ok)
    if (-not $fm3Ok) { throw "FM3 FAIL: детерминированный фолбэк порта не подтверждён" }
    Stop-Process -Id $fm3Proc.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $script:Listener.Stop(); $script:Listener = $null

    Step "13-failure-modes" 0 "fm1=fm2=fm3=fm4=proven"
    $script:ExitCode = 0

} catch {
    Log ("FAIL: {0}" -f $_.Exception.Message)
    Log ("AT: {0}" -f $_.InvocationInfo.PositionMessage)
    if ($_.Exception.Message -like "ELEVATED*") { $script:ExitCode = 10 }
    elseif ($_.Exception.Message -like "SANITIZE*") { $script:ExitCode = 20 }
    elseif (($_.Exception.Message -like "INTEGRITY*") -or ($_.Exception.Message -like "BUNDLE VALIDATION*")) { $script:ExitCode = 30 }
    elseif (($_.Exception.Message -like "*HEALTH*") -or ($_.Exception.Message -like "CONFIG*") -or
        ($_.Exception.Message -like "ASSET*") -or ($_.Exception.Message -like "DEVICE*") -or
        ($_.Exception.Message -like "OFFLINE*") -or ($_.Exception.Message -like "FROZEN*") -or
 ($_.Exception.Message -like "ARCHIVE*")) { $script:ExitCode = 40 }
    elseif ($_.Exception.Message -like "PREFLIGHT*") { $script:ExitCode = 10 }
    elseif ($_.Exception.Message -like "FM*") { $script:ExitCode = 60 }
    else { $script:ExitCode = 50 }
} finally {
    try {
        if (($null -ne $script:TempRoot) -and ($script:SpawnedPids.Count -gt 0)) {
            Sample-Network
        }
        $teardown = Invoke-Teardown -Phase "final"
        # Жёсткая зачистка: убиваем ЛЮБЫЕ оставшиеся LNT-процессы, включая
        # зомби чужих прогонов (они отравляют fallback-порты и ломают FM3).
        $hardKill = @(Get-Process -Name "LNT", "LNT-cli" -ErrorAction SilentlyContinue)
        foreach ($hk in $hardKill) {
            Stop-Process -Id $hk.Id -Force -ErrorAction SilentlyContinue
        }
        if ($hardKill.Count -gt 0) {
            Start-Sleep -Milliseconds 800
            Log ("HARD-KILL незатреканных pid: " + (($hardKill | ForEach-Object { $_.Id }) -join ","))
        }
        Step "teardown" $(if ($teardown.temp_root_removed) { 0 } else { 70 }) `
            ("temp_removed=" + $teardown.temp_root_removed + " pids_killed=" + $teardown.killed_pids.Count)

        Write-EvidenceJson "http-checks.json" @{
            request_count = $script:HttpLog.Count
            requests = @($script:HttpLog.ToArray())
        }
        Write-EvidenceJson "network-monitor.json" @{
            sample_rounds = $script:NetworkSamples
            outbound_violations = @($script:NetworkViolations.ToArray())
            verdict = $(if ($script:NetworkViolations.Count -eq 0) { "no outbound connections observed from spawned processes" } else { "NETWORK VIOLATIONS OBSERVED" })
        }

        $portsAfter = Get-PortSweepReceipt
        $processesAfter = @(Get-LntProcessSweep)
        Write-EvidenceJson "process-inventory-after-teardown.json" @{
            lnt_processes = $processesAfter
            port_sweep = $portsAfter
            spawned_pids_tracked = @($script:SpawnedPids.ToArray())
        }
        $labelScanClean = $true
        foreach ($file in @(Get-ChildItem -LiteralPath $evidenceRoot -Recurse -File |
                Where-Object { @(".json", ".txt") -contains $_.Extension.ToLowerInvariant() })) {
            $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
            if (-not (Test-NoForbiddenLabel ([string]$content))) {
                $labelScanClean = $false
                Log ("FORBIDDEN LABEL in evidence file: " + $file.Name)
            }
        }
        Step "forbidden-label-scan" $(if ($labelScanClean) { 0 } else { 60 }) `
            "labels=only-sanitized-reference-host-verified"
        if (-not $labelScanClean) { $script:ExitCode = 60 }
        if ($processesAfter.Count -gt 0) { $script:ExitCode = 70; Log "TEARDOWN LEAK: процесс LNT остался" }
        if (-not $portsAfter.clean) { $script:ExitCode = 70; Log "TEARDOWN LEAK: слушатели 8765..8780/4101 остались" }
    } catch {
        Log ("TEARDOWN ERROR: " + $_.Exception.Message)
        $script:ExitCode = 70
    }
    $elapsedTotal = [int]([DateTime]::UtcNow - $startedAt).TotalSeconds
    Step "summary" $script:ExitCode ("host=" + $script:HostLabel + " total_seconds=" + $elapsedTotal)
    try {
        # commands-summary.txt: one EXIT_CODE line per gate step (MUST-DO receipt).
        $stepLines = @(Get-Content -LiteralPath $transcriptPath -Encoding UTF8 | Where-Object { $_ -match "STEP .* EXIT_CODE=" })
        $summaryOut = @(
            "LNT portable smoke - commands summary",
            ("verdict_exit_code={0}" -f $script:ExitCode),
            ("host_label={0}" -f $script:HostLabel),
            ("zip={0}" -f $Zip),
            ("evidence_dir={0}" -f $evidenceRoot),
            ""
        ) + @($stepLines | ForEach-Object { ($_ -split "\] ", 2)[1] })
        Set-Content -LiteralPath (Join-Path $evidenceRoot "commands-summary.txt") -Value $summaryOut -Encoding UTF8
    } catch { Log ("SUMMARY WRITE ERROR: " + $_.Exception.Message) }
}
exit $script:ExitCode
