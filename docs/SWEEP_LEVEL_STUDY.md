# Sweep-level study — structure, session, or both?

**Tool:** `backtest/tools/sweep_edge.py`
**Run:** 2026-08-14, 186,650 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-11 (Vantage cache)
**Question:** the sweep-and-reclaim is one trigger. Which LEVEL is worth pointing it at?

```
python3 backtest/tools/sweep_edge.py --out backtest/reports/sweep_edge
python3 backtest/tools/sweep_edge.py --min-risk-atr 0.5
python3 backtest/tools/sweep_edge.py --trigger wick
```

---

## Why it was asked

Two claims were on the table and neither had a number under it.

`indicators/engines/mss_sweeps_mpc.pine` arms the protected internal swing — the iHL a bull iBOS
leaves behind, the iLH a bear iBOS leaves — and signals when price wicks through it and closes
back. That is a STRUCTURE level.

`education/learned/2026-08-11-smc-strategy-too-simple-to-ignore-1150-trades.md` argues for the
same trigger on a completely different level: the previous SESSION's high or low. *"In London,
wait for the Asian session high to be taken, then look for shorts."* He says explicitly that he
tested a fib/premium-discount location filter and threw it out in favour of this.

Aaron's own observation was the third version: price sweeps a previous session's extreme and
then rotates to the other end of that range, or on to the previous day's or week's level.

All three are the same trigger on different levels. So hold the trigger fixed and vary only the
level.

---

## Method

Five level families, one identical trigger, one identical scoring rule.

| family | the level |
|---|---|
| `structure` | the protected iHL / iLH a continuation break left behind |
| `session` | a finished session's high/low — Asia, London, NY |
| `day` | the previous day's high/low — PDH / PDL |
| `week` | the previous week's high/low — PWH / PWL |
| `h4` | the previous H4 candle's high/low — **the baseline, not a candidate** |

**The trigger.** The level is live and nothing has closed through it; this bar's wick trades
through it; this bar closes back on the origin side. A bar that closes through has BROKEN the
level and the level is dead. Given that kill rule the pattern is strictly single-bar.

**The trade.** Entry at the reclaim bar's close, stop beyond the sweep wick, scored +2R before
−1R inside 400 bars. No costs, no ladder, no confirmation step, no zone.

**The control.** Matched on three axes — direction, stop distance, and hour of day. The third
one is not optional for a session study: session sweeps land at specific hours, gold does not
drift uniformly around the clock, and a control drawn from all hours would hand the session rows
an edge made entirely of what time it is.

**h4 is the internal baseline.** It is the cheapest, most frequently taken level on the chart, so
it is what "any old level" scores. A family that does not beat h4 has no level edge whatever it
scores against the random control.

---

## 1. The headline table

```
                    n     WR      expR    risk    ctrl    edge
structure          371   36.9%   +0.105  0.75A   31.5%   +5.3%  (+2.1s)
session           3690   33.5%   +0.004  0.72A   31.9%   +1.6%  (+2.0s)
day                946   34.1%   +0.022  0.83A   32.2%   +1.9%  (+1.2s)
week               174   31.0%   -0.069  0.96A   31.6%   -0.6%  (-0.2s)
h4                6018   31.9%   -0.044  0.64A   31.6%   +0.3%  (+0.5s)
```

Structure ranks first, session and day are barely off the baseline, week is nothing.

**And the whole table shrinks once a minimum stop is imposed.** The median stop is 0.69 ATR —
the sweep wick on gold is often only a few dollars wide, so R is measured against something a
spread would eat a large share of. Re-run at `--min-risk-atr 0.5` (7,463 of 11,199 signals kept):

```
structure          260   37.2%   +0.115  0.95A   32.8%   +4.4%  (+1.5s)
session           2554   35.3%   +0.058  0.95A   33.3%   +2.0%  (+2.1s)
day                724   35.4%   +0.062  1.03A   33.1%   +2.3%  (+1.3s)
week               139   32.4%   -0.029  1.18A   32.2%   +0.2%  (+0.0s)
h4                3786   34.1%   +0.023  0.88A   33.2%   +0.9%  (+1.2s)
```

Structure falls under 2σ. The gap between structure and h4 narrows from 5.0 points to 3.5.

---

## 2. 🔴 The finding: the edge is in the RECLAIM, not in the level

`--trigger wick` keeps everything else and drops only the close-back requirement — the bare touch
fires and the close is ignored.

```
structure          694   29.6%   -0.111  0.48A   29.8%   -0.2%  (-0.1s)
session           7262   29.4%   -0.117  0.49A   30.5%   -1.0%  (-1.9s)
day               1931   30.3%   -0.092  0.57A   30.7%   -0.4%  (-0.4s)
week               395   29.9%   -0.104  0.58A   29.9%   -0.1%  (-0.0s)
h4               11541   28.0%   -0.161  0.42A   30.2%   -2.2%  (-5.3s)
```

**Every family goes negative, and h4 goes significantly negative at −5.3σ.** Taking a level
being touched, without waiting for the close to come back, is a losing trade on this instrument
across eight years.

That is the largest, most stable effect in the whole study, and it is a statement about the
TRIGGER. Every level family gains roughly the same amount from adding the reclaim. The ordering
between families survives — structure is still 2.0 points above h4 — but the ordering is worth a
fraction of what the reclaim itself is worth.

---

## 3. The trend filter does not earn its place

`with-trend` = the sweep points the same way as the last EXTERNAL structure break.

```
structure  with-trend        81   +5.0% (+0.9s)      against-trend   290   +5.4% (+1.9s)
session    with-trend      1658   +1.6% (+1.4s)      against-trend  2032   +1.6% (+1.5s)
day        with-trend       366   +3.6% (+1.4s)      against-trend   580   +0.9% (+0.4s)
h4         with-trend      2935   -0.3% (-0.4s)      against-trend  3083   +0.9% (+1.1s)
```

Session is identical to a tenth of a point on both sides. Structure is marginally BETTER against
the trend. Only `day` shows a spread, and it does not survive the min-stop guard cleanly.

⚠ Read the structure row with the caveat the Pine already carries: our internal structure is
rebuilt inside the PULLBACK of each external leg, so its first protected level points against the
external break by construction. `with-trend` is an awkward question there. It is a clean question
for `session`, and the answer there is nothing.

The "trending market" variant — external structure has continued at least once since its last
change of character, which is what `mss_sweeps_mpc.pine` actually ships as its default filter —
is no better: structure +0.3% (n=159), session +0.5% (n=1792).

---

## 4. Confluence makes it worse, not better

Levels from two families sitting within 0.5 ATR of each other, same side:

```
structure only                      213   +7.2%  (+2.2s)
session only                       3478   +1.3%  (+1.7s)
structure + session                 188   +4.3%  (+1.2s)
union: take either kind            3326   +1.3%  (+1.6s)
```

A structure level that a session level agrees with scores WORSE than one that stands alone. Same
result with the min-stop guard on (+6.7% alone vs +3.3% confluent).

**So "both" is not the answer to the question that was asked.** Requiring the two to line up
cuts the sample by 12% and does not improve what is left.

---

## 5. The video's specific claim is the worst row in its own table

```
                                     n      edge
Asia H/L taken in London           704     -0.8%  (-0.5s)     <- his headline rule
Asia H/L taken in NY               586     +3.1%  (+1.5s)
London H/L taken in Asia           239     -3.0%  (-1.0s)
London H/L taken in NY             700     +0.5%  (+0.3s)
NY H/L taken in Asia               474     +2.1%  (+1.0s)
NY H/L taken in London             177     +2.5%  (+0.7s)
```

With the min-stop guard the split gets sharper, not softer: Asia-in-London **−3.9% (−1.8σ)**,
Asia-in-NY **+3.8% (+1.7σ)**, NY-in-Asia **+4.7% (+1.7σ)**.

Adding his step-1 trend filter does not rescue it (Asia-in-London with-trend: +2.2% unguarded,
−1.4% guarded — it changes sign under a stop guard, which is what noise does).

⚠ **This is not a refutation of his strategy, and the difference matters.** His step 3 (drop to
M1 and wait for a change of character) and step 4 (enter from an M5 order block, not at the close)
are both absent here, and he claims step 4 is what turns a 1:2 trade into a 6R one. What is
measured is the LOCATION rule on its own. The honest statement is: *the location rule carries no
information by itself, so whatever his edge is, it is not living there.*

---

## 6. The rotation Aaron described happens — about one time in seven

Measured before the stop, over the same 400-bar horizon.

```
                  medMFE   >=1R    >=3R    other end   prev day   prev week
structure          0.85R   48.2%   25.1%     28.3%       9.9%       4.2%
session            0.76R   45.5%   25.0%     14.4%       9.6%       4.9%
day                0.77R   46.0%   25.4%     10.0%       9.1%       4.5%
week               0.82R   46.0%   25.9%      6.9%       9.8%       7.2%
h4                 0.64R   43.8%   24.6%     21.2%       9.8%       5.1%
```

"Other end" = the opposite extreme of the same period the level came from — for a swept Asia
high, the Asia low.

**After a session level is swept and reclaimed, price reaches the other end of that session's
range 14.4% of the time.** It reaches the previous day's opposite level 9.6% of the time and the
previous week's 4.9%.

🔴 **And a swept H4 level rotates to its other end MORE often (21.2%) than a session level does.**
The rotation is real — it is just not a property of session levels specifically. A tighter range
is easier to cross, which is most of what that column is measuring.

The with-trend cut does not move it (session 15.1%).

---

## 7. Nothing here is stable year to year

```
structure   2018 +13.8   2019 +11.3   2020  +0.9   2021 +11.6   2022  +4.8
            2023  -7.0   2024  +2.1   2025 +13.9   2026  +2.0
session     2018  +4.6   2019  +5.5   2020  -0.9   2021  +1.6   2022  +1.1
            2023  -0.3   2024  +2.2   2025  -2.5   2026  +7.2
week        2021 +14.0   2022 -15.5   2023 +12.6   2024 -12.0   2025 -14.6
```

Structure is negative in 2023 and its best years are the two thinnest. Session flips sign five
times. Week is pure noise at n≈22/year.

And against the R target, structure's edge peaks exactly at the 2R the table was built on
(+3.1% at 1R, +5.0% at 1.5R, **+5.3% at 2R**, +1.2% at 3R, +1.2% at 5R) — the shape of an
artefact of the target, not of an edge that exists at every horizon.

---

## Verdict

**Structure levels rank above session levels, but not by enough to build on.** The gap is 3.4
points of win rate at +2.1σ, it falls to 1.5σ under a minimum-stop guard, it does not hold up
year to year, and it peaks at the one R target the table was scored at. About ninety rows were
printed in this study; four or five above 2σ is what chance produces at that count.

**The reclaim is the part that works.** It is worth ~2 points of win rate on every family and it
is the difference between a losing trigger and a flat one. `mss_sweeps_mpc.pine` already requires
it. Keep it; do not loosen it.

**Do not add session levels to the MSS sweeps trigger** on the strength of this. Session levels
score below structure levels on the same trigger, confluence between them is worse than structure
alone, and the specific session pairing the video recommends is the weakest of the six.

**Do not read this as "the video is wrong."** It measures his LOCATION rule stripped of his
confirmation and his entry. It says the location rule carries no information on its own — which
means, if his 6R book is real, the work is being done by the M1 change-of-character and the M5
order-block entry, both unmeasured here.

**Nothing in this study is a strategy result.** No costs, no ladder, no position slot, no minimum
stop by default. The median stop is 0.69 ATR — a few dollars on gold, against a ~$0.12–0.33 round
trip depending on tier. Cost alone would be 5–15% of every R.

### What would actually move this forward

1. **Model the confirmation step.** The M1 stream is cached (`XAUUSD__M1.csv`). Requiring an M1
   structure flip after the sweep, before entry, is the one part of the video's model that is both
   unmeasured and cheap to add. It is also the piece he names as the edge.
2. **Model the entry.** `engines/order_blocks/` and `engines/fair_value_gaps/` are both canonical
   and both wired into `backtest/replay`. Entering from the zone rather than at the close changes
   the stop distance, which is the denominator of every number above.
3. **Do neither until one of them is specified.** Adding both at once means the next table cannot
   say which one moved it.
