# MPC BOS — optimization log

One entry per sweep, so a question already answered is not re-measured. Same convention as
`strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md`.

**Where the old log went.** Runs 1–4 (2026-07-31) lived in `strategies/python/mpc_bos/`, which was
deleted on 2026-08-04 as a half-built port with no parity harness (commit `1946f8b`). Their
findings are summarised in Run 5 below and the full text is recoverable at `1946f8b^`. They are
not restated here in full; they are cited, because Run 5 only makes sense against them.

⚠ **NO NUMBER IN THIS FILE COMES FROM A PINE↔PYTHON PARITY-VALIDATED RUN.** There is still no
`mpc_bos_strategy_export.pine` and no `compare_bos.py` (spec §10 steps 3–4 are open). Runs 1–4 came
from a Python port that was never validated; Run 5 comes from a deliberately simplified skeleton
that is not the strategy at all. Read the DIRECTION of everything here, never the decimals.

---

## Run 5 (2026-08-07) — the first configuration that beats a control, and the FVG entry comes OFF

**The question Aaron asked:** *"use everything in the parameters to give me a profitable strategy,
optimize it."* Runs 1–4 had already answered the literal version of that and the answer was no —
82 configurations, profit factor below 1.0 in every one. So this run did not re-search the same
space. It asked what had CHANGED since, and one thing had: **the session VWAP filter (F10), which
was in none of the earlier runs.**

That matters because of what Run 3 concluded:

> *"Every input the strategy has describes the SETUP... Not one of them separated winners from
> losers consistently. What did was the state of the market at the moment of the setup, which no
> existing input can express."*

**VWAP is a context variable.** It is the axis Run 3 said was missing, and unlike Run 3's own
volatility split it has not gone dark with the regime.

### Method — and the three guards, because 564 configurations is how a fit gets manufactured

`backtest/tools/trigger_edge.py` + `bos_sweep.py` (session scratch, grid transcribed below). The
canonical `market_structure` + `vwap` engines are replayed ONCE over **186,384 true-M15 XAUUSD bars
(2018-09-13 → 2026-08-07)**; only the cheap entry logic runs per configuration. Scored **+2R before
−1R**, no sizing, no ladder, no compounding.

1. **A matched random CONTROL per configuration**, on direction *and* stop distance. Gold ran
   1,200 → 4,300 across this window, so a long-side "edge" is free and any harness without a
   control will find one. The control lands on the theoretical breakeven with expectancy ~0.000.
2. **A half-split** — must be positive in BOTH halves of history. This is precisely the test that
   killed Run 3's volatility rule and Run 4's regime labels.
3. **The configuration count is reported**, so the multiple-comparison exposure is visible rather
   than implied. 564 scored.

### The result

| configuration | n | win rate | vs control | net expR after spread | PF |
|---|---|---|---|---|---|
| **0.786 entry · fib 1.0 stop · VWAP on** | 201 | 46.8% | **+14.5% (+4.1σ)** | **+0.276R** | 1.76 |
| 0.786 entry · fib 1.0 stop · VWAP off | 578 | 40.1% | +7.8% (+3.8σ) | +0.101R | 1.34 |
| 0.5 entry (old depth) · VWAP on | 509 | 36.7% | +3.7% (+1.7σ) | +0.056R | 1.16 |
| **0.5 entry · VWAP off — WHAT SHIPPED BEFORE TODAY** | 793 | 36.1% | +2.8% (+1.7σ) | +0.040R | 1.13 |

✅ **Positive in 9 of 9 years.** ✅ **Each switch degrades smoothly** rather than falling off a
cliff, which is the shape a real effect has and a fitted one does not.

✅ **The strongest single piece of evidence is the direction split: shorts +17.7% beat longs
+12.3%.** Gold tripled across this window, so a drift artefact shows up as longs carrying
everything — `mpc_sos_fade/CLAUDE.md` records that exact trap, and Run 3 flagged its own
longs-vs-shorts slice as confounded and unusable. This one points the other way.

✅ **VWAP was tested PAIRED across the whole grid, not cherry-picked from the top:** 276 matched
on/off pairs, VWAP improves expectancy in **210** of them, median ΔexpR **+0.054**.

### 🔴 The headline is not VWAP — it is that the GAP ENTRY comes OFF

**Entry depth is a bigger lever than the filter**, and the two compound. Moving the limit from the
0.5 band to a plain fib 0.786 is what takes the configuration from +3.7% to +14.5%.

That is the same conclusion Run 1 reached from the opposite direction, seven days earlier and with
a different tool:

> *"**The FVG entry — the core of the spec — is the entire loss**, and it has no tail at all: 98
> trades and not one bigger than +3.3R."*

**Two independent measurements, different implementations, same verdict.** The mechanism is that
the GAP decides where the limit rests, and it rests too shallow for a continuation trade — which is
Run 1's structural read ("the entry band and the setup disagree") arriving with a number attached.

⚠ Note this does NOT vindicate Run 1's proposed fix. Run 1 recommended inverting the ladder to the
*shallower* 0.382–0.5 Sniper-Zone pocket; Run 2 then corrected itself and withdrew that read. The
measured answer is **deeper**, not shallower.

### 🔴 The top row of the raw sweep was DISCARDED, and this is the important part

Ranked on expectancy alone the winner was **0.786 entry + 0.886 stop at +0.563R**. It is not in the
shipped defaults, and the reason is a cost measurement rather than a judgement call:

| stop model | median stop | p10 stop | spread as % of R | expR | **net of spread** |
|---|---|---|---|---|---|
| fib 0.886 | **$0.74** | **$0.31** | **29.8%** | +0.563 | +0.265 |
| **fib 1.0 (leg origin)** | $1.73 | $0.73 | 12.7% | +0.403 | **+0.276** |

At a $0.22 Vantage spread the 0.886 stop gives back 30% of R before the trade starts, and the
deepest tenth of its trades rest stops under $0.31 — untradeable. **After costs the ranking
inverts.** This is Run 1's collapsing-stop hazard reached from a new direction: there it inflated
sum-R through position sizing, here it inflates win rate through an unpayable stop distance.

⚠ **Standing rule this run adds: rank on expectancy NET of the spread, not on expectancy.** On this
strategy the two orderings disagree at the top, and the gross ordering picks the configuration you
cannot trade.

### Shipped defaults changed (2026-08-07)

| input | was | now |
|---|---|---|
| `bosUseFvg` | `true` | **`false`** |
| `bosEntryFib` | `"0.618"` | **`"0.786"`** — now the PRIMARY entry, not a fallback |
| `bosWhich` | `"1st only"` | **`"All"`** |
| `bosMinDispAtr` | `0.5` | **`0.0`** |
| `bosSlModel` | `"Fib 1.0 (leg origin)"` | unchanged — **and it must stay** |
| `bosVwapReq` | (new, 2026-08-06) | `"Trend's side"` |

⚠ **Changing a default does not change a chart that already has saved values.** These take effect
on a fresh paste or after "Reset settings to defaults".

### What this run does NOT establish

⚠ **The exit model is not the strategy's.** The skeleton scores a flat +2R-or-−1R. The Pine runs a
30/30/20 ladder with a staged stop and a runner. **The direction transfers; the magnitude does
not**, and `+0.276R per trade` must never be quoted as this strategy's expectancy.

⚠ **564 configurations were searched.** The defences are the 9-of-9 years, the half-split, the
shorts-beat-longs direction check, the smooth degradation across switches, and the paired VWAP
test. They are decent. They are not proof, and this is exactly the exposure Run 3 named in itself.

⚠ **Aaron confirmed on 2026-08-07 that the new defaults beat the old ones in the TradingView
Strategy Tester — DIRECTIONALLY ONLY. The three numbers (net profit, profit factor, trade count)
were not recorded, so no figure anywhere in this repo describes a real run at these settings.**
Record them on the next run; until then the Strategy Tester's agreement is a fact about the sign
and nothing more.

⚠ **Still no parity harness.** Everything above is a claim about a model of the strategy, checked
once against the strategy by eye.

### The next three questions, in order

1. **Record the six numbers** — A vs B, net profit / PF / trade count. Cheapest thing on this list
   and it is the only one that would put a real figure against these defaults.
2. **Does the real TP ladder keep the edge?** A 0.786 entry lands `longTier = 2` (deep), so TP1
   becomes fib 0.5 at ~1.34R. That is a different trade from the flat 2R the skeleton scored.
3. **Build `mpc_bos_strategy_export.pine` + `compare_bos.py`** (spec §10 steps 3–4). Until then
   nothing here can be validated, and the last port was deleted for exactly that reason.

Reproduce: `python3 backtest/tools/trigger_edge.py` for the trigger study; the grid script is
session scratch (`bos_sweep.py`) and its grid is `entry ∈ {0.382, 0.5, 0.618, 0.786} ×
stop ∈ {fib1.0, fib0.886, ATR2, ATR3} × which ∈ {all, 1st, 1st+2nd} × disp ∈ {0.0, 0.5} ×
RR ∈ {1.0, 1.5, 2.0} × vwap ∈ {off, on}`.
