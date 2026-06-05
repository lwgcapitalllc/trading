<#
.SYNOPSIS
    LWG Capital — NinjaTrader 8 (futures) VPS bootstrap / recovery script.

    Companion to bootstrap_vps.ps1 (which covers the MT5 algos side). This one
    rebuilds the NinjaTrader 8 + nt8_agent side of the same VPS.

    HONEST SCOPE NOTE: your uploaded docs include a full runbook for the MT5
    suite (SETUP.md) but NO equivalent for NinjaTrader. What the docs DO tell us
    is the integration shape: NT8 on the VPS, a nt8_agent.py on :8765 started by
    a scheduled task named `LucidFlexAgent`, health = NT8 process + Strategy
    Analyzer open + clean NinjaScript compile. Everything keyed off those facts
    is grounded; the rest uses standard NinjaTrader-on-VPS layout and is exposed
    as parameters so you can correct it.

    CANNOT be automated (GUI / account work) — detected + reported instead:
      - Installing the NinjaTrader 8 desktop app.
      - Logging into your data/broker connection (and any 2FA / license accept).
      - Compiling NinjaScript (NT8 compiles on launch / F5, not from a script).

.PARAMETER Nt8Dir
    NinjaTrader 8 install folder. Default: C:\Program Files\NinjaTrader 8

.PARAMETER Nt8UserDir
    NT8 user-data folder (strategies, db, workspaces, templates). MUST be the
    profile of the account NT8 runs under (your `trader` user), not admin.
    Default: the current user's Documents\NinjaTrader 8.

.PARAMETER RestoreUserData
    Opt-in. Restore the NT8 user-data folder from -UserDataBackup.

.PARAMETER UserDataBackup
    Path (local dir, network share, or already-cloned folder) holding a backup
    of your `NinjaTrader 8` user folder. Required if -RestoreUserData is set.

.PARAMETER Force
    Allow -RestoreUserData to overwrite an existing populated user folder.

.PARAMETER StrategySourceDir
    Optional. Folder in your repo containing NinjaScript .cs strategy files to
    deploy into <Nt8UserDir>\bin\Custom\Strategies. If omitted, this step is skipped.

.PARAMETER AgentScript
    Optional. Full path to nt8_agent.py. Used only for the python-deps step.

.PARAMETER AgentReq
    Optional. Path to a requirements.txt for the agent. If given, installed
    instead of the best-effort default package set.

.PARAMETER AgentTaskXml
    Optional. Path to the scheduled-task XML for the agent. If given (and you're
    elevated), the LucidFlexAgent task is (re)created from it.

.PARAMETER AgentTaskName
    Scheduled task that runs the agent. Default: LucidFlexAgent

.PARAMETER AgentPort
    TCP port the agent listens on. Default: 8765

.PARAMETER TraderUser
    Windows account the agent task runs as. Default: trader

.PARAMETER PythonExe
    Full path to python.exe. Auto-detected if omitted.

.EXAMPLE
    # Fresh box, restore NT8 data from a backup share, deploy strategies from repo:
    .\bootstrap_ninjatrader.ps1 -RestoreUserData -UserDataBackup '\\nas\backups\NinjaTrader 8' `
        -StrategySourceDir 'C:\trading\command-center\strategies' `
        -AgentScript 'C:\trading\nt8_agent.py' -AgentTaskXml 'C:\trading\scheduler\lucidflex_agent_task.xml'

.NOTES
    Run as the `trader` user where possible (so the NT8 user folder + agent task
    line up), elevated if you want the task created. Health check at the end only
    confirms the agent PORT is open and NT8 is running — compile status comes from
    the command-center NT8-compile health dot, which reads NT8's own logs.
#>

[CmdletBinding()]
param(
    [string] $Nt8Dir       = 'C:\Program Files\NinjaTrader 8',
    [string] $Nt8UserDir,   # auto-resolved below (trader profile, then Administrator) if not passed
    [switch] $RestoreUserData,
    [string] $UserDataBackup,
    [switch] $Force,
    [string] $StrategySourceDir = 'C:\trading\algos\markets\futures\lucid_flex',
    [string] $AgentScript  = 'C:\trading\algos\markets\futures\lucid_flex\tools\nt8_agent.py',
    [string] $AgentReq,
    [string] $AgentTaskXml,
    [string] $AgentTaskName = 'LucidFlexAgent',
    [int]    $AgentPort     = 8765,
    [string] $TraderUser    = 'trader',   # everything runs as trader (admin login)
    [string] $PythonExe
)

$ErrorActionPreference = 'Stop'

# Resolve the NT8 user folder if the caller didn't pin it: trader's profile is the
# target state; fall back to Administrator for older boxes. trader is admin, so it
# can read either.
if (-not $Nt8UserDir) {
    $candidates = @(
        'C:\Users\trader\Documents\NinjaTrader 8',
        'C:\Users\Administrator\Documents\NinjaTrader 8'
    )
    $Nt8UserDir = ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
    if (-not $Nt8UserDir) { $Nt8UserDir = $candidates[0] }
}

# Confirmed agent deps (no requirements.txt in the repo): nt8_agent.py imports
# flask + pywinauto + comtypes; vps_backtest_runner.py imports pywinauto + comtypes.
# Everything else is stdlib. pip will pull pywinauto's own deps (incl. pywin32).
$AgentDepsDefault = @('flask', 'pywinauto', 'comtypes')

$script:Results = [ordered]@{}
function Write-Phase { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok    { param($m) Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Info  { param($m) Write-Host "  [..]   $m" -ForegroundColor Gray }
function Write-Warn2 { param($m) Write-Host "  [WARN] $m" -ForegroundColor Yellow }
function Write-Err2  { param($m) Write-Host "  [ERR]  $m" -ForegroundColor Red }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Resolve-Python {
    if ($PythonExe -and (Test-Path $PythonExe)) { return $PythonExe }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                     'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe')) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
function ConvertFrom-SecureToPlain {
    param([System.Security.SecureString]$Secure)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}
function Test-Port {
    param([int]$Port)
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        if ($ok -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
        $c.Close(); return $false
    } catch { return $false }
}
function Invoke-Phase {
    param([string]$Label, [scriptblock]$Body)
    try { & $Body } catch { Write-Err2 "$Label : $($_.Exception.Message)"; $script:Results[$Label] = "FAILED: $($_.Exception.Message)" }
}

# --------------------------------------------------------------------------
Write-Host "LWG Capital — NinjaTrader 8 Bootstrap" -ForegroundColor White
Write-Host "Install: $Nt8Dir   UserData: $Nt8UserDir" -ForegroundColor DarkGray

# Phase 0 — Pre-flight ------------------------------------------------------
function P0 {
    Write-Phase 'Phase 0 — Pre-flight'
    if (Test-Admin) { Write-Ok 'Elevated.' } else { Write-Warn2 'Not elevated — agent task creation will be skipped.' }
    if ($env:USERNAME -ne $TraderUser) {
        Write-Warn2 "Running as '$env:USERNAME', not '$TraderUser'. The NT8 user folder + agent task should belong to '$TraderUser' — re-run as that account if these don't match."
    }
    $script:Py = Resolve-Python
    if ($script:Py) { Write-Ok ("python: $script:Py — " + (& $script:Py --version 2>&1)) }
    else { Write-Warn2 'python.exe not found — agent dependency step will be skipped.' }
    $script:Results['Pre-flight'] = 'OK'
}

# Phase 1 — NT8 install -----------------------------------------------------
function P1 {
    Write-Phase 'Phase 1 — NinjaTrader 8 install'
    if (-not (Test-Path $Nt8Dir)) {
        Write-Warn2 "NinjaTrader 8 NOT installed at $Nt8Dir."
        Write-Warn2 'Download from ninjatrader.com, install, then re-run. (Cannot be scripted — GUI installer.)'
        $script:Nt8Present = $false
        $script:Results['NT8 install'] = 'missing'
        return
    }
    $exe = Get-ChildItem $Nt8Dir -Recurse -Filter 'NinjaTrader.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { Write-Ok "NinjaTrader.exe found: $($exe.FullName)"; $script:Nt8Exe = $exe.FullName; $script:Nt8Present = $true; $script:Results['NT8 install'] = 'OK' }
    else { Write-Warn2 "Folder exists but NinjaTrader.exe not found under it."; $script:Nt8Present = $false; $script:Results['NT8 install'] = 'exe missing' }
}

# Phase 2 — .NET 4.8 (NT8 prerequisite) -------------------------------------
function P2 {
    Write-Phase 'Phase 2 — .NET Framework 4.8'
    $rel = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full' -Name Release -ErrorAction SilentlyContinue).Release
    if ($rel -ge 528040) { Write-Ok ".NET 4.8+ present (release $rel)." ; $script:Results['.NET 4.8'] = 'OK' }
    elseif ($rel)        { Write-Warn2 ".NET present but older than 4.8 (release $rel). NT8 needs 4.8 — install it."; $script:Results['.NET 4.8'] = 'too old' }
    else                 { Write-Warn2 '.NET Framework 4.x not detected. Install .NET Framework 4.8 (NT8 requirement).'; $script:Results['.NET 4.8'] = 'missing' }
}

# Phase 3 — Restore NT8 user-data folder ------------------------------------
function P3 {
    Write-Phase 'Phase 3 — Restore NT8 user-data folder'
    if (-not $RestoreUserData) {
        $hasData = (Test-Path $Nt8UserDir) -and (Get-ChildItem $Nt8UserDir -ErrorAction SilentlyContinue | Select-Object -First 1)
        if (-not $hasData) {
            Write-Warn2 "No NT8 user folder at $Nt8UserDir and -RestoreUserData not set."
            Write-Warn2 'RESILIENCY NOTE: your backup system does not cover this folder. If you have no backup,'
            Write-Warn2 'strategies survive only if their .cs source is in git; db/workspaces/templates are lost.'
        } else {
            Write-Info 'User folder present — restore skipped (pass -RestoreUserData to overwrite from backup).'
        }
        $script:Results['Restore NT8 data'] = 'skipped'
        return
    }
    if (-not $UserDataBackup) { throw '-RestoreUserData set but -UserDataBackup not provided.' }
    if (-not (Test-Path $UserDataBackup)) { throw "Backup source not found: $UserDataBackup" }
    if ((Get-Process NinjaTrader -ErrorAction SilentlyContinue)) { throw 'NinjaTrader is running. Close it before restoring its data folder.' }

    $populated = (Test-Path $Nt8UserDir) -and (Get-ChildItem $Nt8UserDir -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($populated -and -not $Force) { throw "$Nt8UserDir already has data. Re-run with -Force to overwrite (DESTRUCTIVE)." }

    if (-not (Test-Path $Nt8UserDir)) { New-Item -ItemType Directory -Path $Nt8UserDir -Force | Out-Null }
    Write-Info "Copying $UserDataBackup -> $Nt8UserDir"
    Copy-Item (Join-Path $UserDataBackup '*') $Nt8UserDir -Recurse -Force
    Write-Ok 'NT8 user folder restored. NT8 will recompile NinjaScript on next launch.'
    $script:Results['Restore NT8 data'] = 'OK'
}

# Phase 4 — Deploy NinjaScript strategies from repo -------------------------
function P4 {
    Write-Phase 'Phase 4 — Deploy NinjaScript strategies'
    if (-not $StrategySourceDir) { Write-Info 'Skipped (no -StrategySourceDir given).'; $script:Results['Deploy strategies'] = 'skipped'; return }
    if (-not (Test-Path $StrategySourceDir)) { throw "Strategy source not found: $StrategySourceDir" }
    $dest = Join-Path $Nt8UserDir 'bin\Custom\Strategies'
    if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }
    $cs = Get-ChildItem $StrategySourceDir -Recurse -Filter '*.cs' -ErrorAction SilentlyContinue
    if (-not $cs) { Write-Warn2 "No .cs files under $StrategySourceDir"; $script:Results['Deploy strategies'] = 'none found'; return }
    foreach ($f in $cs) { Copy-Item $f.FullName $dest -Force; Write-Ok "deployed $($f.Name)" }
    Write-Warn2 'Strategies copied. They are NOT compiled yet — launch NT8 and press F5 (or it compiles on startup).'
    $script:Results['Deploy strategies'] = "OK ($($cs.Count) files)"
}

# Phase 5 — nt8_agent deps + scheduled task ---------------------------------
function P5 {
    Write-Phase 'Phase 5 — nt8_agent (port + task)'
    # Python deps
    if ($script:Py) {
        if ($AgentReq -and (Test-Path $AgentReq)) {
            Write-Info "pip install -r $AgentReq"
            & $script:Py -m pip install -r $AgentReq --break-system-packages 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Ok 'Agent requirements installed.' } else { Write-Warn2 "pip -r exit $LASTEXITCODE" }
        } else {
            Write-Info "No -AgentReq given; installing best-effort default set."
            foreach ($p in $AgentDepsDefault) {
                & $script:Py -m pip install $p --break-system-packages 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) { Write-Ok "$p installed." } else { Write-Warn2 "could not install $p" }
            }
            Write-Warn2 'Verify these match nt8_agent.py / vps_backtest_runner.py imports.'
        }
    } else { Write-Warn2 'No python — skipped agent deps.' }

    # Scheduled task
    $exists = (& schtasks /query /tn $AgentTaskName 2>$null) -and ($LASTEXITCODE -eq 0)
    if ($exists) {
        Write-Ok "Scheduled task '$AgentTaskName' already exists."
    } elseif ($AgentTaskXml -and (Test-Path $AgentTaskXml)) {
        if (Test-Admin) {
            $sec = Read-Host -AsSecureString "Password for '$TraderUser' (to register $AgentTaskName)"
            $pass = ConvertFrom-SecureToPlain $sec
            try {
                & schtasks /create /tn $AgentTaskName /xml $AgentTaskXml /ru $TraderUser /rp $pass /f | Out-Null
                if ($LASTEXITCODE -eq 0) { Write-Ok "Created '$AgentTaskName'." } else { Write-Warn2 "schtasks /create exit $LASTEXITCODE" }
            } finally { $pass = $null }
        } else { Write-Warn2 "Task XML given but not elevated — re-run as admin to create '$AgentTaskName'." }
    } else {
        Write-Warn2 "Task '$AgentTaskName' not found and no -AgentTaskXml given."
        Write-Warn2 "This task has no XML in the repo — it is created from your MAC by running:"
        Write-Warn2 "    python3 algos/markets/futures/lucid_flex/tools/setup_agent_task.py"
        Write-Warn2 "(it SSHes to the VPS and registers the task). Run that, then re-run this script."
    }

    # Start it
    & schtasks /run /tn $AgentTaskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Info "Started '$AgentTaskName'."; Start-Sleep -Seconds 5 }
    $script:Results['nt8_agent task'] = if ($exists -or ($LASTEXITCODE -eq 0)) { 'OK' } else { 'needs setup' }
}

# Phase 6 — Launch reminder + health ----------------------------------------
function P6 {
    Write-Phase 'Phase 6 — Launch + health check'
    if (-not (Get-Process NinjaTrader -ErrorAction SilentlyContinue)) {
        Write-Warn2 'NinjaTrader is not running. Launch it, log into your data/broker connection,'
        Write-Warn2 'confirm strategies compiled (NinjaScript Editor → no errors), and open Strategy Analyzer.'
        if ($script:Nt8Present -and $script:Nt8Exe) { Write-Info "Launch: `"$script:Nt8Exe`"" }
    } else { Write-Ok 'NinjaTrader process is running.' }

    if (Test-Port -Port $AgentPort) {
        Write-Ok "nt8_agent reachable on :$AgentPort."
        $script:Results['Agent port'] = 'OK'
        # The agent exposes GET /health and GET /nt-health — probe them for real status.
        foreach ($route in @('/health', '/nt-health')) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$AgentPort$route" -UseBasicParsing -TimeoutSec 5
                Write-Ok "GET $route -> HTTP $($r.StatusCode)"
            } catch { Write-Warn2 "GET $route failed: $($_.Exception.Message)" }
        }
    } else {
        Write-Warn2 "Nothing listening on :$AgentPort yet. Check the '$AgentTaskName' task / agent log (GET /agent-log)."
        $script:Results['Agent port'] = 'closed'
    }

    Write-Info 'Compile status: GET /nt-compile-status, or the command-center NT8-compile health dot.'
}

P0
Invoke-Phase 'NT8 install'      { P1 }
Invoke-Phase '.NET 4.8'         { P2 }
Invoke-Phase 'Restore NT8 data' { P3 }
Invoke-Phase 'Deploy strategies'{ P4 }
Invoke-Phase 'nt8_agent task'   { P5 }
Invoke-Phase 'Health'           { P6 }

Write-Phase 'Summary'
foreach ($k in $script:Results.Keys) {
    $v = $script:Results[$k]
    $color = if ($v -like 'OK*') { 'Green' } elseif ($v -like '*FAILED*' -or $v -like '*missing*' -or $v -like '*closed*' -or $v -like '*too old*') { 'Red' } else { 'Yellow' }
    Write-Host ("  {0,-18} {1}" -f $k, $v) -ForegroundColor $color
}

Write-Host "`nManual steps this script cannot do for you:" -ForegroundColor White
Write-Host "  - Install the NinjaTrader 8 desktop app." -ForegroundColor Gray
Write-Host "  - Log into your data/broker connection (and any 2FA / license accept)." -ForegroundColor Gray
Write-Host "  - Compile NinjaScript — NT8 does this on launch / F5, then check for errors." -ForegroundColor Gray
Write-Host "  - Open Strategy Analyzer (required for the command-center NinjaTrader health dot)." -ForegroundColor Gray
