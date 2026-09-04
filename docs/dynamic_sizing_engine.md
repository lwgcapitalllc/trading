# Dynamic Sizing & Risk Engine — Scope

**Status:** Phase 1 core BUILT & unit-tested 2026-06-21 (the pure Python engine + pipeline),
and `ORB.cs` reshaped to the rules (unit size, halts removed, emits the per-trade record) —
that `.cs` still needs a VPS compile + backtest to verify. The remaining VPS-coupled tail
(agents export the record, completion-path wiring, the per-run mode switch, the timeline UI)
is NOT done — it needs the live VPS and is specced under "Build progress" below.
**Owner context:** Aaron. Decisions locked 2026-06-21; engine core landed the same day.

---

## The problem (plain English)

The backtest picks trade size from a simple risk %. It ignores the prop firm's rules
about how many contracts you're allowed and when. So the size is wrong — and because
**consistency** and the **pass/fail date** are both built from size, they're wrong too.
All three are the same number underneath.

What's true today (verified in code):
- The strategy sizes each trade off risk % and grows with equity (`ORB.cs` `CalcContracts`
  uses `AccountSize + cumulativePnl`).
- The firm's **contract ladder** (`Ruleset.max_contracts` JSON in
  `command-center/backend/models.py`) is **never enforced during the run**. It's only
  checked afterward, for display, and never moves the verdict
  (`evaluator.compute_contract_cap_status`, marked "INFORMATIONAL ONLY").
- The consistency rule and PASS/WARN/DISCARD verdict are computed post-run in
  `command-center/backend/services/evaluator.py`, but on trade sizes that ignore the ladder.

Net: the grader's math is right; the sizes it runs on are not the firm's sizes. So the
verdict, consistency %, and time-to-pass are not yet trustworthy.

---

## Governing principle (non-negotiable)

**NO STRATEGY KNOWS HOW TO MANAGE RISK.** A strategy's only job is to identify a setup and
signal that it wants to enter. It never decides size, never enforces account rules.

- **Gates / filters** decide *whether* the trade is allowed at all.
- **The sizing engine** then takes every factor into account — balance, drawdown, contract
  ladder, consistency — and says "okay, you can take it, but only at this contract / lot
  size" so we never blow accounts or violate a ruleset.

Everything below serves this. If a design choice puts any risk-management decision back
inside a strategy, it's wrong.

---

## Decisions locked (2026-06-21)

1. **Where the logic lives → one Python engine.** The strategy emits a stream of trades
   at unit size; one shared engine decides real size per trade and grades the run. Written
   once, works for NinjaTrader and MT5. (Rejected: duplicating dynamic sizing inside every
   `.cs` and `.mq5`.)
2. **Scope of first build → get one ruleset right first.** Make sizing + consistency +
   pass/fail timeline fully accurate for a single eval ruleset. Eval→funded chaining is a
   follow-up (see Phase 2).
3. This plan is saved (this doc + a memory pointer).

---

## Target architecture

```
Strategy (.cs / .mq5)         →  emits raw trade stream (unit size, NO account halts)
  signal + stop/target + time     entry time/price, exit price, direction,
                                   stop distance (risk per contract), exit reason

Python sizing & risk engine   →  walks the stream in time order, for each trade:
                                   sizes it, applies halts, updates account state,
                                   detects breaches  →  produces verdict + timeline

Evaluator / API               →  reads engine output, returns verdict + day-by-day data
```

The engine and the grade become **one pass**: the dynamic-sizing simulation *is* the
evaluation. Single source of truth for sizing, consistency, drawdown, and verdict.

### The cost (deliberate refactor)

Today `ORB.cs` (and peers) run their own account-governance halts — daily-loss halt,
profit-target stop, consecutive-loss halt, profit lock-in. These are computed on the
strategy's own P&L, which is the **wrong size** once the engine sizes trades. So they
**move out of the strategy files and into the engine.**

After the refactor the strategy keeps only:
- entry signal
- stop / target proposal
- time rules (entry cutoff, force-flat)

The strategy is run with account halts **off**, so it emits the *full* signal stream;
the engine then applies halts at the correct size. This is also what the LWG framework
wants: strategy proposes, the governance layer sizes and vetoes ("most restrictive wins").

---

## The sizing waterfall (per trade, in order)

Each step can only **shrink** the size, never grow it. Final = smallest of all.

1. **Base size from the account's goal** (the risk budget; see "Sizing is set by the
   engine" in `LWG_Strategy_Framework.md` for the full rationale):
   - **Bullet (eval, pass fast):** the max size the scaling table allows, on A/SOS Fade setups
     only, guarded so one stop-out can't breach the floor.
   - **Funded / live (consistency):** a fixed fraction of the room left to the drawdown
     floor — **room ÷ 7** — recomputed every trade. Contracts = budget / (stop distance ×
     point value). NOT a % of balance: size off the room, not the balance.
2. **Drawdown clamp.** Never risk more than the distance to the trailing max-loss floor.
   As balance nears the floor, size shrinks. ("Size down when near failing.")
3. **Contract ladder clamp.** Cap at max contracts for the current balance band and phase
   (eval = usually fixed cap; funded = ladder that unlocks with balance). This is the
   scaling rule, finally enforced.
4. **Consistency throttle.** If a consistency rule is active, cap size so no single day's
   profit can exceed the allowed share of the target. After a big day, size down on purpose
   to stay consistent.
5. **Most restrictive wins.** Final = min of the above, ≥ 0. If 0, the trade is skipped
   (couldn't be taken legally).

Then walk equity forward: apply trade at real size, update balance / peak / trailing floor /
daily P&L; apply daily-loss halt and profit-target stop; check breaches (trailing max-loss,
consecutive bad days, drawdown from peak). A halt drops the rest of that day's trades from
the stream.

---

## What the user gets to see (the goal)

- How long until passed, or the exact day **and reason** failed.
- Consistency share day by day, and the **first day it broke** (if ever).
- Drawdown safety margin over time.
- Contract count on every trade, so sizing-up and sizing-down is visible.

---

## UI fix that rides along

When a prop ruleset is attached, firm-controlled fields (risk %, flatten time, scaling,
etc.) show as **"set at run time by ruleset"** and are read-only — not editable inputs.
Editable-but-ignored boxes are misleading. Small frontend change, pairs naturally here.

---

## Open questions — resolved at build start (2026-06-21)

1. **Trade export — does it carry per-trade stop distance? → NO, neither runner does.**
   The stop is internal to each strategy and absent from both exports. NT8's native
   Trades CSV *does* carry entry/exit price + entry time (the backend parser just drops
   them, `parse_trades_csv`); MT5's HTML report collapses entry/exit into one price cell
   and has no stop. So the contract is NOT a one-liner — every strategy must emit a
   dedicated per-trade record (incl. stop distance), and both VPS agents must export it.
   This is the bulk of the remaining VPS-coupled work.
2. **No strategy exit depends on position size — CONFIRMED** for ORB (price-based
   stops/targets via `SetStopLoss`/`SetProfitTarget`, one entry per direction/day;
   `CalcContracts` only sets size). Re-sizing in post-sim is valid. Would break only if
   intrabar margin/liquidation is ever modeled — not today. (VWAP_MR and Momentum, the
   other two NT8 strategies checked here, were deleted 2026-06-21.)
3. **Per-trade record schema LOCKED** as `sizing_engine.RawTrade`: index, entry_time,
   exit_time, direction(±1), entry_price, exit_price, stop_distance (risk per contract,
   price points), point_value, commission_per_side, exit_reason. `RawTrade.from_record`
   reads this off a dict, so it is the literal runner→engine contract.
4. Phase 2 trigger: eval→funded chaining (below). `ContractLadder` already parses both
   funded scaling shapes seen in the DB (`bidirectional_band`, `cumulative_ratchet`).

---

## Build progress (2026-06-21)

**Done — the local, fully-testable core (no live-system risk):**
- `command-center/backend/services/sizing_engine.py` — the pure engine. `RawTrade`
  (the locked contract), `ContractLadder` (eval fixed cap + both funded scaling shapes),
  `EngineRuleset` (ruleset view), the 5-step waterfall (`size_trade`) and the equity walk
  (`run_engine`) with daily-loss + profit-target halts and trailing-floor breach
  detection. It reuses `trailing_drawdown.compute_trailing_mll`'s floor math and emits a
  size-correct `daily_pnl` designed to feed the EXISTING `evaluator.evaluate_run`
  unchanged — the simulation IS the evaluation, with no second grader. No DB, no network,
  no clock.
- `command-center/backend/tests/test_sizing_engine.py` — 14 unit tests, all green:
  each waterfall clamp in isolation, both ladder scaling shapes, halts dropping the rest
  of a day, stop-overrun floor breach, time-ordering, output shape.
- `command-center/backend/services/decision_log.py` + `tests/test_decision_log.py`
  (7 tests) — the ONE reusable, extensible audit log for the whole system. One record
  per signal (taken or not): the idea + setup score, every gate's verdict in order (which
  one shut it down — or that all passed), the sizing decision (size + what bound it, or why
  skipped), and the full life of a taken trade (entry, exit, exit reason, P&L). Gates are an
  ordered list, so a new gate (news, spread, score, open-risk) just calls `decision.gate(…)`
  — no schema change. Append-only JSONL, pure stdlib, identical in backtest and live. Wired
  into the engine when the engine is reworked (below).
- UI: `RunBacktestModal` foundational block relabelled "Firm-controlled — set at run time
  by the ruleset, read-only" (the foundational fields were already read-only chips, so
  this is the wording fix the doc asked for, not a behaviour change).

**Sizing model LOCKED (2026-06-21) — supersedes the placeholder in code.** Risk per trade
is NOT a % of balance and NOT `daily loss limit ÷ trade count` (both ideas are dead; there
is no fixed trade count). It is goal-driven: **bullet** = max scaling size on A/SOS Fade setups
(one loss can't breach); **funded/live** = **room ÷ 7** of the distance to the drawdown
floor, recomputed every trade. Gates (time cutoff, daily loss/profit limit, consistency
limit, the Section-3 filters) decide *whether* a trade is taken; the engine decides *how
big*. The stop comes from the strategy.

**Minimum size / round-up (locked 2026-06-21).** When the ideal size rounds below the
smallest tradeable unit (1 micro on futures), round **up to 1** ONLY if 1 unit breaks no
HARD cap — it fits the room (one loss can't breach) and the firm's contract ladder allows
≥ 1. If a SOFT target (room÷7 budget or the consistency throttle) is what shrank it, the
minimum is allowed (so a small account still trades, logged `bound_by: min_size`); if a
HARD cap did (no room for even 1 micro, or the ladder), the trade is **skipped** — never
rounded up into a breach. (Forex variant — round to the broker's lot step/min, not an
integer micro — is a later refinement; ORB is futures-micro integers today.)

Full rationale and the streak math live in
`LWG_Strategy_Framework.md` ("Sizing is set by the engine"). **IMPLEMENTED in the engine
2026-06-21:** `run_engine(..., mode="bullet"|"consistent")` does goal-driven base sizing
(bullet = max the rules allow with the one-loss-can't-breach guard; consistent = room ÷ 7),
the open-trade risk reservation, the daily-halt / insufficient-room / account-breached
gates, and emits the decision log per signal. 25 unit tests green. What remains is feeding
it real ORB trades — the VPS tail below.

**Open-trade risk is reserved (locked 2026-06-21).** Available room for a NEW trade =
room to the floor − the risk still on the table from positions already open. So if only a
little room is left and a trade is running, the next signal is **blocked** (a gate:
`insufficient_room`) — the open trade's possible loss is already claiming the room. The
exception: once an open trade's stop is at **breakeven** it can no longer lose, so it
reserves nothing and the room frees up — the strategy is free to take the next signal.
This makes the engine **stateful over open positions**, not just a closed-trade re-sizer.
Caveat — knowing a trade is "already at breakeven" at the instant of the next signal is
trivial **live** (real-time stop state) but in **backtest** needs the strategy to emit a
"breakeven reached at T" event (part of the trade-management breakeven move, framework
Section 3). Until that exists, backtest reserves an open trade's **full** risk until it
closes (conservative). Build order: breakeven move + its log event, then the open-risk
reservation can honor the "free will if in profit" case in backtest too.

**`ORB.cs` reshaped (2026-06-21) — code done, needs VPS verify.** ORB now trades **unit
size (1 contract)**; its self-policing halts are **removed** (daily-loss halt, profit-target
stop, profit lock-in, consecutive-loss halt all move to the engine); it keeps only the entry
signal, the stop, the target, and the time rules (force-flat, entry hours, allowed days). It
emits the per-trade record — the `RawTrade` contract columns — to `engine_trades.csv`
(`strategy_results.csv` still written, now a unit-size reference only). `runner_dispatch.
build_foundational_params` was trimmed to inject only the surviving NinjaScriptProperties
(`CommissionPerSide`, `ForceFlatTimeET`, `EarliestEntryTimeET`, `LatestEntryTimeET`,
`DaysOfWeekAllowed`). Local backend suite still green; **the `.cs` itself must be compiled +
backtested on the VPS** (can't be validated locally, and `test_integration.py` is forbidden
because it fires real NT8 jobs). `sizing_pipeline.run_sizing_engine` already locks the
export→engine→files contract end to end on synthetic data.

**NOT done — the remaining VPS-coupled tail:**
1. **Both VPS agents export the record file** — NT8 `nt8_agent.py` clears `engine_trades.csv`
   before each run and ships it after; MT5 `mt5_agent.py` gets the same once the two MT5
   strategies (LondonBreakout, MeanReversion) are reshaped the same way.
2. **Wire `run_sizing_engine` into the completion path** (`backtest_runner._handle_complete`):
   read the exported records → `run_sizing_engine` → feed its `daily_pnl` to
   `evaluator.evaluate_run`. The pipeline already persists `decisions.jsonl` + timeline +
   daily P&L. **Glue landed 2026-06-21:** `sizing_pipeline.engine_result_to_kpis` rebuilds the
   canonical KPI dict (net_pnl, profit_factor, win_rate, max_drawdown, trade_count + avg
   win/loss) from the SIZED run, because the engine emits daily P&L but no KPI summary and both
   `evaluate_run` (net_pnl) and `worthiness.score_run_after_evals` (PF/DD/trade_count) need one.
   4 unit tests green. The remaining wiring is the `_handle_complete` edit itself — read
   `result["engine_trades"]`, size **per ruleset** (each firm's ladder/floor differ), grade
   each ruleset against its own sized run; the run's headline kpis/daily_pnl = the primary
   (first) ruleset's. Open decision: whether multi-firm runs store one sized timeline (primary)
   or one per ruleset.
3. **Per-run bullet/consistent switch** — field on `BacktestRunRequest` + the run row + the UI.
4. **UI** for the day-by-day timeline (contracts per trade, floor margin, consistency
   share, day/reason passed-or-failed).

---

## Phasing

- **Phase 1 (this build):** Python engine + the waterfall + halts moved out of strategies,
  graded accurately against a **single eval ruleset**. Plus the read-only UI fix.
- **Phase 2 (later):** treat a run as a sequence — trade under eval rules until target hit
  (the pass), then switch the active ruleset to the funded variant and continue (ladder
  changes, consistency often turns off). Ruleset model already distinguishes
  `prop_eval` / `prop_funded`.

---

## Key files (from code exploration)

- `command-center/backend/models.py` — `Ruleset` (~324–365), `EvaluationDetail` (~491–518)
- `command-center/backend/services/evaluator.py` — verdict + consistency (~212–367),
  `compute_contract_cap_status` (~20–49, informational only today)
- `command-center/backend/services/runner_dispatch.py` — `inject_foundational` /
  `build_foundational_params` (~85–121)
- `command-center/backend/routers/backtests.py` — injection at run creation (~225–235)
- `command-center/backend/services/lab_db.py` — `backtest_runs` + `evaluations` schemas
- `strategies/ninjatrader/ORB.cs` — example strategy whose halts move to the engine
