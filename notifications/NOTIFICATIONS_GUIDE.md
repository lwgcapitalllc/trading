# Notifications Guide
**Folder:** `notifications/`

Four scripts handle all Telegram communication.

---

## Files

| File | Purpose | Runs |
|---|---|---|
| `reporter.py` | Daily summary per bot | 4pm Texas daily (SYS_REPORTER task) |
| `monitor.py` | Health checks + real-time alerts | Every 1 minute (SYS_MONITOR task) |
| `telegram_bot.py` | Command handler | 24/7 at startup (SYS_TELEGRAM task) |
| `start_telegram.py` | Single-instance launcher | Called by SYS_TELEGRAM instead of telegram_bot.py directly |

**Telegram credentials:**
- Token: `8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8`
- Chat ID: `429207285` (@cryptobetta)

---

## reporter.py — Daily Summary

Sends grouped messages at 4pm Texas time — one message per account type group
(Demo accounts together, Live accounts together). Skips weekends automatically.

Each report contains:
- Today's P&L (% and $), trades (W/L/BE), max drawdown
- Bot uptime, running status
- Account start balance, current balance, total growth
- Last 30 trades: win rate, profit factor, avg R, Calmar
- AI suggestions

**Shared equity:** SMC Trend and Mean Reversion share `gold_main_equity.json`
since they run on the same MT5 account. Their balance will always be identical.

**Run manually:**
```bash
python notifications/reporter.py                    # all bots, weekdays only
python notifications/reporter.py --group demo       # demo bots only
python notifications/reporter.py --group live       # live bots only
python notifications/reporter.py --force            # override weekend skip
python notifications/reporter.py --test             # verify Telegram connection
```

**Calmar rating:** ✅ >= 3.0 | ⚠️ >= 2.0 | ❌ < 2.0

---

## monitor.py — Real-Time Alerts

Runs every 1 minute. Sends Telegram alerts for:

| Event | Alert |
|---|---|
| Bot goes offline | ALERT — Bot Offline |
| Bot comes back online | ALERT — Bot Online |
| Daily profit goal hit | ALERT — Daily Goal Hit |
| Daily loss cap hit | ALERT — Daily Loss Cap Hit |
| Weekly loss cap hit | ALERT — Weekly Loss Cap Hit |
| Telegram bot down | Auto-restarts up to 3 times, then 🚨 CRITICAL |

State tracked in `C:\algos\monitor_state.json`. Resets at midnight Texas time.

---

## telegram_bot.py — Command Handler

Polls Telegram every 10 seconds. `start_telegram.py` kills any existing
instance first to prevent duplicates, then starts telegram_bot.py.

### Read-Only Commands

| Command | Response |
|---|---|
| `/status` | All bots with account, instrument, uptime |
| `/balance` | Balances grouped by account type |
| `/trades` | Today's W/L/BE per bot |
| `/report` | Prompts which group to report |
| `/demo` | Report demo accounts only |
| `/live` | Report live accounts only |
| `/all` | Report all accounts |
| `/help` | Command list |

### Report Flow

**Weekday:**
```
You:  /report
Bot:  Which accounts? Reply /demo, /live, or /all

You:  /demo
Bot:  Generating Demo report. Check messages shortly.
```

**Weekend:**
```
You:  /report
Bot:  It's Saturday — markets closed.
      Reply /demo, /live, or /all to send anyway.

You:  /all
Bot:  Generating All accounts report.
```

### Control Commands (require /confirm within 30 seconds)

| Command | Action |
|---|---|
| `/restart` | Restart all bots |
| `/restart smc` | Restart one bot (smc/reversion/scalper/fft) |
| `/stop` | Stop all bots |
| `/stop scalper` | Stop one bot |
| `/emergency` | Kill all bots immediately |
| `/confirm` | Execute the pending action |

---

## Account Type Configuration

Each instance `config.json` has:
```json
"account_type": "demo",
"instrument":   "XAUUSD"
```

Change `account_type` to `"live"` when moving to a live account.
This controls which tab it appears on in the algo panel and how
reports are grouped in Telegram.

---

## Installation

```bash
ssh forexvps "pip install requests"
ssh forexvps "python C:\algos\notifications\reporter.py --test"
```

Install tasks (PowerShell on VPS):
```powershell
$tasks = @(
    @{file="telegram_task.xml"; name="SYS_TELEGRAM"},
    @{file="reporter_task.xml"; name="SYS_REPORTER"},
    @{file="monitor_task.xml";  name="SYS_MONITOR"}
)
foreach ($t in $tasks) {
    Copy-Item "C:\algos\scheduler\$($t.file)" "C:\temp\$($t.file)"
    schtasks /create /tn $t.name /xml "C:\temp\$($t.file)" /ru trader /rp "312MXFjt7Q8Zoec"
}
```

---

## DST Note

`reporter_task.xml` trigger time:
- CDT (Mar–Nov): 4pm CT = 21:00 UTC — current setting
- CST (Nov–Mar): 4pm CT = 22:00 UTC — update in November

---

## User Access Control

Access is controlled via `C:\algos\users.json` on the VPS.
This file is **never committed to git** — it lives on the VPS only.

### Roles

| Role | Can do |
|---|---|
| `admin` | Everything — status, balance, trades, report, restart, stop, emergency, /users |
| `readonly` | Read only — status, balance, trades, report. No control commands. |

### users.json format

```json
{
  "users": {
    "429207285": {
      "name": "Jason",
      "role": "admin",
      "added": "2026-05-17"
    },
    "123456789": {
      "name": "Partner",
      "role": "readonly",
      "added": "2026-05-18"
    }
  }
}
```

A `users.template.json` in the `notifications/` folder shows the format.

### Adding / removing / changing roles

Manage users directly from your Mac via the algo panel — no VPS login needed:

```
algo → [4] Manage individual bot → select Telegram → [u] Manage users
```

From there you can list, add, remove, and change roles interactively.

To find someone's chat ID: ask them to message @userinfobot on Telegram.
Unauthorized access attempts are also logged to the VPS console:
`UNAUTHORIZED: chat=123456789 user=@theirhandle (Their Name)`

### Viewing current users

Via algo panel: `algo` → `[4]` → `Telegram` → `[u]` → `[1] List users`
Via Telegram: send `/users` (admin only — read-only view)

### Security layers

1. **Chat ID whitelist** — anyone not in `users.json` gets rejected silently (one message telling them it's private)
2. **Role enforcement** — readonly users can't use control commands even if they try
3. **Unauthorized logging** — all rejected attempts logged to VPS console with username and message
4. **Token privacy** — bot token is in the Python file; keep your repo private or move to env var

