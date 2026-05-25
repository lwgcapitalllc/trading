# LWG Capital — Monorepo Migration Instructions for Claude Code

---

## Objective
Migrate the existing `algos` repository into a new `lwg-capital` monorepo structure with two top-level directories: `algos/` (existing system) and `smart-money/` (new system). All existing VPS paths, Task Scheduler references, and deploy scripts must be updated without breaking live bots during the transition.

---

## Current State

- Existing repo: `algos` on GitHub (main branch)
- VPS path: `C:\algos`
- VPS SSH alias: `forexvps`
- Live bots running on Windows VPS (ForexVPS)
- Backup branch: `backups` orphan branch on existing repo
- Mac control panel runs via `algo` alias

---

## Target State

```
trading/                              ← New GitHub repo
├── README.md                        ← Top level overview
├── algos/                           ← Existing system moved here
│   ├── README.md
│   ├── algo.py
│   ├── bots/
│   ├── shared/
│   ├── notifications/
│   ├── scheduler/
│   ├── scripts/
│   ├── docs/
│   └── markets/
└── smart-money/                     ← New system
    ├── README.md                    ← Smart Money Replication System proposal
    ├── config/
    ├── scanner/
    ├── forex/
    ├── profiler/
    ├── ranking/
    ├── data/
    ├── reports/
    └── docs/
```

---

## Phase 1 — Create New Monorepo Locally (Mac) ✅ COMPLETE — SKIP THIS PHASE

### Step 1.1 — Create New Local Repo
```bash
mkdir ~/trading
cd ~/trading
git init
```

### Step 1.2 — Import Existing Algos Repo with Full Git History
```bash
# Add existing algos repo as a remote
git remote add algos-origin https://github.com/YOUR_USERNAME/algos.git
git fetch algos-origin

# Use git subtree to import algos into the algos/ subdirectory
# This preserves all commit history
git subtree add --prefix=algos algos-origin main
```

### Step 1.3 — Verify Algos Directory Structure
- Confirm all files from existing repo are present under `algos/`
- Confirm git log shows full history preserved
- Confirm no files are missing

### Step 1.4 — Create Smart Money Directory Structure
```bash
mkdir -p smart-money/config
mkdir -p smart-money/scanner
mkdir -p smart-money/forex
mkdir -p smart-money/profiler
mkdir -p smart-money/ranking
mkdir -p smart-money/data/raw
mkdir -p smart-money/data/processed
mkdir -p smart-money/reports
mkdir -p smart-money/docs
```

### Step 1.5 — Add Smart Money README
- Copy the `smart_money_replication_system.md` proposal file into `smart-money/README.md`
- This becomes the entry point for Claude Code when building the smart money system

### Step 1.6 — Create Top Level README
Create `lwg-capital/README.md` with the following content:

```markdown
# LWG Capital — Trading Operations

## Systems

### algos/
Automated algo trading suite for XAUUSD on PU Prime demo accounts.
Runs on Windows VPS (ForexVPS). Three instances: gold_main, gold_scalper, gold_fft.
See algos/README.md for full documentation.

### smart-money/
Smart money replication system. Scans and profiles the most consistent
crypto and forex traders for copy trading candidate pool construction.
See smart-money/README.md for full documentation.

## VPS
- Provider: ForexVPS
- OS: Windows
- SSH alias: forexvps
- Deploy path: C:\trading\algos

## Repository
- Main branch: active development
- Backups branch: VPS data backups (orphan branch, never merges to main)
```

### Step 1.7 — Create Top Level .gitignore
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
.Python
*.egg-info/
dist/
build/
.eggs/
*.pkl
*.pickle

# Data files (backed up separately to backups branch)
smart-money/data/raw/
smart-money/data/processed/
*.json.bak

# Environment
.env
.venv
venv/
env/

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# IDE
.vscode/
.idea/
EOF
```

### Step 1.8 — Initial Commit
```bash
git add .
git commit -m "Initial LWG Capital monorepo — imported algos, scaffolded smart-money"
```

---

## Phase 2 — Create New GitHub Repo and Push

### Step 2.1 — Create New GitHub Repo
- Go to GitHub and create a new private repository named `trading` under the `lwgcapitalllc` organization
- Set to private
- Do NOT initialize with README (repo already has one)

### Step 2.2 — Push to GitHub
```bash
cd ~/trading
git remote add origin https://github.com/lwgcapitalllc/trading.git
git branch -M main
git push -u origin main
```

### Step 2.3 — Migrate Backups Branch
```bash
# Add old repo as remote
git remote add old-repo https://github.com/YOUR_USERNAME/algos.git
git fetch old-repo

# Push old backups branch to new repo
git push origin algos-origin/backups:refs/heads/backups
```

### Step 2.4 — Verify GitHub
- Confirm main branch shows correct structure with algos/ and smart-money/
- Confirm backups branch is present
- Confirm full commit history is visible

---

## Phase 3 — Update VPS (Critical — Do Not Skip Steps)

### Step 3.1 — SSH Into VPS
```bash
ssh forexvps
```

### Step 3.2 — Stop All Bots First
```bash
taskkill /f /im python.exe
del C:\algos\mt5_connect.lock 2>nul
```

### Step 3.3 — Clone New Repo to VPS
```bash
cd C:\
git clone https://github.com/lwgcapitalllc/trading.git
```

### Step 3.4 — Verify New Clone
```bash
cd C:\trading
dir
cd algos
dir
```
- Confirm all bot files are present under C:\trading\algos\

### Step 3.5 — Copy Live State Files from Old Location
These files are VPS-only runtime files not tracked on main branch:
```bash
# Copy all live bot state files to new location
xcopy C:\algos\markets C:\trading\algos\markets /E /I /Y

# Copy credentials and users
xcopy C:\algos\credentials.json C:\trading\algos\credentials.json /Y
xcopy C:\algos\users.json C:\trading\algos\users.json /Y

# Copy any trained model files
xcopy C:\algos\bots\*_model.pkl C:\trading\algos\bots\ /Y
xcopy C:\algos\bots\*_model_scaler.pkl C:\trading\algos\bots\ /Y
```

### Step 3.6 — Update Task Scheduler XML Files
For each XML file in `algos/scheduler/`:
- Open each `*_task.xml` file
- Find all references to `C:\algos\`
- Replace with `C:\trading\algos\`
- Save each file

### Step 3.7 — Reimport Updated Task Scheduler Tasks
```bash
# Delete old tasks
schtasks /delete /tn SYS_STARTUP /f
schtasks /delete /tn SYS_BACKUP /f
schtasks /delete /tn SYS_MONITOR /f
schtasks /delete /tn SYS_PNL /f
schtasks /delete /tn SYS_REPORTER /f
schtasks /delete /tn SYS_TELEGRAM /f

# Reimport updated tasks from new location
cd C:\trading\algos\scheduler
for %f in (*.xml) do schtasks /create /xml %f /tn %~nf
```

### Step 3.8 — Update Backup Script
In `C:\trading\algos\scripts\backup.py`:
- Find all references to `C:\algos`
- Replace with `C:\trading\algos`
- Find git worktree reference to `C:\algos-backup`
- Confirm worktree path still works or update as needed

### Step 3.9 — Recreate Git Worktree for Backups Branch
```bash
cd C:\trading
git worktree add C:\trading-backup backups
```

### Step 3.10 — Test Startup
```bash
cd C:\trading
schtasks /run /tn SYS_STARTUP
```
Wait 60 seconds then verify:
```bash
wmic process where "name='python.exe'" get commandline 2>nul
```
- Confirm all three bot instances are running
- Confirm paths show `C:\trading\algos`

### Step 3.11 — Verify Bot State Files Are Being Written
```bash
type C:\trading\algos\markets\fx\instances\gold_main\bot_state.json
type C:\trading\algos\markets\fx\instances\gold_scalper\bot_state.json
type C:\trading\algos\markets\fx\instances\gold_fft\bot_state.json
```
- Confirm each file shows current balance and live status

### Step 3.12 — Test Telegram Bot
- Send `/status` to Telegram bot
- Send `/balance` to Telegram bot
- Confirm responses are accurate and pulling from new paths

---

## Phase 4 — Update Mac Control Panel

### Step 4.1 — Update algo.py Path References
In `algos/algo.py` on Mac:
- Find any hardcoded VPS path references to `C:\algos`
- Replace with `C:\trading\algos`

### Step 4.2 — Update SSH Alias if Needed
Check current `forexvps` alias in `~/.ssh/config` or `~/.zshrc` / `~/.bashrc`:
- If alias includes any path references update them
- If alias is just an SSH shortcut no change needed

### Step 4.3 — Update algo Shell Alias
Check `~/.zshrc` or `~/.bashrc` for the `algo` alias:
- Update any path references to point to new monorepo location
- Source the updated file: `source ~/.zshrc`

### Step 4.4 — Test Mac Control Panel
```bash
algo
```
- Confirm control panel launches correctly
- Confirm it can reach VPS and pull correct status

---

## Phase 5 — Verify Everything and Clean Up

### Step 5.1 — Run Full Verification Checklist
- [ ] All three bots running on VPS at new paths
- [ ] bot_state.json files updating correctly
- [ ] Telegram bot responding to all commands correctly
- [ ] Task Scheduler tasks all pointing to new paths
- [ ] Backup script running correctly to backups branch
- [ ] Mac control panel working correctly
- [ ] Git pull on VPS pulls from `lwgcapitalllc/trading` repo

### Step 5.2 — Monitor for 24 Hours
- Watch Telegram for daily 4pm CT report
- Confirm report generates correctly from new paths
- Confirm backup task runs at midnight CT
- Check backups branch on GitHub for new backup commits

### Step 5.3 — Archive Old Repo (Do Not Delete Yet)
- On GitHub rename old `algos` repo to `algos-archived`
- Do NOT delete it until system has run stably for at least 7 days
- After 7 days of stable operation old repo can be safely archived or deleted

### Step 5.4 — Update Deploy Workflow Documentation
Update the deploy workflow in `algos/README.md` to reflect new paths:
```bash
# New deploy workflow
git add . && git commit -m "..." && git push
ssh forexvps "cd C:\trading && git pull origin main"

# Restart bots
ssh forexvps "del C:\trading\algos\mt5_connect.lock 2>nul && taskkill /f /im python.exe"
sleep 3
ssh forexvps "schtasks /run /tn SYS_STARTUP"
sleep 60
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul"
```

---

## Important Notes for Claude Code

- Do NOT delete `C:\algos` on VPS until full verification is complete and stable for 7 days
- The backups branch must be migrated before decommissioning the old repo — it contains AI training data and model files
- Task Scheduler tasks must be deleted and reimported — do not just edit XML files without reimporting
- The `mt5_connect.lock` file must be deleted before restarting bots every time
- Each MT5 terminal must remain logged into ONLY its own account — verify after restart
- If any step fails during VPS migration roll back by restarting bots from `C:\algos` using old Task Scheduler tasks — do not proceed until issue is resolved
- Smart money system in `smart-money/` is independent of algos — it does not run on the VPS and does not affect live bots in any way
