# Notes — Setup messages (the signals room) for the extreme-leg bot

Added 2026-09-16. The live `extreme_leg_demo` logged "Setup alerts: OFF" because this package never
implemented `backtest/setups.py`. Code: `setups.py`, fed by `strategy.py` step 7, read through
`ExtremeLegExecution.live_setups()` / `drain_setups()`.

## What one setup is

One ARMED EPISODE per side: a liquidity sweep arms the side for `swept_minutes`, and the trade fires
at market on the first 5m shift of structure in that window that the refusal ladder accepts.

- Key: `ExtremeLegStrategy:<L|S>:t<sweep time ms>` — time, never a bar number (a re-warm
  renumbers bars). Key scheme `xleg-time-v1`.
- An episode opens ONLY on a sweep bar. A later sweep while still armed keeps the same thread.
- Taken → ENTERED. Refused on the shift → BLOCKED with the ladder's own sentence (or "a trade is
  already open" / "the account's risk budget had no room"). Window closes → NO TRADE, naming the
  last refusal.
- Confluences: the sweep (which level families), the 15m trend against the trade (only when that
  rule is on), and the 5m shift.

## Why the root is sent on the SHIFT, not on the sweep — MEASURED

`python3 backtest/tools/alert_rate.py --strategy extreme_leg --symbol XAUUSD.p --tf 5 --server
PUPrime-Demo`, shipped defaults, 189,331 M5 bars 2024-01-01 → 2026-09-01:

| announce when | roots / month | became trades |
|---|---|---|
| every armed sweep | 90.9 | 2% |
| armed and the ladder would already pass | 45.7 | 3% |
| **the shift prints (shipped)** | **7.1** | **23%** |

Over 2019-01-01 → 2026-09-01 (543,770 bars): 6.8 roots/month, 18.8 messages/month, 140 of 622
announced setups traded, and **all 140 trades were announced first**. For comparison the SOS Fade
channel is ~11 roots/month at 26%. ⚠ A market-entry bot gives no lead time once the shift prints:
the root, the ENTERED reply and the trade alert arrive together. The value is in the refusals.

## Proven reporting-only

Trades, refusals and every per-bar state, digested with sha256, over PU Prime `XAUUSD.p` M5 with
`extreme_leg_demo`'s own settings (market cut ON):

- 2024-01-01 → 2026-09-01: 51 trades, 174 refusals — same as the 2026-09-02 record.
- 2019-01-01 → 2026-09-01: 140 trades, 472 refusals, sha `a3e9b940…` before, after, and after with
  the setup watch drained every bar.

The Pine gate (`compare_extreme_leg.py`) was not re-run: no export is on this machine, and nothing
here touches a value the gate compares.

Tests: `tests/test_setup_watch.py` (8; red before `setups.py` existed; three mutations run, each red).
