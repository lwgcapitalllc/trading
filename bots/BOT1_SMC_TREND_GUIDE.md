# BOT1_SMC_TREND_GUIDE.md
# Bot 1 — SMC Trend Following

**File:** `bots/bot1_smc_trend.py`
**Strategy:** Smart Money Concepts — Judas Swing + Fair Value Gap
**Direction:** WITH H4 trend only — counter-trend entries permanently blocked
**Trades per day:** 0–3 quality setups per session (market-limited, no artificial cap)
**Account:** Main account — runs alongside Bot 2

---

## What It Does

Identifies when institutions fake a directional move to sweep retail stop-losses, then trades the reversal. The key filter: the sweep direction must align with the H4 EMA 200 trend. If H4 is bullish, only bullish Judas Swings qualify. This single rule eliminated 90%+ of bad trades.

---

## When It Trades

| Session | UTC | Fort Worth (CDT) |
|---|---|---|
| London kill zone | 07:00–10:00 | 2:00–5:00am |
| NY kill zone | 12:00–15:00 | 7:00–10:00am |
| Outside kill zones | — | Manages open positions only |
| Market close window | 19:45–21:00 | 2:45–4:00pm |

---

## Entry Logic — All Must Be True

1. **Asian session range** marked (20:00–00:00 UTC)
2. **Judas Swing detected** — price sweeps Asian high/low then reverses
3. **Hard H4 filter** — sweep direction matches H4 EMA 200 trend
4. **Fair Value Gap** on M5 confirms displacement
5. **Confluence score ≥ 5/8** (raised from 4)
6. **AI approves** ≥ 55% win probability

---

## Confluence Scoring (0–8)

| Signal | Points |
|---|---|
| Judas Sweep confirmed | +2 |
| FVG fully aligned | +2 |
| FVG partially present | +1 |
| London kill zone | +1 |
| NY kill zone | +1 |
| At FVG midpoint | +1 |
| H4 counter-trend | −1 (now impossible — blocked before scoring) |

---

## Trade Management — 0.01 Lot Safe

At minimum lot size (0.01) partial closes don't work. The bot uses a runner system instead:

| Stage | Trigger | Action |
|---|---|---|
| Breakeven | +1R profit | Stop moves to entry — trade is free |
| Bank profit | +2R profit (non-runner) | Full close — profit secured |
| Runner | Best performing trade at +2R | Trailing stop activates |
| Trail wide | Runner at 0–5R | 2× ATR trail |
| Trail mid | Runner at 5–8R | 1.5× ATR trail |
| Trail tight | Runner at 8R+ | 1× ATR trail |
| Key level | Weekly H/L hit | Runner closes immediately |
| Market close | 19:45 UTC daily | All positions force-closed |
| Weekend | Friday 19:45 UTC | All positions force-closed |

**Runner logic:** When multiple trades are open and any hit 2R, the best performing trade becomes the runner. All others at 2R close and bank profit. One runner per session maximum.

---

## Re-Entry After Breakeven Stop

If a trade stops at breakeven and the H4 trend is unchanged, the bot re-enters once:

1. Trade stops at BE → bot logs the direction as a re-entry opportunity
2. Next time a Judas Swing appears in the same direction → re-enters automatically
3. Re-entry logged with `is_reentry=1` feature for AI training
4. Maximum one re-entry per original setup

Log shows `[RE-ENTRY]` when this fires. The AI learns whether re-entries perform better or worse than original entries over time.

---

## AI Brain (v2)

| Parameter | Value | Change from v1 |
|---|---|---|
| Minimum trades to train | 15 | Was 30 — trains twice as fast |
| AUC gate | 0.55 | Was 0.52 — stricter quality requirement |
| Retrains every | 5 new trades | Was 10 — adapts twice as fast |

**New features the AI now learns from:**
- `daily_trades_so_far` — how many trades already placed today
- `daily_pnl_pct` — current day P&L at time of entry
- `simultaneous_open` — how many positions open at entry
- `is_reentry` — whether this is a re-entry after a BE stop

**Daily performance logger** saves at midnight UTC: total trades, wins/losses, max simultaneous positions, max drawdown %, final P&L %, day of week. After 7+ days the AI has pattern data on which day conditions produce losses.

---

## Risk Controls

| Control | Value | Notes |
|---|---|---|
| Risk per trade | 2% | Of current balance |
| Daily loss cap | 10% | No new entries — manages open trades only |
| Weekly loss cap | 20% | 6hr cooldown then resumes |
| Consecutive losses | 3 | 30min → 1hr → 3hr cooldown |
| Market close | 19:45 UTC | Force-closes all — no overnight holds |

---

## Regime Behaviour

| Regime | Bot 1 response |
|---|---|
| TRENDING | Full size — ideal |
| TRANSITIONING | 50% size |
| RANGING | No new entries |

---

## Tuning Guide

| Problem | Parameter in config.json | Adjustment |
|---|---|---|
| Still too many trades | `min_confluence_score` | Raise to 6 |
| Missing good setups | `min_confluence_score` | Lower to 4 |
| Stops hit too early | `atr_sl_multiplier` | Raise 1.5 → 1.8 |
| Profits not banking | `partial_close_r` | Lower 2.0 → 1.5 |
| AI too slow | `min_trades_train` in shared_ai_brain.py | Lower to 10 |

---

## Log Messages to Watch

```
H4 FILTER: sweep=bearish but H4=bullish. Counter-trend blocked.      ← working correctly
Confluence score 6/8 | sweep(+2) | FVG-aligned(+2) | ny(+1)...      ← strong setup
AI approved 68% >= 55%                                                ← AI gate passed
AI not yet trained (8/15 trades). Rules-based. 7 more needed.        ← AI learning
ORDER FILLED | ticket=... | bullish 0.01L @ 4688.63                  ← trade placed
ORDER FILLED | ticket=... | bullish 0.01L @ 4680.00 [RE-ENTRY]       ← re-entry fired
T12345678 -> BREAKEVEN @ 4688.63                                      ← free trade
T12345678 stopped at BREAKEVEN. Re-entry available if bias unchanged. ← re-entry armed
T12345678 FULL CLOSE @ 2.1R -- banking profit.                        ← profit secured
T12345678 RUNNER active @ 2.0R                                        ← runner running
Market closing in 15 min [DAILY-CLOSE] -- closing all 2 positions.   ← eod protection
New day 2026-05-15 | $2,746.54 | AI: Trained | AUC=0.61 | WR(10)=67% ← morning report
```
