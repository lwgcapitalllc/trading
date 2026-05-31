<#
.SYNOPSIS
    LWG Capital — VPS bootstrap / disaster-recovery script.

    Rebuilds the algo trading suite on a fresh (or wiped) Windows VPS from the
    GitHub repo plus the `backups` branch. Idempotent: safe to re-run. Each
    phase checks current state before acting, and a failed phase reports the
    problem and moves on rather than aborting the whole run.

    This automates everything in docs/SETUP.md that can be automated. The two
    things it CANNOT do for you (and will instead detect + report) are:
      1. Installing the three MT5 terminals (GUI installers + manual login).
      2. Filling in real account passwords in credentials.json.

.DESCRIPTION
    Phases (run in order):
      0. Pre-flight ........ admin check, locate git + python
      1. Clone / update .... clone repo to -RepoRoot, or git pull if present
      2. Python deps ....... pip install the runtime packages
      3. MT5 check ......... verify the three terminals exist (cannot install)
      4. Secrets scaffold .. create credentials.json / users.json templates if absent
      5. Restore data ...... (opt-in) restore live state from the `backups` branch
      6. Backup worktree ... set up C:\trading-backup for future SYS_BACKUP runs
      7. Task Scheduler .... create the 10 tasks, disable the 4 BOT_ tasks
      8. Start ............. clear stale lock, run SYS_STARTUP, verify processes

.PARAMETER RepoUrl
    Git URL to clone. Default: the LWG Capital trading monorepo.

.PARAMETER RepoRoot
    Where the repo lives on the VPS. Default: C:\trading

.PARAMETER Branch
    Branch to check out for code. Default: main

.PARAMETER RestoreData
    Opt-in. Restore live bot state (balances, P&L, trade history, AI models)
    from the `backups` branch. OFF by default because it overwrites live data —
    only use on a genuinely fresh VPS or after disaster recovery.

.PARAMETER Force
    Allow -RestoreData to overwrite existing bot_state.json files. Without it,
    the restore phase refuses if live state is already present.

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
    # Fresh VPS, full rebuild including data restore:
    .\bootstrap_vps.ps1 -RestoreData

.EXAMPLE
    # Re-run on a partially-set-up box, skip the risky data restore:
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
    [switch] $RestoreData,
    [switch] $Force,
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
$BackupWorktree = 'C:\trading-backup'      # README: backups worktree location
$RestoreStaging = 'C:\trading-restore'     # SETUP.md staging dir for restore
$LockFile      = Join-Path $AlgosRoot 'mt5_connect.lock'
$TempDir       = 'C:\temp'

# Runtime Python packages. NOTE: SETUP.md lists `zoneinfo`, but that PyPI package
# is a pre-3.9 backport and fails to install on Python 3.11. On Windows the
# package you actually need for IANA timezones is `tzdata` — substituted here.
$PipPackages = @('requests', 'pandas', 'numpy', 'MetaTrader5', 'tzdata')
$PipFlags    = @('--break-system-packages')   # per SETUP.md; harmless if pip ignores

# The three MT5 terminals (RECOVERY: must be installed + logged in by hand).
$Mt5Terminals = @(
    [pscustomobject]@{ Name = 'MT5 Main';    Path = 'C:\Program Files\PU Prime MT5 Terminal\terminal64.exe'; Account = '700103491' }
    [pscustomobject]@{ Name = 'MT5 Scalper'; Path = 'C:\MT5_Scalper\terminal64.exe';                          Account = '700107520' }
    [pscustomobject]@{ Name = 'MT5 FFT';     Path = 'C:\MT5_FFT\terminal64.exe';                              Account = '700107749' }
)

# Account credentials template (PASSWORDS ARE PLACEHOLDERS — fill in by hand).
$PlaceholderMarker = 'REPLACE_ME'
$CredentialsTemplate = [ordered]@{
    accounts = [ordered]@{
        '700103491' = [ordered]@{ password = $PlaceholderMarker; server = 'PUPrime-Demo' }
        '700107520' = [ordered]@{ password = $PlaceholderMarker; server = 'PUPrime-Demo' }
        '700107749' = [ordered]@{ password = $PlaceholderMarker; server = 'PUPrime-Demo' }
    }
}

# Telegram users template (admin entry from SETUP.md — verify the ID before use).
$UsersTemplate = [ordered]@{
    '429207285' = [ordered]@{ name = 'Aaron'; role = 'admin'; added = (Get-Date -Format 'yyyy-MM-dd') }
}

# Task Scheduler tasks: xml file -> task name. Order matches SETUP.md.
$Tasks = @(
    [pscustomobject]@{ Xml = 'startup_coordinator_task.xml'; Name = 'SYS_STARTUP' }
    [pscustomobject]@{ Xml = 'telegram_task.xml';            Name = 'SYS_TELEGRAM' }
    [pscustomobject]@{ Xml = 'monitor_task.xml';             Name = 'SYS_MONITOR' }
    [pscustomobject]@{ Xml = 'pnl_tracker_task.xml';         Name = 'SYS_PNLTRACKER' }
    [pscustomobject]@{ Xml = 'reporter_task.xml';            Name = 'SYS_REPORTER' }
    [pscustomobject]@{ Xml = 'backup_task.xml';              Name = 'SYS_BACKUP' }
    [pscustomobject]@{ Xml = 'smc_trend_task.xml';           Name = 'BOT_SMC_TREND' }
    [pscustomobject]@{ Xml = 'mean_reversion_task.xml';      Name = 'BOT_MEAN_REVERSION' }
    [pscustomobject]@{ Xml = 'scalper_task.xml';             Name = 'BOT_SCALPER' }
    [pscustomobject]@{ Xml = 'fft_task.xml';                 Name = 'BOT_FFT' }
)
# These are started by SYS_STARTUP only — disable so they never auto-fire.
$DisableTasks = @('BOT_SMC_TREND', 'BOT_MEAN_REVERSION', 'BOT_SCALPER', 'BOT_FFT')

# Files restored from the `backups` branch (relative to repo root). Tolerant:
# missing files are skipped (e.g. AI models that don't exist until training).
$RestoreFiles = @(
    'markets\fx\instances\gold_main\bot_state.json'
    'markets\fx\instances\gold_main\smc_trend_trades.json'
    'markets\fx\instances\gold_main\mean_reversion_trades.json'
    'markets\fx\instances\gold_main\smc_trend_model.pkl'
    'markets\fx\instances\gold_main\smc_trend_model_scaler.pkl'
    'markets\fx\instances\gold_main\mean_reversion_model.pkl'
    'markets\fx\instances\gold_main\mean_reversion_model_scaler.pkl'
    'markets\fx\instances\gold_main\gold_main_equity.json'
    'markets\fx\instances\gold_main\smc_trend_daily.json'
    'markets\fx\instances\gold_main\mean_reversion_daily.json'
    'markets\fx\instances\gold_scalper\bot_state.json'
    'markets\fx\instances\gold_scalper\scalper_trades.json'
    'markets\fx\instances\gold_scalper\scalper_model.pkl'
    'markets\fx\instances\gold_scalper\scalper_model_scaler.pkl'
    'markets\fx\instances\gold_scalper\scalper_equity.json'
    'markets\fx\instances\gold_fft\bot_state.json'
    'markets\fx\instances\gold_fft\fft_trades.json'
    'markets\fx\instances\gold_fft\fft_equity.json'
    'markets\fx\instances\gold_fft\fft_daily.json'
    'users.json'
)

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

function Copy-IfExists {
    param([string]$Src, [string]$Dst)
    if (Test-Path $Src) {
        $dstDir = Split-Path $Dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Copy-Item $Src $Dst -Force
        return $true
    }
    return $false
}

function Get-RunningBots {
    # Returns python processes whose command line references a bot script.
    try {
        Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -and ($_.CommandLine -match 'bot_|startup_coordinator|telegram|monitor|pnl_tracker') }
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
# Phase 5 — Restore live data from the `backups` branch (opt-in)
# --------------------------------------------------------------------------
function Invoke-RestoreData {
    Write-Phase 'Phase 5 — Restore data from backups branch'
    if (-not $RestoreData) {
        Write-Info 'Skipped (pass -RestoreData to restore live state on a fresh VPS).'
        $script:Results['Restore data'] = 'skipped'
        return
    }

    # Guard 1: never restore over a running system.
    $running = @(Get-RunningBots)
    if ($running.Count -gt 0) {
        throw "Bot processes are running ($($running.Count)). Refusing to restore over a live VPS. Stop bots first."
    }
    # Guard 2: don't clobber existing live state unless -Force.
    $existing = $RestoreFiles | Where-Object { $_ -like '*bot_state.json' } |
                ForEach-Object { Join-Path $RepoRoot $_ } | Where-Object { Test-Path $_ }
    if ($existing -and -not $Force) {
        throw "Live bot_state.json files already exist. Re-run with -Force to overwrite (DESTRUCTIVE)."
    }

    if (Test-Path $RestoreStaging) { Remove-Item $RestoreStaging -Recurse -Force }
    Write-Info "Cloning backups branch -> $RestoreStaging"
    Invoke-Native { & git clone --branch backups --single-branch $RepoUrl $RestoreStaging } 'git clone (backups)'

    $copied = 0; $skipped = 0
    foreach ($rel in $RestoreFiles) {
        $src = Join-Path $RestoreStaging $rel
        $dst = Join-Path $RepoRoot $rel
        if (Copy-IfExists -Src $src -Dst $dst) { $copied++; Write-Ok "restored $rel" }
        else { $skipped++; Write-Info "not in backup, skipped: $rel" }
    }
    Remove-Item $RestoreStaging -Recurse -Force
    Write-Ok "Restore complete — $copied file(s) restored, $skipped not present in backup."
    $script:Results['Restore data'] = "OK ($copied restored)"
}

# --------------------------------------------------------------------------
# Phase 6 — Backup worktree (so SYS_BACKUP works going forward)
# --------------------------------------------------------------------------
function Invoke-BackupWorktree {
    Write-Phase 'Phase 6 — Backup worktree setup'
    $backupScript = Join-Path $AlgosRoot 'scripts\backup.py'
    if (-not (Test-Path $backupScript)) {
        Write-Warn2 "scripts\backup.py not found — skipping worktree setup."
        $script:Results['Backup worktree'] = 'missing script'
        return
    }
    if (Test-Path $BackupWorktree) {
        Write-Ok "Backup worktree already present at $BackupWorktree."
        $script:Results['Backup worktree'] = 'OK (existing)'
        return
    }
    try {
        Write-Info 'Running backup.py --setup'
        & $script:Py $backupScript --setup 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
        Write-Ok 'Backup worktree created.'
        $script:Results['Backup worktree'] = 'OK'
    } catch {
        Write-Warn2 "backup.py --setup failed: $($_.Exception.Message)"
        $script:Results['Backup worktree'] = 'failed'
    }
}

# --------------------------------------------------------------------------
# Phase 7 — Task Scheduler
# --------------------------------------------------------------------------
function Invoke-InstallTasks {
    Write-Phase 'Phase 7 — Task Scheduler'
    if ($SkipTasks) { Write-Info 'Skipped (-SkipTasks).'; $script:Results['Task Scheduler'] = 'skipped'; return }
    if (-not (Test-Admin)) {
        Write-Warn2 'Not elevated — cannot create scheduled tasks. Re-run as admin.'
        $script:Results['Task Scheduler'] = 'skipped (not admin)'
        return
    }

    $schedDir = Join-Path $AlgosRoot 'scheduler'
    if (-not (Test-Path $schedDir)) { Write-Err2 "Scheduler dir not found at $schedDir"; $script:Results['Task Scheduler'] = 'failed'; return }
    if (-not (Test-Path $TempDir)) { New-Item -ItemType Directory -Path $TempDir -Force | Out-Null }

    $sec = Read-Host -AsSecureString "Password for the '$TraderUser' VPS account"
    $pass = ConvertFrom-SecureToPlain -Secure $sec
    try {
        foreach ($t in $Tasks) {
            $xmlSrc = Join-Path $schedDir $t.Xml
            if (-not (Test-Path $xmlSrc)) { Write-Warn2 "missing xml: $($t.Xml) — skipping $($t.Name)"; continue }
            $xmlTmp = Join-Path $TempDir $t.Xml
            Copy-Item $xmlSrc $xmlTmp -Force
            # /f makes this idempotent (recreate if the task already exists).
            & schtasks /create /tn $t.Name /xml $xmlTmp /ru $TraderUser /rp $pass /f | Out-Null
            if ($LASTEXITCODE -eq 0) { Write-Ok "created $($t.Name)" }
            else { Write-Warn2 "schtasks /create returned $LASTEXITCODE for $($t.Name)" }
        }
    } finally {
        $pass = $null   # drop the plaintext password
    }

    foreach ($name in $DisableTasks) {
        & schtasks /change /tn $name /disable | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "disabled $name (SYS_STARTUP fires it)" }
        else { Write-Warn2 "could not disable $name (exit $LASTEXITCODE)" }
    }
    $script:Results['Task Scheduler'] = 'OK'
}

# --------------------------------------------------------------------------
# Phase 8 — Start + verify
# --------------------------------------------------------------------------
function Invoke-StartSystem {
    Write-Phase 'Phase 8 — Start system'
    if ($NoStart) { Write-Info 'Skipped (-NoStart).'; $script:Results['Start'] = 'skipped'; return }

    # Don't start into a broken state.
    if ($script:Mt5Missing) {
        Write-Warn2 'MT5 terminal(s) missing — not starting bots. Install them, then run: schtasks /run /tn SYS_STARTUP'
        $script:Results['Start'] = 'skipped (MT5 missing)'; return
    }
    if ($script:CredsPlaceholder) {
        Write-Warn2 'credentials.json still contains placeholders — not starting bots. Fill it in, then run: schtasks /run /tn SYS_STARTUP'
        $script:Results['Start'] = 'skipped (creds placeholder)'; return
    }

    if (Test-Path $LockFile) { Remove-Item $LockFile -Force; Write-Info 'Cleared stale mt5_connect.lock' }

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
Write-Host "RestoreData=$RestoreData  Force=$Force  SkipDeps=$SkipDeps  SkipTasks=$SkipTasks  NoStart=$NoStart" -ForegroundColor DarkGray

# Pre-flight is fatal; the rest are independent so a partial rebuild still reports.
Invoke-Preflight

Invoke-Phase 'Clone/update'    { Invoke-CloneRepo }
Invoke-Phase 'Python deps'     { Invoke-PipInstall }
Invoke-Phase 'MT5 check'       { Invoke-CheckMt5 }
Invoke-Phase 'Secrets scaffold'{ Invoke-ScaffoldSecrets }
Invoke-Phase 'Restore data'    { Invoke-RestoreData }
Invoke-Phase 'Backup worktree' { Invoke-BackupWorktree }
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
Write-Host "  - Install + log into the three MT5 terminals (one account each, Algo Trading ON)." -ForegroundColor Gray
Write-Host "  - Put real passwords in $AlgosRoot\credentials.json (replace '$PlaceholderMarker')." -ForegroundColor Gray
Write-Host "  - Verify the Telegram admin ID in $AlgosRoot\users.json." -ForegroundColor Gray
Write-Host "`nVerify from your Mac:  algo   (control panel)   and Telegram:  /status  /balance" -ForegroundColor White
