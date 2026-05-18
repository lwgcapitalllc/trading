# Setup Guide — LWG Capital Algo Suite

Fresh VPS setup or rebuild from scratch.

---

## Prerequisites

- Windows VPS with RDP access
- Python 3.11 installed at `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\`
- Git installed
- MT5 terminals installed (see MT5 section)
- GitHub repo: https://github.com/lwgcapitalllc/algos

---

## 1. Clone Repository

```powershell
cd C:\
git clone https://github.com/lwgcapitalllc/algos.git
cd C:\algos
pip install requests zoneinfo pandas numpy MetaTrader5 --break-system-packages
```

---

## 2. MT5 Terminals

Three separate MT5 installations required:

| Terminal | Install Path | Account |
|---|---|---|
| MT5 Main | `C:\Program Files\PU Prime MT5 Terminal\` | #700103491 |
| MT5 Scalper | `C:\MT5_Scalper\` | #700107520 |
| MT5 FFT | `C:\MT5_FFT\` | #700107749 |

Each terminal must:
1. Be logged into **only** its own account
2. Have Algo Trading enabled (green play button in toolbar)
3. Be running before bots start

---

## 3. Credentials File

Create `C:\algos\credentials.json` (never commit this file):

```json
{
  "accounts": {
    "700103491": {"password": "...", "server": "PUPrime-Demo"},
    "700107520": {"password": "...", "server": "PUPrime-Demo"},
    "700107749": {"password": "...", "server": "PUPrime-Demo"}
  }
}
```

---

## 4. Telegram Users File

Create `C:\algos\users.json`:

```json
{
  "429207285": {"name": "Aaron", "role": "admin", "added": "2026-05-14"}
}
```

---

## 5. Restore Bot State from Backup

After a fresh clone, restore VPS-only data from backup:

```powershell
# Copy bot state (balances, P&L)
copy "C:\algos\backup\markets\fx\instances\gold_main\bot_state.json" "C:\algos\markets\fx\instances\gold_main\bot_state.json"
copy "C:\algos\backup\markets\fx\instances\gold_scalper\bot_state.json" "C:\algos\markets\fx\instances\gold_scalper\bot_state.json"
copy "C:\algos\backup\markets\fx\instances\gold_fft\bot_state.json" "C:\algos\markets\fx\instances\gold_fft\bot_state.json"

# Copy trade histories
copy "C:\algos\backup\markets\fx\instances\gold_main\smc_trend_trades.json" "C:\algos\markets\fx\instances\gold_main\"
copy "C:\algos\backup\markets\fx\instances\gold_main\mean_reversion_trades.json" "C:\algos\markets\fx\instances\gold_main\"
copy "C:\algos\backup\markets\fx\instances\gold_scalper\scalper_trades.json" "C:\algos\markets\fx\instances\gold_scalper\"
copy "C:\algos\backup\markets\fx\instances\gold_fft\fft_trades.json" "C:\algos\markets\fx\instances\gold_fft\"

# Copy Telegram users
copy "C:\algos\backup\users.json" "C:\algos\users.json"
```

---

## 6. Install Task Scheduler Tasks

Run in PowerShell as Administrator:

```powershell
$tasks = @(
    @{file="startup_coordinator_task.xml"; name="SYS_STARTUP"},
    @{file="telegram_task.xml";            name="SYS_TELEGRAM"},
    @{file="monitor_task.xml";             name="SYS_MONITOR"},
    @{file="pnl_tracker_task.xml";         name="SYS_PNLTRACKER"},
    @{file="reporter_task.xml";            name="SYS_REPORTER"},
    @{file="backup_task.xml";              name="SYS_BACKUP"},
    @{file="smc_trend_task.xml";           name="BOT_SMC_TREND"},
    @{file="mean_reversion_task.xml";      name="BOT_MEAN_REVERSION"},
    @{file="scalper_task.xml";             name="BOT_SCALPER"},
    @{file="fft_task.xml";                 name="BOT_FFT"}
)

foreach ($t in $tasks) {
    $xml = "C:\algos\scheduler\$($t.file)"
    Copy-Item $xml "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
}

# Disable individual BOT_ tasks — SYS_STARTUP handles them
schtasks /change /tn BOT_SMC_TREND      /disable
schtasks /change /tn BOT_MEAN_REVERSION /disable
schtasks /change /tn BOT_SCALPER        /disable
schtasks /change /tn BOT_FFT            /disable
```

---

## 7. Start Everything

```bash
ssh forexvps "schtasks /run /tn SYS_STARTUP"
sleep 60
ssh forexvps "wmic process where \"name='python.exe'\" get commandline 2>nul"
```

---

## 8. Verify

Run on Mac:
```bash
algo  # open control panel — all bots should show RUNNING with uptime
```

Send in Telegram:
```
/status   → all 4 bots green
/balance  → correct balances
```
