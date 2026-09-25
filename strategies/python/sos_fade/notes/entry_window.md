# The no-entry window — measured 2026-09-23, ships OFF

**Read before touching:** `entry_window.py`, the "No new entries from / ...until (New York,
HH:MM)" settings in `config.py`, or the places `execution.py` and `dual_clock.py` ask it.

## What it is

Two times of day in New York. While the window is open, no new trade may start: first entries
and re-entries alike, and the level memory cannot arm either. An open trade is left alone.
Both empty = off (the shipped default). The window may run past midnight.

- **It tests the time the order would be LIVE, not the bar that decided it.** A decision made
  on the 11:15 bar rests an order from 11:30, so an 11:30 window refuses it. Testing the
  deciding bar lets an order placed one bar early fill inside the window.
- **The clock is New York, DST-aware** (`zoneinfo`), half-open: 11:30 is inside, 15:30 is not.
- A refused setup is logged with block code 11, "No-entry window", like every other refusal.
- No Pine side. The parity gate cannot see it; it is inert while both times are empty, and the
  gate was green with it in the tree.

## Why it was built

Aaron (2026-09-23) wanted to test refusing entries in the New York midday hours. Measured
BEFORE building it, off the shipped book: 11:30–15:30 held **45 trades for +6.8R** (first
entries 24 for +10.9R, re-entries 21 for −4.1R). So this was never a losing block — the
question was whether removing it buys drawdown, and whether that holds up.

## The measurement

Replay basis: run `ea46142df097`'s params, XAUUSD.p M15, 2020-01-01 → 2026-09-20, `puprime_ecn`,
spread + commission + swap charged, consistent sizing, 100-lot ceiling. Every row pins the
scale gate "Stop improved", the give-back guard and the reversal exit off, and level memory off.

| window | trades | total R | worst DD (R) | R / DD | 2020–22 R | DD | 2023–26 R | DD |
|---|---|---|---|---|---|---|---|---|
| off (`e805a5d503a8`) | 244 | 234.5 | 7.39 | 31.7 | 68.3 | 7.39 | 166.2 | 5.32 |
| 11:30–15:30 (`24fa78af53a3`) | 221 | 230.6 | 5.29 | 43.5 | 58.5 | 4.88 | 172.1 | 5.29 |
| 11:00–16:00 (`10a952eaab5a`) | 217 | 213.4 | 6.47 | 33.0 | 51.4 | 5.05 | 162.0 | 6.47 |
| 12:00–15:00 (`4b1c330e5705`) | 232 | 223.9 | 5.36 | 41.8 | 53.9 | 4.90 | 170.0 | 5.36 |

✅ The gate works: zero first entries and zero re-entries filled inside the window in all three.
✅ Off reproduces the earlier pinned baseline exactly, so the setting is inert when empty.

## Verdict — not adopted

- **Every window LOSES total R** (−3.9, −21.1, −10.6), and every one loses in 2020–22.
- **The drawdown cut is one stretch.** The 7.39R worst drawdown (2022-01-24 → 2022-07-14) is
  shortened by five −1R stop-outs that happened to open midday; the new worst is a 2024 stretch.
  One stretch is not a property of the hours.
- **The removed trades are mixed by year**: 2020 +12.9R, 2021 +2.0, 2022 −5.0, 2023 −5.5,
  2024 −2.5, 2025 +2.2, 2026 −0.3. No year-on-year pattern to lean on.
- **The central window's net removal is one trade.** The 49 removed trades were +3.8R, of which
  one was +16.86R; the other 48 were −13R. The 26 trades that took their place were −0.1R.
- The wider window (11:00–16:00) is the worst of the three on every column, which is the
  opposite of what a real bad-hours effect does.

Kept in the tree because it is cheap, off by default and generic (every fork inherits it); a
future session question ("are the Asia hours worse?") is one setting away, not a new build.
