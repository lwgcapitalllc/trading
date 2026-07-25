# Shared-Risk Stacks — the work to make a stack a real simulation

**Scope:** Turn today's stack (a *screen* — two finished runs added together) into a real
simulation on ONE account with ONE risk budget the strategies compete for.
**Design + phases:** `PORTFOLIO_STACKING.md` and `PORTFOLIO_STACKING_BUILD_PLAN.md`. This document
is the concrete execution list for that plan's **Phase 2**, rewritten against the Stacks UI that
actually shipped (2026-07-25) rather than the separate "Portfolios" page the plan originally assumed.
**Status:** Not started. Written 2026-07-25.
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
`strategies/python/mpc_sos_fade/execution.py` already takes an injected `account` (default
`SoloAccount`). `strategies/python/mpc_bleg/` still sizes itself. Repeat the same edit.

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

## Verification

- B-LEG parity exit 0 with `SoloAccount` before anything else is built.
- Two-leg smoke run, deliberately tight cap: open risk never exceeds the cap, the contention log
  records the collisions, and the combined net is **lower** than the screen's. If shared mode ever
  beats the screen, the risk gate is not being enforced.
- A stack of legs that never overlap in time must produce a combined net equal to the screen's — the
  account was never the bottleneck, so there is nothing to take away.

## Not in scope

NT8 or MT5 legs (Python only — a foreign leg would need its fills fed to the same account live).
Splitting same-bar ties by weight (`request_fills` is ready for it, but it needs the strategy step
split into decide/commit). Using unrealized equity as the cap base.

## Rough size

About a week to real stacked runs with contention markers on screen.
