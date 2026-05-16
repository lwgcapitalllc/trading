# BOT5_FFT_GUIDE.md
# Bot 5 — FFT (Fibonacci Fractal Trading) Strategy

**File:** `bots/bot5_fft.py`
**Strategy:** Fibonacci Fractal Trading — proprietary dual-fib confluence system
**Instrument:** XAUUSD (Gold Spot)
**Primary timeframe:** M15
**Trend filter:** H1 + H4 EMA 200
**Account:** Dedicated `C:\MT5_FFT\terminal64.exe` instance

---

## Strategy Logic

The FFT strategy uses two Fibonacci tools simultaneously. A trade is only
taken when both fibs agree — when the sniper green zone falls inside the
FFT entry zone. This overlap is the entire edge of the strategy.

### The Two Fibs

**FFT Fib (Standard Retracement)**

Drawn on the move that caused the Break of Structure:
- Bullish: from the Higher Low → new Higher High
- Bearish: from the Lower High → new Lower Low

Defines the entry consideration zone: 61.8% to 88.6% retracement.

This fib also defines take profits:
- TP1: 50% retracement level (80% of position)
- TP2: 38.2% retracement level (20% of position)
- Deep entry (78.6%+ entry): TP1 = 70.2%, TP2 = 61.8%

**Sniper Fib (Reverse Fibonacci — Green Zone)**

Drawn on the counter move immediately BEFORE the BOS candle:
- Bullish: from the Lower High DOWN to the Higher Low
- Bearish: from the Higher Low UP to the Lower High

The 38.2% to 50% range of this fib = the GREEN ZONE.

### The Critical Rule

Entry is ONLY valid when the sniper green zone (38.2–50%) overlaps
with the FFT entry zone (61.8–88.6%). No overlap = no trade, no exceptions.

When overlap is confirmed:
- Entry 1: at the sniper 50% level (top of green zone)
- Entry 2: at the sniper 38.2% level (bottom of green zone) — only if lots allow

---

## Bullish Setup Step by Step

```
1. Identify downtrend structure (lower highs, lower lows)
2. A counter move rallies from a lower low UP to a lower high
   → Draw Sniper Fib: from the lower low UP to this lower high
3. Price breaks ABOVE a prior swing high (BOS confirmed)
4. A new Higher High forms
   → Draw FFT Fib: from the Higher Low UP to the new Higher High
5. Price retraces DOWN from the Higher High
6. Watch for price to enter FFT 61.8–88.6% zone
7. Check if Sniper 38.2–50% overlaps with that zone → GREEN ZONE
8. Enter at sniper 50% (Entry 1) with:
   - SL: 1% below the bottom of the green zone
   - TP1: FFT 50% level (above entry — price must rise)
   - TP2: FFT 38.2% level (even higher)
9. Move to breakeven at +0.5R
```

## Bearish Setup Step by Step

```
1. Identify uptrend structure (higher highs, higher lows)
2. A counter move drops from a higher high DOWN to a higher low
   → Draw Sniper Fib: from the higher high DOWN to this higher low
3. Price breaks BELOW a prior swing low (BOS confirmed)
4. A new Lower Low forms
   → Draw FFT Fib: from the Lower High DOWN to the new Lower Low
5. Price retraces UP from the Lower Low
6. Watch for price to enter FFT 61.8–88.6% retracement zone
   (these are price levels ABOVE the lower low — price came back up)
7. Check if Sniper 38.2–50% overlaps → GREEN ZONE
8. Enter SHORT at sniper 50% (Entry 1) with:
   - SL: 1% above the top of the green zone
   - TP1: FFT 50% retracement level (BELOW entry — price must drop)
   - TP2: FFT 38.2% retracement level (even lower)
9. Move to breakeven at +0.5R
```

---

## Trade Management Rules

| Rule | Detail |
|---|---|
| Entry 1 | Sniper 50% — always taken if setup valid |
| Entry 2 | Sniper 38.2% — only if account allows 2 separate orders |
| Stop Loss | 1% behind bottom of green zone (configurable via `sl_pct_behind_zone`) |
| Breakeven | Move SL to entry when +0.5R profit |
| TP1 | FFT 50% — close 80% of position (or 100% at 0.01 lots) |
| TP2 | FFT 38.2% — close remaining 20% |
| Deep entry | If entry at 78.6% or 88.6%: TP1=70.2%, TP2=61.8% |
| Min lots | Single entry, full close at TP1 |
| Market close | Force-close all at 19:45 UTC daily |

---

## Confluence Scoring (0–10)

The bot scores each setup for quality. Minimum score of 4 required.

| Factor | Points |
|---|---|
| H1 trend aligned with BOS | +2 |
| H4 trend aligned with BOS | +2 |
| Both H1 and H4 aligned | +1 extra |
| FVG present at green zone | +2 |
| London or NY session | +1 |
| Deep entry (tighter SL) | +1 |
| Tight green zone overlap (>70%) | +1 |

---

## Configurable Parameters

All parameters live in `config.json` under `bot5_fft`. The bot auto-reads
them on startup — no code changes needed to tune.

| Parameter | Default | Description |
|---|---|---|
| `swing_lookback` | 3 | Candles each side to confirm a swing point |
| `bos_min_body_mult` | 1.5 | BOS candle must be 1.5× ATR in body size |
| `fft_entry_min` | 0.618 | Entry zone bottom (61.8%) |
| `fft_entry_max` | 0.886 | Entry zone top (88.6%) |
| `fft_deep_threshold` | 0.786 | Deep entry starts at 78.6% |
| `fft_tp1_normal` | 0.500 | TP1 for normal entries |
| `fft_tp2_normal` | 0.382 | TP2 for normal entries |
| `fft_tp1_deep` | 0.702 | TP1 for deep entries |
| `fft_tp2_deep` | 0.618 | TP2 for deep entries |
| `sl_pct_behind_zone` | 0.01 | SL distance as % of price beyond green zone |
| `breakeven_at_r` | 0.5 | Move to BE at 0.5R |
| `risk_pct` | 1.0 | Risk per trade as % of balance |
| `max_daily_loss_pct` | 5.0 | Daily loss cap |
| `max_weekly_loss_pct` | 15.0 | Weekly loss cap |
| `max_trades_per_day` | 3 | Max FFT trades per day |
| `min_ai_probability` | 0.52 | Minimum AI win probability gate |

---

## AI Brain (v2)

The FFT bot uses the shared AI brain, same as Bot 1 and Bot 2:
- Trains at 15 closed trades
- Retrains every 5 new trades
- AUC gate: 0.55
- Features include: confluence score, ATR, session, H4 alignment, FVG, spread,
  daily trades count, daily P&L %, simultaneous positions

The AI learns which confluence combinations produce the best outcomes and starts
filtering marginal setups once enough data is collected.

---

## File Structure

```
bots/
└── bot5_fft.py

markets/fx/instances/xauusd_fft/
├── config.json                ← All parameters (committed to GitHub)
├── credentials.json           ← NEVER committed — create manually on VPS
├── credentials.template.json
├── bot5.log
├── bot5_trades.json
├── bot5_daily.json
├── bot5_equity.json
├── bot5_weekly.json
└── bot5_model.pkl
```

---

## Setup — Step by Step

**1. Confirm MT5_FFT terminal is running and logged in**

RDP into VPS → open `C:\MT5_FFT\terminal64.exe` → verify logged into FFT demo account.

**2. Create credentials.json on VPS**

```json
{
    "login":    YOUR_FFT_ACCOUNT_NUMBER,
    "password": "YOUR_FFT_PASSWORD",
    "server":   "PUPrime-Demo"
}
```

File location: `C:\algos\markets\fx\instances\xauusd_fft\credentials.json`

**3. Add Task Scheduler task**

Name: `FX_XAUUSD_Bot5_FFT`

Command:
```
python C:\algos\bots\launcher.py --bot bot5 --config C:\algos\markets\fx\instances\xauusd_fft\config.json
```

**4. Add to launcher.py BOT_SCRIPTS**

```python
BOT_SCRIPTS = {
    "bot1": "bot1_smc_trend.py",
    "bot2": "bot2_mean_reversion.py",
    "bot3": "bot3_scalper.py",
    "bot4": "bot4_lucidflex.py",
    "bot5": "bot5_fft.py",         ← add this
}
```

**5. Add to algo.py LOG_MAP and TASK_BOT_MAP**

```python
LOG_MAP["FX_XAUUSD_Bot5_FFT"] = ("fx", "xauusd_fft", "bot5.log")
TASK_BOT_MAP["FX_XAUUSD_Bot5_FFT"] = "bot5"
```

**6. Start**

```bash
algo restart
```

---

## Strategy Refinement — Version History

This bot will be refined over time as more chart examples are provided.

| Version | Change |
|---|---|
| v1.0 | Initial implementation — BOS detection, dual fib, green zone overlap |
| v1.1 | TBD — after first real trade examples reviewed |

When new chart examples are provided, the following may be tuned:
- `swing_lookback` — if bot is missing obvious swing points
- `bos_min_body_mult` — if too many weak BOS signals are passing
- `fft_entry_min/max` — if the entry zone should be tighter or wider
- Confluence scoring weights — based on which factors actually correlate with wins

---

## Log Messages to Watch

```
BOS BULLISH @ 4540.00 | FFT zone: 4510.00-4495.00 | Green zone: 4518.00-4525.00
GREEN ZONE OVERLAP | retrace=72.0% | deep=NO | overlap=4518.00-4525.00
SETUP | BULLISH | score=7/10 | session=london | FVG=True | deep=False
AI: AI approved 64% >= 52%
SIGNAL | BULLISH | score=7 | AI=64% | entry=4520.00 SL=4513.00 | TP1=4548.00 TP2=4562.00 | R:R=4.0
ORDER FILLED | ticket=12345 | bullish 0.01L @ 4520.10
T12345 -> BREAKEVEN @ 4520.10 (0.52R)
No BOS detected. Waiting 60s.                         ← normal idle
Regime RANGING — FFT strategy needs trending.         ← correct filter
Price 4590 not yet in entry zone. Waiting for retrace ← waiting for setup
No green zone overlap with FFT entry zone. Skip.      ← no trade — correct
```
