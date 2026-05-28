# Bot 1 — SMC Trend Following (Multi-Instrument)
**File:** `bots/bot_smc_trend.py` | **Account:** Main (shared with Bot 2) | **MT5:** `C:\Program Files\PU Prime MT5 Terminal`

---

## What This Bot Is Built To Do

Bot 1 identifies institutional manipulation — moments when large players fake a move to sweep retail stop-losses before reversing in the real direction. It waits for these "Judas Swings" at specific high-probability session windows, then enters with the trend. It is a patient, selective bot that only takes trades when multiple conditions align. Quality over quantity.

---

## Strategy

**Smart Money Concepts (SMC) — Judas Swing + Fair Value Gap**

1. During the Asian session (20:00–00:00 UTC), a price range forms as institutions accumulate quietly
2. At the London or NY open, institutions sweep above or below that range to trigger retail stops (the Judas Swing)
3. Price immediately reverses — the bot enters on the Fair Value Gap left by the displacement candle
4. The H4 EMA 200 acts as a hard trend filter — only sweeps in the direction of the H4 trend are taken

**When it trades:**

| Session | UTC | Texas (CDT) |
|---|---|---|
| London kill zone | 07:00–10:00 | 2:00–5:00am |
| NY kill zone | 12:00–15:00 | 7:00–10:00am |
| Dead zone | — | 4:00–5:00pm |
| Market close | 19:45 UTC | 2:45pm |

**Entry checklist — all must be true:**
- Asian session range detected
- Judas Swing sweeps the range then reverses
- Sweep direction matches H4 EMA 200 trend (hard block if not)
- Fair Value Gap confirmed on M5
- Confluence score >= 5/8
- AI approves >= 55% win probability

**Confluence scoring:**

| Signal | Points |
|---|---|
| Judas Sweep confirmed | +2 |
| FVG fully aligned | +2 |
| FVG partially present | +1 |
| London kill zone | +1 |
| NY kill zone | +1 |
| At FVG midpoint | +1 |

---

## Profitability Goal

- **Target per trade:** 3R minimum (1:3 risk/reward)
- **Runner system:** Best trade at 2R becomes a runner with trailing stop — can capture 5R, 8R, or more on strong trending days
- **Re-entry:** If stopped at breakeven and bias unchanged, re-enters once — maximises capture on strong moves
- **Regime boost:** Full size in TRENDING, 50% in TRANSITIONING

---

## Risk Goal

| Control | Value |
|---|---|
| Risk per trade | 1% of balance |
| Breakeven | +1R — trade becomes free |
| Daily loss cap | 5% — no new entries |
| Weekly loss cap | 10% — 6hr cooldown |
| Consecutive losses | 3 max — then cooldown |
| No overnight holds | Force-close 19:45 UTC |
| No counter-trend | H4 filter is a hard block |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Trail starts | Entry | SL ratchets up with peak, clamped to original SL floor |
| Velocity tighten | Fast favourable move | Trail distance shrinks (min 0.6× base) |
| Velocity loosen | Slow / adverse move | Trail distance widens (max 1.4× base) |
| Breakeven | Trail crosses entry | be_done set — enables new entries (no hard snap) |
| Trail wide | 0–5R | 2× ATR from peak (before velocity adj) |
| Trail mid | 5–8R | 1.5× ATR from peak |
| Trail tight | 8R+ | 1× ATR from peak |
| Bank profit | +2R (non-runner) | Full close |
| Runner armed | Best trade at +2R | Runner active — trail already running |
| Key level hit | Weekly H/L | Runner closes |
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
Learns from: confluence score, ATR, session, FVG, daily P&L %, simultaneous positions, re-entry flag.

**Pass-through when untrained:** The AI always allows trades (rules-based pass-through) when either no
model has been trained yet OR the current trades file has fewer than 15 closed trades. This prevents a stale
`.pkl` from a previous run blocking new entries on a fresh instance with no data.

Trade close logging is fully implemented — every exit (SL/TP hit, 2R bank, runner key-level exit, dead zone,
market close) calls `log_close(ticket, close_price, pnl_usd)` which writes `outcome`, `pnl_usd`, and
`close_price` to `smc_trend_trades.json` and triggers AI retraining. `risk_usd` is correctly recorded at entry.

---

## Regime Behaviour

| Regime | Response |
|---|---|
| TRENDING | Full size |
| TRANSITIONING | 50% size |
| RANGING | No new entries |

---

## Multi-Instrument Scanner

Every cycle the bot scans all symbols in `bot_smc_trend.watchlist` (config.json).
The symbol with the highest confluence score wins and gets the trade entry.

**Watchlist (gold_main instance):** `["XAUUSD.s", "GBPJPY.s", "EURUSD.s", "XAGUSD.s", "USDJPY.s"]`
*(verify exact broker symbol strings on VPS before going live — brokers add suffixes like `.s`)*

**Volatility filter (Phase 2):** Before evaluating a setup, the scanner checks whether the instrument is actually moving. It computes `atr_ratio = ATR(5) / ATR(20)` on H1 candles. If the ratio is below `min_atr_ratio` (default 0.8 — current volatility less than 80% of recent baseline), that symbol is skipped for the cycle. If the entire watchlist is below the floor, the bot sits out rather than forcing a trade in dead conditions.

**Dynamic risk engine (Phase 3):** Before scanning, the bot checks `available_risk = daily_budget − used_risk − realized_daily_loss`. `used_risk` is the sum of current SL-to-price risk across all open trades fetched live from MT5 each cycle. A trade moved to breakeven contributes ~0; a trailing winner with SL in profit contributes negative (frees extra capacity). If `available_risk < proposed_risk_pct`, the scan is skipped. Sizing caps at `available_risk` so the bot never over-allocates when multiple positions are open. The daily hard cap still exists — when `realized_daily_loss >= daily_budget`, new entries stop.

**Correlation control (Phase 4):** After scanning, the bot iterates candidates in rank order and runs each through `CorrelationGuard` before entering. The guard reads `correlation_map` from config (a list of `{"symbols": [...], "tier": "high"|"medium"|"low"}` entries). Only `"high"`-tier pairs trigger action:
- `"block"` (default): the candidate is skipped if any open position is high-correlated with it.
- `"shared_budget"`: the candidate is allowed but its risk is capped to the minimum live SL risk of any high-correlated open trade — if the correlated trade is at breakeven, the new entry sizes to near-zero.

The bot tries the next-ranked candidate before sitting out — a valid non-correlated setup on another instrument is still taken. All candidates exhausted → waits 60s.

**Breakeven gate (Phase 5):** Before scanning for a new entry, the bot checks all open trades. If any open trade has not yet reached breakeven (risk > 0), the scan is skipped. Once all open trades are at breakeven or better, the bot scans the full watchlist and enters the highest-scoring setup.

Config keys (in `bot_smc_trend` section):
- `"min_atr_ratio": 0.8` — lower = more permissive, higher = stricter
- `"force_trade": false` — set to `true` to bypass the volatility filter entirely
- `"daily_budget_pct": 5` — total risk budget per day; defaults to the existing daily loss cap
- `"min_sweep_atr_factor": 0.15` — Judas Swing minimum distance as a fraction of M15 ATR. Normalises across instruments. Raise to 0.20–0.25 for stricter sweeps; lower to 0.10 if setups are being missed.
- `"velocity_trail_sensitivity": 1.5` — how much momentum tightens/widens the trail. At 1.5, gaining 0.2R/cycle tightens trail by 30%; losing 0.2R/cycle widens it by 30%. Range 0.6–1.4× base.

**Unresolved symbol handling:**
- Any symbol not found on the broker is logged to `symbol_errors.log` in the instance dir
- bot_state flag is set → monitor.py sends one Telegram alert per bad symbol per day
- Alert: `⚠️ Bot SMC Trend: Symbol 'XYZ' not found on broker — skipped. Fix config.json.`

**Per-trade ATR:** Each trade stores its ATR at entry time. Trailing stops use the stored ATR so position management is correct even when the runner is on a different instrument than the current scan.

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Too many trades | `min_confluence_score` | Raise to 6 |
| Missing setups | `min_confluence_score` | Lower to 4 |
| Stops hit early | `atr_sl_multiplier` | Raise 1.5 -> 1.8 |
| Profit not banking | `partial_close_r` | Lower 2.0 -> 1.5 |
| No sweeps detected | `min_sweep_atr_factor` | Lower to 0.10 |
| Too many false sweeps | `min_sweep_atr_factor` | Raise to 0.20–0.25 |

---

## Key Log Messages

```
H4 FILTER: sweep=bearish but H4=bullish. Counter-trend blocked.
Confluence score 6/8 | sweep(+2) | FVG-aligned(+2) | ny(+1)
AI approved 68% >= 55%
ORDER FILLED | bullish 0.01L @ 4688.63
ORDER FILLED | bullish 0.01L @ 4680.00 [RE-ENTRY]
T12345 -> BREAKEVEN @ 4688.63
T12345 RUNNER active @ 2.0R
DEAD ZONE PORTFOLIO CLOSE | Net P&L=+$45.20 | Closing all 2 positions
New day 2026-05-16 | $2,759.28 | AI: Trained | AUC=0.61 | WR(10)=67%
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
4. Heartbeat is written every 60s during the cooldown — monitor.py will not fire a "Loop Stalled" alert while the bot is in this state.
