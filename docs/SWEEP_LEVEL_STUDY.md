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

`indicators/engines/mss_sweeps.pine` arms the protected internal swing — the iHL a bull iBOS
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
change of character, which is what `mss_sweeps.pine` actually ships as its default filter —
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
is the difference between a losing trigger and a flat one. `mss_sweeps.pine` already requires
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


---

## Idea from a live trade — the setup's stop is hunted at the previous day's low (Aaron, 2026-10-02)

**Recorded at Aaron's request as a future strategy candidate. Nothing below is measured.**

**What happened** (PU Prime 1-minute bars, UTC): an SOS Fade long re-entry at 4159.79, stop
4145.40, filled at 00:47. Price fell through the stop at 01:06–01:09 and kept going to **4133.82 at
01:10 — 5.46 below the previous New York day's low of 4139.28** (set 2026-10-01 00:54). ⚠
**Corrected 2026-10-02: it did NOT close back above that low within the minute** — the 01:10
one-minute bar closed at 4136.78, still below; the first one-minute close back above was 01:13
(4140.56). On 5-minute bars the 01:05 bar swept to 4138.32 and closed back at 4140.18. It was at
4148 by 01:27, reached 4161.77 at 02:29 and 4164.54 by 02:58. ⚠ The entry price is unreconciled:
this doc says 4159.79, the research brief said 4152.53. The 00:47 fill minute traded
4158.14–4160.66, which fits 4159.79 and not 4152.53; the broker's deal record settles it. Aaron: *"it went and swept the
previous day low, classic sweep."* The stop sat 6.12 above the previous day's low, so it was in the
path of the sweep.

**Why it is not already answered by this study:** section 1 measured a sweep-and-reclaim of the
previous day's level ON ITS OWN — 724 signals, +0.062R, 1.3σ, no edge. Aaron's idea is
CONDITIONED: a live SOS Fade setup in the same direction whose stop sits just short of that level.
That conditioning is untested.

**Two ways to test it — pin which one before measuring (`Pin the Trade First`):**

1. **A stop rule.** When an SOS Fade long's stop sits within X of the previous day's low (short:
   high), put the stop beyond that level instead. Same entry; wider stop, smaller size. Question:
   do the trades it saves outweigh the larger losses?
2. **A new entry.** After an SOS Fade setup's stop is taken, wait for price to sweep the previous
   day's level and close back across it, then enter in the setup's direction, stop beyond the sweep
   wick. That is the existing RECLAIM re-entry pointed at the previous day's level instead of the
   setup's deep edge.

Discover on the first half of 2020–2026, confirm on the second; costs charged; one position slot,
so count the trades it displaces. One live example is an anecdote, not a sample.

---

## Measured — the previous-day sweep, faded on 5 minutes, by session (2026-10-02)

**Tool:** `backtest/tools/pd_sweep_fade.py` · trades: `backtest/reports/pd_sweep_fade/trades.csv`
**Data:** PU Prime `XAUUSD.p`, 2,389,738 one-minute bars, 2020-01-01 → 2026-09-30, resampled to 5m.
**Costs:** `puprime_ecn` — spread $0.12 on the ask side, $1.00/side/lot commission, swap per night.
⚠ **Not reconciled with the lab** — no lab strategy exists for this trade, and this session was
research only. Read every number below as a study figure.

```
python3 backtest/tools/pd_sweep_fade.py --csv backtest/reports/pd_sweep_fade/trades.csv
```

**The trade, pinned with Aaron before measuring.** Previous trading day's high/low, day rolling at
18:00 New York (the liquidity engine's validated boundary). A 5m bar trades through it and closes
back; first touch only, a 5m close through kills it. Stop beyond the lowest point from sweep to
entry + 0.1 ATR, never closer than 0.5 ATR. Time stop at the next 18:00 New York. Targets under 1R
skipped. Entries and exits each tested separately, never as a ladder:

| entry | rule |
|---|---|
| now | market at the sweep bar's close |
| push | Aaron's pick: the next 5m bar must push past its own open, then the first 1m close back across that open |
| flip | first 1m change of character (canonical structure engine) within 60 min |

| exit | rule |
|---|---|
| near | the last small 5m swing before the sweep (4161.77 on 2026-10-02) |
| far | the top of the whole drop — highest high of the 2 hours before (4183.76 on 2026-10-02) |

The live example reproduces: the sweep bar is 01:05 (Asia); "now" enters 4140.18 and would have
been stopped by the push to 4133.82; "push" enters 4140.56 at 01:13, never threatened, and the near
target filled at 02:29 (~+3R before costs).

775 sweep-and-reclaim signals. Net R per trade, ± one standard error:

```
                      2020-01 → 2023-04          2023-05 → 2026-09
now/near   all        -0.152 ±0.090  n=313       -0.217 ±0.088  n=324
           Asia       -0.217 ±0.164  n=109       -0.280 ±0.137  n=136
           London     -0.346 ±0.173  n=63        -0.573 ±0.224  n=39
           NY         -0.032 ±0.164  n=94        -0.163 ±0.159  n=101
           reopen     +0.021 ±0.231  n=47        +0.134 ±0.236  n=48
push/near  all        -0.177 ±0.100  n=186       -0.265 ±0.108  n=180
           Asia       -0.355 ±0.171  n=63        -0.356 ±0.165  n=77
now/far    all        -0.093 ±0.104  n=353       -0.192 ±0.102  n=377
           reopen     +0.094 ±0.264  n=56        +0.349 ±0.265  n=71
push/far   all        -0.043 ±0.107  n=243       -0.273 ±0.108  n=236
flip/far   all        -0.100 ±0.384  n=13        +0.155 ±0.265  n=24

push minus now, SAME signals:  near -0.122 ±0.040 (P push better 0%)   far -0.177 ±0.041 (0%)
```

"reopen" is the hours outside the three session windows — in practice 22:00–23:59 UTC, the first
two hours of the new trading day. Full table (every session × entry × exit, longs/shorts, and a
random control matched on hour, half, direction, stop and target distance): run the tool.

### Verdicts

- **Fade the previous-day sweep, any session — Reject — proven harmful.** −0.19R ±0.06 per trade at
  the simplest entry, negative in both halves, and below its own matched random control.
- **The session question: none.** Asia loses in both halves (push entry −0.36R ±0.17 and −0.36R
  ±0.17); London is the worst session; New York is flat-to-negative. **Asia only — Reject — proven
  harmful.**
- **Wait for the push before entering — Reject — proven harmful.** On the same signals it is
  0.12–0.18R WORSE than entering at the sweep close, ±0.04, in both halves. The live example is the
  exception: the push saved that one trade, and it does not on average.
- **The reopen window (22:00–23:59 UTC) — Reject — not proven.** +0.02 to +0.35R, positive in both
  halves at every entry, but under 1.3σ in each, about 19 trades a year, median stop $1.12, a third
  of them on the first 5m bar after the daily break, and at the reopen's p99 spread ($0.19) the
  first half falls to +0.02 ±0.27. About 24 session rows were tried; one at this strength is what
  chance produces. Worth one follow-up only if a reason for it can be named before re-measuring.
- **1m structure-flip confirmation — Reject — not proven.** 37 trades in 6.7 years: the canonical
  engine marks a 1m change of character inside an hour after only ~30% of sweeps.
- **New entry after an SOS Fade stop is taken (idea 2 above) — Reject — not proven.** It happened
  5–6 times in 6.7 years and every one lost (−1.01R). The 2026-10-02 trade is the rare case.
- **Stop rule (idea 1 above) — not run.** It changes SOS Fade's own stop, so it cannot be measured
  without a strategy change; given the sweep does not reverse on average, not recommended.

### Overlap with the live bots

Replayed at their default configs on the same window (SOS Fade 251 trades, extreme leg 117). Only
8% of sweep trades enter while SOS Fade is in the market (about 3% on the same side), and 3% while
the extreme leg is. So the trade is mostly independent of both bots — it just has no edge.
⚠ The replay ran on a working tree carrying another session's uncommitted SOS Fade edits.

---

## Follow-ups on the same day — after a failed SOS Fade trade, the Asia push, the 100 fib (2026-10-02)

Same data, costs and halves as the section above. ⚠ **None of it is reconciled with the lab**, and
the SOS Fade replays ran on the same working tree carrying another session's uncommitted edits.
⚠ The scripts were scratch work outside the repo; re-running needs them rebuilt from the rules below.

### A failed SOS Fade trade, then a previous-day sweep — does it reach 1R?

Failed = the trade never reached 0.5R. Then within 24h price sweeps the previous day's level on the
trade's side and a 5m bar closes back; enter at that close, stop beyond the sweep, target 1R.

| case | reached 1R | net R ± |
|---|---|---|
| every sweep (baseline) | 44% (340/775) | −0.12 ±0.04 |
| after any failed SOS Fade trade | 36% (13/36) | −0.32 ±0.17 |
| after a failed FIRST entry | 20% (5/25) | −0.66 ±0.17 |

- **Reject — proven harmful.** A failed SOS Fade trade makes the next sweep worse, not better.
- The "failed twice in a row, then a third entry on the sweep" chain Aaron described: 4 exact cases
  (1 reached 1R), 11 on a looser reading (5 reached 1R). Too few to measure.

### The aggressive Asia push into the previous day's level — does it retrace?

Push = in Asia's first 2 hours, price travels at least 3x the 15m ATR one way from the Asia open
(not necessarily in consecutive candles, per Aaron). 633 such sessions; 252 ran through the previous
day's level.

| | through the level | did not reach it |
|---|---|---|
| half the push back by Asia's end | 79% | 82% |
| all of the push back by day end | 68% | 71% |
| ran another 50% further first | 23% | 20% |

- **The level adds nothing.** Big Asia pushes retrace most of the time whether or not they sweep it.
- **Trading the retrace — Reject.** Entering on a 25% or 38% bounce off the running extreme, stop
  beyond it, exit at half the push or the Asia open: −0.03 ±0.04, −0.07 ±0.06, −0.08 ±0.02 (−3.5σ,
  proven harmful), −0.11 ±0.05. The retrace is common, but buying it after it starts does not pay.

### SOS Fade losers: sweep the 100 fib, close back in, then a new break of structure?

First entries stopped at the 88.6 fib (r ≤ −0.9): 47 of them. Second entries are excluded because
their trades do not record the fib ladder (47 more losers). Followed for 5 days on 15m closes.

- 43 of 47 (91%) swept the 100 and closed back inside. The 100 sits just past the stop, so this is
  near-certain and carries no information. 3 broke it and never came back; 1 never reached it.
- **Of the 43, only 7 (16%) closed beyond the leg's far end (the 0 fib) before closing back through
  the sweep's extreme.**
- **Trading it — Reject — proven harmful.** Buy the close back inside, stop at the sweep extreme,
  target the 0 fib, ECN costs: n=43, hit 14%, median payoff 4.5R, net −0.48R ±0.23 (P better than
  zero ≈ 2%). First half −0.37 ±0.40, second half −0.59 ±0.26.
