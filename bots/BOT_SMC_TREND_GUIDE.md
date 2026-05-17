# Bot 1 — SMC Trend Following
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
| Dead zone | — | 3:00–7:00pm |
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
| Risk per trade | 2% of balance |
| Breakeven | +1R — trade becomes free |
| Daily loss cap | 10% — no new entries |
| Weekly loss cap | 20% — 6hr cooldown |
| Consecutive losses | 3 max — then cooldown |
| No overnight holds | Force-close 19:45 UTC |
| No counter-trend | H4 filter is a hard block |

---

## Trade Management

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +1R | Stop to entry |
| Bank profit | +2R (non-runner) | Full close |
| Runner armed | Best trade at +2R | Trail activates |
| Trail wide | 0–5R | 2x ATR |
| Trail mid | 5–8R | 1.5x ATR |
| Trail tight | 8R+ | 1x ATR |
| Key level hit | Weekly H/L | Runner closes |
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
Learns from: confluence score, ATR, session, FVG, daily P&L %, simultaneous positions, re-entry flag.

---

## Regime Behaviour

| Regime | Response |
|---|---|
| TRENDING | Full size |
| TRANSITIONING | 50% size |
| RANGING | No new entries |

---

## Tuning

| Problem | Config key | Fix |
|---|---|---|
| Too many trades | `min_confluence_score` | Raise to 6 |
| Missing setups | `min_confluence_score` | Lower to 4 |
| Stops hit early | `atr_sl_multiplier` | Raise 1.5 -> 1.8 |
| Profit not banking | `partial_close_r` | Lower 2.0 -> 1.5 |

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
