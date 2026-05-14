# BOT1_SMC_TREND_GUIDE.md
# Bot 1 — SMC Trend Following

**File:** `bots/bot1_smc_trend.py`
**Style:** Trend following — rides institutional order flow with the H4 trend
**Capital allocation:** 60–80% of account (runs alongside Bot 2)
**Trades per day:** 0–3 (quality over quantity — most days 0–1)

---

## What It Does

Waits for institutions to fake a directional move to trigger retail stop-losses, then trades the reversal — but **only in the direction of the H4 trend**. This pattern (Judas Swing) repeats at London and NY session opens when institutional volume floods in.

The bot marks the Asian session range, waits for London or NY, and requires: price sweeping the Asian high/low, reversing, AND that reversal aligning with the H4 EMA 200 trend. Counter-trend setups are blocked entirely regardless of score.

---

## When It Trades

| Session | UTC | ET |
|---|---|---|
| London kill zone | 07:00–10:00 | 2:00–5:00am |
| NY kill zone | 12:00–15:00 | 7:00–10:00am |
| Asian session | 20:00–00:00 | Range building only — no entries |
| All other hours | — | Manages open positions only |

---

## How It Finds a Trade

1. Marks Asian session high and low
2. Detects Judas Swing — sweep of Asian range with reversal close
3. **Hard H4 filter** — sweep direction must match H4 EMA 200 trend or trade is blocked
4. Confirms Fair Value Gap (FVG) on M5
5. Scores setup 0–8 — minimum **5** required
6. AI model approves or blocks
7. Places order with broker-side stop loss

**Why the H4 filter:** Without it the bot was taking counter-trend trades every 5 minutes (46 trades in one session). H4 filter reduces this to 0–3 genuine with-trend setups per session.

---

## How It Manages Trades — 0.01 Lot Safe

Partial close (splitting a position) doesn't work at 0.01 lots minimum. Instead:

| Stage | Trigger | Action |
|---|---|---|
| 1 | +1R profit | Stop to breakeven — trade is free |
| 2 | +2R profit (non-runner) | Full close — profit banked |
| 3 | Best trade at +2R | Becomes the runner — trail activates |
| Runner | After 2R | Dynamic ATR trail (2× → 1.5× → 1× as profit grows) |
| Force close | 21:45 UTC daily | All positions closed before market close |
| Force close | Friday 21:45 UTC | Weekend protection |

**Runner logic:** When multiple trades reach 2R, the single best performing trade stays open as the runner with a trailing stop. All others close and bank profit. Guarantees money is secured while the strongest trade runs further.

---

## Risk Controls

| Parameter | Default | Description |
|---|---|---|
| `min_confluence_score` | **5** | Minimum to take a trade (raised from 4) |
| `atr_sl_multiplier` | 1.5 | SL = 1.5 × ATR beyond sweep wick |
| `risk_pct_bot1` | 2.0% | Per trade risk |
| `max_daily_loss_pct_bot1` | 10% | Daily loss cap |
| `max_weekly_loss_pct_bot1` | 20% | Weekly loss cap |

---

## Regime Behaviour

| Regime | Bot 1 behaviour |
|---|---|
| TRENDING | Full size — ideal |
| TRANSITIONING | 50% size |
| RANGING | No entries |

---

## Tuning Guide

| Problem | Parameter | Change |
|---|---|---|
| Still too many trades | `min_confluence_score` | Raise to 6 |
| No trades firing | `min_confluence_score` | Lower to 4 |
| Stops hit before move | `atr_sl_multiplier` | Raise 1.5 → 1.8 |
| Profits banking too slow | `partial_close_r` (bot1_trend) | Lower 2.0 → 1.5 |

---

## Log Messages to Watch

```
H4 FILTER: sweep=bearish but H4=bullish. Counter-trend blocked.     ← working correctly
In LONDON kill zone — scanning for setup...                          ← active
Score 3 < 5. Skip.                                                   ← quality filter working
Confluence score 6/8 | sweep(+2) | FVG-aligned(+2) | london(+1)... ← strong setup
AI approved 68%                                                      ← AI gate passed
ORDER FILLED | ticket=... | bullish 0.01L @ 4688.63                 ← trade placed
T12345678 → BREAKEVEN @ 4688.63                                     ← free trade
T12345678 FULL CLOSE @ 2.1R — banking profit.                       ← secured
T12345678 RUNNER active @ 2.0R                                      ← best trade running
Market closing in 15 min — closing all 3 position(s). [DAILY-CLOSE] ← eod cleanup
Market closing in 15 min — closing all 2 position(s). [WEEKEND-CLOSE] ← friday cleanup
```
