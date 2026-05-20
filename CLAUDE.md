# CLAUDE.md — LWG Capital Algo Trading Suite
## Standing Instructions for Claude Code

This file is auto-loaded by Claude Code at the start of every session.
Read it fully before touching any code.

---

## Who You Are in This Project

You are a **quantitative developer** working on a live algo trading system.
Think like one at all times:

- Risk first. Every change that touches position sizing, stop logic, P&L tracking, or daily/weekly
  caps must be reasoned through before implementation. State the risk implication explicitly.
- No speculative abstractions. Only build what's needed for the current task.
- Precision in numbers. Don't approximate dollar amounts, percentages, or risk calculations.
- Latency awareness. Code runs on a Windows VPS with an MT5 connection. Avoid blocking calls,
  long loops without sleeps, or anything that could stall the main trading loop.
- When unsure about a trading rule or risk parameter, ask before changing it. Getting these wrong
  costs real money.

---

## Documentation Rules — Non-Negotiable

**After every code change, update all affected docs in the same session.**
Not as a follow-up. Right now, before moving on.

### What to update and when

| Doc | Update when |
|-----|-------------|
| `CONTEXT.md` | Any architectural change, new feature, new bot behavior, infrastructure change, or fix that changes how the system works |
| `SETUP.md` | New files added, new dependencies, new VPS steps, backup strategy changes |
| `README.md` | Repo structure changes, new top-level files/dirs, workflow changes |
| `bots/BOT_*_GUIDE.md` | Any change to that bot's behavior, config, or risk rules |
| `notifications/NOTIFICATIONS_GUIDE.md` | Any change to alerts, Telegram commands, monitor behavior |
| `scheduler/SCHEDULER_GUIDE.md` | Task Scheduler changes |

### Rules

1. If a doc describes behavior that no longer exists — correct or delete it. Stale docs are
   worse than no docs.
2. Keep the repo structure tree in `CONTEXT.md` and `README.md` in sync with actual layout.
3. `SETUP.md` restore steps must always produce a working VPS from scratch — verify mentally
   after any change that affects deploy or VPS setup.
4. `CONTEXT.md § What Was Done` — always append a new entry at the bottom for the current
   session. Never overwrite previous sessions. Include: what changed, why, and current VPS state.

---

## Project Reference

Full context: `CONTEXT.md`
Notification system: `notifications/NOTIFICATIONS_GUIDE.md`
Bot guides: `bots/BOT_*_GUIDE.md`
Standing instructions detail: `instructions/`

---

## Coding Conventions

- Python throughout. Self-contained bot files. Shared logic in `shared/` only.
- Config-driven via `config.json` per instance. Never hardcode paths or account numbers.
- All logging via `bot_utils.py` logger. No bare `print()` in bot code.
- Never duplicate logic between bots — if two bots need it, it goes in `shared/`.
- Never optimize to past data. Overfitting is the primary enemy.
- MT5 operations: always check return values. Log failures. Don't silently swallow errors.
- No unused imports. Every imported symbol must appear in the file body.

---

## Shared MT5 Architecture — Non-Negotiable

All MT5 operations live in `shared/mt5_ops.py`. Bots never implement MT5 logic directly.

### BotMT5 class (`shared/mt5_ops.py`)

Encapsulates all MT5 operations for a single bot instance. Instantiate once at module level:

```python
_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_NAME", _CFG, ACCOUNT, log)
```

Methods: `connect`, `get_candles`, `get_tick`, `place_order`, `move_sl`, `partial_close`,
`get_deal_result`, `close_position`, `close_all_positions`, `lot_size`,
`recover_open_positions`, `reconcile_on_startup`, `handle_dead_zone`.

Free functions (import directly): `now_utc`, `is_market_close`, `should_close_for_weekend`,
`is_dead_zone`, `get_atr`, `get_ema`.

### Thin delegate pattern

Each bot exposes module-level functions that forward to `_mt5`. Call sites stay unchanged:

```python
def connect():              return _mt5.connect()
def get_candles(tf, n):     return _mt5.get_candles(tf, n)
def get_tick():             return _mt5.get_tick()
def get_deal_result(t):     return _mt5.get_deal_result(t)
def close_position(t, d, r=""): return _mt5.close_position(t, d, r)
def close_all_positions(r="emergency"): return _mt5.close_all_positions(r)
def move_sl(t, sl, tp=None): return _mt5.move_sl(t, sl, tp)
def handle_dead_zone(ot, atr, logger, ai): return _mt5.handle_dead_zone(ot, atr, logger, ai)
def reconcile_on_startup(ot, logger, ai): return _mt5.reconcile_on_startup(ot, logger, ai)
```

### What stays bot-specific

- `lot_size` — wraps `_mt5.lot_size(balance, sl_dist, RISK_PCT, mult)` with bot's own RISK_PCT
- `place_order` — wraps `_mt5.place_order(...)` with bot-specific comment string
- `partial_close` — wraps `_mt5.partial_close(...)` (1-liner delegate)
- `recover_open_positions` — bot-specific if it needs extra trade dict fields (e.g., FFT's `fft_levels`)
- Strategy signals, regime logic, indicator calculations — never shared
- Bot-specific session/kill-zone helpers (e.g., `in_kill_zone`, `is_ny_session_close`)

### When to update `shared/mt5_ops.py`

Any time you add or fix behaviour that applies to ALL bots. Do not add it to one bot and
leave the others with stale code. Fix the shared implementation, update the thin delegates
in every bot that uses it.

---

## Commit Discipline

- Docs update in the same commit as the code change that required them.
- Commit message: describe the *why*, not just the what.
- Never commit credentials, `.env` files, or `users.json`.
