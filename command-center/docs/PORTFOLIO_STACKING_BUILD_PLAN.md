# Portfolio Stacking — build plan

**Scope:** The shared-account portfolio — one balance, one live risk budget the legs compete for.
Python legs first (all the MPC strategies are Python). Design: `PORTFOLIO_STACKING.md`.
**Status:** Phase 0 + Phase 1 built 2026-07-17 (`backtest/portfolio/`: combine, account, clock,
simulator — 41 new tests + strategy parity exit 0). Phases 2–4 (lab, analytics, forward) to do.

**Locked policies (2026-07-17):** shrink-to-fit with a floor · split-by-weight on same-time ties ·
cap = % of live (realized) balance · hard account halt from the ruleset.

---

## The shape of the work

The hard part is a **live cross-leg risk manager**, not a report merge. Legs can't run
independently and be combined afterward, because every leg's size depends on the shared balance and
every leg's *permission* to enter depends on the risk other legs have open right now. So the core is
an interleaved simulator with a central account. Build that first and prove it in isolation; the lab
wiring and UI are ordinary after that.

---

## Phase 0 — the combine screen (cheap, first)  ✅ core built 2026-07-17

**Built:** `backtest/portfolio/combine.py` + `combine_runs`/`Leg`/`leg_from_result`, 12 tests green
(`backtest/tests/test_combine.py`). Still to do: the thin lab "Combine" panel (2D-style surface).


A fast diversification check that reuses runs you already have. **No account, no contention** — each
leg is a finished standalone run; we just add their results together. This is an **idealized upper
bound**, not the demo: it assumes every leg trades a full account and never gets blocked. Use it to
decide *which* strategies are worth stacking; use Phase 1 for what the stack actually does.

- **Input:** N completed single-strategy lab runs (each already has `daily_pnl` stored).
- **Combine:** sum the legs' `daily_pnl` by UTC day → one combined daily series → cumulative combined
  equity curve. (Daily buckets, so no `exit_ms` merge needed — the curve is day-resolution.)
- **Report:** correlation matrix of the legs' daily returns; diversification drawdown (combined max DD
  vs Σ leg max DDs); per-leg contribution to combined net. All arithmetic over the stored per-run data.
- **Code:** `backtest/portfolio/combine.py` (pure, offline-testable) — `combine_runs(list_of_run_results)`
  → `{combined_equity_curve, combined_daily_pnl, correlation, diversification_dd, per_leg}`.
- **Lab surface (thin):** a "Combine" panel that takes a set of completed runs and shows the combined
  curve + correlation + diversification numbers. No new runner — it reads existing run rows.
- **Label it plainly in the UI:** "idealized — ignores shared-risk contention; see Portfolio run for
  the real account." So it's never mistaken for the demo result.
**Tests** (`backtest/tests/test_combine.py`): two runs with offsetting daily P&L → combined DD < Σ DDs;
two identical runs → correlation ≈ 1 and combined DD ≈ 2× one leg; combined net == Σ leg nets.

---

## Phase 1 — the shared-account simulator (`backtest/portfolio/`)

Pure Python, offline-testable, importable without the FastAPI app — same discipline as `output.py`.

### 1A. `account.py` — `PortfolioAccount` + `SoloAccount`  ✅ built 2026-07-17 (13 tests green)
The broker. Owns the balance and the risk budget.
- **State:** balance (realized), open positions `{leg, qty, entry, current_stop, dir, point_value}`.
- **`reserved()`** — Σ `qty × point_value × max(0, dir·(entry − current_stop))` over open positions,
  in account dollars. Recomputed from live stops, so it falls to 0 at breakeven.
- **`cap()`** — `risk_pct × balance` (live realized balance).
- **`request_fill(leg, dir, stop_distance, risk_pct) -> qty`** — the gate at §3.4:
  `room = cap − reserved`; `desired = risk_pct × balance`; `granted = min(desired, room)`; block if
  `granted < floor`, else `qty = granted / (point_value × stop_distance)`.
- **`request_fills(list) -> {leg: qty}`** — the same-bar batch: **split `room` by `desired`**, then
  floor-check each. (One split, no re-split in v1.)
- **`update_stop(leg, current_stop, qty)`**, **`on_close(leg, pnl)`** — keep reservations and balance
  current.
- **`halt` check** — daily-loss / trailing max-loss on the combined balance stops all legs.
- **`SoloAccount`** — one leg, `cap = ∞`, sizes off its own balance: byte-identical to today, for
  standalone runs and the parity harness.
**Tests** (`backtest/tests/test_account.py`): reservation drops to 0 at breakeven; cap tracks balance;
room = cap − reserved; two same-bar requests over a tight budget split by weight; a sub-floor grant
blocks; a full close frees the whole reservation.

### 1B. `clock.py` — one merged timeline  ✅ built 2026-07-17 (7 tests green)
- Merge N legs' bar streams into one event stream ordered by UTC timestamp.
- At each timestamp yield **position-updates before entries**, so freed room is released first.
- Handle mixed timeframes/instruments (a 5m leg steps 3× per 15m bar).
**Tests:** interleave two hand-built streams; assert order and the release-before-entry rule.

### 1C. The strategy seam  ✅ built 2026-07-17 — **parity exit 0**, 40 bot tests green
Injected `account` (default `SoloAccount`) into `execution.py`: sizing reads `account.balance`,
the fill gate calls `account.request_fill` (scales the bot's own qty), partials/costs `book_pnl`,
close frees the reservation, each bar reports the live stop. `compare_strategy.py` exit 0 on the
20,076-bar export — standalone behaviour unchanged.

Route sizing, entry-permission, and balance through an injected account.
- **Files:** `strategies/python/mpc_sos_fade/execution.py` (the three call sites: where it sizes →
  `account.request_fill`; where it books P&L → `account.on_close`; each bar → `account.update_stop`),
  and its config/driver to accept an `account`.
- **Default = `SoloAccount`**, so nothing changes for a standalone run.
- **Gate at FILL, not placement** — a resting limit reserves nothing until it fills.
- **Parity gate:** `tools/compare_strategy.py` must stay **exit 0** with the `SoloAccount`. This is the
  proof the refactor didn't move standalone behaviour. Run `/audit-strategy` after.
**This is the highest-risk step — do it second (right after the account exists) and re-prove parity
before going further.**

### 1D. `simulator.py` — drive the legs through the account  ✅ built 2026-07-17 (4 tests green)
`simulate(legs, account)` runs the legs on the merged clock, orders holders-before-flat legs
(release-before-entry), and returns combined trades + per-leg trades + the contention log.
**v1 limit:** two flat legs filling on the exact same tick are first-come, not split-by-weight
(needs the strategy step split into decide/commit — the account's `request_fills` batch is ready
for it). Real leg adapter (EngineStack + strategy) is Phase 2.
- Build each leg's `EngineStack` + strategy (as `python_runner._replay` does today), hand them all the
  one `PortfolioAccount`, and step them on the `clock`.
- Collect: the combined trade stream, each leg's own trades, and the **contention log** (each entry
  the gate shrank or blocked — leg, time, requested vs granted risk, and the trade's eventual P&L so
  the cost of the collision is visible).
- Combined result via `build_results(combined_trades, initial_capital=account_size)` → the same
  four-key shape the lab already consumes.
**Tests:** two legs that never overlap → combined net == sum of their nets (the account was never the
bottleneck); two legs forced to overlap on a tight cap → the second is shrunk/blocked and the
contention log records it.

---

## Phase 2 — lab integration (`command-center/`)

### 2A. Storage — `services/lab_db.py`
Tables `portfolios`, `portfolio_legs`, `portfolio_runs`, and `portfolio_run_id` on `backtest_runs`
(child leg-runs, hidden from `list_runs()` like `stress_test_id`). Heavy output (combined curve,
daily P&L, contention log, analytics) → `reports/lab/<portfolio_run_id>/`; the row stores the dir.
Columns per `PORTFOLIO_STACKING.md` §... plus `risk_cap_pct`, `entry_floor_pct`, `account_size`,
`capital_base` on `portfolios`.

### 2B. Runner — `services/portfolio_runner.py`
- Load each leg's strategy + params + instrument + timeframe, build the `PortfolioAccount` from the
  portfolio's cap/floor/account-size, and run **one** `simulator` over all legs (not N separate
  backtests — the account is shared, so it's one simulation).
- Persist the combined result + contention log; write each leg's own trades as a child
  `backtest_run` (`runner="python"`, `portfolio_run_id` set) so each leg keeps a drill-in detail page.
- Stamp canonical Sharpe, evaluate the **combined** daily P&L against the portfolio's rulesets, score
  worthiness — all reused (combined result is the standard four-key shape).
- **Lock:** gate under the `python` scope (`ensure_platform_idle("python")`).

### 2C. API — `routers/portfolios.py`
CRUD + `POST /portfolios/{id}/run` (202, background the runner) + `GET /portfolios/runs/{id}`.
Register in `main.py`. Delete cascades child leg-runs + report dirs (mirror the `delete_run` cascade).

### 2D. Frontend — Portfolios page
`pages/Portfolios.tsx`, `usePortfolios`, a `NavItem` in `Sidebar.tsx`, types mirrored, fetch only in
`api/client.ts`.
- **Composer** — add legs (strategy + instrument + timeframe + params via `ParamEditor` + requested
  risk %), set account size, risk cap %, entry floor, and rulesets.
- **Run detail** — combined equity curve (TradingView panel, coloured by leg), the account PASS/DISCARD
  per ruleset, the **open-risk-vs-cap chart**, and the **contention log**.

---

## Phase 3 — analytics, portfolio optimize, stress

- **Analytics** (`backtest/portfolio/analytics.py`): per-leg contribution, daily-return correlation
  matrix, diversification drawdown (account max DD vs Σ leg max DDs).
- **Portfolio optimize:** grid/search over the account knobs (cap %, per-leg risk %, legs on/off, tie
  order) scored by an account objective — reuse `expand_grid` + `objectives.py`.
- **Stress:** feed the combined trades to `stress_tester`, but resample by **day-block** to preserve
  cross-leg co-movement.

## Phase 4 — forward test
Deploy each leg as a bot on one demo account; run the same aggregator over the live account's fills.
Needs the live-bot deploy path (currently empty) and each leg backtest-proven first.

---

## Out of scope until asked
NT8/MT5 legs (Python-only for now — an NT8 leg would need its fills fed to the same account live, a
bigger seam); tie re-split; unrealized-equity cap base.

---

## Verification (end of Phase 1, before any UI)

1. `test_account.py`, `test_clock.py`, `test_simulator.py` green.
2. **Parity:** `compare_strategy.py` exit 0 with `SoloAccount` — the standalone bot is unchanged.
3. Two-leg smoke run: same strategy on 15m and 5m, one $20k account, tight 5% cap. Confirm the
   contention log shows the collisions, open risk never exceeds the cap, and the combined curve is one
   account. Then wire the lab.
