# MPC M15 Playbook — strategy spec

**File:** `indicators/mpc_m15_playbook_strategy.pine`
**Source of the idea:** `education/learned/2026-08-11-smc-strategy-too-simple-to-ignore-1150-trades.md`
(Lewis Kelly, "This SMC Strategy Is Too Simple to Ignore", https://youtu.be/lTrDQPVfJyI)
**Status:** built 2026-08-11. **Not compiled, not measured, no Python port, no parity harness.**

---

## Why this file exists

`indicators/mpc_m15_playbook.pine` is an **indicator**. It draws structure, sessions,
fair value gaps, order blocks, liquidity levels and a confirmation table, and it places
no orders — so the Strategy Tester cannot score it and there is no way to find out
whether the model wins. This file is the same five rules with an execution layer.

The two are meant to sit on one chart: the indicator draws, the strategy trades.

---

## The five steps, as implemented

| # | Video | This file |
|---|---|---|
| 1 | Direction — 15m swing structure only | `pbDirTf` (default `15`) run through the canonical structure engine; `dir` +1/−1 gates the side |
| 2 | Location — the current session sweeps the previous session's high/low | pool **frozen at the session open**: London takes Asia's, New York takes London's. Sweep = any trade through it |
| 3 | Confirmation — the 1m flips to agree with the 15m | `pbConfTf` (default `1`) run through the same engine; a **new** CHoCH in the direction timeframe's direction, after the sweep |
| 4 | Point of interest — nearest untouched 5m OB or FVG | `pbPoiTf` (default `5`) fair value gaps. Nearest LIVE gap on the far side of price, skipping any price has already traded into |
| 5 | Targets — TP1 previous day's low, TP2 previous week's low | `pdl`/`pdh` and `pwl`/`pwh`, ordered by distance and validated against the entry |

Entry is a **limit into the zone** (`execZoneEntry`: proximal edge by default), stop
beyond the zone's far edge plus a buffer, size = risk% ÷ stop distance.

---

## The decisions the video does not make, and what was chosen

**The pool is frozen at the session open.** Asia and London overlap, and so do London
and New York, so "the previous session's high" is ambiguous while both are running. It
is read once, at the moment the new session opens, and never again — a level that moves
under the setup watching it is not a level.

**New York wins the overlap.** It is the later session and its pool is whatever London
had made by the time it opened.

**A shift only counts after the sweep.** The sequence is location *then* confirmation; a
1m flip before the sweep is a different setup wearing the same flag.

**The confirmation is a COUNTER, not a flag.** A change of character is an edge, and a
flag read back through `request.security` is a level that stays true — so the engine
returns how many shifts it has seen and the strategy compares it with its own previous
bar. Nothing else can tell "it just shifted" from "it shifted at some point".

**The proximal edge depends on the direction.** It is the bottom of a zone above price
and the top of a zone below it. Written without the direction, every long rests at the
far edge of its gap.

**A limit must rest on the far side of the market.** If the chosen zone is no longer
beyond price by the time the setup completes, the setup is refused (block code 6) rather
than sent as a limit that fills immediately at market.

**Targets are ordered by distance, not by name.** Whether the previous day's low is
nearer than the previous week's is a fact about the week. A target on the wrong side of
the entry, or nearer than `execMinRr`, is not a target — `execTpFallbackR` substitutes a
fixed R multiple, or the setup is refused if that is 0.

**One trade per session.** A fill latches the session; the next arm waits for the next
session open.

**The fill bar may not stage its own stop.** A resting limit is reached by price coming
to it from the wrong side, so the fill bar's favourable extreme is the approach to the
order, not a move the trade made. (`indicators/BUG_exit_fill_price_mismatch.md`.)

**A rung is issued only while unfilled.** Calling `strategy.exit` again with an id whose
order has already filled places a NEW order rather than modifying it, which banks another
slice of the remainder every bar.

---

## Known gaps — read before quoting a number

**Only the FAIR VALUE GAP half of step 4 is modelled.** The video's point of interest is
"an order block OR a fair value gap". A gap-only rule takes strictly FEWER setups than he
does, so a low trade count here is partly this. Adding order blocks means either a second
OB implementation inside `request.security` (which this repo forbids) or running the
strategy on the zone timeframe itself.

**Everything crosses a `request.security` boundary.** The 1m confirmation and the 5m zone
are observed at the CHART bar's close — up to one chart bar late, never early. Run it on
5m for fidelity; 15m buys more history and a coarser trigger.

**TradingView loads limited 1-minute history.** With the confirmation ON, the far end of a
long backtest may see no 1m structure at all and simply take no trades there. Read the
trade list's first date against the chart's, and never read the tester's window header as
what arrived — it states what you asked for. (`indicators/CLAUDE.md`, 2026-08-07.)

**No control.** Gold tripled across any window this will be run on, so a long-side result
is free. Before believing any edge here, score it against random entries matched on
direction and stop distance — `backtest/tools/trigger_edge.py` is the shape that has
already caught this twice in this repo.

**The video's own numbers are two different books.** The 6.14 average win/loss and 3.07
profit factor are the 230-trade subset; across all 1,154 trades it is 3.93 and 1.92. The
title quotes one and the headline stats the other.

---

## What would make this trustworthy

1. Compile it and run it. Read the tail of the trade list before anything else.
2. Read a handful of setups on the chart against the indicator's own drawing — the state
   panel reports which gate the sequence is sitting on.
3. A control run (`trigger_edge.py` shape) on the sweep-plus-confirmation trigger alone.
4. Only then: an export twin, a Python port under `strategies/python/`, and a
   `compare_*.py` gate. `docs/STRATEGY_WORKFLOW.md` has the six stages.

⚠ Step 4 is a real lift here and nothing else in the repo has needed it: this strategy
reads THREE bar streams (1m, 5m, 15m) and `backtest/optimizer.run_sweep` replays one
frame, `run_dual` two. The lab cannot sweep it as built.
