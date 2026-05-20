# LWG Capital LLC — Algo Trading Suite
## Claude Context File

> Drop this at the start of any Claude chat or Claude Code session.
> Keep it updated as the project evolves.

---

## What This Project Is

Multi-bot algorithmic trading system for gold (XAUUSD) and futures (MNQ).
Built in Python, runs 24/7 on a Windows VPS (ForexVPS, IP: 45.82.164.112).
Controlled from Mac via `algo.py` command-line panel.
Code lives on GitHub. Deploy flow: edit on Mac → git push → ssh pull on VPS → algo restart.

---

## The Bots

| Bot | File | Strategy | Account | MT5 Instance |
|-----|------|----------|---------|--------------|
| SMC Trend | `bot_smc_trend.py` | Judas Swing + FVG, H4 trend filter, M15 entry | gold_main #700103491 | PU Prime Terminal |
| Mean Reversion | `bot_mean_reversion.py` | BB + RSI + VWAP, 1R target, fast close | gold_main #700103491 | PU Prime Terminal |
| Scalper | `bot_scalper.py` | EMA stack + pullback, M5/M1, 5–20 trades/day | gold_scalper #700107520 | MT5_Scalper |
| FFT | `bot_fft.py` | Dual Fibonacci confluence, H1+H4 trend | gold_fft #700107749 | MT5_FFT |
| Futures | `bot_futures.py` | SMC_TREND on MNQ via Tradovate API | futures_account1 | N/A (Tradovate) |

SMC Trend and Mean Reversion share one MT5 account and are designed to be uncorrelated — one works trending markets, the other ranging markets.
Scalper is isolated on its own account due to high volatility (+50% / -8% swings possible).
FFT is the lowest risk (1%) — unproven in live trading, still learning.

---

## Shared Components

| File | Role |
|------|------|
| `shared_ai_brain.py` | AI engine (Claude API), trade logger, daily performance logger |
| `shared_calmar.py` | Calmar ratio tracker, morning report |
| `shared_regime.py` | Market regime classifier: TRENDING / TRANSITIONING / RANGING |
| `bot_utils.py` | Config loader, logging, path resolver |
| `launcher.py` | Universal Task Scheduler launcher |
| `startup_coordinator.py` | Orchestrates bot startup sequence |
| `tradovate.py` | Tradovate API executor for Bot Futures |
| `algo.py` | Mac control panel — start/stop/status/logs/restart |

---

## Risk Rules (All Bots)

- SMC Trend: 2% risk, 3:1 target, 10% daily loss cap
- Mean Reversion: 2% risk, 1:1 target, 10% daily loss cap
- Scalper: 2–3.5% risk (auto-scaling), -8% floor
- FFT: 1% risk, 2:1–5:1 target, 5% daily loss cap
- Futures (MNQ): 1% risk, max 4 contracts, 3% daily loss cap

**Dead Zone (all bots): No new entries 3:00pm–7:00pm Texas time.**
During dead zone: net profit → close all. Individual profit + portfolio negative → breakeven. Losing worsening → close immediately.

---

## AI Thresholds

- SMC Trend + Mean Reversion: min_ai_probability = 0.55 (stricter, more history)
- Scalper + FFT: min_ai_probability = 0.52 (newer, learning phase)

---

## Infrastructure

- **VPS:** ForexVPS Windows Server, 24/7
- **Mac control:** `python algo.py start|stop|restart|status`
- **Deploy:** `git push` on Mac → `ssh forexvps "cd C:\algos && git pull"` → `algo restart`
- **Monitoring:** Telegram bot for alerts, reporter.py for daily summaries, monitor.py for health checks
- **Scheduling:** Windows Task Scheduler via XML task files
- **Backup:** `backup.py` runs twice daily (midnight + noon CT) via SYS_BACKUP. Commits VPS runtime
  data to the `backups` orphan branch via a git worktree at `C:\algos-backup`. Never touches `main`,
  so Mac deploys and VPS backups never conflict. See README § VPS Data Backup for full file list.

---

## Repo Structure

```
algos/
├── algo.py                    ← Mac control panel
├── backup.py                  ← Twice-daily backup to backups branch
├── CLAUDE.md                  ← Auto-loaded Claude Code instructions (quant rules + doc rules)
├── CONTEXT.md                 ← This file
├── stress_test_suite.py
├── instructions/              ← Detailed standing instructions (referenced by CLAUDE.md)
├── .claude/
│   ├── settings.local.json
│   └── commands/              ← Custom slash commands: /session-start /update-context /quant-review
├── shared/
│   ├── shared_ai_brain.py
│   ├── shared_calmar.py
│   └── shared_regime.py
├── bots/
│   ├── bot_utils.py
│   ├── launcher.py
│   ├── startup_coordinator.py
│   ├── bot_smc_trend.py
│   ├── bot_mean_reversion.py
│   ├── bot_scalper.py
│   ├── bot_fft.py
│   └── bot_futures.py
├── executors/
│   └── tradovate.py
└── markets/
    ├── fx/instances/
    │   ├── gold_main/
    │   ├── gold_scalper/
    │   └── gold_fft/
    └── futures/instances/
        └── futures_account1/
```

Note: VPS runtime data (`*_trades.json`, `bot_state.json`, `*.pkl`, etc.) is gitignored
on `main` and backed up to the separate `backups` branch by `backup.py`.

---

## Current Phase

Demo trading. Targets to advance:
- 15+ closed trades per bot
- Calmar >= 2.0 to continue demo
- Calmar >= 2.5 (SMC Trend) / 2.0 (Mean Reversion) to begin prop firm evaluation
- FFT risk stays at 1% until 30+ trades with solid Calmar

Calmar benchmarks: 2.0 = okay | 3.0 = decent | 5.0+ = exceptional

---

## Coding Conventions

- Python throughout
- Each bot is self-contained in its own file
- Shared logic lives in shared/ — never duplicate in bot files
- Config driven via config.json per instance
- All logging via bot_utils.py logger setup
- Never optimize to past data — overfitting is the enemy

---

## What Was Done This Session (2026-05-19)

### Bug 1 — Silent bot hangs (FIXED)
All 4 bots had `input("Type CONFIRM to start:")` behind a `sys.stdin.isatty()` check.
Windows Task Scheduler allocates a real console, so `isatty()` returned `True` and the bots
blocked forever waiting for keyboard input — appearing alive in the process list but never trading.
Fix: removed the prompt entirely. Entry point is now just `run()`.

### Bug 2 — Log close never called (FIXED — most critical)
All 4 bots called `log_entry()` on trade open but **never called `log_close()`** on close.
Result: every trade in `*_trades.json` had `outcome: null`, `pnl_usd: null`, `close_price: null`.
AI brain had zero training data. Telegram `/balance` always showed starting balance.

Fix applied to all 4 bots:
- Added `get_deal_result(ticket)` helper — queries `mt5.history_deals_get()` to get close price
  and P&L for positions closed externally by the broker (SL/TP hit)
- `close_position()` now returns `(success, close_price, pnl_usd)` instead of a plain bool
- `manage_positions()` and `handle_dead_zone()` now accept `logger` and `ai` as parameters
- Every trade removal — SL/TP hit, momentum flip, max hold, dead zone, market close — calls
  `logger.log_close(ticket, cp, pnl)` and `ai.on_trade_closed(ticket, cp, pnl)`
- Fixed `risk_usd=0.0` in all `log_entry()` calls — now passes actual dollar risk amount

### Bug 3 — Log staleness alert added to monitor.py
Monitor now detects "alive but blocked" bots: if process is running but log file hasn't been
written in 90 minutes, sends Telegram alert with last log line. Controlled by `LOG_STALE_MINUTES = 90`.

### Full account reset
- All 4 MT5 accounts reset to $1,000 via broker backoffice (old equity was from a buggy period)
- All VPS tracking files reset: `*_trades.json → []`, `*_equity.json → [{balance:1000}]`,
  `*_weekly.json → {weekly_start:1000}`, `bot_state.json` balances zeroed
- Backup branch cleared of stale pre-reset data; fresh backup committed at 2026-05-19 05:13 UTC
- All 4 bots restarted cleanly. Scalper killed → file wiped → restarted (in that order) to ensure
  it loaded the empty file rather than writing its stale in-memory state back to disk.

### Current VPS state (as of end of session)
- All 4 bots running: `BOT_SMC_TREND`, `BOT_MEAN_REVERSION`, `BOT_SCALPER`, `BOT_FFT`
- Telegram bot running: `SYS_TELEGRAM`
- All `*_trades.json`: 0 entries (clean slate)
- No `.pkl` model files exist (AI never trained — log_close was broken)
- Next closed trade on any bot = first real data point with outcome populated

---

---

## What Was Done This Session (2026-05-19 — Session 2)

### Feature — Peak protection lock alert + `/resume` override

**Problem:** When `bot_scalper.py`'s `DailyProfitEngine` triggered peak protection (daily P&L
pulled back 10 percentage points from peak after hitting the +10% daily goal), the bot locked
silently. No Telegram alert was sent. The only signal was the 90-minute stall alert — a blunt
proxy. User had no way to override the lock without a full restart.

**Changes:**

`shared/bot_state.py`
- Added `lock_reason: ""`, `lock_alerted: False`, `resume_trading: False` to `_default_state`

`bots/bot_scalper.py`
- Imported `write_bot`, `read_bot` from `bot_state`
- On `should_stop`: writes `day_locked=True`, `lock_reason=<stop_reason>`, `lock_alerted=False`
  to `bot_state.json` immediately after `close_all_positions`
- Wait loop now checks `read_bot("scalper").get("resume_trading")` each 60s cycle.
  If True: clears the flags, resets `daily_engine.stopped = False`, and breaks out — resuming
  trading without a restart. Peak protection is then OFF for the rest of the day.

`notifications/pnl_tracker.py`
- `check_alerts()` now detects `day_locked=True` + not `lock_alerted` and fires:
  `🔒 Bot Scalper — Day Locked` with the exact reason, balance, and `/resume` hint
- Daily reset block now also resets `day_locked`, `lock_alerted`, `lock_reason`

`notifications/telegram_bot.py`
- Added `/resume <bot>` command: sets `resume_trading=True` in bot_state. No confirm required.
  Responds with a warning that peak protection is now OFF for the rest of the day.
- Added `/resume` to admin `ROLE_COMMANDS`
- Updated `/help` text with Override section

**Only the scalper has peak profit protection** — SMC Trend, Mean Reversion, and FFT only have
daily loss caps, no peak drawdown engine. The `day_locked` field in bot_state.py is generic and
can be extended to other bots in future.

### Infrastructure — CLAUDE.md + .claude/commands/

Added `CLAUDE.md` at repo root (auto-loaded by Claude Code every session). Contains:
- Quant developer mindset rules
- Non-negotiable documentation update rules
- Coding conventions

Added `.claude/commands/` with custom slash commands:
- `/session-start` — oriented session startup checklist
- `/update-context` — prompt to update CONTEXT.md after a session
- `/quant-review` — pre-commit risk and doc coverage review

Renamed and removed: `instructions/keep_docs_updated.md` content is now folded into `CLAUDE.md`.
The `instructions/` folder is kept for future detailed instruction files.

### Scalper overnight incident (2026-05-18→19)

Scalper hit +10% daily goal at 12:46 AM CT ($1,082.21, +$120 from ~$962 day-start).
Peak protection activated. Bot kept trading, peaked at approximately +22.5% (~$1,179),
then P&L pulled back 10pp to +12.5% → peak protection triggered lock at ~2 AM CT.
`close_all_positions` ran; bot entered midnight-wait loop. Log went silent.
Stall alert fired at 3:33 AM CT. Actual locked balance: $1,082.85.
`/balance` showed $1,088.13 (pnl_tracker reading from trades.json — stale vs MT5 actual).

---

## What Was Done This Session (2026-05-19 — Session 3)

### Feature — Migrate Telegram bot to shared group chat

All Telegram interactions (commands, replies, and scheduled alerts) now go to a shared group
chat ("LWG Capital Algos Notifications", id `-1003977707258`) instead of admin DM.

**Changes across 4 files:**

`notifications/telegram_bot.py`
- Added `GROUP_CHAT = "-1003977707258"` constant alongside `ADMIN_CHAT` (kept)
- `send()` broadcasts to `GROUP_CHAT` (startup ping, unsolicited alerts)
- Main polling loop now splits `chat_id` (where to reply) and `user_id` (who sent it).
  `chat_id = msg.chat.id`, `user_id = msg.from.id`. All `get_role()` / `can()` calls
  use `user_id`; all `send_to()` calls use `chat_id`. This is correct for groups: every
  member shares one `chat.id` but each has a unique `from.id`.
- `UNAUTHORIZED` log line now shows both: `chat={chat_id} user={user_id} (@username)`
- `cmd_users()` "← you" marker uses `user_id` not `chat_id`
- `pending_action` (module-level dict) replaced with `pending_actions: dict` keyed by
  `user_id`. Two users can now `/restart` simultaneously without overwriting each other's
  confirm state. `request_confirm()` and `cmd_confirm()` take `user_id` param.
- `cmd_report()` and `_ask_report_group()` take `user_id` param to set per-user
  pending action for the report group selection flow.
- `handle_message()` signature updated to `(text, chat_id, user_id)`

`notifications/monitor.py`
- Added `GROUP_CHAT` constant; renamed `TELEGRAM_CHAT` → `ADMIN_CHAT` for consistency
- `send_alert()` now sends to `GROUP_CHAT`

`notifications/pnl_tracker.py`
- Added `GROUP_CHAT` constant (kept `ADMIN_CHAT`)
- `send_alert()` now sends to `GROUP_CHAT`

`notifications/reporter.py`
- Added `GROUP_CHAT` constant; renamed `TELEGRAM_CHAT` → `ADMIN_CHAT` for consistency
- `send_telegram()` now sends to `GROUP_CHAT`

**Authorization model unchanged:** `users.json` still stores personal Telegram user IDs
(from `@userinfobot`). The group chat ID is only used as a send destination — never for auth.

---

---

## What Was Done This Session (2026-05-19 — Session 4)

### Root-cause investigation — balance discrepancy and false alerts

Diagnosed three compounding bugs that caused scalper `/balance` to show $785.67 vs MT5 actual
$910.62, a false weekly cap alert, and a "/resume not locked" confusion:

1. **Hardcoded starting balance** — `pnl_tracker.py` used `BOT_STARTING_BALANCES = {"scalper": 1000.0}`
   rather than reading the actual session-start balance. Any restart with a different balance
   immediately breaks all P&L math.
2. **Unlogged trade closes** — when the bot restarts with an empty `open_trades` list but
   old MT5 positions still open, subsequent closes are not matched to trades.json records
   ("Could not find open trade"). Those trades show `outcome=None` forever, corrupting cumulative P&L.
3. **Floating P&L captured before close** — `close_position()` saved `p.profit` (the unrealised
   float P&L BEFORE the order executes) instead of the actual fill P&L from deal history.
   This produced wrong positive pnl_usd on losing trades.

### Feature — Startup reconciliation (all 4 bots)

Added `reconcile_on_startup(open_trades, logger, ai)` function to all 4 bots
(`bot_scalper.py`, `bot_smc_trend.py`, `bot_mean_reversion.py`, `bot_fft.py`).

Logic runs once at startup, after `recover_open_positions()`:
- **Missed close** (in trades.json as open, NOT in MT5): bot was down when trade closed.
  Calls `get_deal_result(ticket)` to fetch actual close price + P&L from MT5 deal history.
  Logs the close via `logger.log_close()`. If deal history is unavailable, marks
  trade as `outcome="unknown"` via `logger.mark_orphaned()` (excluded from P&L math).
- **Phantom position** (in MT5, NOT in trades.json): trades.json was wiped or trade entered
  before logger was initialised. Adds a stub entry via `logger.log_entry(..., is_reentry=True)`
  so the position is tracked going forward.

### Fix — Actual close P&L (all 4 bots)

`close_position()` in all 4 bots now:
1. Executes the close order.
2. Sleeps 0.3s for MT5 to record the deal.
3. Calls `get_deal_result(ticket)` to fetch the actual fill price and realised P&L.
4. Falls back to `p.profit` (pre-close float) only if deal history is unavailable.

`get_deal_result()` lookback extended from 1 day to 7 days in all bots.

### Fix — mark_orphaned() in shared_ai_brain.py

Added `TradeLogger.mark_orphaned(ticket)` method. Sets `outcome="unknown"`, `pnl_usd=None`,
`r_multiple=None` on a pending trade with no recoverable deal history. The "unknown" outcome
is excluded from `pnl_tracker.py`'s `outcome in ('win','loss','breakeven')` filter, so it
cannot corrupt P&L calculations.

### Feature — Bot publishes MT5 ground truth to bot_state (all 4 bots)

Every main-loop iteration each bot now writes to `bot_state.json`:

```json
{
  "balance":      <MT5 acct.balance>,
  "daily_start":  <session daily_start>,
  "weekly_start": <weekly_start>,
  "last_write":   "<UTC ISO timestamp>",
  "status":       "running"
}
```

`last_write` is a heartbeat timestamp used by `pnl_tracker.py` to determine whether
the bot is actively running.

### Feature — pnl_tracker.py dual-mode P&L calculation

`pnl_tracker.py` now operates in two modes per bot:

**LIVE mode** (bot `last_write` within 300 seconds):
- Uses `balance`, `daily_start`, `weekly_start` from `bot_state.json` directly.
- `daily_pnl = balance − daily_start`, `weekly_pnl = balance − weekly_start`.
- No trades.json math, no hardcoded starting balance — values are MT5-authoritative.

**OFFLINE mode** (bot stopped or last_write stale > 5 min):
- Falls back to trades.json math (existing behaviour).
- Uses `bot_state["balance"]` as the last-known balance when trades.json has no `pnl_usd`
  data, rather than the hardcoded $1,000 starting balance.

Printed output now includes `[live]` or `[offline]` tag per bot each run.

### Fix — Weekly cap: interruptible cooldown (all 4 bots)

Replaced `time.sleep(21600)` weekly cap with a 60-second poll loop that:
- Sets `bot_state: day_locked=True, lock_reason="WEEKLY CAP: …"` so `pnl_tracker.py`
  fires the existing lock alert and Telegram reports it correctly.
- Exits early if `read_bot(key).get("resume_trading")` is set (via `/resume` command).
- On early exit or expiry, sets `day_locked=False`.

Previously the bot was unreachable for 6 hours — no monitoring, no override, no alerts.

### Fix — Weekly start persistence (scalper)

Scalper was not persisting `weekly_start` across restarts. Pattern now matches the other
bots: reads/writes `scalper_weekly.json` on startup and on weekly reset.

### VPS state after this session

All 4 bot files updated. Not yet deployed — deploy required via git push or rsync to VPS.
Existing trades.json files on VPS have some corrupted `pnl_usd` values (from old pre-close
floating P&L bug). Once bots are restarted after deploy, `reconcile_on_startup` will
correctly tag any pending-but-closed trades. Historical pnl_usd corruption for already-closed
trades will not be fixed automatically — a one-time trades.json reset is acceptable if
needed, since going-forward records will be clean.

---

## What I Am Working On (Update This Section Each Session)

- Last completed: Full accounting reconciliation overhaul across all 4 bots + pnl_tracker.
- Next up: Deploy to VPS (rsync or git push), restart all bots, verify live output shows
  `[live]` mode in pnl_tracker and that `/balance` matches MT5 actual balance within $1.
- Open questions / decisions pending:
  - Existing trades.json on VPS has corrupted pnl_usd. Consider resetting to `[]` per bot
    on first deploy, letting reconcile_on_startup re-log any currently-open positions.
  - `bot_futures.py` — NOT yet audited for the same reconciliation/P&L bugs.
  - Scalper: consider whether to raise `peak_drawdown_trigger_pct` above 10%.
