# Notes — Setup messages (the signals room) for FFT

Added 2026-09-24. `fft_1` posted "no setup messages" to the health room on every start, because
this package never implemented `backtest/setups.py`. Code: `setups.py`, fed by `strategy.py`
step 7, read through `FftExecution.live_setups()` / `drain_setups()`.

## What one setup is

One touch of one leg: the 5m fib's leg (its direction and the 5m candle its 1.0 is anchored on),
first touch or second. Its thread:

- **Root + LIMIT RESTING** the first minute every rule passes and a limit rests at the 61.8.
- **WITHDRAWN** when a rule pulls the limit, naming the rule (almost always rule 4, the 1m trend
  turning); **MOVED** when it comes back or the fib extends to a new 61.8.
- **ENTERED** when it fills. **NO TRADE** when price reaches the 61.8 while a rule refuses it, when
  TP1 prints before the broker's ask reaches a buy limit, or when the fib moves to a new leg first.
- Key: `FftStrategy:<L|S>:t<anchor candle start ms>:<first|second>` — time, never a bar number.
  Key scheme `fft-time-v1`.
- ⚠ **Nothing is announced until a limit has rested.** The study counts ~16 first touches per
  trade; a leg that never passed every rule was never going to trade.
- ⚠ **A run past TP3 is NOT a withdrawal** — it is the fib extending, and the limit is re-placed at
  the new 61.8. Reported as a pull, it posted a WITHDRAWN and a MOVED for every extension.

## MEASURED — `algos/tools/setup_alert_rate.py fft_1`, raw PU Prime M1

2020-01-01 → 2026-09-18, 2,378,595 one-minute bars, 80.5 months:

| | |
|---|---|
| roots | 538 — 6.7 a month |
| became trades | 187 — 35% |
| trades announced first | 187 / 187 |
| root to fill | median 53 minutes, 10th percentile 3 |
| all messages | 2,889 — 35.9 a month |

Most of the extra messages are the limit being pulled and replaced as the 1m trend flips (679
withdrawals, 597 moves). They are real broker cancels and re-places, so they stay. SOS Fade's
channel is ~11 roots a month at 26%; the extreme leg's 6.8 at 23%.

## Proven reporting-only

Trades and every spent leg, sha256, with the watch on and off, same bars: **187 trades, 5,118
spent legs, sha `0159f9aeedd95aab` both ways** (HEAD `b16f8945` against the working tree).
`algos/tools/setup_alert_rate.py fft_1` repeats the trade half of that check on every run and
exits 1 if the trades differ or a trade goes unannounced. (It was an FFT-only tool for a day; one
tool now serves every bot.)

Tests: `tests/test_setup_watch.py` (5, real bars, the real strategy — no stand-in). Each named
mutation was run and went red.
