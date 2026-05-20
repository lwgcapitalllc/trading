# Bot 5 — FFT (Fibonacci Fractal Trading)
**File:** `bots/bot_fft.py` | **Account:** Dedicated FFT account | **MT5:** `C:\MT5_FFT`

---

## What This Bot Is Built To Do

Bot 5 trades a proprietary dual-Fibonacci confluence strategy. It only enters when two separate Fibonacci tools agree on the same price zone — the FFT fib defines where price might retrace to, and the Sniper fib defines where specifically within that zone to enter. The overlap of these two zones is the entire edge. No overlap means no trade, no exceptions. This strategy works on any trending instrument and any timeframe.

---

## Strategy

**FFT (Fibonacci Fractal Trading) — Dual Fib Confluence**

Two fibs are drawn on every qualifying setup:

**FFT Fib (standard retracement):**
- Drawn on the move that caused the Break of Structure
- Bullish: from Higher Low to new Higher High
- Bearish: from Lower High to new Lower Low
- Defines the entry consideration zone: 61.8% to 88.6% retracement

**Sniper Fib (reverse fib — green zone):**
- Drawn on the counter move immediately BEFORE the BOS candle
- The 38.2% to 50% band of this fib = the GREEN ZONE

**The critical rule:** The green zone must overlap with the FFT 61.8–88.6% zone. If they don't overlap, no trade.

**When it trades:** M15 entries. H1 + H4 EMA 200 trend filter. Dead zone 3–7pm Texas.

**Entry checklist — all must be true:**
- Break of Structure confirmed on M15
- H1 and H4 EMA 200 both agree on trend direction
- Price retraces into FFT 61.8–88.6% zone
- Sniper 38.2–50% green zone overlaps that same zone
- Confluence score >= 4/10
- AI approves >= 52%

**Entry execution:**
- Entry 1: at sniper 50% (top of green zone)
- Entry 2: at sniper 38.2% (bottom of green zone) — only if lots allow

---

## Profitability Goal

- **TP1 (80% of position):** FFT 50% retracement level
- **TP2 (20% of position):** FFT 38.2% retracement level
- **Deep entry (78.6%+ entry):** TP1=70.2%, TP2=61.8% — adjusted for deeper retrace
- **Min lots (0.01):** Single entry, full close at FFT 50%
- **R:R target:** 2:1 minimum, typically 3:1 to 5:1 depending on entry depth
- **Refinement:** Strategy improves over time as more chart examples are provided

---

## Risk Goal

| Control | Value |
|---|---|
| Risk per trade | 1% of balance |
| Stop loss | 1% behind bottom of green zone |
| Breakeven | +0.5R — move to entry |
| Daily loss cap | 5% — no new entries |
| Weekly loss cap | 15% — cooldown |
| Max trades per day | 3 |
| No overnight holds | Force-close 19:45 UTC |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +0.5R | Stop to entry |
| TP1 | FFT 50% level | Close 80% (or 100% at 0.01 lots) |
| TP2 | FFT 38.2% level | Close remaining 20% |
| Deep entry TPs | Entry at 78.6%+ | TP1=70.2%, TP2=61.8% |
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
Learns from: confluence score, ATR, session, H4 alignment, FVG, overlap tightness, daily P&L %.

Trade close logging is fully implemented — every exit (SL/TP hit, dead zone, market close) calls
`log_close(ticket, close_price, pnl_usd)` which writes `outcome`, `pnl_usd`, and `close_price` to
`fft_trades.json` and triggers AI retraining. `risk_usd` is correctly recorded at entry (accounts for
the `risk_mult` regime multiplier).

**Refinement over time:** As more chart examples are provided, the BOS detection sensitivity, swing lookback, and confluence scoring weights will be tuned. Version history tracked in config comments.

---

## Confluence Scoring (0–10)

| Factor | Points |
|---|---|
| H1 trend aligned | +2 |
| H4 trend aligned | +2 |
| Both H1 and H4 aligned | +1 extra |
| FVG at green zone | +2 |
| London or NY session | +1 |
| Deep entry (tighter SL) | +1 |
| Tight overlap (>70% of sniper zone) | +1 |

---

## Regime Behaviour

| Regime | Response |
|---|---|
| TRENDING | Full size — required |
| TRANSITIONING | Reduced entries |
| RANGING | No new entries — strategy requires trend |

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Missing obvious BOS | `swing_lookback` | Lower 3 -> 2 |
| Too many weak BOS | `bos_min_body_mult` | Raise 1.5 -> 2.0 |
| Entry zone too tight | `fft_entry_min` | Lower 0.618 -> 0.50 |
| Entry zone too wide | `fft_entry_max` | Lower 0.886 -> 0.786 |
| SL too tight | `sl_pct_behind_zone` | Raise 0.01 -> 0.015 |

---

## Key Log Messages

```
BOS BULLISH @ 4540.00 | FFT zone: 4510.00-4495.00 | Green zone: 4518.00-4525.00
GREEN ZONE OVERLAP | retrace=72.0% | deep=NO | overlap=4518.00-4525.00
SETUP | BULLISH | score=7/10 | session=london | FVG=True
AI approved 64% >= 52%
SIGNAL | BULLISH | entry=4520.00 SL=4513.00 | TP1=4548.00 TP2=4562.00 | R:R=4.0
ORDER FILLED | bullish 0.01L @ 4520.10
T12345 -> BREAKEVEN @ 4520.10 (0.52R)
No BOS detected. Waiting 60s.
No green zone overlap with FFT entry zone. Skip.
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$31.50 | Closing all 1 position
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
