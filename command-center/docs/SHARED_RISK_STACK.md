# Shared-Risk Stacks — the work to make a stack a real simulation

**Scope:** Turn today's stack (a *screen* — two finished runs added together) into a real
simulation on ONE account with ONE risk budget the strategies compete for.
**Design + phases:** `PORTFOLIO_STACKING.md` and `PORTFOLIO_STACKING_BUILD_PLAN.md`. This document
is the concrete execution list for that plan's **Phase 2**, rewritten against the Stacks UI that
actually shipped (2026-07-25) rather than the separate "Portfolios" page the plan originally assumed.
**Status:** Written 2026-07-25. ✅ **COMPLETE 2026-08-09.** Items 1 and 2 landed in `backtest/`
(`run_stack`, driven by `backtest/tools/stack_run.py`); items 3–5 landed here the same day —
`stacks.mode` + the three account columns, `POST /stack` branching on the mode,
`GET /stacks/{id}/contention`, and the Stacks page's mode chip + shared-account panel. Item 6 is
kept: the screen is still the default and still says on screen that it is an upper bound.
⚠ **One deliverable from item 5 is DEFERRED and named rather than quietly dropped: the contention
MARKERS on the price chart.** Every measured run so far refuses nothing (see *What the first run
found* below), so a marker layer would be a generic mechanism nobody has ever exercised — this
repo's own recorded trap, and its first real user would be its first test. The events are served
and rendered as a per-leg table; add the markers when a run actually produces some.
⚠ **The seam moved from where this document assumed it would be**, and that is the one thing to
re-read before picking item 2 up: it lives in the strategy CONSTRUCTOR (`account=` / `leg=`, threaded
to `Execution`) plus `backtest.replay.build_strategy`, which REFUSES a strategy that cannot accept an
account rather than letting it fall back to its own uncapped `SoloAccount`. A `services/portfolio_runner.py`
in this app should CALL `run_stack`, never rebuild it. Full record: `backtest/CLAUDE.md` →
*The shared-account run*.
**Owner decision that started it:** two $10k legs were showing a $20k stack, which exposed that a
stack has never modelled a shared account at all.

---

## The problem in one paragraph

A stack today runs each strategy as its own standalone backtest and adds the results together. Each
strategy therefore sized every trade as if it owned the whole account. In reality they share one
account: if SOS Fade has 10% of the account at risk in an open trade, B-LEG cannot also take a full
position. If that open trade moves to breakeven, the risk it was holding is freed and B-LEG can
enter after all. If both want in on the same bar, they split what's available. None of that is
modelled, so the current stack **overstates** the result. It is a candidate screen, not a result.

---

## What already exists (do not rebuild)

`backtest/portfolio/` — built 2026-07-17, 41 tests green, offline and app-agnostic:

- `account.py` — `PortfolioAccount`: one balance; an open trade RESERVES risk measured to its
  **current** stop, so a stop moved to breakeven frees its room automatically. Cap = % of live
  balance. `request_fill` **scales the leg's own desired qty down** to whatever room is left
  (shrink-to-fit) and blocks below a floor; it never re-derives the qty, which is what keeps the
  strategy's standalone behaviour intact. Every shrink and block lands in a `contention` log.
  `SoloAccount` = no cap, always full size = today's standalone behaviour, and the parity anchor.
- `clock.py` — `merge_streams`: k-way merge of the legs' bars into one time-ordered stream.
- `simulator.py` — `simulate(legs, account)`: steps the legs on that clock, ordering
  **holders before flat legs** each tick so freed room is released before anyone tries to enter.
  Returns combined trades, per-leg trades, and the contention log.
- `combine.py` — the cheap screen. This is what the Stacks page effectively reproduces today.

**The gap is wiring, not logic.** Nothing in `command-center/` calls `simulate()`.

---

## The work

### 1. Give B-LEG the account seam
`strategies/python/sos_fade/execution.py` already takes an injected `account` (default
`SoloAccount`). `strategies/python/b_leg/` still sizes itself. Repeat the same edit.

- Constructor takes `account=None, leg: str = "strat"`; default to `SoloAccount(balance=…)`.
- Entries go through `account.request_fill(...)`; stop moves call `account.update_stop(...)`;
  exits call `account.on_close(...)`.
- **Gate:** B-LEG's own parity/regression suite still passes with the `SoloAccount`. If standalone
  behaviour moved at all, the seam is wrong. (Same gate SOS Fade passed: `compare_strategy.py`
  exit 0.)

Small — a day, most of it re-verification.

### 2. `services/portfolio_runner.py` — the real runner
The core of the work. One simulation, not N backtests.

- Build each leg's `EngineStack` + strategy exactly as `python_runner._replay` does today.
- Construct one `PortfolioAccount` from the stack's account size, risk cap %, and entry floor %.
- Hand every leg that same account and run `simulate()` over the merged clock.
- Persist: the combined result (standard four-key shape → `build_results`), each leg's own trades as
  a child run so the existing drill-in detail page still works, and the **contention log**.
- Reuse the existing tail: canonical Sharpe, ruleset evaluation against the COMBINED daily P&L,
  worthiness scoring.
- **Lock:** under the `python` scope (`ensure_platform_idle("python")`), like every python job.

### 3. Storage
Extend, don't duplicate. The `stacks` table already holds instrument, bar type/value, window and
costs. Add:

- `stacks`: `mode` (`'screen'` | `'shared'`), `account_size`, `risk_cap_pct`, `entry_floor_pct`.
- A place for the contention log and combined curve — `reports/lab/<stack_id>/`, same pattern as
  stress tests.
- Keep `stack_members` exactly as is. Ownership ≠ membership still holds.

**Migration:** every existing stack is `mode='screen'`. Nothing that exists today changes meaning.

### 4. API
Extend `routers/stacks.py`. `POST /stack` takes the mode and the account knobs; a shared-mode stack
runs through `portfolio_runner` instead of dispatching N python runs. Add
`GET /stacks/{id}/contention`. The existing `GET /stacks/{id}` and `/chart-spec` keep their shapes so
the page keeps working through the change.

### 5. Frontend
`StackConfigModal` gets a mode toggle and, in shared mode, the three account fields. `StackDetail`
keeps everything it has and adds:

- **Open risk vs cap** — a band under the equity chart showing how full the account was over time.
  This is the "am I actually using my capital" picture.
- **Contention markers on the price chart** — a marker where a strategy was shrunk or blocked, in
  that strategy's colour. Rides the existing per-trade `layer`/`layerColor` hand-off, so ChartPanel
  stays strategy-agnostic. The Strategies dropdown filters them like it filters trades.
- **A contention summary per strategy** — "B-LEG: blocked 14, shrunk 9, est. cost $X". This is the
  number that says whether the strategies actually fight each other or peacefully coexist.
- **A screen-vs-shared delta** — the honest headline: what the idealised screen promised versus what
  one account actually delivered.

### 6. Keep the screen
Do not delete the current behaviour. It is fast, reuses finished runs, and is the right first pass
for "are these two even worth stacking". Label it honestly in the UI as an upper bound.

---

## Order

1 → 2 → 3 → 4 → 5. Steps 1 and 2 are the real work; 3–5 are ordinary once the simulation runs.

## What the first run through the LAB found (2026-08-09)

Driven end to end through the running backend — `mode: "shared"`, XAUUSD M15, 2024, $10,000, cap
10% — two legs, 23,712 bars, four replays (the shared book plus one solo control each):

| | trades | R | closing |
|---|---|---|---|
| `sos_fade` shared | 17 | +20.04 | |
| `sos_fade` solo | 17 | +20.04 | $21,681.11 |
| `b_leg` shared | 16 | +6.31 | |
| `b_leg` solo | 16 | +6.31 | $15,188.43 |
| **shared account** | **33** | **+26.35** | **$36,805.85** |

✅ **The seam is NEUTRAL, which is the control this first run exists to establish**: every leg
posts the same R shared as solo, so with nothing refused the shared account changed the DOLLARS
(one balance compounding both legs) and moved no decision. Peak open risk touched exactly the
10.00% cap with 2 of 2 legs holding, and the contention log is empty — the same result the
full-history CLI run reports, and for the same reason: open risk is measured to each trade's
CURRENT stop, so a stop moved to breakeven releases its room before the other leg asks.

🔴 **AND IT REFUTES THIS DOCUMENT'S OWN VERIFICATION CRITERION, WHICH IS THE FINDING WORTH
KEEPING.** The bullet below used to read *"the combined net is **lower** than the screen's. If
shared mode ever beats the screen, the risk gate is not being enforced."* The measured shared
account closes **$36,806 against the screen's $26,870 — HIGHER — with the gate working perfectly
and nothing refused.**

The prediction assumed refusals are the only thing that differs between the two views. They are
not. **A screen gives each leg its own private balance, and a shared account COMPOUNDS both legs
onto one** — so B-LEG sizes its later trades off a balance A+ has already grown, which is more
money on the same trades rather than less risk. Two effects pull in opposite directions and the
compounding one is unbounded while the refusal one is capped by how often the budget is actually
full.

⚠ **So "shared beats the screen" is NOT evidence the cap is broken.** The check that says the gate
is enforced is the pair the runner already produces: `peak_open_risk_pct <= risk_cap_pct`, and every
difference in R tracing to a row in the contention log. Do not re-add the net-P&L version of this
test — it would have failed on a correct implementation, which is the worst kind of check to
write down.

## Verification

- B-LEG parity exit 0 with `SoloAccount` before anything else is built.
- Two-leg smoke run, deliberately tight cap: **open risk never exceeds the cap**, the contention
  log records the collisions, and every R difference between a leg's shared and solo book traces
  to a logged event. ⚠ **Compare R, never net dollars** — see the finding above.
- A stack of legs that never overlap in time must produce the same R shared as solo. **Its
  DOLLARS will differ, and that is correct** — one balance compounding both legs is the whole
  point of the shared view.

## Not in scope

NT8 or MT5 legs (Python only — a foreign leg would need its fills fed to the same account live).
Splitting same-bar ties by weight (`request_fills` is ready for it, but it needs the strategy step
split into decide/commit). Using unrealized equity as the cap base.

## Rough size

About a week to real stacked runs with contention markers on screen. **Actual: the simulation
landed 2026-08-09 and the lab wiring the same day; the markers are deferred (see Status).**
