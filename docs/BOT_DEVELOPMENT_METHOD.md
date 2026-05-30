# Bot Development Method — The S.Y.S.T.E.M. Approach

> **For Claude Code:** This file defines the standard, non-negotiable process for
> creating, validating, and deploying any trading bot in this repository.
> Every bot must move through these six steps **in order**. Do not skip steps,
> jump straight to live deployment, or merge later steps into earlier ones.
> If a bot fails a step, it does not advance — it is fixed or discarded.

This is a futures/NinjaTrader adaptation of the S.Y.S.T.E.M. Method (NexGenAlgo).
The framework is standard systematic-trading practice; the step names are kept
for a shared vocabulary. Tooling here is **NinjaScript / C# / CME futures**, not
the no-code MetaTrader EAs the original framework assumes.

---

## The Six Steps

### S — Strategy Idea
Define the edge as clear, unambiguous, rule-based logic. Before any code exists,
the strategy must specify exactly:
- **Entry** — what conditions trigger a trade
- **Exit** — profit target and stop logic
- **Sizing** — how position size is calculated (must respect venue risk rules)

If it cannot be written as rules a machine can follow with no discretion, it is
not ready. Output of this step: a complete written spec.

### Y — Yield Logic (Build)
Translate the spec into an executable bot. In this repo that means Claude Code
writing the actual **NinjaScript (C#) strategy** — entry/exit conditions,
filters, risk parameters, and the prop-firm constraints wired in.
Keep it simple: complexity is a liability, not an edge.
Output: a compiling, runnable bot.

### S — Stress Test (Backtest)
Validate the built bot against **years of real historical data** with realistic
spread, slippage, and commission models. Run across varied market conditions
(trending and ranging). This step happens off-VPS, on a normal machine — it is
research, not live running. Its purpose is to **filter out bad strategies** and
confirm a genuine edge exists.
Output: honest performance numbers (net P&L, drawdown, profit factor, trades).

### T — Threshold Check (Robustness / "Monkey Test")
Deliberately try to break the system. The core test is **parameter and
condition robustness**: shift parameters off their optimal values, change
timeframes, change the instrument, and confirm the edge **survives across a
range of inputs** — not just one curve-fit sweet spot. If it only works at
exactly one parameter set, it is curve-fitted and must be discarded.
- Primary tools: walk-forward analysis, parameter-sensitivity sweeps.
- Optional add-on: **Monte Carlo** on trade sequence (shuffle trade order to
  stress the equity-curve and drawdown distribution). Useful, but it is a
  supplement here — the defining test of this step is parameter robustness.
Output: confirmation the edge is robust, or a discard decision.

### E — Evaluate (Demo)
Forward-test the survivor on a **demo account for 30–60 days minimum**, in live
conditions, with no real capital at risk. Demo reveals what backtests hide:
real slippage, spread expansion, missed fills, execution delays. Log every
trade and compare live execution against backtest expectations. Significant
deviation means something is wrong — diagnose before going live.
Output: a bot proven on the actual venue's real conditions.

### M — Master (Deploy)
Go live with discipline. Deployment is operations, not a switch-flip:
conservative position sizing, enforced daily/weekly loss limits, system-health
monitoring, and no manual intervention during normal drawdowns.
The system trades; the operator manages the system.

---

## Hard Rules

1. **Order is fixed.** S → Y → S → T → E → M. Each step builds on the last;
   skipping one leaves a blind spot that costs money live.
2. **A failed step is a stop.** A bot that fails the backtest never reaches the
   demo. A bot that fails the Threshold Check never reaches deployment.
   Filtering is the point — let it work.
3. **Backtest in parallel, build/deploy sequentially.** Testing several strategy
   *ideas* at once is cheap and encouraged. Building and demo-ing production
   bots is done one at a time to avoid half-finished work and tangled bugs.
4. **Venue-first.** Every bot is built and tuned for one specific venue's
   instruments, contract specs, and rules. Bots are not portable between venues
   without re-validation from the Stress Test step onward.
5. **Risk rules are a design input, not an afterthought.** Prop-firm daily-loss
   and drawdown limits are hard constraints baked into position sizing from
   step Y.

---

## Step-to-Verb Quick Reference

| Step | Name            | One-line meaning                                  |
|------|-----------------|---------------------------------------------------|
| S    | Strategy Idea   | Decide the rules (entry, exit, sizing)            |
| Y    | Yield Logic     | Build the bot — write the NinjaScript/C# code     |
| S    | Stress Test     | Backtest on years of real historical data         |
| T    | Threshold Check | Perturb parameters/conditions; catch curve-fitting|
| E    | Evaluate        | Demo forward-test, 30–60 days, live conditions    |
| M    | Master          | Deploy with conservative sizing and loss limits   |
