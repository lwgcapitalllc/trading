# Bot 2 — Mean Reversion (Multi-Instrument)
**File:** `bots/bot_mean_reversion.py` | **Account:** Main (shared with Bot 1) | **MT5:** `C:\Program Files\PU Prime MT5 Terminal`

---

## What This Bot Is Built To Do

Bot 2 trades price snapping back to its statistical average after extreme overextension. When gold stretches too far from its mean — confirmed by Bollinger Bands, RSI, and VWAP simultaneously — the probability of a snapback is high. This bot captures that move quickly and banks profit at 1R. It runs 24 hours and generates consistent smaller wins, complementing Bot 1 which is session-specific.

---

## Strategy

**Mean Reversion — Bollinger Band + RSI + VWAP Confluence**

A signal fires when all three confirm the same overextension:
- Price outside Bollinger Band (2+ standard deviations)
- RSI below 28 (oversold) or above 72 (overbought)
- Price deviated from VWAP by 1.5+ standard deviations
- Rejection candle confirms buyers/sellers stepping in

**When it trades:** 24 hours, every day. Dead zone 3–7pm Texas.

**Entry checklist — all must be true:**
- Price outside Bollinger Band (2+ std dev)
- RSI confirms overbought/oversold
- VWAP deviation confirms overextension
- Rejection candle present
- Confluence score >= 4
- AI approves >= 55%

---

## Profitability Goal

- **Target per trade:** 1R (tight, fast, consistent)
- **Philosophy:** Many small wins compound faster than few large wins at this account size
- **Early close:** Closes if RSI returns to neutral (50 area) — mean has been reached, no reason to hold
- **Cash flow layer:** Designed to generate consistent daily P&L while Bot 1 waits for high-quality setups

---

## Risk Goal

| Control | Value |
|---|---|
| Risk per trade | 2% of balance |
| Breakeven | +0.3R — very fast protection |
| Full close | +1R — always banks profit |
| Daily loss cap | 10% — no new entries |
| Weekly loss cap | 20% — 6hr cooldown |
| No overnight holds | Force-close 19:45 UTC |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.3R | Stop to entry — very fast |
| Full close | +1R | Entire position closes |
| Early close | RSI returns to neutral | Mean reached — exit |
| Tight trail | After BE, before 1R | 0.3x ATR trail |
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
Learns from: confluence score, RSI value, BB position, VWAP deviation, daily P&L %, simultaneous positions, regime score.

Trade close logging is fully implemented — every exit (SL/TP hit, 1R full close, RSI-neutral early close,
dead zone, market close) calls `log_close(ticket, close_price, pnl_usd)` which writes `outcome`, `pnl_usd`,
and `close_price` to `mean_reversion_trades.json` and triggers AI retraining. `risk_usd` is correctly
recorded at entry.

---

## Regime Behaviour

Bot 2 is the INVERSE of Bot 1 — it thrives when Bot 1 struggles:

| Regime | Response |
|---|---|
| RANGING | Full size — ideal, price oscillates predictably |
| TRANSITIONING | 75% size |
| TRENDING | 40% size — trends fight reversion |

---

## Multi-Instrument Scanner

Every cycle the bot scans all symbols in `bot_mean_reversion.watchlist` (config.json).
The symbol with the highest confluence score wins and gets the trade entry.

**Watchlist (Phase 1 defaults):** `["XAUUSD", "EURUSD", "AUDUSD", "USDCAD", "EURGBP"]`
*(verify exact broker symbol strings on VPS before going live)*

**Unresolved symbol handling:**
- Any symbol not found on the broker is logged to `symbol_errors.log` in the instance dir
- bot_state flag is set → monitor.py sends one Telegram alert per bad symbol per day

**Per-trade ATR:** Each trade stores its ATR at entry. RSI early-exit and trailing stop use the stored ATR, keeping position management correct per instrument.

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Giving back profits | `breakeven_at_r` | Lower to 0.2 |
| Closing too early | `partial_close_r` | Raise to 1.5 |
| Too few signals | `bb_std_entry` | Lower 2.0 -> 1.8 |
| Too many bad signals | `bb_std_entry` | Raise 2.0 -> 2.2 |

---

## Key Log Messages

```
REVERSION SIGNAL | BULLISH | score=5 | RSI=24.3
AI approved 61% >= 55%
ENTRY | bullish | lots=0.02 | entry=4385.20 SL=4380.00 TP=4400.00
T12345 -> BREAKEVEN @ 4385.20 (0.31R)
T12345 FULL CLOSE @ 1.0R -- banking profit.
T12345 EARLY CLOSE -- RSI neutral (48.2) | profit=0.8R
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$22.10 | Closing all 1 position
New day 2026-05-16 | $2,759.28 | AI: Trained | AUC=0.58 | WR(10)=60%
```


---

## Startup Reconciliation

On every restart, `reconcile_on_startup()` runs before the main loop:

**Missed closes** (trade open in trades.json, position gone from MT5):
- Bot was down when the trade closed. Fetches actual close price + P&L from MT5 deal history
  (7-day lookback). Logs via `TradeLogger.log_close()` or marks `outcome="unknown"` via
  `TradeLogger.mark_orphaned()` if history is unavailable.

**Phantom positions** (position in MT5, no record in trades.json):
- Adds a stub `log_entry(..., is_reentry=True)` so the position is tracked going forward.

## Balance and State Persistence

Every main-loop iteration writes to `bot_state.json`:
- `balance` — actual `mt5.account_info().balance`
- `daily_start` — balance at start of current UTC day
- `weekly_start` — balance at start of current ISO week (persisted in weekly JSON file)
- `last_write` — UTC timestamp used by `pnl_tracker.py` to detect live mode

## Weekly Cap Behaviour

When weekly drawdown exceeds the cap:
1. All open positions are closed.
2. `bot_state: day_locked=True, lock_reason="WEEKLY CAP: …"` — triggers lock alert.
3. Interruptible 6-hour cooldown (60-second poll). `/resume <bot>` breaks it early.
