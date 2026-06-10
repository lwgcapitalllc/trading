# LWG Capital — Speed Game Plan (Optimize + Stress, then Queue)
**Last updated:** 2026-06-06

> Companion to the Project State Snapshot and Roadmap. Slots in as the next
> milestone, **ahead of M6 (stacking)** — stacking needs B-grade strategies, and
> this is what produces them faster.

---

## For Claude Code — how to execute this

- **Strict build order.** Steps 1 → 6, in order. Do not start a step until the
  previous step's **Done when** is met.
- **Stop and report after each numbered step.** Show the result, confirm the
  Done-when criteria, then wait for the go-ahead before the next step.
- **Smallest viable change first.** No speculative abstractions. The UI does not
  change in any step except where a step explicitly adds a screen.
- **Respect locked principles** (see Snapshot): NT8/MT5 stays the engine (#5),
  generic strategies with ruleset-injected foundational config (#2, #3), one
  shared regime classifier (#4), SA-lock-of-1 stays (#7).
- **Update the affected CLAUDE.md / docs in the same session** as the change that
  made them stale (command-center backend + frontend CLAUDE.md, Snapshot,
  Roadmap). Never deferred.
- **Ask one clear question with concrete options** if input is needed; otherwise
  proceed.

---

## The one idea behind all of it

There are two kinds of work in this system:

- **Work that needs a fresh backtest against price data** — slow.
- **Work that reuses results you already computed** — fast.

Right now you do slow work where fast work would do. The fix is to run the
platform's **built-in optimizer** once (one data load, all CPU cores), and then
reuse that single run for everything downstream — winner selection, sensitivity,
and Monte Carlo input.

**One heavy run → three results: winner shortlist, sensitivity read, Monte Carlo input.**

Nothing here costs money. No cloud, no new subsystem, no Python backtest engine.
Principle #5 (NT8/MT5 is the engine) stays intact.

---

## What's slow today and why

| Today | Problem |
|---|---|
| M2 optimizer fires **one full backtest per combo**, serialized behind the SA-lock-of-1, reloading data every time | This is the 4-min × N pain. Both platforms have a native optimizer that loads data once and runs the grid across all cores. You built a hand-crank next to a button. |
| M3 sensitivity **re-runs NT8** for each ±10% / ±25% perturbation | Same disease. The optimizer grid already tested the values around the winner — the answer is sitting in results you already have. |
| M3 walk-forward orchestrates **N separate NT8 runs** for IS/OOS windows | Both platforms have walk-forward built into their own optimizer. One data load, all cores. |
| M3 Monte Carlo: 10k reshuffles in numpy, ~5s, no backtest re-run | **Already correct. Do not touch.** This is the model for everything else. |

---

## Sweep vs optimize — what they are and the order

- **Sweep** = which instrument fits this strategy? Same settings, run across many
  pairs. Cheap (plain backtests).
- **Optimize** = for the one instrument that fit, what are the best settings? One
  instrument, many combos. Expensive.

**Order: sweep first, then optimize.** Find the instrument with a pulse, then
spend the heavy combo grid only on that winner. Optimizing all instruments first
would waste the expensive step on dead pairs.

**Guard:** sweep with a tiny coarse settings grid per instrument, not a single
default set — a pair that only needed tuning shouldn't get buried at defaults.

**NT8 sweep stays serial for now (decided).** NT8 runs one backtest per instance,
so side-by-side instrument sweeps would require multiple NT8 instances (more
memory, more setup, more to break). Not worth it yet — the sweep is the cheapest
step and runs unattended. Revisit extra instances only if sweeps still hurt after
everything else is fast. MT5 sweeps still batch into one native job (free).

---

## Build order (speedups first, queue last)

### Step 1 — Native optimizer on ONE platform, ONE strategy (+ parity check)

**Goal:** prove the built-in optimizer works and its numbers match your current
pipeline, before anything depends on it.

- Change the **agent**, not the UI. NT8: `nt8_agent.py` / `nt8_backtest_runner.py`
  drives the Strategy Analyzer in **Optimize mode** over the parameter ranges,
  instead of looping single Run-mode backtests.
- The grid sweeps **only `[Category("Strategy Logic")]` params**. Foundational
  params stay injected from the active ruleset (Pass 1 rule) — the optimizer must
  not touch them.
- Parse the optimization result grid back into the Runs table.
- **Parity check (non-negotiable):** run a single combo through the native
  optimizer and confirm net P&L and trade count match the *same* combo run
  through the current single-run path. Optimize mode behaves differently from
  Run mode under pywinauto — this is the riskiest piece. If numbers don't match,
  the driver is wrong. Fix before trusting anything downstream.

**First target (locked): ORB on NT8** — furthest along (20 runs), real edge on
TRENDING days per M4. (To start on MT5 instead, swap this to MeanReversion on MT5
and begin at Step 4's MT5 wiring for the optimizer path.)

**Done when:** one native optimization run over ORB's param ranges returns a
ranked grid whose individual combos match single-run numbers.

---

### Step 2 — Re-score the shortlist with your real objective

**Goal:** the native optimizer ranks by a plain built-in metric (net profit /
Sharpe). Your real test is eval-pass-probability + regime-filtered Sharpe. Don't
let the proxy throw away a real winner.

- Take a **wide cut** from the native ranking — top ~25%, not top 1.
- Re-score that shortlist server-side with the existing M2/M4 objective
  (eval-pass probability, regime-filtered scoring).
- Auto-tier the re-scored results: Tier 1 / Tier 2 keep, Tier 3 discard.

**Why wide:** a combo that looks mediocre on profit but strong on eval-pass
survives to your scorer. A tight cut would silently drop it.

**Done when:** an optimization run yields auto-tiered winners using your real
objective, not the platform's proxy.

---

### Step 3 — Make that one run power stress testing too

**Goal:** stress testing stops being a separate slow phase. The Step 1 run feeds it.

- **Sensitivity → free read of the optimizer map.** Stop re-running ±10% / ±25%.
  The grid already contains the neighborhood around the winner. Compute
  robustness from the surface: winner inside a plateau of good results = robust;
  lonely spike with bad neighbors = overfit. No new backtests.
- **Walk-forward → native mode.** Switch from N orchestrated NT8 runs to NT8
  Strategy Analyzer's **Walk Forward** mode (and MT5's **Forward** setting in
  the `.ini`). One data load, all cores.
- **Monte Carlo → unchanged.** Confirm it consumes the winning combo's trade
  list. That's all.
- **"Overfit detection" is not a fourth method** — it's the *purpose* of
  sensitivity + walk-forward. No separate thing to build. (Optional later: one
  clean overfit score derived from the optimization grid, fast like MC.)

**Done when:** a single native optimization run produces the winner shortlist,
the sensitivity read, and the MC input — and the existing A–F grade is computed
from them with no extra backtests.

---

### Step 4 — Port the pattern to the second platform

**Goal:** same speedup on the other runner.

- M5 already wired `mt5_agent.py` for single backtests via `ini`+`set` files.
  Extend the `.ini` to **Optimization mode** (and **Forward** for walk-forward).
  Same idea, free.
- **Data caveat:** PU Prime demo serves only ~8 months of M5, ~2 years of M15.
  That caps walk-forward window count on low-timeframe forex. Dukascopy CSV
  import (your Pass 3) is the real fix later. Set expectations accordingly; don't
  over-trust low-TF forex walk-forward until Pass 3.

**Done when:** both NT8 and MT5 run the full fast optimize+stress pipeline.

---

### Step 5 — Telegram "done" notice from the command center

**Goal:** the "AI tells me when it's done" piece of the end goal.

- Wire the command center to the **existing** Telegram bot so a finished job
  pushes: *done — here are the suggested winners to fine-tune* (strategy, best
  combos, grade, tier).
- **Subsystem independence:** `algos/` and `command-center/` don't touch each
  other (locked principle). Cleanest path is the command center calling the
  bot's send path / a shared notify boundary, **not** importing `algos/` code.
  Decide this boundary explicitly before building.

**Done when:** finishing a job (single strategy for now) pings Telegram with the
graded shortlist.

---

### Step 6 — The queue (LAST)

**Goal:** unattended. You load strategies; the command center does the rest.

- Once one strategy runs the full fast pipeline by itself, the queue is just
  "do that for a list."
- Load N strategies → command center walks them one at a time (the SA-lock-of-1
  still serializes *across* strategies, which is fine — each job already uses all
  cores internally) → each produces a graded shortlist → Telegram fires when the
  **whole queue** is done.

**Done when:** you queue several strategies, walk away, and come back to a clean
list of tiered winners worth pushing into refinement.

---

## How this connects to the end goal

This milestone is the bridge to the AI loop:

**AI writes strategies → drops them in the queue → command center finds the best
combos and grades them → Telegram hands you the shortlist to fine-tune.**

Only after this is solid do you go hunting for more strategies. Building the
finder before the strategies is the right order — otherwise you drown in
strategies you can't test fast enough.

---

## Roadmap placement

Insert as the next milestone, **before M6 (stacking)**. Bump M6→M7, etc., or
name it inline (e.g. "M5.5 — Fast Optimize + Stress"). Stacking requires 2–3
B-grade strategies; this milestone is the machine that produces them.

---

## Decisions locked

- **First target:** ORB on NT8 (Step 1).
- **Order:** sweep first, then optimize. Sweep with a small coarse grid, not one
  default set.
- **NT8 sweeps stay serial** for now; extra NT8 instances are a later "only if it
  still hurts" call. MT5 sweeps batch natively.
- **Monte Carlo is untouched.** Sensitivity and walk-forward are reworked to
  reuse / use native modes per Step 3.

---

*End of game plan.*
