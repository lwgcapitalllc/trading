# Notes — Setup messages (the signals room) for Realign

**Reporting only. After any entry change, re-run `algos/tools/setup_alert_rate.py realign_1`.**

Added 2026-09-24. `realign_1` posted "no setup messages" to the health room on every start: it
inherits SOS Fade's setup reporting switched off, because SOS Fade's three confluences describe a
setup this fork never trades. Code: `setups.py`, fed by `strategy.py::_step_core` after each bar's
decision, read through `RealignExecution.live_setups()` / `drain_setups()`.

## What one setup is

One armed false break (the tracker's `Armed` record): the 15m breaks against its own trend, the
swing it leaves standing is the target, and the setup waits up to 72 hours for the 5m to break
against it and then realign. The entry is at MARKET, so there is no resting-limit message.

- **Root** — the conditions so far: the 15m trend, the false break, the 20-day momentum, the 5m
  counter move, the 5m realignment. The projected stop once the counter move has printed; the target.
- **ENTERED** — the realignment fired and the market order went in.
- **NO TRADE** — the realignment fired and a rule refused it (the order layer names which,
  `RealignExecution.refusal`, reporting only); the 72-hour window closed; a newer false break
  replaced it; or the 15m broke on the same way and the false break became a trend.
- Key: `RealignStrategy:<L|S>:t<arm time ms>` — time, never a bar number. Key scheme
  `realign-arm-time-v1`.

## 🔴 Announced only while the momentum rule would let it trade — MEASURED

`realign_1` refuses a trade WITH the 20-day move. Announcing every armed setup told the reader about
setups the bot was going to refuse. PU Prime `XAUUSD.p` M5, 2020-01-01 → 2026-09-24, 477,478 bars:

| announce | roots a month | became trades | trades announced first |
|---|---|---|---|
| every armed false break | 9.2 | 15% | 115 / 115 |
| **only while momentum is against the trade (shipped)** | **4.6** | **31%** | **115 / 115** |
| on the 5m counter move | 7.9 | 18% | 115 / 115 |
| counter move + momentum | 4.0 | 35% | 115 / 115 |

The shipped rule keeps the earliest warning (the arm) at SOS Fade's hit rate (~26%) and extreme
leg's (23%). 740 messages over 80.7 months, 9.2 a month. The top reasons a setup ends without a
trade: the false break became a trend (185), the window closed (44), a newer false break (22).

⚠ **It uses `tradeable`, which `backtest/setups.py` describes for a decision already made.** Momentum
is re-read every bar and can turn inside the window; the alert layer checks `tradeable` before any
bookkeeping for exactly that case, so the root arrives the bar it turns. A setup once announced
stays tradeable (its outcome must close the thread), and a FILL is always tradeable (no trade is
ever unannounced). Real bars never exercised the second rule — no trade in 2020-2026 filled on a
setup not already announced — so it is pinned by a direct test.

## Proven reporting-only

Every bar's decision (stop, target, fills) and every trade, sha256, HEAD `98709da9` against the
working tree, `realign_1`'s settings, 2020-01-01 → 2026-09-24: **115 trades, sha
`bfc5c3acdadf82fd` both ways.** `algos/tools/setup_alert_rate.py realign_1` repeats the trade
check with the watch on and off, and exits 1 if they differ or a trade goes unannounced.

Tests: `tests/test_setup_watch.py` (7, real bars, the real strategy through the live contract).
Each named mutation was run and went red, except the one the docstring says real bars cannot reach.
