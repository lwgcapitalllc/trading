<#
.SYNOPSIS
    LWG Capital — VPS bootstrap / disaster-recovery script.

    Rebuilds the algo trading suite on a fresh (or wiped) Windows VPS from the
    GitHub repo. Idempotent: safe to re-run. Each phase checks current state
    before acting, and a failed phase reports the problem and moves on rather
    than aborting the whole run.

    No bots are registered yet (the first-attempt suite was deleted 2026-06-22 — see
    algos/docs/BOT_DEPLOYMENT_INFRA.md). This script provisions the FOUNDATION: repo,
    Python, deps, the SYS_ task scaffold, and the secrets mechanism. When a real
    strategy is ready to deploy as a bot, add its MT5 terminal + account to the two
    lists in "Static configuration" below and its task to $Tasks — the per-bot data
    is the only thing that changes; the machinery here does not.

    The two things it CANNOT do for you (and will instead detect + report) are:
      1. Installing each registered bot's MT5 terminal (GUI installer + manual login).
      2. Filling in real account passwords in credentials.json.

.DESCRIPTION
    Phases (run in order):
      0. Pre-flight ........ admin check, locate git + python
      1. Clone / update .... clone repo to -RepoRoot, or git pull if present
      2. Python deps ....... pip install the runtime packages
      3. MT5 check ......... verify each registered bot's terminal exists (none yet)
      4. Secrets scaffold .. create credentials.json / users.json templates if absent
      5. Task Scheduler .... create the SYS_ tasks (no BOT_ tasks registered yet)
      6. Start ............. clear stale lock, run SYS_STARTUP, verify processes

.PARAMETER RepoUrl
    Git URL to clone. Default: the LWG Capital trading monorepo.

.PARAMETER RepoRoot
    Where the repo lives on the VPS. Default: C:\trading

.PARAMETER Branch
    Branch to check out for code. Default: main

.PARAMETER SkipDeps
    Skip the pip install phase.

.PARAMETER SkipTasks
    Skip the Task Scheduler phase.

.PARAMETER NoStart
    Do everything except starting the bots at the end.

.PARAMETER TraderUser
    Windows account the scheduled tasks run as. Default: trader

.PARAMETER PythonExe
    Full path to python.exe. Auto-detected if omitted.

.EXAMPLE
    # Fresh VPS, full rebuild:
    .\bootstrap_vps.ps1

.EXAMPLE
    # Re-run on a partially-set-up box:
    .\bootstrap_vps.ps1

.NOTES
    Run from an ELEVATED PowerShell prompt (Task Scheduler creation needs admin).
    You will be prompted ONCE for the `trader` account password (entered as a
    secure string — it is never written to disk or echoed).
#>

[CmdletBinding()]
param(
    [string] $RepoUrl    = 'https://github.com/lwgcapitalllc/trading.git',
    [string] $RepoRoot   = 'C:\trading',
    [string] $Branch     = 'main',
    [switch] $SkipDeps,
    [switch] $SkipTasks,
    [switch] $NoStart,
    [string] $TraderUser = 'trader',
    [string] $PythonExe
)

$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------
# Static configuration — derived from the repo docs. Edit here, not inline.
# --------------------------------------------------------------------------
$AlgosRoot     = Join-Path $RepoRoot 'algos'
$LockFile      = Join-Path $AlgosRoot 'mt5_connect.lock'
$TempDir       = 'C:\temp'

# Runtime Python packages. NOTE: `zoneinfo` is a pre-3.9 backport that fails to
# install on Python 3.11 — on Windows the package you actually need for IANA
# timezones is `tzdata`, used here. MetaTrader5 is for live MT5 bots (no bots yet)
# and the command-center MT5 backtest agent.
$PipPackages = @('requests', 'pandas', 'numpy', 'MetaTrader5', 'tzdata')
$PipFlags    = @('--break-system-packages')   # harmless if pip ignores

# Per-bot MT5 terminals (RECOVERY: each must be installed + logged in by hand).
# EMPTY — no bots registered. When deploying a bot, add a row, e.g.:
#   [pscustomobject]@{ Name = 'MT5 <bot>'; Path = 'C:\<dir>\terminal64.exe'; Account = '<acct#>' }
$Mt5Terminals = @()

# Account credentials template (PASSWORDS ARE PLACEHOLDERS — fill in by hand).
# EMPTY accounts — add one entry per bot account when deploying, e.g.:
#   '<acct#>' = [ordered]@{ password = $PlaceholderMarker; server = 'PUPrime-Demo' }
$PlaceholderMarker = 'REPLACE_ME'
$CredentialsTemplate = [ordered]@{
    accounts = [ordered]@{}
}

# Telegram users template (verify the admin Telegram ID before use).
$UsersTemplate = [ordered]@{
    '429207285' = [ordered]@{ name = 'Aaron'; role = 'admin'; added = (Get-Date -Format 'yyyy-MM-dd') }
}

# Task Scheduler tasks: xml file -> task name. SYS_STARTUP must be created first.
$Tasks = @(
    [pscustomobject]@{ Xml = 'startup_coordinator_task.xml'; Name = 'SYS_STARTUP' }
    [pscustomobject]@{ Xml = 'telegram_task.xml';            Name = 'SYS_TELEGRAM' }
    [pscustomobject]@{ Xml = 'monitor_task.xml';             Name = 'SYS_MONITOR' }
    [pscustomobject]@{ Xml = 'deadman_task.xml';             Name = 'SYS_DEADMAN' }
    [pscustomobject]@{ Xml = 'logbackup_task.xml';           Name = 'SYS_LOGBACKUP' }
)
# SYS_PNLTRACKER and SYS_REPORTER were removed 2026-08-05 with the scripts behind them.
# SYS_DEADMAN and SYS_LOGBACKUP were added in the same pass: both had task XMLs sitting in
# algos/scheduler/ that this list never registered, so a rebuilt box came back with no
# dead-man's switch — the one alarm that fires when the box itself dies — and nothing would
# have said so, because a missing alarm is silent by construction.
# BOT_ tasks are started by SYS_STARTUP only — disable so they never auto-fire.
# No bots are registered yet, so this list is empty.
$DisableTasks = @()

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
$script:Results = [ordered]@{}

function Write-Phase { param([string]$Msg) Write-Host "`n=== $Msg ===" -ForegroundColor Cyan }
function Write-Ok    { param([string]$Msg) Write-Host "  [OK]   $Msg" -ForegroundColor Green }
function Write-Info  { param([string]$Msg) Write-Host "  [..]   $Msg" -ForegroundColor Gray }
function Write-Warn2 { param([string]$Msg) Write-Host "  [WARN] $Msg" -ForegroundColor Yellow }
function Write-Err2  { param([string]$Msg) Write-Host "  [ERR]  $Msg" -ForegroundColor Red }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Native {
    # Runs a native command and throws on non-zero exit.
    param([scriptblock]$Cmd, [string]$What)
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
}

function Resolve-Python {
    if ($PythonExe -and (Test-Path $PythonExe)) { return $PythonExe }
    # Prefer a profile-INDEPENDENT (all-users) install first — this is the layout
    # we want going forward so Python isn't tied to one Windows profile.
    foreach ($shared in @('C:\Python311\python.exe', 'C:\Program Files\Python311\python.exe')) {
        if (Test-Path $shared) { return $shared }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # Fall back to per-user installs (the current, profile-bound situation).
    $documented = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    if (Test-Path $documented) { return $documented }
    $documentedAdmin = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'
    if (Test-Path $documentedAdmin) { return $documentedAdmin }
    return $null
}

function Test-PythonProfileBound {
    # True if the resolved python lives inside a per-user profile (AppData), which
    # ties the whole system to one Windows account — the thing we want to avoid.
    param([string]$Path)
    return ($Path -match '\\Users\\[^\\]+\\AppData\\')
}

function ConvertFrom-SecureToPlain {
    param([System.Security.SecureString]$Secure)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try   { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-RunningBots {
    # Returns python processes whose command line references a bot script.
    try {
        Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -and ($_.CommandLine -match 'bot_|--bot |startup_coordinator|telegram|monitor') }
    } catch {
        @()
    }
}

# --------------------------------------------------------------------------
# Phase 0 — Pre-flight
# --------------------------------------------------------------------------
function Invoke-Preflight {
    Write-Phase 'Phase 0 — Pre-flight'

    if (Test-Admin) { Write-Ok 'Running elevated (admin).' }
    else { Write-Warn2 'Not elevated. Task Scheduler phase will be skipped — re-run as admin for it.' }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { throw 'git not found on PATH. Install Git for Windows, then re-run.' }
    Write-Ok ("git: " + (& git --version))

    $script:Py = Resolve-Python
    if (-not $script:Py) {
        throw @'
python.exe not found. Install Python 3.11 — and on a FRESH VPS, install it for
ALL USERS to a profile-independent location so the system isn't tied to one
Windows account. From an elevated prompt, the silent all-users install is:

  py311.exe /quiet InstallAllUsers=1 PrependPath=1 TargetDir=C:\Python311

Then re-run this script (it will find C:\Python311\python.exe), or pass -PythonExe.
'@
    }
    Write-Ok ("python: $script:Py — " + (& $script:Py --version 2>&1))
    if (Test-PythonProfileBound -Path $script:Py) {
        Write-Warn2 'This Python lives inside a user profile (AppData) — it is tied to ONE Windows account.'
        Write-Warn2 'That is the cause of the cross-profile mess (tasks run as one account, Python lives in another).'
        Write-Warn2 'On your NEXT rebuild, install Python for all users to C:\Python311 (see the all-users command'
        Write-Warn2 'in this script''s not-found message) so the box is profile-independent. No action needed today.'
    } else {
        Write-Ok 'Python is in a profile-independent location — good.'
    }

    $script:Results['Pre-flight'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 1 — Clone / update repo
# --------------------------------------------------------------------------
function Invoke-CloneRepo {
    Write-Phase 'Phase 1 — Clone / update repository'
    if (Test-Path (Join-Path $RepoRoot '.git')) {
        Write-Info "Repo already present at $RepoRoot — pulling latest $Branch."
        Push-Location $RepoRoot
        try {
            Invoke-Native { & git fetch origin } 'git fetch'
            Invoke-Native { & git checkout $Branch } 'git checkout'
            Invoke-Native { & git pull origin $Branch } 'git pull'
        } finally { Pop-Location }
        Write-Ok 'Repository updated.'
    } else {
        if (Test-Path $RepoRoot) { throw "$RepoRoot exists but is not a git repo. Remove or relocate it first." }
        Write-Info "Cloning $RepoUrl -> $RepoRoot"
        Invoke-Native { & git clone --branch $Branch $RepoUrl $RepoRoot } 'git clone'
        Write-Ok 'Repository cloned.'
    }
    if (-not (Test-Path $AlgosRoot)) { throw "Expected algos dir not found at $AlgosRoot — wrong repo or layout." }
    $script:Results['Clone/update'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 2 — Python dependencies
# --------------------------------------------------------------------------
function Invoke-PipInstall {
    Write-Phase 'Phase 2 — Python dependencies'
    if ($SkipDeps) { Write-Info 'Skipped (-SkipDeps).'; $script:Results['Python deps'] = 'skipped'; return }

    foreach ($pkg in $PipPackages) {
        Write-Info "pip install $pkg"
        try {
            & $script:Py -m pip install $pkg @PipFlags 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "pip exit $LASTEXITCODE" }
            Write-Ok "$pkg installed."
        } catch {
            Write-Warn2 "Could not install $pkg : $($_.Exception.Message)"
        }
    }
    $script:Results['Python deps'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 3 — MT5 terminal verification (cannot auto-install)
# --------------------------------------------------------------------------
function Invoke-CheckMt5 {
    Write-Phase 'Phase 3 — MT5 terminal verification'
    if ($Mt5Terminals.Count -eq 0) {
        Write-Ok 'No bots registered — no MT5 terminals required yet.'
        $script:Mt5Missing = $false
        $script:Results['MT5 check'] = 'OK (no bots)'
        return
    }
    $missing = @()
    foreach ($t in $Mt5Terminals) {
        if (Test-Path $t.Path) { Write-Ok "$($t.Name) present (acct #$($t.Account))." }
        else { Write-Warn2 "$($t.Name) MISSING — expected at $($t.Path) (acct #$($t.Account))."; $missing += $t }
    }
    if ($missing.Count -gt 0) {
        Write-Warn2 'Install the missing terminal(s) by hand, log each into ONLY its own account,'
        Write-Warn2 'enable Algo Trading (green button), and leave them running before starting bots.'
    }
    $script:Mt5Missing = ($missing.Count -gt 0)
    $script:Results['MT5 check'] = if ($missing.Count -eq 0) { 'OK' } else { "$($missing.Count) missing" }
}

# --------------------------------------------------------------------------
# Phase 4 — Secrets scaffold (never overwrite existing)
# --------------------------------------------------------------------------
function Invoke-ScaffoldSecrets {
    Write-Phase 'Phase 4 — Credentials / users scaffold'

    $credPath = Join-Path $AlgosRoot 'credentials.json'
    if (Test-Path $credPath) {
        Write-Ok 'credentials.json already exists — left untouched.'
        $script:CredsPlaceholder = ((Get-Content $credPath -Raw) -match $PlaceholderMarker)
    } else {
        ($CredentialsTemplate | ConvertTo-Json -Depth 5) | Set-Content -Path $credPath -Encoding UTF8
        Write-Warn2 "credentials.json scaffolded with placeholder passwords."
        Write-Warn2 "EDIT $credPath and replace every '$PlaceholderMarker' before starting bots."
        $script:CredsPlaceholder = $true
    }

    $usersPath = Join-Path $AlgosRoot 'users.json'
    if (Test-Path $usersPath) {
        Write-Ok 'users.json already exists — left untouched.'
    } else {
        ($UsersTemplate | ConvertTo-Json -Depth 5) | Set-Content -Path $usersPath -Encoding UTF8
        Write-Warn2 "users.json scaffolded with the documented admin entry — verify the Telegram user ID."
    }
    $script:Results['Secrets scaffold'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 5 — Task Scheduler
# --------------------------------------------------------------------------
function Invoke-InstallTasks {
    Write-Phase 'Phase 5 — Task Scheduler'
    if ($SkipTasks) { Write-Info 'Skipped (-SkipTasks).'; $script:Results['Task Scheduler'] = 'skipped'; return }
    if (-not (Test-Admin)) {
        Write-Warn2 'Not elevated — cannot create scheduled tasks. Re-run as admin.'
        $script:Results['Task Scheduler'] = 'skipped (not admin)'
        return
    }

    $schedDir = Join-Path $AlgosRoot 'scheduler'
    if (-not (Test-Path $schedDir)) { Write-Err2 "Scheduler dir not found at $schedDir"; $script:Results['Task Scheduler'] = 'failed'; return }
    if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Path $TempDir -Force | Out-Null }

    # No password is asked for, and that is the fix for a real outage.
    #
    # This used to prompt for the `trader` password and pass it as /ru /rp, so every task stored a
    # copy. The VPS provider rotates that password (see the CheckAndPromptPasswordChange task), and
    # when it changed on ~30 May 2026 EVERY SYS_* task stopped launching — silently. `schtasks /run`
    # still returned SUCCESS and the tasks still read `Ready`; only `Last Run Time` gave it away by
    # never advancing. Crash alerts were off for two months and SYS_STARTUP would not have brought
    # bots back after a reboot.
    #
    # The XMLs now declare SYSTEM (`S-1-5-18` / `ServiceAccount`), which needs no password and
    # cannot go stale. Passing /ru here would OVERRIDE that principal and reintroduce the bug, so
    # the XML is applied as-is.
    foreach ($t in $Tasks) {
        $xmlSrc = Join-Path $schedDir $t.Xml
        if (-not (Test-Path $xmlSrc)) { Write-Warn2 "missing xml: $($t.Xml) — skipping $($t.Name)"; continue }
        $xmlTmp = Join-Path $TempDir $t.Xml
        Copy-Item $xmlSrc $xmlTmp -Force
        # /f makes this idempotent (recreate if the task already exists).
        & schtasks /create /tn $t.Name /xml $xmlTmp /f | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "created $($t.Name) (runs as SYSTEM)" }
        else { Write-Warn2 "schtasks /create returned $LASTEXITCODE for $($t.Name)" }
    }

    foreach ($name in $DisableTasks) {
        & schtasks /change /tn $name /disable | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "disabled $name (SYS_STARTUP fires it)" }
        else { Write-Warn2 "could not disable $name (exit $LASTEXITCODE)" }
    }
    $script:Results['Task Scheduler'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 6 — Start + verify
# --------------------------------------------------------------------------
function Invoke-StartSystem {
    Write-Phase 'Phase 6 — Start system'
    if ($NoStart) { Write-Info 'Skipped (-NoStart).'; $script:Results['Start'] = 'skipped'; return }

    if (Test-Path $LockFile) { Remove-Item $LockFile -Force; Write-Info 'Cleared stale mt5_connect.lock' }

    # No bots registered — SYS_STARTUP only launches Telegram + monitoring. Fire it
    # and report, but skip the bot-connection wait (there is nothing to wait for).
    if ($Mt5Terminals.Count -eq 0) {
        Write-Info 'No bots registered — running SYS_STARTUP for Telegram/monitoring only...'
        & schtasks /run /tn SYS_STARTUP | Out-Null
        Start-Sleep -Seconds 5
        $procs = @(Get-RunningBots)
        Write-Ok "SYS_STARTUP fired — $($procs.Count) system process(es) running (Telegram/monitoring)."
        $script:Results['Start'] = "OK (no bots; $($procs.Count) sys procs)"
        return
    }

    # Bots registered — don't start into a broken state.
    if ($script:Mt5Missing) {
        Write-Warn2 'MT5 terminal(s) missing — not starting bots. Install them, then run: schtasks /run /tn SYS_STARTUP'
        $script:Results['Start'] = 'skipped (MT5 missing)'; return
    }
    if ($script:CredsPlaceholder) {
        Write-Warn2 'credentials.json still contains placeholders — not starting bots. Fill it in, then run: schtasks /run /tn SYS_STARTUP'
        $script:Results['Start'] = 'skipped (creds placeholder)'; return
    }

    Write-Info 'Running SYS_STARTUP...'
    & schtasks /run /tn SYS_STARTUP | Out-Null
    Write-Info 'Waiting 60s for sequential bot startup...'
    Start-Sleep -Seconds 60

    $running = @(Get-RunningBots)
    if ($running.Count -gt 0) {
        Write-Ok "$($running.Count) bot/system process(es) running:"
        $running | ForEach-Object { Write-Host "         $($_.CommandLine)" -ForegroundColor DarkGray }
        $script:Results['Start'] = "OK ($($running.Count) procs)"
    } else {
        Write-Warn2 'No bot processes detected yet. Check VPS logs and `algo` control panel.'
        $script:Results['Start'] = 'no procs detected'
    }
}

# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
function Invoke-Phase {
    param([string]$Label, [scriptblock]$Body)
    try { & $Body }
    catch {
        Write-Err2 "$Label : $($_.Exception.Message)"
        $script:Results[$Label] = "FAILED: $($_.Exception.Message)"
    }
}

Write-Host "LWG Capital — VPS Bootstrap" -ForegroundColor White
Write-Host "Repo: $RepoUrl  ->  $RepoRoot  (branch $Branch)" -ForegroundColor DarkGray
Write-Host "SkipDeps=$SkipDeps  SkipTasks=$SkipTasks  NoStart=$NoStart" -ForegroundColor DarkGray

# Pre-flight is fatal; the rest are independent so a partial rebuild still reports.
Invoke-Preflight

Invoke-Phase 'Clone/update'    { Invoke-CloneRepo }
Invoke-Phase 'Python deps'     { Invoke-PipInstall }
Invoke-Phase 'MT5 check'       { Invoke-CheckMt5 }
Invoke-Phase 'Secrets scaffold'{ Invoke-ScaffoldSecrets }
Invoke-Phase 'Task Scheduler'  { Invoke-InstallTasks }
Invoke-Phase 'Start'           { Invoke-StartSystem }

# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
Write-Phase 'Summary'
foreach ($k in $script:Results.Keys) {
    $v = $script:Results[$k]
    $color = if ($v -like 'OK*') { 'Green' } elseif ($v -like '*FAILED*' -or $v -like '*missing*' -or $v -like '*no procs*') { 'Red' } else { 'Yellow' }
    Write-Host ("  {0,-18} {1}" -f $k, $v) -ForegroundColor $color
}

Write-Host "`nManual steps this script cannot do for you:" -ForegroundColor White
Write-Host "  - Verify the Telegram admin ID in $AlgosRoot\users.json." -ForegroundColor Gray
if ($Mt5Terminals.Count -gt 0) {
    Write-Host "  - Install + log into each bot's MT5 terminal (one account each, Algo Trading ON)." -ForegroundColor Gray
    Write-Host "  - Put real passwords in $AlgosRoot\credentials.json (replace '$PlaceholderMarker')." -ForegroundColor Gray
}
Write-Host "`nWhen you deploy your first bot: add its terminal + account to the lists in this" -ForegroundColor White
Write-Host "script's 'Static configuration' block and its task XML to `$Tasks, then re-run." -ForegroundColor White
Write-Host "Verify from your Mac:  algo   (control panel)   and Telegram:  /status" -ForegroundColor White
