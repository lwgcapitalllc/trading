# SOS Fade — Secondary (1m sniper) re-entry

**Status:** BUILT, unit-tested, measured over the full 7.9 years, and **ON by default since
2026-08-07**. 🔴 **Six of its defaults moved together on 2026-08-20 and the feature is a different
one after that date — read *The 2026-08-20 reshape* at the bottom before any figure above it.** The Python is the *exact* version of a
feature Aaron prototyped in `sos_fade_strategy.pine` (that Pine WIP is stashed:
`git stash list` → "secondary-trade pine WIP"). Pine can only sample the 1m engine once per
15m bar via `request.security`, so its timing is approximate; the Pine tooltip itself says
**"the exact version is the Python port."** This doc is the source of truth for that port.

---

## What it is (one paragraph)

After the **primary** 15m SOS Fade trade on a leg has already traded and gone flat (back to
breakeven), keep re-entering on that *same* 15m leg from the 1-minute chart. While the 15m
divergence **and** SOS are still live and price is back inside the **0.618–0.886** zone of the
15m fib, watch the 1m chart (same structure engine) for a **1m shift of structure** in the
trade direction. When one fires, rest a limit at a **38.2% retrace of that 1m leg**. The tight
1m leg is what makes it a *sniper* entry — small stop, fast to breakeven.

**How many re-entries one setup may have is `exec_sec_once_per_setup` (default ON = one).** The
original rule was *each distinct 1m LEG fires at most one*, which is not the same thing: a live
15m setup keeps producing fresh 1m legs, so it could re-enter repeatedly. Measured, it did —
2024-12-02 took two off one structure break (15m SOS bar 7893, 1m legs 120399 and 120499, the
second filling two minutes after the first closed). With the cap on, a fill retires the **15m SOS
bar** as well, which is one-to-one with the primary. ⚠ **The cap is per SETUP, not per lifetime**:
a new break of structure re-opens it.

A re-entry is **never the first trade on a leg** — the primary must have traded that leg first.

---

## The rules (ported line-for-line from the Pine WIP `f_secArm`)

Config toggle: **`exec_secondary`** (Pine `execSecondary`), **default True since 2026-08-07**
(Aaron's call). Off = primary only, one entry per 15m leg. ⚠ **Every measurement in this repo
taken before that date is a primary-only book** — pin it Off to reproduce one.

Cap: **`exec_sec_once_per_setup`** (default **True**), described above. Python-only, like
`exec_sec_retrace` — the Pine WIP has neither.

⚠ **`run_dual` has exactly one caller.** `backtest/optimizer.run_sweep` replays a single frame, so
the optimizer, sweeps and the stress test's pooled sensitivity **refuse** a config with this on
rather than silently replaying a primary-only book and ranking it against a baseline that has
re-entries. `algos/live/bridge.py` refuses it too. `b_leg` pins it **Off** — SOS Fade never places an
order in that fork, so there is no primary to re-enter behind, and its `run_dual` raises.

### 1m leg latch (records the leg a re-entry will trade)
- The 1m structure engine runs continuously on 1m bars. Its **latched** state per side is: the
  bar of the most recent 1m SOS, and the leg that SOS defined — `legHi` = 1m fib **0.0**,
  `legLo` = 1m fib **1.0** (= the stop anchor). A "new 1m SOS" = that latched bar advanced.
- Clear the long 1m leg the instant the 15m long setup dies (`aplusL_sosBar` is `None`); mirror
  for shorts. A stale 1m leg can never arm a fresh 15m leg.
- **Latch a long leg** when: `exec_secondary` ON, a new 1m **bull** SOS fired, the 15m long
  setup is live (`aplusL_sosBar` not None), `bullDivActive`, price is in the zone
  (`zoneL`), and `legHi > legLo`. Mirror for shorts (bear SOS, `bearDivActive`, `zoneS`).
- 🔴 **The `bullDivActive` / `bearDivActive` test above is now `exec_sec_req_div`, default ON
  (2026-08-20).** It came straight from the Pine WIP, which tests it in both the latch and the arm,
  and the port copied both. **It is a different question from `exec_arm_div`, and that is what hid
  it for a month:** `exec_arm_div` says what may arm the PRIMARY, and the shipped bot is
  SWEEP-armed with it OFF — so the re-entry was demanding a divergence its own primary was never
  required to have. On a sweep-armed book the feature cannot fire at all. MEASURED 2026-08-20 on
  lab run `4fb168fe354f`'s params (XAUUSD 15m, 2025-08-20 → 2026-08-18, 23,530 M15 + 352,348 M1
  bars), `exec_secondary` forced ON and nothing else touched: **0 re-entries in the year.** On the
  2025-12-09 short every other gate passed — primary reached breakeven, price closed back inside
  the zone for 433 one-minute bars, account flat, a 1m bear SOS inside the zone at 2025-12-11
  01:15 — and this one test alone refused it. 🔴 **It was flipped OFF by default on 2026-08-20** —
  keeping it ON kept the feature unreachable on the book it ships with, which is a stored figure
  worth less than a working feature. Pin it back ON to reproduce anything dated 2026-08-07 →
  2026-08-20; those numbers are also in `sos_fade_optimization.md`.
- **Zone** (`zoneL`): `fibo_dir == 1` and price in `[fiboP6, fiboP3]` (0.886…0.618).
  Mirror `zoneS`: `fibo_dir == -1` and price in `[fiboP3, fiboP6]`.

### Arm (rest the limit)
`lArmed` is true only when **all** hold:
- `exec_secondary` and `exec_longs`,
- **flat** (no open position),
- 15m long setup live (`aplusL_sosBar` not None),
- **the primary already traded this leg**: `tradedSosL == aplusL_sosBar`,
- `bullDivActive`, `fibo_dir == 1`, `fibsReady` (all 15m fib levels present),
- the latched 1m leg is valid (`legHi/legLo` set, `legHi > legLo`),
- this 1m leg hasn't already re-entered (`lLegTraded is None or lLeg != lLegTraded`),
- not in the late-day block, and (`not longVeto` or `not exec_respect_veto`).

Mirror for `sArmed`.

### The trade, on arm
| | Long | Short |
|---|---|---|
| entry (resting limit) | `legHi − (legHi−legLo)·0.382` | `legLo + (legHi−legLo)·0.382` |
| stop | `legLo − slBuf` (1m 100%) | `legHi + slBuf` |
| TP1 | 15m `fiboP2` (0.5) | 15m `fiboP2` |
| TP2 | 15m `fiboP1` (0.382) | 15m `fiboP1` |
| TP3 | runner (ratchet trail, same as primary) | runner |

Sizing = the same `exec_risk_pct` / stop-distance as the primary. On fill, **retire that 1m
leg** (`lLegTraded := lLeg`) so it can't re-enter twice.

**The minimum-stop floor applies here too, since 2026-08-07** — the same `_stop_clears_floor` the
15m path uses, not a second copy of the rule. Until then `_secondary_pending` asked only
`dist > 0`, so the shipped `"% of price"` 0.08 floor did not reach the one path where it matters
most: sizing is `risk / stop_distance`, and a 1-minute leg is a **shorter leg**, so its stop
distance is smaller by construction.

⚠ **Measured before it was added, and it refuses almost nothing: ONE setup in 7.9 years**
(2024-12-02 20:08 — a $2.08 stop against a $2.11 floor). Two full replays at shipped defaults,
control reproducing the shipped book exactly: **188 trades / +165.46R / ddR 5.53 → 188 / +165.42R /
ddR 5.53**, all 180 primaries identical, −0.04R. The refused trade did not vanish — a later
re-entry took the freed slot 47 minutes on. 🔴 **1,956 secondary limits were placed and 90 rested
under the floor, but all 90 are the SAME limit re-placed every 1m bar** — one setup resting 90
minutes. **A resting order is re-placed per bar, so counting placements counts bars, not risk.**
The case for the guard is consistency, not this measurement.

⚠ The floor reads the **15-minute** ATR(14) (`_update_atr` runs in `step`, never
`step_secondary`) — correct, since the setup and its risk are 15m, and irrelevant outside
`"x ATR(14)"` mode.

---

## The one deliberate deviation from the Pine — exact 1m timing

The Pine samples the 1m engine at the 15m close, so its re-entry fill is approximate. **The
Python runs the 1m bars for real:**

- **Primary** (the 15m SOS Fade trade) stays exactly as today — armed, filled and managed on **15m**
  bars. This is what keeps `compare_strategy.py` parity **green** (`exec_secondary` defaults
  off, so with it off the whole strategy is bit-identical to the validated port).
- **Secondary** is the 1m improvement — the 1m leg latch, the arm, the limit **fill**, and the
  TP1/TP2/stop management all happen on real **1m** bars. This is the sniper entry Aaron wants
  ("get in and out with profit, or move to breakeven as soon as possible") that a 15m bar
  cannot express.

**Zone check uses the live 1m close** (not the 15m close the Pine used) — "price is back in the
zone right now," faithful to the exact-timing intent.

**Consequence: there is NO Pine parity gate for the secondary.** The Pine is only the
approximate version. So the secondary is verified **visually** — the command-center price chart
with the 15m→1m drill-down, trade markers landing on the 1m candles at the 1m SOS + retrace.
That drill-down is why the chart work happened first.

---

## Python architecture

```
1m df ─┐
       ├─ DualClock ─┬─ on 15m bar close: EngineStack → Signals → Sequence → Execution (PRIMARY, 15m)
15m df ┘             │       └─ updates the "15m context" the secondary reads
                     └─ on each 1m bar:   Structure1m → Secondary latch/arm → Execution (SECONDARY, 1m)
```

- Bars are timestamped at **open** (UTC). A 15m bar at `t` covers `[t, t+15m)`; its 1m bars are
  `t … t+14m`. Calc-on-close: the 15m context for `[t, t+15m)` is only known at `t+15m`, so a
  secondary forming inside that window reads the **previously closed** 15m context — correct,
  non-repainting, and matches Pine's `lookahead_off`.
- **`Structure1m`** — a lean feed: `StructureEngine` + `StructureFib` on 1m (same `show_internal`
  pin as the primary), exposing latched `m1_bull_sos_bar` / `m1_bear_sos_bar` + leg hi/lo and
  the `new_bull_sos` / `new_bear_sos` edges. It does NOT run fvg/rsi/liquidity/sessions — the
  secondary needs only 1m structure.
- **Execution** grows a secondary path: an `_entry_kind` tag on the open position, a
  `step_secondary(bar1m, arm)` entry point that reuses the existing bar-fill primitives
  (`_try_entry_fill_bar`, `_manage_open_bar`, `_advance_stage`, `_current_stop`). 15m bars only
  touch a **primary** position; 1m bars only touch a **secondary** position — they share the one
  position slot but never the same trade, because the secondary only arms when flat.

## Verification

1. **Unit** — `Structure1m` (SOS latch + leg + edge), the arm/latch truth table, one hand-traced
   end-to-end re-entry.
2. **Visual** — a real run with `exec_secondary=True`, opened in the lab's price chart, drilled to
   1m at a re-entry: the 1m SOS, the retrace to 38.2%, the fill marker, the 15m TP levels.
3. **Parity guard** — `compare_strategy.py` stays exit 0. ⚠ **It is a 15-minute harness: it drives
   `.run()`, never `run_dual`, so NO re-entry setting can reach it at all** — that is why six of
   them could be changed at once on 2026-08-20. It proves the primary never moved; it can say
   nothing whatever about the re-entry, and reading a green gate as covering one is rule 14.

### Where it actually stands (2026-08-06)

1 and 3 are DONE. **2 was never done, and the reason is worth recording because it was a false
belief rather than a missing tool.** Both `strategies/python/sos_fade/CLAUDE.md` and the lab's
own param description stated that the broker serves **~35 days** of 1-minute history, so the only
window anyone believed was reachable was a few days of local cache — over which the secondary fired
zero times, which is exactly what a rare setup does over four days. That reading was correct and the
premise under it was not.

🔴 **The 35-day figure was a guess and it is false. MEASURED against the live `MT5_Lab` terminal
(VantageMarkets-Demo) on 2026-08-06: real 1-minute XAUUSD runs back to 2018-09-14 — ~2.8M bars,
7.9 years**, the same depth the M15 history has. Six windows sampled across the range return
1,341–1,392 bars/day at exactly 1.0-minute spacing, and a pre-floor request is refused rather than
silently served daily bars.

⚠ **Verify M1 depth by bar DENSITY, never by the earliest timestamp.** MT5 answers a too-deep
intraday request with coarser bars still labelled as the timeframe you asked for — see
`backtest/data/history.py`, which exists for precisely this and measured the floor above.

**So there is no data obstacle and there never was.**

### The measurement (2026-08-06) — it does not earn its place

Three replays over **186,274 M15 + 2,744,333 M1 bars, 2018-09-14 → 2026-08-05**, shipped defaults:

| | A `run(df15)` | C `run_dual` secondary ON |
|---|---|---|
| trades | 180 | 190 |
| total R | +139.90 | +165.46 |
| max drawdown | 45.6% (5.61R) | 50.7% (6.53R) |
| avg R / trade | +0.777 | +0.871 |
| **avg R / trade, best secondary removed** | **+0.777** | **+0.731** |

**B — `run_dual` with the secondary OFF — reproduced A exactly (180 trades, identical entries).**
That control is not ceremony: the two share one position slot, so without it a difference in C is a
mix of *the re-entries made money* and *the 1m stream nudged the primary*, and nothing afterwards
separates them. **Zero primaries displaced**, either direction.

**Ten re-entries in 7.9 years:**

```
2019-11-07 L  -1.000R    2024-01-16 L  +0.082R    2024-12-03 L  +1.000R
2020-09-15 S  +0.048R    2024-01-16 L  -1.000R    2025-01-29 S  +0.054R
2022-03-06 S  -0.092R    2024-12-02 L  +0.144R    2025-08-21 S  -1.000R
2023-04-03 L +27.327R
```

🔴 **2023-04-03 is +27.33R of the +25.56R total. Remove it and the other nine are −1.77R**, and the
book's average R per trade falls **below** baseline. A rising total with a falling average is what
dilution looks like from outside. ⚠ **+25.56R is not evidence either way** — the jitter audit puts
this strategy's run-to-run spread at **sd 15.06R**. ⚠ **The fat-tail defence does not rescue it:**
SOS Fade is designed tail-heavy, but the primary stays positive without any single trade and these ten do
not. Ten trades cannot tell a small edge from a small negative one — the same verdict, for the same
reason, as B-LEG.

**That verdict was overturned on 2026-08-20, and the reason was in the last sentence of it:** what
would change the answer is a reason to expect more than ten fires, and there was one — the feature
was gated on a divergence its own primary never needed, so it was firing on a fraction of the
setups it was written for. See *The 2026-08-20 reshape*.

⚠ **Every figure above post-dates a fix on the same day.** `run_dual` built its 1m signal without
`last_conf_high`/`last_conf_low`, which the shared `_advance_stage` reads on every managed bar, so
the first 1m bar after any fill raised `AttributeError` — **the re-entry had never once opened a
position on real data.** Any earlier claim about this feature describes code that could not run.


---

## The 2026-08-20 reshape — five defaults, one new setting, and the feature this doc now describes

Everything above this line describes the shape shipped between 2026-08-07 and 2026-08-20. Five
defaults moved on 2026-08-20 and a sixth setting was added, and the leg went from **10 re-entries to
54** over the same 7.9 years.

| what | was | is | why |
|---|---|---|---|
| needs a live 15m divergence | ON | **OFF** | it demanded what the primary never needed — **0 re-entries in the most recent 12 months** |
| what triggers it | a 1m shift of structure | **a fair-value gap in the zone** | the shift confirms late; on 2025-10-29 it missed by $8.02 and price ran 114 points |
| where the stop sits | the 1m leg origin | **the 0.886 fib** | the gap trigger has no 1m leg to stop behind |
| its first target | the 15m 0.5 fib | **1.25 × its own risk** | a 1m entry handed a 15m target scratches — 15 of 54 finished flat |
| how much banks there | nothing | **half** | banking half left zero scratches, 30 wins, 24 losses |
| what it risks | the same as a primary | **half a primary** | one trade is +20.68R of the leg's +27.84R |

**The two numbers that decided it.** Re-entry total, and the same total with its single best trade
removed: the old shape **+29.50R / −0.36R**, the new shape **+27.84R / +7.16R** at full weight and
**+13.92R** at the shipped half weight. **The headline column would have kept the old shape.**

**What it costs.** Worst closed-trade drawdown on a $10k start: primaries alone **51.8%**, plus
re-entries at half weight **60.4%**, at full weight **68.1%**. It is the SAME drawdown made deeper —
both trough in the 2023-04-05 → 2024-10-29 stretch, inside which the primaries lose 6.34R and the
re-entries lose a further 4.70R off the same setups. 🔴 **They fail together: this is the first hard
number in the repo on the correlation the root philosophy warns about in words.**

⚠ **The size lever is invisible in every R table.** It scales the lot only, so the re-entries report
**27.84R at a quarter weight and at full weight alike** — R is measured against each trade's own
risk. Multiply by the size setting before comparing a re-entry's R with a primary's.

⚠ **Not usable live, unchanged.** The live runner drives one timeframe and refuses this config
outright.
