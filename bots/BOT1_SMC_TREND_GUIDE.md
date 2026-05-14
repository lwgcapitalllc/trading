# Bot 1 — SMC Trend Following

**File:** `bots/bot1_smc_trend.py`
**Style:** Trend following — rides institutional order flow
**Capital allocation:** 60–80% of account
**Trades per day:** 0–2 (quality over quantity)

---

## What It Does

Waits for institutions to fake a directional move to trigger retail stop-losses, then trades the reversal. This pattern — called a Judas Swing in Smart Money Concepts — repeats reliably at the London and NY session opens when institutional volume floods in.

The bot does nothing for most of the day. It marks the Asian session range, waits for London or NY to open, and looks for one specific thing: price sweeping through the Asian high or low and closing back inside. When that happens with enough confluence, it enters.

---

## When It Trades

| Session | UTC | ET |
|---|---|---|
| London kill zone | 07:00–10:00 | 2:00–5:00am |
| NY kill zone | 12:00–15:00 | 7:00–10:00am |
| Asian session | 20:00–00:00 | Range building only — no entries |
| All other hours | — | Silent |

---

## How It Finds a Trade

1. Marks the Asian session high and low (the range)
2. Detects a "Judas Swing" — price breaks the Asian low/high with a wick, then closes back inside
3. Confirms a Fair Value Gap (FVG) on M5 — a price imbalance candle left by the displacement
4. Scores the setup 0–8 using confluence signals (sweep, FVG alignment, H4 trend, session, FVG midpoint)
5. Minimum score of 4 required to proceed
6. AI model votes approve or block based on 15 historical features
7. If approved — calculates position size for exactly the configured risk % and places the order with a broker-side stop loss

---

## How It Manages Trades

| Milestone | Action |
|---|---|
| +1R profit | Stop loss moves to breakeven — trade is now free |
| +3R profit | 50% of position closes — profit banked |
| Runner (50%) | Dynamic ATR trailing stop activates |
| 0–5R on runner | Trail = 2× ATR (wide — survives pullbacks) |
| 5–8R on runner | Trail = 1.5× ATR |
| 8R+ on runner | Trail = 1× ATR (tight — protect gains) |
| Weekly key level hit | Runner closes immediately |
| NY session close (15:00 UTC) | Runner closes — no overnight exposure |

---

## Risk Controls

All configured in `config.json` → `bot1_trend` section.

| Control | Default | Notes |
|---|---|---|
| Risk per trade | 2% | Of current account balance |
| Daily loss cap | 10% | No new entries rest of day |
| Weekly loss cap | 20% | 6hr cooldown then regime check |
| Consecutive losses | 3 | 30min → 1hr → 3hr cooldown |
| News blackout | 30 min | Around configured events |

---

## Regime Behaviour

The bot reads the shared regime classifier every hour. ADX, ATR ratio, and RSI range determine whether the market is trending or ranging.

| Regime | Bot 1 behaviour |
|---|---|
| TRENDING | Full size — ideal conditions |
| TRANSITIONING | 50% size |
| RANGING | No entries — market not suitable for trend following |

---

## AI Learning

After 30 closed trades the Random Forest model trains on these features: confluence score, ATR, sweep wick size, session, H4 alignment, FVG presence, spread, day/hour, rolling win rate, and price position in daily range. Walk-forward validated — never trained on future data. Retrains every 10 new trades. If AUC falls below 0.52 (no better than random) the model is discarded and the bot runs rules-only.

---

## Log Messages to Watch

```
In NY kill zone — scanning for setup...        ← active, looking
No Judas Swing detected                         ← no setup this minute, normal
Asian range: H=2400.50 L=2385.20               ← range identified
Confluence score 7/8                            ← strong setup
AI approved 68%                                 ← AI gate passed
ORDER FILLED | bullish 0.02L @ 2387.50         ← trade placed
T12345678 → breakeven @ 2387.50                ← stop moved to BE
T12345678 PARTIAL CLOSE 50% @ 3.0R             ← profit banked
T12345678 RUNNER trail SL=2389.00              ← runner active
```

---

## Works On

Any liquid instrument with clear session structure and institutional participation. Gold (XAUUSD), major FX pairs (GBPJPY, GBPUSD, EURUSD), indices (US30, NAS100). Adjust `asian_session_start_utc` in config for non-gold pairs — for GBPJPY use 0–4 UTC (Tokyo open builds the range).
