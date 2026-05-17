# Notifications Guide
**Folder:** `notifications/`

Four scripts handle all Telegram communication. They run independently
of the trading bots so a bot crash never prevents an alert from firing.

---

## Files

| File | Purpose | Runs |
|---|---|---|
| `reporter.py` | Daily summary per bot | 4pm Texas daily (Task Scheduler) |
| `monitor.py` | Health checks + real-time alerts | Every 1 minute (Task Scheduler) |
| `telegram_bot.py` | Command handler — status, control | 24/7 at startup (Task Scheduler) |
| `start_telegram.py` | Single-instance launcher for telegram_bot | Called by SYS_TELEGRAM task |

**Telegram credentials (hardcoded in all files):**
- Bot token: `8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8`
- Chat ID: `429207285` (@cryptobetta)

---

## reporter.py — Daily Summary

Sends one message per bot at 4pm Texas time. Skipped on weekends automatically.

Each report contains:
- Today's P&L (% and $), trades (W/L/BE), max drawdown
- Bot uptime for the day, running status
- Account start balance, current balance, total growth
- Last 30 trades: win rate, profit factor, avg R, Calmar ratio
- AI-generated suggestions based on performance patterns

**Note:** SMC Trend and Mean Reversion share `gold_main_equity.json` since they
run on the same MT5 account. Their balance and growth % will always be identical.
Their individual trade performance (win rate, profit factor) is tracked separately.

**Run manually:**
```bash
python notifications/reporter.py              # all bots (weekdays only)
python notifications/reporter.py --force      # force even on weekends
python notifications/reporter.py --test       # verify Telegram connection
```

**Calmar rating:**
- ✅ >= 3.0 — strong, can leverage safely
- ⚠️ >= 2.0 — acceptable, keep building
- ❌ < 2.0 — needs attention

---

## monitor.py — Real-Time Alerts

Runs every 1 minute via Task Scheduler. Sends instant Telegram alerts for:

| Event | Alert |
|---|---|
| Bot goes offline | ALERT — Bot Offline |
| Bot comes back online | ALERT — Bot Online |
| Daily profit goal hit | ALERT — Daily Goal Hit |
| Daily loss cap hit | ALERT — Daily Loss Cap Hit |
| Weekly loss cap hit | ALERT — Weekly Loss Cap Hit |
| Telegram bot down | Auto-restarts up to 3 times, then 🚨 CRITICAL alert |

State tracked in `C:\algos\monitor_state.json` — resets daily at midnight Texas time.

**Run manually:**
```bash
python notifications/monitor.py
```

---

## telegram_bot.py + start_telegram.py — Command Handler

`start_telegram.py` is called by the Task Scheduler. It kills any existing
telegram_bot.py process first (prevents duplicates), then launches telegram_bot.py.

telegram_bot.py polls Telegram every 10 seconds and responds to commands.

### Read-Only Commands

| Command | Response |
|---|---|
| `/status` | All bots running/stopped with uptime |
| `/balance` | Current balance per account with growth % |
| `/trades` | Today's trade count W/L/BE per bot |
| `/report` | Daily report (weekdays). Prompts /force on weekends. |
| `/help` | Full command list |

### Control Commands (require /confirm within 30 seconds)

| Command | Action |
|---|---|
| `/restart` | Restart all bots |
| `/restart smc` | Restart one bot (smc/reversion/scalper/fft) |
| `/stop` | Stop all bots |
| `/stop scalper` | Stop one bot |
| `/emergency` | Kill all bots immediately |
| `/confirm` | Execute the pending action |
| `/force` | Force weekend report after /report prompt |

**Example weekend report flow:**
```
You:  /report
Bot:  📅 It's Saturday — gold markets are closed.
      Send /force within 2 minutes to generate the report anyway.

You:  /force
Bot:  📊 Generating report. Check messages shortly.
```

---

## Installation

**1. Install dependency on VPS:**
```bash
ssh forexvps "pip install requests"
```

**2. Test Telegram connection:**
```bash
ssh forexvps "python C:\algos\notifications\reporter.py --test"
```

**3. Install Task Scheduler tasks (PowerShell on VPS):**
```powershell
$tasks = @(
    @{file="telegram_task.xml"; name="SYS_TELEGRAM"},
    @{file="reporter_task.xml"; name="SYS_REPORTER"},
    @{file="monitor_task.xml";  name="SYS_MONITOR"}
)
foreach ($t in $tasks) {
    Copy-Item "C:\algos\scheduler\$($t.file)" "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
    Write-Host "Installed: $($t.name)"
}
```

**4. Verify tasks installed:**
```bash
ssh forexvps "schtasks /query /fo TABLE | findstr SYS_"
```

---

## DST Note

The 4pm Texas trigger uses UTC time in `reporter_task.xml`:
- CDT (Mar–Nov): 4pm CT = 21:00 UTC — current XML setting
- CST (Nov–Mar): 4pm CT = 22:00 UTC — update in November

To update in November, change `21:00:00` to `22:00:00` in `reporter_task.xml`
then reinstall: `schtasks /delete /tn SYS_REPORTER /f` and recreate.
