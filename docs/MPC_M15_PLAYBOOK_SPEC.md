# MPC M15 Playbook — strategy spec

**File:** `indicators/strategies/mpc_m15_playbook_strategy.pine`
**Source of the idea:** `education/learned/2026-08-11-smc-strategy-too-simple-to-ignore-1150-trades.md`
(Lewis Kelly, "This SMC Strategy Is Too Simple to Ignore", https://youtu.be/lTrDQPVfJyI)
**Status:** built 2026-08-11; standardised onto the house input panel and colour palette
2026-08-14. **Not compiled, not measured, no Python port, no parity harness.**

---

## Why this file exists

`indicators/engines/mpc_m15_playbook.pine` is an **indicator**. It draws structure, sessions,
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
order, not a move the trade made. (`indicators/docs/BUG_exit_fill_price_mismatch.md`.)

**A rung is issued only while unfilled.** Calling `strategy.exit` again with an id whose
order has already filled places a NEW order rather than modifying it, which banks another
slice of the remainder every bar.

---

## The panel and the palette (2026-08-14)

The inputs use the numbered groups every strategy in `indicators/strategies/` uses, so section 5
is Entry whichever file you open. The contract, and the rule deciding which section a new toggle
goes in, live in `indicators/strategies/CLAUDE.md` — not here.

**Sections 3, 4, 5, 6, 7, 8, 10, 11 are present. 1, 2, 9 and 12 are absent and the numbering does
not close up**, because the number is the address:

| absent | why |
|---|---|
| `1 · Confirmation table` | this strategy reads no JARVIS table — same as BOS, D and H4 |
| `2 · Market structure` | its engine runs INSIDE `request.security` and Pine cannot draw from there. A chart-frame copy would draw the 5m's swings while the strategy trades the 15m's. **Open — Aaron's call**, and the fix is a feature (return the swing prices through the security call) rather than a port |
| `9 · Drawing: fibs` | no fibs |
| `12 · Debug` | held one per-event Pine Logs line; cut 2026-08-14 (*"for events, we don't need that"*). Everything it reported is on the chart, read from the same `sBlk`/`lBlk` |

**The session drawing is a BOX per session round its own high and low, not a full-height stripe,
and that is a fact about the model rather than about taste: the box's top and bottom ARE the pool.**
What London sweeps is the top of Asia's box. A box is also left standing when its session ends —
it is the level the next session hunts.

**`Show the previous session's high / low` defaults ON**, unlike the other draw toggles. It is
step 2 drawn — the single line that explains why the strategy did or did not act on a given day.

⚠ **The chart shows the last 100 trading days of sessions and the last 40 trades, and neither
limit is a bug.** TradingView allows 500 drawing objects per script, shared across all three
families; the split is at the top of the Pine and both tooltips state their own limit. **Read trade
counts off the Strategy Tester's list, never off the boxes on the chart.**

**The six session strings are hardcoded, not inputs.** They DECIDE trades — the sweep pool is read
off them — which normally means they belong in a trade group rather than being collapsed away. They
are frozen anyway because every Pine file in this repo has carried the identical DST-aware values
since 2026-07-31, so a divergence here would be a bug and not a setting. ⚠ **A change to them
belongs in every file that carries the block.**

**Every colour a trade is drawn in is `mpc_strategy.pine`'s.** Change a value there and copy it
down, never pick one here. The state panel deliberately keeps the separate TABLE palette.

⚠ **The first paste costs one "Reset settings to defaults"** (every input moved), and in the same
visit untick Style → **"Trades on chart"** — this file draws its own position box, entry triangles
and result callout, so the built-in markers double-draw at a second set of exit prices.

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
