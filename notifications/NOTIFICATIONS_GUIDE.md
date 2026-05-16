# Notifications Guide
**Folder:** `notifications/`

Three scripts handle all Telegram communication. They run independently
of the trading bots so a bot crash never prevents an alert from firing.

---

## Files

| File | Purpose | Runs |
|---|---|---|
| `reporter.py` | Daily summary per bot | 4pm Texas daily (Task Scheduler) |
| `monitor.py` | Health checks + real-time alerts | Every 5 minutes (Task Scheduler) |
| `telegram_bot.py` | Command handler — status, control | 24/7 at startup (Task Scheduler) |

**Telegram credentials (hardcoded in all three files):**
- Bot token: `8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8`
- Chat ID: `429207285` (@cryptobetta)

---

## reporter.py — Daily Summary

Sends one message per bot at 4pm Texas time containing:
- Today's P&L (% and $), trades (W/L/BE), max drawdown
- Bot uptime for the day, running status
- Account start balance, current balance, total growth
- Last 30 trades: win rate, profit factor, avg R, Calmar ratio
- AI-generated suggestions based on performance patterns

**Run manually:**
```bash
python notifications/reporter.py              # all bots
python notifications/reporter.py --bot bot1   # one bot
python notifications/reporter.py --test       # verify Telegram
```

**Calmar rating:**
- ✅ >= 3.0 — strong, can leverage safely
- ⚠️ >= 2.0 — acceptable, keep building
- ❌ < 2.0 — needs attention

---

## monitor.py — Real-Time Alerts

Runs every 5 minutes via Task Scheduler. Sends instant Telegram alerts for:

| Event | Alert |
|---|---|
| Bot goes offline | 🚨 BOT OFFLINE — with restart instructions |
| Bot comes back online | ✅ BOT ONLINE |
| Daily profit goal hit | 🎯 DAILY GOAL HIT — with amount |
| Daily loss cap hit | 🛑 DAILY LOSS CAP HIT — bot paused |
| Weekly loss cap hit | 🚫 WEEKLY LOSS CAP HIT — 6hr cooldown |

State tracked in `monitor_state.json` — knows what changed since last check.
Resets daily goal/cap alerts at midnight Texas time automatically.

**Run manually:**
```bash
python notifications/monitor.py
```

---

## telegram_bot.py — Command Handler

Polls Telegram every 10 seconds. Responds to your messages from anywhere.

### Read-Only Commands (instant)

| Command | Response |
|---|---|
| `/status` | All bots running/stopped with uptime |
| `/balance` | Current balance per account with growth % |
| `/trades` | Today's trade count W/L/BE per bot |
| `/report` | Trigger full daily report immediately |
| `/help` | Full command list |

### Control Commands (require /confirm)

All control commands show a confirmation prompt. You must send `/confirm`
within 30 seconds or the action is cancelled. This prevents accidental
restarts or stops when messaging on mobile.

| Command | Action |
|---|---|
| `/restart` | Restart all bots |
| `/restart bot1` | Restart one bot (bot1/bot2/bot3/bot5) |
| `/stop` | Stop all bots |
| `/stop bot3` | Stop one bot |
| `/emergency` | Kill all bots immediately via taskkill |
| `/confirm` | Execute the pending action |

**Example flow:**
```
You:  /restart bot1
Bot:  ⚠️ Confirm required
      Action: Restart Bot 1 — SMC Trend
      Send /confirm within 30 seconds.

You:  /confirm
Bot:  ✅ Restart Bot 1 — SMC Trend executed
      ✅ 📈 Bot 1 — SMC Trend
```

**Emergency stop** kills all python.exe processes on the VPS immediately.
Use only if bots are misbehaving and you cannot RDP in. The Task Scheduler
will restart them automatically on the next VPS boot.

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
# Copy XMLs to temp
Copy-Item C:\algos\scheduler\reporter_task.xml C:\temp\
Copy-Item C:\algos\scheduler\monitor_task.xml C:\temp\
Copy-Item C:\algos\scheduler\telegram_bot_task.xml C:\temp\

# Install
schtasks /create /tn "ALGO_Daily_Reporter" /xml "C:\temp\reporter_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
schtasks /create /tn "ALGO_Monitor"        /xml "C:\temp\monitor_task.xml"  /ru trader /rp "312MXFjt7Q8Zoec"
schtasks /create /tn "ALGO_Telegram_Bot"   /xml "C:\temp\telegram_bot_task.xml" /ru trader /rp "312MXFjt7Q8Zoec"
```

**4. Verify tasks installed:**
```bash
ssh forexvps "schtasks /query /fo TABLE | findstr ALGO"
```

---

## DST Note

The 4pm Texas trigger uses UTC time in the XML:
- CDT (Mar–Nov): 4pm CT = 21:00 UTC ← current XML setting
- CST (Nov–Mar): 4pm CT = 22:00 UTC ← update XML in November

To update in November, edit `scheduler/reporter_task.xml` and change
`21:00:00` to `22:00:00`, then reinstall the task.
