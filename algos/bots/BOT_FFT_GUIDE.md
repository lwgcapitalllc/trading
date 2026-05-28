# Bot 5 — FFT (Fibonacci Fractal Trading) — Scanner-Ready
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

**When it trades:** M15 entries. H1 + H4 EMA 200 trend filter. Dead zone 4–5pm CT (gold market close window).

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
| Weekly loss cap | 10% — cooldown |
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

## Dead Zone (4:00–5:00pm CT — gold market close window)

No new entries. Portfolio-level management every minute:
- Net profitable across all trades → close all immediately
- Individual trade profitable, portfolio negative → move to breakeven
- Losing trade getting worse → close immediately at best price
- Losing trade improving → hold and monitor until the hour closes

---

## AI Brain

Trains at 15 closed trades. Retrains every 5. AUC gate 0.55.
Learns from: confluence score, ATR, session, H4 alignment, FVG, overlap tightness, daily P&L %.

Trade close logging is fully implemented — every exit (SL/TP hit, dead zone, market close) calls
`log_close(ticket, close_price, pnl_usd)` which writes `outcome`, `pnl_usd`, and `close_price` to
`fft_trades.json` and triggers AI retraining. `risk_usd` is correctly recorded at entry (accounts for
the `risk_mult` regime multiplier).

**Structure engine:** BOS/SOS/RETRACEMENT events are detected by `shared/structure_engine.py` — event-driven, no fixed candle lookback. Body closes confirm all breaks; wicks anchor fib levels only.

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

## Watchlist and Scanner

The FFT bot uses `InstrumentScanner` for all symbol evaluation — the architecture supports multiple instruments.

**Phase 1 watchlist:** `["XAUUSD"]` — gold only.
Expansion gate: 30+ closed trades with solid Calmar ratio (tracked in `fft_equity.json`). Do not expand early.

**config.json note:** `_watchlist_note` field documents the gate. Do not remove it — it's a reminder to future maintainers.

**Volatility filter (Phase 2):** Before evaluating a setup, the scanner checks `atr_ratio = ATR(5) / ATR(20)` on H1 candles. Symbols below `min_atr_ratio` (default 0.8) are skipped. Since FFT is gold-only, if XAUUSD is compressed the bot simply sits out the cycle.

**Dynamic risk engine (Phase 3):** Before scanning, the bot checks `available_risk = daily_budget − used_risk − realized_daily_loss`. `used_risk` is computed from live MT5 SL distances each cycle. Trades at breakeven contribute ~0; trailing winners with SL in profit free up extra capacity. If `available_risk < proposed_risk_pct`, the scan is skipped. The daily hard cap still enforces the ceiling.

**Correlation control (Phase 4):** FFT is gold-only, so the correlation guard will only fire if the watchlist is ever expanded. The `correlation_map` (`{"symbols": ["XAUUSD.s", "XAGUSD.s"], "tier": "high"}`) is in place for when that happens. `correlation_action = "block"` is set in the bot_fft config section.

**Breakeven gate (Phase 5):** Before scanning for a new entry, the bot checks all open trades. If any open trade has not yet reached breakeven (risk > 0), the scan is skipped. Once all open trades are at breakeven or better, the bot scans the full watchlist and enters the highest-scoring setup.

Config keys (in `bot_fft` section):
- `"min_atr_ratio": 0.8`
- `"force_trade": false`
- `"daily_budget_pct": 5` — total risk budget per day; defaults to `max_daily_loss_pct`

**Unresolved symbol handling:**
- Any symbol not found on the broker is logged to `symbol_errors.log` in the instance dir
- bot_state flag is set → monitor.py sends one Telegram alert per bad symbol per day

---

## Structure Engine

`shared/structure_engine.py` tracks BOS/SOS/RETRACEMENT events candle-by-candle.

**Key rules:**
- Body close above current HH → **BOS** (bullish). New HH = that close. Old HH becomes new HL.
- Body close below current HL → **SOS** (bullish structure broken). Bias flips to bearish.
- First bearish body-close back under the new HH close → **RETRACEMENT_BEGAN**. Fires once per leg.
- Wick-only breaks never register.
- SOS is tested only after `leg_established = True` (first confirmed BOS). Bootstrap phase never triggers SOS.
- SOS takes priority over RETRACEMENT on the same candle.

**Bootstrap:** seeds HH/HL from first 20 candles. Treat pre-first-BOS signals with lower confidence.

**Outputs per candle:** `bias`, `swing_high`, `swing_low`, `fib_anchor_high/low`, `bos`, `sos`, `retracement_began`, `leg_established`.

## Tuning

| Problem | Config key | Fix |
|---|---|---|
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
