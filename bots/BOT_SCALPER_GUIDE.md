# Bot 3 — EMA Momentum Scalper (Multi-Instrument)
**File:** `bots/bot_scalper.py` | **Account:** Dedicated scalper account | **MT5:** `C:\MT5_Scalper`

---

## What This Bot Is Built To Do

Bot 3 is an aggressive account-growth engine. It trades momentum on M5 using EMA stack alignment and M1 pullback entries. It runs a dynamic daily profit engine — once it hits its daily target it keeps running with peak protection until either a 10% pullback from the day's peak or a hard ceiling. It compounds position sizes automatically as the account grows. It must run on its own separate account because its risk profile is incompatible with Bot 1 and Bot 2.

---

## Strategy

**EMA Momentum Scalping — M5 Stack + M1 Pullback Entry**

1. M5 EMA stack (9/21/50) must all point in the same direction
2. Price pulls back to the EMA9 on M1 — a genuine retracement, not drift
3. A momentum candle fires in the trend direction (body >= 0.3x ATR)
4. RSI must not be extreme against the trade (no buying above 75, no selling below 25)
5. Enter immediately — scalps require fast execution

**When it trades:** All sessions except 3:00–7:00pm Texas (dead zone) and the previous dead zone start 15:00–19:00 UTC as a secondary check.

**Entry checklist:**
- M5 EMA 9/21/50 all aligned in same direction
- Price within 0.3x ATR of EMA9 on M1 (real pullback)
- Momentum candle body >= 0.3x ATR
- RSI not extreme against trade direction
- AI approves >= 52%

---

## Profitability Goal

- **Daily target:** +10% of account balance
- **Dynamic engine:** After hitting 10%, peak protection activates — bot keeps trading until a 10% pullback from the day's high-water mark
- **Hard ceiling:** +50% in a day — bot stops and locks in gains
- **Compounding tiers:** Risk % increases automatically as account grows

| Balance | Risk per trade |
|---|---|
| $0–$2,000 | 2.0% |
| $2,000–$4,000 | 2.5% |
| $4,000–$7,000 | 3.0% |
| $7,000–$10,000 | 3.5% |
| $10,000+ | 2.0% (resets, compounds again) |

---

## Risk Goal

| Control | Value |
|---|---|
| Daily loss floor | -8% — bot stops for the day |
| Peak protection | 10% pullback from day's peak triggers stop |
| Hard ceiling | +50% — locks in gains |
| Weekly loss cap | 20% |
| No overnight holds | Force-close 19:45 UTC |
| Momentum reversal | Closes immediately if M5 bias flips while in profit |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.5R | Stop to entry — fast |
| Trail | After BE | 0.4x ATR tight trail |
| Max hold | 20 M1 candles | Force-close — scalps don't drag |
| Momentum flip | M5 bias reverses + in profit | Close immediately |
| Market close | 19:45 UTC | Force-close all |

---

## Dead Zone (3:00–7:00pm Texas)

No new entries. Portfolio-level management every minute:
- Net profitable across all trades → close all immediately
- Individual trade profitable, portfolio negative → move to breakeven
- Losing trade getting worse → close immediately at best price
- Losing trade improving → hold and monitor until 3:45pm TX
- Any trade still open at 3:45pm TX → hard close

---

## AI Brain

Trains at 15 closed trades. Retrains every 5. AUC gate 0.55.
Learns from: EMA stack strength, pullback depth, momentum body size, RSI at entry, daily P&L %, daily trade count.

Trade close logging is fully implemented — every exit (SL/TP hit, momentum flip, max hold, dead zone, market close)
calls `log_close(ticket, close_price, pnl_usd)` which writes `outcome`, `pnl_usd`, and `close_price` to
`scalper_trades.json` and triggers AI retraining. `risk_usd` is correctly recorded at entry.

---

## Multi-Instrument Scanner

Every cycle the bot scans all symbols in `bot_scalper.watchlist` (config.json).
The symbol with the highest EMA stack strength wins the entry.

**Watchlist (Phase 1 defaults):** `["XAUUSD", "US30", "NAS100", "EURUSD", "GBPUSD"]`
*(verify exact broker symbol strings on VPS before going live)*

**Volatility filter (Phase 2):** Before evaluating a setup, the scanner checks `atr_ratio = ATR(5) / ATR(20)` on H1 candles. Symbols below `min_atr_ratio` (default 0.8) are skipped. If the entire watchlist is compressed, the bot sits out the cycle.

Config keys (in `bot_scalper` section):
- `"min_atr_ratio": 0.8`
- `"force_trade": false`

**Unresolved symbol handling:**
- Any symbol not found on the broker is logged to `symbol_errors.log` in the instance dir
- bot_state flag is set → monitor.py sends one Telegram alert per bad symbol per day

**Per-trade ATR:** Each trade stores its ATR at entry. The momentum-flip detection and trailing stop use the stored ATR, ensuring correct stop distances for each instrument.

**Position sizing:** Compounding tiers apply per trade using the candidate symbol's instrument info, not the default XAUUSD tick values.

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Too few signals | `pullback_tolerance` | Raise 0.3 -> 0.5 |
| Too many bad entries | `pullback_tolerance` | Lower 0.3 -> 0.2 |
| Stops hit on noise | `atr_sl_multiplier` | Raise 0.8 -> 1.0 |
| BE too slow | `breakeven_at_r` | Lower 0.5 -> 0.3 |
| Too aggressive | `daily_profit_target_pct` | Lower 10 -> 5 |

---

## Key Log Messages

```
SCALP SIGNAL | BULLISH | price=4388.50 | RSI=52.1 | stack=3/3
AI approved 64% >= 52%
FILLED | bullish 0.02L @ 4388.65
T12345 BE @ 4388.65 (0.5R)
T12345 MOMENTUM FLIP -- closing at 1.2R
DAILY TARGET HIT: +10.3%. Peak protection active. Continuing.
PEAK PROTECTION: pulled back 10% from peak +22%. Locked +12%.
DAILY CEILING HIT: +50.1%. Banking everything.
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$18.40 | Closing all 3 positions
PROGRESS | $1,000 -> $10,000 (10%) | growth=+0.0% | risk=2.0%
```

---

## Startup Reconciliation

On every restart, `reconcile_on_startup()` runs before entering the main loop:

**Missed closes** (trade in `scalper_trades.json` as open, but position not in MT5):
- Bot was down when the trade closed. Fetches actual close price + realised P&L from MT5
  deal history (7-day lookback window).
- If found: logs the close via `TradeLogger.log_close()`.
- If not found (deal expired from history): marks the trade `outcome="unknown"` via
  `TradeLogger.mark_orphaned()`. Orphaned trades are excluded from all P&L calculations.

**Phantom positions** (position in MT5, no record in `scalper_trades.json`):
- trades.json was wiped or trade entered before logger initialised.
- Adds a stub `log_entry(..., is_reentry=True)` so the position is tracked going forward.

## Balance and State Persistence

Every main-loop iteration writes to `bot_state.json`:
- `balance` — actual `mt5.account_info().balance`
- `daily_start` — balance at start of current UTC day (from `daily_engine.start`)
- `weekly_start` — balance at start of current ISO week (persisted in `scalper_weekly.json`)
- `last_write` — UTC timestamp used by `pnl_tracker.py` to detect live mode

`weekly_start` survives restarts via `scalper_weekly.json` in the instance folder.

## Weekly Cap Behaviour

When the weekly drawdown exceeds `WEEKLY_LOSS_CAP_PCT`:
1. All open positions are closed.
2. `bot_state: day_locked=True, lock_reason="WEEKLY CAP: …"` is set — `pnl_tracker.py`
   sends the lock alert within 1 minute.
3. Bot enters a 6-hour interruptible cooldown (60-second poll loop, not `time.sleep(21600)`).
4. `/resume scalper` breaks the cooldown early by setting `resume_trading=True` in bot_state.
