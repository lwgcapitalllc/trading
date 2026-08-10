# MPC OB Fade — Strategy Spec (Stage 1 of `docs/STRATEGY_WORKFLOW.md`)

**Source of truth:** `indicators/mpc_ob_fade_strategy.pine` — **not yet written.** Until it exists
this document IS the spec, and it is a fork of `indicators/mpc_strategy.pine` (the A+ execution
layer) with exactly one rule changed and one filter added.
**Purpose:** the exact, machine-followable rules the Pine and the Python port both reproduce.
**Status:** DRAFT 2026-08-09 — awaiting Aaron's sign-off on the four questions at the bottom.
**Owns:** `strategies/python/mpc_ob_fade/`, `indicators/mpc_ob_fade_strategy.pine` (+ its export
twin), `tools/compare_ob_fade.py`.

---

## One paragraph

The **same** A+ SOS-fade setup this house already trades — sweep, shift of structure, retrace into
the 0.5–0.886 fib band — taken on the setups A+ **refuses for want of a fair value gap**, using a
live **order block** in the band as the point of interest instead. It exists as its own bot rather
than as a mode of A+ because A+ has ONE position slot, and every measurement of this idea as a
toggle lost money by DISPLACING A+ trades rather than by the added trades being bad.

**By construction the two bots can never take the same setup.** A+ is pinned to gaps
(`exec_poi_source = "FVG"`); this bot fires only where no qualifying gap exists. That is the
property the A+/B-LEG pair needed a whole overlap audit to establish, and here it falls out of the
rule. ⚠ It does NOT make them independent — both read one structure stream on one instrument.

---

## What is inherited, unchanged

**Everything except the two rules in the next section.** The A+ sequence, the entry pricing, the
stop, the exit ladder, the filters, the sizing. Stated explicitly so nobody has to infer it:

| | |
|---|---|
| Stage 1 ARM | liquidity sweep or RSI divergence, per `exec_arm_sweep` / `exec_arm_div` |
| Stage 2 SOS | external same-side structure break inside `aplus_window`, retro-link included |
| Stage 3/4 ZONE | fib 0.5 tapped → EARLY, 0.618 reached → READY |
| Sequence death | opposite SOS · TP3 · leg invalidated · continuation BOS |
| Entry pricing | the four fib entry rules (`exec_fib_nearest` ON, Method 3 off), clamped into the band, resting LIMIT |
| Stop | `exec_sl_level` 0.886 + `exec_sl_buf_tk`, floored by `exec_min_stop_mode` |
| Targets | deep/shallow TP1+TP2 by entry depth, TP3 = the runner |
| Stop staging | TP1 → breakeven+buffer, TP2 → floor, then the runner trail |
| Runner trail | `"Structure + % ratchet"`, `exec_trail_pct` 1.0 |
| Time stop | `"Before TP1 only"`, 36h |
| Vetoes / HTF / direction / final hour | as A+ |
| Sizing | `exec_risk_pct` 10, self-sizing, `qty = equity × risk% / stop_distance` |

The full register of exit levers is `strategies/python/mpc_sos_fade/CLAUDE.md` → `## The exit
ladder`, and it is shared. **A new lever there lands here in the same commit.**

---

## RULE 1 — the point of interest (the whole strategy)

A+ asks: *is a live FVG overlapping the 0.5–0.886 band?* This bot asks:

> **Is a live ORDER BLOCK overlapping the band, AND is there NO qualifying FVG in it?**

Precisely, on each bar the entry is priced:

1. Build the candidate gap list exactly as A+ does — live FVGs overlapping `[fiboP2, fiboP6]`,
   after the **deep-only** gate (`exec_fvg_deep_only`, gap fully past 0.5) and the **pre-zone** gate
   (`exec_fvg_pre_zone`, the gap existed before price arrived).
2. **If that list is non-empty, this bot does not trade the leg at all.** No order, no block
   fallback. That setup belongs to A+.
3. Otherwise build the same list from live **order blocks**, same direction, same band, through the
   **same two gates**, and price the entry off it with the same four fib rules.

Three consequences worth stating rather than discovering:

⚠ **The gap list is checked AFTER its eligibility gates, not before.** A gap that exists but is
refused by deep-only or pre-zone does NOT hand the leg to A+ — A+ will not trade it either, so
treating it as a gap would leave the setup untraded by both bots. This is the same ordering
`signals.pois_for` already uses for the "FVG first" ranking, and it is load-bearing in both.

⚠ **A block obeys every rule a gap does, by construction.** It is adapted into the gap's own
`(top, bottom, is_bullish, born)` shape and read through the ONE seam (`signals.pois_for`), so the
deep-only gate, the pre-zone gate and the four entry rules are each written once and see one kind of
thing. Do not write a second entry path for blocks.

⚠ **`born` is the block's `created_index` — the bar the engine could first REPORT it — never its
anchor candle**, which can be ~10 bars older. The pre-zone gate asks whether the zone was already
there when price arrived; answering with the anchor would be look-ahead wearing a reasonable field
name.

### What this bot and A+ are, together

A+ plus this bot is exactly `exec_poi_source = "FVG first"` **split across two position slots**.
That is the point: as one bot on one slot it measured 276 trades / +102.90R against A+'s own 159 /
+142.18R, and **82% of the shortfall was 29 A+ trades that never happened**, not the trades added.

---

## RULE 2 — the swept-pool filter (`ob_pool_filter`, default **OFF**)

**What a pool is.** Every A+ setup arms on a liquidity sweep, and the liquidity engine names which
level was swept. `Signals.recent_ssl` / `recent_bsl` carry that name, from a closed set:

`""` · `H4 High/Low` · `Day High/Low` · `Asia High/Low` · `Ldn High/Low` · `NY High/Low`

`ob_pool_filter ∈ {"Off", "Day only"}`. **"Day only"** refuses the setup unless the pool that armed
it is `Day High` or `Day Low` — yesterday's high or low, the level with the most resting stops
behind it.

⚠ **A DIVERGENCE-armed setup has no swept pool and is therefore REFUSED under "Day only".** That is
a real behaviour, not an edge case: the filter is a claim about the sweep, and a setup with no sweep
cannot satisfy it. It is inert at today's arm defaults (`exec_arm_sweep` True, `exec_arm_div` False)
and would bite the moment divergence-arming is switched on. Refusing is the honest answer —
admitting an unfiltered setup through a filter that could not be evaluated is the *"no" and "cannot
ask" must never be the same value* rule, which this repo has now broken five times.

### Why it ships OFF, and it is not modesty

Measured on the 103 order-block trades this population produced when run as a toggle on A+:

| | n | reached TP2 | total | worst drawdown | return per unit of drawdown |
|---|---|---|---|---|---|
| all | 103 | 24% | +14.59R | 11.61R | 1.26 |
| **Day pool only** | 59 | 31% | **+17.32R** | **6.61R** | **2.62** |
| H4 pool only | 44 | 16% | −2.74R | 14.55R | −0.19 |

The Day half carries the return AND avoids most of the drawdown; the H4 half loses money and causes
the pain. That is a strong-looking split and it is **not established**:

- **z = 1.71** on the TP2-rate difference, against a 1.96 bar — and **~14 features were searched**
  to find it, so the multiple-comparison discount is real.
- 59 trades. **95% CI on mean R is −0.124 .. +0.711** — tilted positive, still containing zero.
  (For calibration, B-LEG's was −0.40 .. +0.37 and this repo called that "a measurement that has
  not started".)
- Positive in **3 of 7 years**; +17.32R total, **+6.17R without 2022**.

⚠ **So the filter is built as a LEVER and measured on this bot's own trade list, never baked in.**
Building it in from day one would freeze an overfit into the strategy's definition, where no later
run could separate it from the setup. The first measurement of this bot is taken with it **Off**.

---

## Config pins — what must NOT be inherited

`ObFadeConfig` is a `SosFadeConfig` superset, so **every A+ default it does not re-declare arrives
uninvited, including ones added to A+ after this fork's Pine is written.** That is the defect that
bit `mpc_bos` on 2026-08-07, and the rule it left behind applies here in both directions.

| field | pin | why |
|---|---|---|
| `exec_poi_source` | `"Order block"` + the no-gap gate | this fork's whole rule |
| `exec_secondary` | **`False`** | the 1m re-entry needs `run_dual`; every sweep and optimizer path refuses it outright, and A+ has defaulted it **True** since 2026-08-07 |
| `exec_req_fvg` | `True` | "no gap in the zone" is meaningless if the gap requirement is off |

**And the reverse rule, which is the one that gets forgotten: nothing in `config.py` may exist
without a Pine input behind it.** A field the export cannot carry is a field `compare_ob_fade.py`
can never check, so a run using one is unverifiable by construction. Pine input first, then port.

---

## Risk — it is a second bot on one account

`exec_risk_pct` is **per trade**. Two bots on one balance is the account-level question, and there
are two different answers depending on where you are:

- **Backtest** — `backtest/portfolio/run_stack` replays both legs on ONE balance with ONE risk
  budget they compete for, plus a SOLO control replay per leg. That is how this bot's real
  contribution gets measured, and comparing **R** rather than net dollars is mandatory (a shared
  account compounds both legs onto one balance, so it can close HIGHER than a screen while the cap
  is working — `command-center/docs/SHARED_RISK_STACK.md` predicted the opposite and was wrong).
- **Live** — `algos/shared/account_risk.py` reads the BROKER's exposure across every magic.
  `mpc_sos_fade_demo` carries `account_risk_cap_pct: 10.0`, which **equals** that bot's own
  `exec_risk_pct`, so a second bot does not share the budget — the two take turns. Expect more live
  contention than any stack backtest shows, because a RESTING limit holds the whole budget while it
  waits and `backtest/portfolio/` reserves at the FILL.

Nothing about this bot may go live before `docs/LIVE_TRADING_PIPELINE.md` is satisfied for it,
including a distinct magic number.

---

## What is measured, and what is not

**Measured** (155,807 M15 bars, 2020-01-01 → 2026-08-06, the A+ book asserted to reproduce 159
trades / +142.18R with the order-block engine tracking but never trading):

- **179** A+ setups died on "No FVG in zone". **130 (73%)** had a same-direction live block in
  0.618–0.786; **152 (85%)** in the shipped 0.5–0.886 band. ⚠ The headline 130 is the NARROW band —
  this spec's rule uses the shipped band, so the candidate population is the 152.
- Of the 130, **27** would have been refused outright by an existing block rule, leaving **103**.
- Those 103, run through A+'s own slot: **+14.59R**, 24% reaching TP2, maxDD 11.61R.

**NOT measured, and each is a reason no number here is a forecast:**

1. **Every figure above was produced by trades sharing A+'s single slot.** A standalone bot has its
   own slot and will take MORE setups than 103 and different ones. The trade list will move.
2. No TP1/TP2 scale-out combination was found that helps — 19 combinations replayed, all inside a
   3.2R band once the single best trade is removed. The shipped 0/0 stands until re-measured **on
   this bot's own trades**.
3. The pool filter is unmeasured on this bot (see Rule 2).
4. **No jitter audit, no overlap audit, no out-of-sample split.** All three are prerequisites to
   calling this an edge, not to building it.

---

## The six stages, and where this one stops

Per `docs/STRATEGY_WORKFLOW.md`. **Only after stage 6 is green can a sweep, an optimization or a
backtest number from this bot be trusted.**

| # | artefact | state |
|---|---|---|
| 1 | `docs/MPC_OB_FADE_SPEC.md` | **this file — awaiting sign-off** |
| 2 | `indicators/mpc_ob_fade_strategy.pine` | not started |
| 3 | `indicators/mpc_ob_fade_strategy_export.pine` | not started |
| 4 | a real TradingView CSV | **only a human can do this** |
| 5 | `strategies/python/mpc_ob_fade/` | not started |
| 6 | `tools/compare_ob_fade.py` exit 0 | not started |

⚠ The Pine is a fork of `mpc_strategy.pine`, so it starts near the same **CE10117 token pressure**
that forced the internal fib out on 2026-08-09. The order-block engine is ~111 lines and is
recoverable from commit `cc0ecec` — **recover it from git, never rewrite it from memory.** Budget a
cut, and cut something cosmetic and defaulted OFF, exactly as every earlier cut in that file was
made.

---

## Open questions for sign-off

1. **The name.** `mpc_ob_fade` / "MPC OB Fade", baked into ~8 file paths. Confirm before stage 2.
2. **The pool filter's shape.** Shipping as `{"Off", "Day only"}`. Is a third option worth having —
   e.g. "Day or session" (Day + Asia/Ldn/NY, excluding only H4)? It costs one string and would let
   the sweep answer *which* pools matter rather than only *whether Day does*.
3. **The direction toggles.** A+ trades both sides. This bot's 103 measured trades were not split by
   side; if you want longs-only or shorts-only it is a config default, not new code — but it should
   be a measurement, not a preference.
4. **Timeframe.** M15, same as A+, unless you want the parity export taken elsewhere.
