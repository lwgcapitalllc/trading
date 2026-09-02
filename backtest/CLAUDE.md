# CLAUDE.md — backtest/ (the Python backtest runner)

**Purpose:** Standing instructions for `backtest/`, the LWG Python bar-replay backtest runner.
**Scope:** This package only — the data layer, replay loop, fill/cost model, output adapter, and
local optimizer. It does NOT cover the engines it replays (`engines/`), the strategies it runs
(`strategies/python/`), or the lab that consumes it (`command-center/`).
**Status:** **Deliverable A COMPLETE 2026-07-16.** A0 (data layer) + A1 (replay loop) landed
2026-07-15; A2 (fill & cost model), A3 (output adapter), the lab's `runner="python"` adapter, and A4
(local optimizer) all landed 2026-07-16. See `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
**Last reviewed:** 2026-08-12 — ⚠ **The dated build narrative that used to sit here moved VERBATIM to `backtest/docs/BACKTEST_BUILD_NOTES.md`. Nothing was deleted.** It was 63 KB in **three** paragraphs, one of them **37,463 bytes on a single line** — unreadable by a person, and loaded in full every time anyone opened this package. The rules it taught are in `## Rules` below and each names its entry in the notes. **The standing lesson is about WHERE a lesson lives: a rule buried in a 38,000-byte paragraph is not findable, so in practice it is not a rule — it is only evidence that somebody once knew.**

---

## What this is

Strategy- and instrument-agnostic backtest infrastructure — the same character as `engines/`: a
shared library, not owned by any one app. It pulls broker data, replays it bar-by-bar through the
canonical `engines/`, simulates fills against real ticks, and emits the
`{equity_curve, daily_pnl, kpis, engine_trades}` shape the command-center lab already consumes
(registered there as `runner="python"`, next to `"mt5"`/`"ninjatrader"`).

**Why top-level, not inside command-center:** it must be importable standalone — CLI backtests, the
`/audit-strategy` parity harness, CI — without dragging in the FastAPI app. The lab consumes it
through a thin `runner="python"` adapter in `runner_dispatch`, the same thin-shim pattern engines use.

## Build pieces (from the plan)

- **A0 — Data layer** *(done)*. `backtest/data/`. Pull broker bars directly at the base timeframe,
  cache to disk, resample UP to the target timeframe. Ticks (2yr deep) back the fill model.
- **A1 — Replay loop** *(done)*. `backtest/replay/`. `iter_bars(df)` turns the data-layer frame into
  `ReplayBar`s (0-based index + epoch-ms UTC time); `EngineStack.step(bar)` drives the canonical
  engines in Pine order (structure → order blocks → fib{structure/sniper/macro/internal} → FVG →
  RSI-divergence → liquidity → sessions) and returns a `BarState`; `run(df, warmup=…)` is the
  convenience iterator.
  **`order_blocks` was wired in 2026-08-08 and is OPT-IN, default OFF** (`EngineConfig.order_blocks`).
  The engine has been canonical and Pine-parity green since 2026-07-31, but until now its only
  consumers were the command-center price chart (`services/ob_overlays.py`) and its own harness — so
  no STRATEGY could see a block, which is what blocked the course's POI-based session plays
  (`education/smc/SMC_KNOWLEDGE_BASE.md` → plays 1 and 3). ⚠ **Off by default because the cost is
  real and was MEASURED, not assumed: +17.7% on a replay** (5,760 bars, best of 3 — 328.5 ms → 386.7
  ms), paid per sweep combo, for output no current strategy reads. ⚠ **`BarState.order_blocks` is
  `None` when the flag is off and an `OrderBlockEvents` when it is on — `None` means the engine never
  ran, an events object with empty lists means it ran and found nothing.** Collapsing those is the
  "no" vs "cannot ask" defect this repo has met on the live bot's terminal probe, the optimizer's
  sensitivity score and the news calendar; here the empty object would read as *no blocks* and a
  strategy would take no trades while looking perfectly healthy. ⚠ **There are deliberately NO OB
  tuning fields on `EngineConfig`** — every OB constant is HARDCODED in `mpc_assistant.pine` rather
  than exposed as an `input.*`, so a config field could never be carried by an export column and no
  parity gate could check it (the `BosConfig` rule, 2026-08-07). The engine's defaults ARE the Pine's
  constants. If mpc re-exposes one as an input, add the field then, with its export column.
  ⚠ **The position in `step()` is the Pine's** (`extendOBs` then the push/turn creation sites, right
  after `st.process`) and is currently behaviour-NEUTRAL — the engine is standalone and nothing
  downstream reads it — so do not "tidy" it: the day something reads a block, the order is already
  right. Pinned by `tests/test_replay_order_blocks.py` (8 tests, all 8 watched RED against HEAD),
  whose load-bearing case asserts that enabling it leaves all ten other `BarState` fields
  byte-identical — every measured figure in this repo was produced by a stack with no OB engine in it.
  `EngineConfig` carries the engine-construction knobs; note `show_internal` (default True): the
  `market_structure` engine always computes internal structure, but a consumer whose Pine has
  "Show Internal Structure" OFF sets this False, which blanks the snapshot's internal-derived fields
  (`i_confirmed_*` / `ifib_seed_*`) so the Structure fib does not adopt an internal-swing anchor. The
  mpc_sos_fade bot pins it False; the engine parity harnesses keep it True (they validated internal ON).
- **A2 — Fill & cost model** *(done 2026-07-16; bar-mode costs added 2026-08-01)*.
  `backtest/fills.py` + the tick seam in `mpc_sos_fade/execution.py`. **Two fill models, and the
  distinction is load-bearing:** `fill_model="bar"` (default) is the strategy's own bar-level
  intrabar-path GUESS, and it matches what the Pine assumes, so it is the ONLY model
  `compare_strategy.py` may diff. **Bar mode charges zero costs BY DEFAULT — which is not the same
  as charging none by construction, and until 2026-08-01 the two were confused.** A caller may
  now hand `MpcSosFadeStrategy(..., cost_profile=<AccountProfile>)` and have commission and a
  per-fill slippage estimate charged into each trade's own P&L; omit it and the path is
  byte-identical to what it has always been, which is what keeps the parity gate valid. Build the
  strategy through `backtest.replay.build_strategy` rather than calling the class directly — it
  REFUSES to run a strategy that cannot accept a profile when the caller stated costs, instead of
  silently dropping them (that silent drop is exactly the lab bug this closed: the command center
  collected `commission_per_side` / `slippage_ticks` for months, stored them, displayed them, and
  charged neither). Two units to get right, both stated in `AccountProfile`: commission is per
  **LOT** per side (a lot is `contract_size` units — 100 oz for gold), and `slippage_ticks` is a
  **bar-mode-only** estimate charged on **market exits only**, because a resting limit fills at
  its price or better or not at all and tick mode measures the real thing off the tape.
  **Bar mode learned the SPREAD and the SWAP on 2026-08-02**, which were the two costs bar mode
  could have priced all along and did not: `AccountProfile` gained `spread` (price units, bar-mode
  only — tick mode has the real book) and `bid_ask_fills`. Both default to the honest zero, so a
  profile built before they existed is byte-identical. Swap needed no new code at all — the charge
  path has always run in bar mode and was dead only because callers passed `swap=None`.
  ⚠ **The two spread fields are ALTERNATIVES, not layers** — a flat charge, or transacting on the
  real side of the book; running both bills one spread twice, and `_charge_spread` refuses the
  second. ⚠ **They do not agree, and the gap is the finding, not a defect**: a flat charge assumes
  market orders, and a strategy whose entries and exits all name a PRICE feels the spread as fill
  TIMING instead — measured on `mpc_sos_fade`, the flat charge costs 5.7R and the fill model costs
  none, because the whole burden lands on shorts (which buy the ask to exit). ⚠ **Spread is a fact
  about the SYMBOL as much as the account** — the values in `PROFILES` are XAUUSD's, measured per
  broker off that broker's own cached ticks (**Vantage 0.22 over 1.49M ticks, PU Prime 0.33 over
  688k**; quoting one for the other is a 50% error), exactly as `swap` already was.
  `fill_model="tick"` resolves every level against real bid/ask ticks (long enters on the ask, exits
  on the bid), measures stop slippage off the actual next tick rather than assuming a constant, and
  charges commission + swap into the trade's own P&L. **Tick mode is expected to DISAGREE with the
  Pine on ambiguous bars — that is the improvement, not drift.** Bar mode must stay bit-identical
  forever; `test_execution_ticks.py::test_bar_mode_is_untouched_by_a2` is the guard.
  Measured on the 365d 15m XAUUSD run: real fills cost 1.3% of net, 0 bars fell back to the guess.
  ⚠ **Bar mode has one KNOWN LIMITATION that is not a defect and must not be "fixed" (recorded
  2026-08-01):** a stop staged mid-bar can be behind the market by the time it goes live next bar
  (price tags TP1, the stop stages to breakeven, price closes back through it in the SAME bar), so
  the exit fills at the next bar's OPEN rather than at the stop. Being out is CORRECT; only the
  exit PRICE is imprecise, and only because bar replay checks orders once per bar while a real
  broker watches every tick. **It errs in the safe direction (backtest looks slightly worse than
  reality), it is identical in Pine and Python so parity is unaffected, and tick mode legitimately
  disagrees with it** — that is the improvement, not drift. Canonical write-up:
  `strategies/python/mpc_sos_fade/CLAUDE.md` → `### Wrong-side stop fills`.
- **A3 — Output adapter** *(done 2026-07-16)*. `backtest/output.py`. `build_results(trades, …)` →
  the lab's `{equity_curve, daily_pnl, kpis, engine_trades, blocked_setups}`. Strategy-agnostic: it consumes any
  trade object carrying the reporting fields (`execution.Trade` satisfies it) and owns no strategy
  or fill logic — pure reporting arithmetic. It deliberately does NOT compute `sharpe`/`cagr`: the
  lab stamps canonical Sharpe from `daily_pnl` at completion (`metrics.apply_canonical_sharpe`) and
  a second definition here is exactly the duplicate-definition bug that doc warns about. The two lab
  contracts it mirrors by hand (the equity-curve point; `sizing_engine.RawTrade`) are locked by
  `tests/test_output.py` — including one that builds the REAL `RawTrade` from our rows, so the
  contract can't silently drift. Each equity-curve point also carries `favorable`/`adverse` (the
  trade's excursion, read from `Trade.mfe_usd`/`mae_usd` via `getattr` default 0.0, so a trade
  duck-type lacking them is fine) — the lab's TradingView-style equity chart reads them.
  🔴 **A point's `size` is the BASE quantity, and a trade can hold more than that.** A strategy
  that SCALES IN buys further lots at their own prices (`execution.py::_exit_portion` closes each
  against its own entry), so `(exit_price - entry_price) * dir * size` stops reproducing `profit`
  the moment one fills. Measured on lab run `295a6ff29d21`: eight trades booked **exactly $0.00**
  with the exit BELOW the entry on a short, and the lot that took the profit back was in no field
  of the point. Since 2026-08-18 the point carries `adds` — one record per FILLED lot, so the row
  can account for its own P&L — and since 2026-08-20 that record is TRADE-SHAPED: `mfe_price`,
  `mae_price`, `exit_price`, `exit_ms`, `exit_reason`, `pnl_usd` beside the original three, so a lot
  can be read the way a trade is. ⚠ **Everything past `qty` is optional PER LOT** and is copied only
  where the strategy recorded it; 🔴 **an absent field is never defaulted to `0.0`** — a lot reported
  as exiting at price zero is a measurement nobody took, and reads as one. Absent means nothing
  closed it. ⚠ **Absent, not `[]`, on a trade that never added**: an
  empty list on every trade of every strategy without the feature would read as a feature that ran.
  ⚠ **No backfill exists and none can** — a stored run never recorded the lots; re-run it.
  Two tests in `tests/test_output.py` pin both directions (the lots reach the point; a trade
  without them omits the key), and deleting the emission reddens the first alone.
  ⚠ **`build_engine_trades` deliberately omits them** — it is the unit-size contract the sizing
  engine re-sizes from, and it cannot model a position that grew mid-trade.
  ⚠ **`costs_usd` on a point is SIGNED, and a positive value is a real outcome, not an error.**
  The convention is the broker's (`execution.py::_charge`): **negative = charged, positive =
  CREDITED**, because a short's gold swap genuinely pays you (+26.98 points/night on Vantage) and
  can exceed the spread on the same trade — measured at **39 of 161 trades net-credit** on the
  reference run. `reprice.py`'s `cost_usd` is the OPPOSITE sign (positive = charge), so anything
  crossing between the two must negate, never take an absolute value. **Taking `Math.abs()` is the
  bug this warning exists for**: the lab's `Fees charged` row did exactly that until 2026-08-03 and
  read **$415,990 against a true $332,371 — and $514,315 against $252,998 on swap alone, 103%
  high**, while the pill beside it showed the correct figure. A cost model that can pay you is not
  an edge case here; it is the normal state of a short. Wired into
  the lab 2026-07-16 as `runner="python"`. **`blocked_setups`** (added 2026-07-27,
  `build_blocked_setups`) is the same idea for the trades that never happened: a setup one of the
  strategy's own rules refused places no order, so it is in no trade list and this is its ONLY
  channel to the lab. Same duck-type discipline (`dir`/`time_ms`/`code`/`edge`/`label`/`reason`),
  always present as a key, `[]` when a strategy records none. Full path:
  `command-center/backend/CLAUDE.md` → *Blocked setups*. **`missed_setups`** (added 2026-07-27,
  `build_missed_setups`) is its companion one step earlier in a setup's life: not "which ready trade
  did a rule refuse" but "how far did this setup get before it died". Same duck-type
  (`dir`/`time_ms`/`edge`/`met`/`near` + `labels`/`reasons`/`met_lines`), same always-present-and-
  empty rule. `met_lines` arrives pre-FORMATTED and `of` is a per-record number, so nothing here or
  downstream knows what a "confluence" is — a strategy scoring out of four just ships `of=4`. `near`
  is the strategy's own "worth looking at" flag and must pass through UNTOUCHED: the chart derives
  its opening view from it, so defaulting or dropping it silently changes what a reader sees first.
  ⚠ **`zone_time_ms` / `zone_turn_ms` (added 2026-08-08) bracket the RETRACE, and `time_ms` is NOT a
  substitute for either** — that is the bar the setup DIED, a median 17 and up to 717 bars later and
  a median $22 from the setup's own `edge` (measured). A consumer that read `time_ms` as "where the
  setup was" put marks in the wrong part of a chart for a day; see
  `strategies/python/mpc_sos_fade/CLAUDE.md` → *The RETRACE a miss was waiting on*. **`None` means
  price never reached the zone and stays `None`** — a fallback to `time_ms` is the defect itself, and
  a `0` is the epoch.
  Full path: `command-center/backend/CLAUDE.md` → *Missed setups*.
  **`fib`** (added 2026-08-02, `_trade_fib`) is the newest optional key on an equity-curve POINT:
  the fib LEG a trade was priced off, as `{start_ms, levels: [[ratio, price], …]}`, and absent
  entirely when a trade carries none. Same duck-type discipline as everything else here — any object
  exposing `levels` as (ratio, price) pairs satisfies it, so this file knows nothing about which
  ratios a fib "should" have and a strategy with its own ladder just ships different pairs.
  ⚠ **It COPIES, and must keep copying.** The prices are the ones the strategy had in hand when it
  placed the order; recomputing them here — or in the chart — from anchors and a direction would be
  a second implementation of one leg, and the two would eventually disagree about a trade neither
  can re-run. Pinned by `test_the_fib_ladder_is_COPIED_never_recomputed`, which feeds it a
  deliberately non-linear ladder and requires it back unchanged.
- **A4 — Local optimizer** *(done 2026-07-16)*. `backtest/optimizer.py`. `run_sweep(module_path, df,
  combos, …)` replays one strategy over N parameter sets with the bars loaded ONCE and combos fanned
  across cores — no VPS, no terminal lock, no deploy/compile (4 combos over 3 months = 9s).
  **It owns only "replay fast."** The LAB still expands the grid (min/max/step is the lab's contract,
  shared with NT8/MT5 — `optimization_runner.expand_grid`) and still scores/ranks/picks the winner
  (`objectives.py`, `_pick_best_run`), so nothing above the seam has a Python-specific branch.
  Configs arrive **fully built** (`Combo.config`), so exactly one place knows how a lab param dict
  becomes a strategy config. Each combo gets a fresh strategy + engine stack — sharing either would
  make results a function of grid order. **Sweep in bar mode, validate the winner in tick mode:** a
  tick pass is ~1,100s vs ~10s for the 365d 15m run, so a 100-combo grid is ~31h vs ~2min, and real
  fills only moved that run's net by 1.3%. Reached from the lab via `runner="python"` on the existing
  native-optimizer contract (`python_runner.start_native_optimization` / `native_opt_results`).
  **Callers must be import-safe** — the pool spawns workers, which re-import the calling module; a
  script needs an `if __name__ == "__main__"` guard (`python_runner` is a module, so it is safe).

## Tools

- **`tools/internal_break_audit.py`** (2026-08-23) — does an INTERNAL break against the trade
  predict a bad entry? Aaron's observation from the price chart on a losing re-entry, asked two
  ways because it is really two rules: **refuse the setup**, or **take it and leave at flat**.
  ⚠ **Committed 2026-08-24 having sat untracked for a day, and the reason is worth more than the
  tool**: it was about to be deleted as unattributable cruft because it was blocking a repo-wide
  format check, and it exists nowhere else — an untracked file has no history to recover from.
  **A tool nobody has committed is a tool one tidy-up away from never having existed.**
  ⚠ **The numbers in its docstring are its author's, not re-run here.** It was committed unchanged
  apart from formatting; whoever next trusts a figure from it runs it first.
  ⚠ **It is a STATIC RE-SCORE of one book, not a replay** (its own docstring says so at length):
  with one position slot, refusing a setup does not merely remove its R, it lets whatever queued
  behind it trade instead — the effect this repo has already MEASURED running the other way in
  Run 12. `--replay` is the honest mode; the default is the cheap one.

- **`tools/recovery_report.py`** (new 2026-08-19) — replays a strategy, then replays the
  **loss-recovery** rule over its losses and prices the addition against the only honest
  alternative: turning `exec_risk_pct` up on the strategy you already own. The rule itself lives
  in `strategies/python/loss_recovery/` and that CLAUDE.md is the one that explains it.
  🔴 **It charges costs to BOTH sides, and that is load-bearing rather than tidy** — charging the
  recovery leg alone is rule 11 broken, and it FLIPS the verdict: uncosted-primary said the risk
  dial won, costing both says the recovery wins by 1.3–1.7x. The primary holds a median 0.3 days
  and 100 of its 181 trades are SHORTS, which gold pays a swap CREDIT to hold, so it loses only
  7% of gross to costs while the recovery leg loses far more.
  ⚠ **Read the drawdown column, never the balance alone.** The rule buys RETURN, not safety —
  MEASURED, max drawdown is 48.3% at 25% size against the primary's 48.8%, and it goes UP to
  57.2% at full size. `--sweep` prints the whole size curve.
  🔴 **`--exits` and `--soft-curve` (2026-08-19) grid the EXIT rules, and three of the four
  candidates LOSE** — structural invalidation on the opposing CHoCH +16.2R → +9.7R, an early
  breakeven step → +4.2R, and splitting the lock's trigger from its destination → −2.3R at 2R→1R.
  The one that survives is `soft_stop_r`, which cuts at a fraction of R **without moving the
  distance the trade was SIZED on** — the whole point, since a nearer stop otherwise just buys a
  bigger position and costs the same money.
  ⚠ **Its curve is a PLATEAU and the tool prints it as one.** Everything from −0.25R to the
  structural stop lands between +12.9R and +18.5R against a measured run-to-run sd of 15.06R, so
  the finding is that cutting early is FREE, not that it earns more; what moves monotonically is
  the loss SIZE (−1.01R → −0.30R) bought with win rate (58% → 37%).
  ⚠ **Read `--soft-curve`'s `less top 5` column, not its ranking** — below −0.25R the rule goes
  negative once its five best trades are deleted, which is the only place the cliff is visible.
  🔴 **`--stops` (2026-08-19) answers WHERE the stop goes, and killed the strongest-sounding
  idea yet**: resting it on the LOSING trade's entry price. It is 2.4x tighter ($38.18 → $16.05
  median), so the same risk buys 2.4x the position and the trade resolves in 43 bars against 294
  — every step of the mechanism works — and net R goes **+16.2R → +1.8R** with max drawdown UP.
  The primary's entry is a price the market has just been trading around, so the stop sits in
  fresh congestion; **median MFE falls 1.01R → 0.89R, which a 2.4x smaller R should have RAISED.**
  ⚠ **That excursion column is the diagnostic, not the P&L** — it is what distinguishes "the stop
  was unlucky" from "the trades are dying before their move".
  ⚠ **A percent ratchet loses to the confirmed-swing trail on both stops**, and flatly across a
  20x range of steps: at 1% one step is $40 against a $38 median stop (inert — the `mpc_bleg`
  trap), at 0.05% it binds constantly and hands back the runners.
  🔴 **`--search` (2026-08-19) is the stop sweep, and its best row is a trap worth knowing.**
  A stop on the CHoCH BAR's own extreme scores **+24.4R against the shipped +16.2R** on a stop 7x
  tighter with a LOWER drawdown — and **−7.4R once its five best trades are deleted**, where the
  shipped stop survives the same deletion at +2.3R. Median hold 4 bars: a different, hour-long
  rule that caught five big moves, not a better version of this one.
  ⚠ **Every stop row is scored against a structure-BLIND ATR control at a matched distance**, and
  that is what makes the table readable — the last confirmed swing scores −12.3R at almost exactly
  the same stop SIZE as the signal bar's +24.4R. **Size is not the variable; where the level came
  from is.**
  🔴 **It also settles "the +1R lock gives up the runners": the runners are not reachable.** Of the
  35 trades that lock, only **3 ever saw +2R while still open** (median MFE +1.06R), yet the median
  trade was offered **+2.33R more within 30 days of closing**. Price tags +1R, takes the stop, then
  runs — so every wider trail pays 32 trades of given-back R to catch 3, which is what the measured
  alternatives all do. **That gap is a RE-ENTRY signal, not a trailing-stop problem.**
  ⚠ Everything it prints is a LAB finding: no Pine twin, no parity gate, `enabled` defaults False.

- **`tools/recovery_smoothness.py`** (new 2026-08-19) — the companion question to the one above:
  loss recovery does not reduce MAX drawdown, so does it at least smooth the curve? **No.** Average
  drawdown 16.6% → 17.2%, median 11.4% → 12.2%, time under water 75% → 79%, longest underwater
  stretch identical at 612 days, monthly mean/std unchanged at 0.314 → 0.318.
  🔴 **It exists because max drawdown is ONE MOMENT and a single-number verdict hid the rest of the
  curve.** The equal-drawdown comparison in `recovery_report.py` is matched on the max, so it can
  read 1.53x while every broader measure is a wash — which it is.
  ⚠ **Per-trade R volatility falls 3.32R → 2.88R and that is NOT smoothing**, it is dilution from
  adding quarter-size trades; return per unit of it goes 0.215 → 0.190. Never quote a volatility
  drop without the return beside it.

- **`tools/rso_scan.py`** (new 2026-08-16) — finds RETAIL SHAKE OUT (RSO) setups and draws them.
  Drives the canonical `engines/market_structure/` rather than hand-rolled pivots: A = `bull_sos`,
  B = a wick under the level that break left behind, C = the next aggressive `bull_sos`. Shorts
  come from `invert()`, and 🟢 **the sign-symmetry that trick assumes is now CHECKED rather than
  assumed** — `--verify-mirror` counts `bear_sos` on real bars against `bull_sos` on inverted bars
  and they matched exactly (424 = 424). 🔴 **FIRST RUN, 186,759 M15 bars 2018-09-13 → 2026-08-13:
  ZERO ENTRIES, and the tool exists to have found that.** Funnel: 847 A-breaks → 16 shake outs →
  **0** real breaks. **The binding constraint is C**, which needs TWO `bull_sos` inside ~32 bars,
  against a measured density of **one SOS per 220 bars** (external 847 / internal 575 over the same
  frame — the internal stream is RARER, so the obvious fix makes it worse). ⚠ **`docs/MPC_FB_SPEC.md`
  §4.6 has to be re-specified before any RSO code is written: Aaron's own
  `indicators/engines/mss_sweeps_mpc.pine` fires on a RECLAIM — price wicks the level and closes
  back — not on a second structure break, and that one substitution is the difference between an
  indicator that signals and this scan's zero.** ⚠ **A trigger that never fires has not been
  measured, it has been mis-specified** — do not read the zero as "RSO has no edge". ⚠ Trigger only:
  no 4H bias and no discount filter, because `run_sweep` replays a single frame. No baseline moves —
  this is a new tool and nothing consumed it before today.
- **`tools/loaded_level_scan.py`** (new 2026-08-13) — counts the LOADED LEVEL / "Da Vinci" setup
  (`docs/DAVINCI_MODEL_SPEC.md`, extracted from 16 Inter Equity Trading videos into
  `education/learned/`) and scores it against a matched random control. A level is *loaded* when
  price returned to it, respected it and moved away; the entry is the sweep of that level, the stop
  sits past an already-swept "empty" level, the target is the opposing pool. **MEASURED 2026-08-13
  on XAUUSD M15, 186,759 bars (2018-09-13 → 2026-08-13): long 49 trades, 34.7% vs a matched random
  22.9% — +11.8 points, z +1.96, +0.751R/trade (+0.633R net of spread). Short 80 trades, 21.2% vs
  20.9% — z +0.09 and −0.137R net of spread.** Funnel across both sides: armed 2,198 → loaded 2,151
  → inducement 1,879 → target built 1,444 → 129 entries; the three biggest drop causes are `rr below
  floor` 819, `block broken` 717, `expired` 531, and they are instrumented rather than inferred.
  ⚠ **`--away-mult` (added 2026-08-18) is the "and MOVES AWAY" half of the loaded rule, which the
  first cut silently dropped** — ATR(50) × this that price must TRAVEL from a level before it counts
  as loaded. **It DEFAULTS TO 0.0 and is provably inert there**: `need` is zero and both tests
  reduce to `max(highs) − low ≥ 0` and `high − min(lows) ≥ 0`, which always hold — so the shipped
  baseline above reproduces exactly and nothing in this entry moves. **It is a knob to SWEEP, not a
  value to ship**: raising it tightens what counts as loaded and every number here would have to be
  re-measured at the new setting. Same reasoning as an unmeasured cost tier — a plausible default is
  a hardcode with better manners.
  ⚠ The setup DIAGRAM renderer is now direction-aware. It drew a short with the long layout, which
  put "LOADED LOW" on a high and stacked four markers on one line — **the same class of error
  `invert()` exists to prevent one level up, and silent both times.** Right-edge labels are also
  stacked apart on purpose: entry, block and stop are a tight cluster BY CONSTRUCTION (the model
  puts the stop just past the block), and an unreadable label is the same as no label.
  🔴 **Two defects were found and fixed the day it was measured, and both are this repo's own
  standing rules restating themselves.** `Setup.dir` was documented as `"long" | "short"` and
  `dir="short"` was constructed **nowhere** — a declared field that was never assigned (root rule
  10), so the tool was long-only while reporting both sides. The short side now comes from
  `invert()`, which negates prices and swaps high/low so the *same* long code detects shorts, rather
  than from a hand-written bearish branch where a sign error is invisible; `unmirror()` maps the
  setup back. And it had **no control at all** — on an instrument that went 1,200 → 4,300 any
  long-biased rule looks profitable, so `control()` matches direction, stop distance and target
  distance and prints a z-score beside every row. The long baseline reproduced exactly after both
  fixes. ⚠ **The z-score peaks at `min_rr = 2.0`, which is the tool's own pre-existing default**
  (1.0 → +1.3 points z +0.29, i.e. NO edge; 1.5 → z +0.77; 2.0 → z +1.96; 2.5 → z +1.64; 3.0 → z
  +1.02). A peak sitting exactly on the shipped default is a selection-effect candidate and stays
  suspect until a walk-forward separates the two. ⚠ **H1 (n=13) and H4 (n=3) are too thin to
  score**, which is awkward — the source videos teach the model on H4/H1 and above, so the only
  frame with a usable sample is the one the author uses least. ⚠ **No parity gate and no Pine twin.
  Every number here is a lab finding.**
- **`tools/session_relay_scan.py`** + **`tools/sweep_confluence.py`** (new 2026-08-08) — the session
  relay playbook (London sweeps Asia's low, NY sweeps London's, then structure flips back) and the
  broader question underneath it: does a liquidity sweep carry a directional bias at all, and do
  session + daily sweeps landing together carry more? Both compose `market_structure/`, `liquidity/`
  and `sessions/`; neither invents an engine. ⚠ **`session_relay_scan.py` deliberately produces no
  entry, stop or R** — it answers "how many are there", and a P&L number there would smuggle in a
  dozen decisions nobody has made. `sweep_confluence.py` does take the crudest tradeable framing
  (enter at the sweep bar's close, stop past the swept extreme, fixed-multiple target, a bar holding
  both books the stop) **and prints a non-sweep `control` row in the same table** — every bucket is
  read against that row, never on its own.
- **`tools/internal_realign_scan.py`** (new 2026-08-13) — counts the INTERNAL REALIGNMENT setup in
  history and scores its geometry against a matched random control. A bullish 15m external trend is
  broken by a bearish SOS (a false break / structural liquidity grab); on a lower frame the internal
  structure turns counter and back with-trend to realign, and the scan asks how often that happens
  and whether the realignment carries information. Both directions. Feeds
  `strategies/python/mpc_realign/` and `docs/MPC_REALIGN_SPEC.md`.
  🔴 **ITS SHORT-SIDE RESULT WAS WRONG IN SIGN, AND THAT IS THE STANDING WARNING ON THIS TOOL.** It
  reported the internal-events stream at **+9.6% over control (+2.1σ)** for shorts — its strongest
  row — and a real replay through the exit ladder gives **−13.26R against +20.22R** on the other
  stream. The scan is not broken: it scores every setup **independently, at a FIXED target, with no
  exit ladder, no staged stop and no position slot**, and that short edge lived entirely in the tail
  (+0.1σ at 1R, +2.1σ at 4R). The real ladder banks at the structural target and stages the stop to
  breakeven long before 4R, so **the edge it measured is one the strategy never collects.**
  ⚠ **Take COUNTS from this tool; take the direction of anything exit-sensitive from a REPLAY.** A
  trigger prior is not a strategy result, and disagreeing in SIGN is the one disagreement that no
  amount of care about magnitude protects you from.
  🔴 **It prefers resampling from contiguous M1 over a cached lower frame, and the reason generalises
  to every streaming-engine tool here.** The M5 cache held 26,886 bars over 3.5 years; feeding a
  streaming state machine across holes that size silently builds structure over bars that never
  traded, and the frame comes back clean. `_gap_report` prints the density so the hole is visible
  rather than inferred.
  ⚠ **Two of its filters were VACUOUS on their first attempt and each failed in the reassuring
  direction.** A lookback slice rejected every `bear_sos` by its own twin `bear_bos` (a CHoCH bar
  raises both), reporting **ZERO occurrences** — indistinguishable from "the setup never happens";
  and a forward "did it reclaim" scan stopped only on `bear_sos`, so it walked through entire
  downtrends until some bull break appeared and returned **101/101**. Both are now bounded so that
  each outcome is reachable. **A pattern counter that returns 0 or 100% is reporting on its own
  bounds, not on the market.**
  🔴 **ITS PATTERN RANKING ALSO FAILED TO SURVIVE A REPLAY — THE SECOND FAILURE, AND THE ONE THAT
  MAKES THIS A PROPERTY OF THE TOOL RATHER THAN A ONE-OFF.** It ranks the strict three-step sequence
  LAST of three, and a replay over the same history puts it **FIRST on average R, profit factor and
  drawdown simultaneously** on a free book — it only falls behind once costs are charged. So the
  tool has now been overturned once in SIGN (the short trigger stream) and once in ORDER. **What it
  measures is TRIGGER quality; what a strategy is ranked on is what its exits bank. Do not choose a
  default from this tool.** Tables: `strategies/python/mpc_realign/CLAUDE.md` → *The pattern rule*.
  `internal_realign_scan.py --pattern any|opposing|strict --frame 5` · defaults to `strict`, the
  sequence that was DRAWN.
- **`tools/scratch_audit.py`** + **`tools/swap_audit.py`** (new 2026-08-11) — is a "breakeven" exit
  actually breakeven on a real account, and what does overnight swap cost. Written for Aaron's
  theory that `exec_be_buf_tk` (30 ticks = $0.30) cannot cover a $0.32 spread; full record in
  `strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md` → **Run 17**.
  ⚠ **A scratch is classified on the PRICE MOVE, never on the money, and that is the whole design.**
  Sorting the cohort by profit would put every negative scratch in the loss bucket and return "all
  scratches are positive" by construction. The cohort has to be defined by what the strategy DID and
  then measured on what it got.
  🔴 **`Trade.costs_usd` does NOT contain the spread under `bid_ask_fills`** — that model moves the
  FILL PRICES rather than charging a fee, so its effect is already inside `entry_price` /
  `exit_price` and appears in no cost field. Reading `costs_usd` alone would report a scratch as
  free. The two are printed separately for that reason.
  ⚠ **`swap_audit.py` runs on `puprime_standard` deliberately**: $0.00 commission and 0 bar-mode
  slippage make `costs_usd` **pure swap** with nothing to disentangle, and the swap is identical on
  all three PU Prime tiers (measured 2026-08-08), so nothing is lost by reading it off that one.
  ⚠ **Its "ceiling on a stop ratchet" figure is an UPPER BOUND and says so in its own output** —
  moving a stop changes when it triggers, and this repo has two records of that arithmetic getting
  the SIGN wrong (`bos_sweep.py`, the minimum-stop guard). If the number is small, do not build the
  thing; if it is large, replay it.
- **`tools/cost_tiers.py`** (new 2026-08-10) — replays one strategy under several BROKER ACCOUNT
  TIERS and prints trades / total R / delta-vs-free, one real replay per row. It exists because
  `docs/LIVE_TRADING_PIPELINE.md` → G5a answers *which PU Prime account type* with exactly that
  table, and the table was built by hand on 2026-08-06 and had to be rebuilt on 2026-08-10 when the
  raw tiers' spread and commission stopped being marketing figures and became measurements.
  **A measurement nobody can re-run in one command is a claim.**
  `cost_tiers.py --spread puprime_ecn=0.12` · defaults to the three PU Prime tiers over
  2020-01-01 → 2026-08-03, which is the window every G5a figure is quoted on.
  ⚠ **`--spread TIER=VALUE` is a WHAT-IF and the output labels it `stated`, never `measured`.**
  `fills.py` carries `SPREAD_UNMEASURED` on any tier nobody has read a spread off and REFUSES
  rather than borrowing a sibling's — this flag overrides for one run and **writes nothing back**.
  It is per TIER and not one global number on purpose: a single spread applied to every row would
  hand Standard the raw tiers' quote and flatten the one difference the table is about.
  ⚠ **It charges `bid_ask_fills`, which REPLACES the flat spread charge rather than adding to it**,
  and it is the only cost model here that can change WHICH trades exist. That is why a tier
  comparison has to be replayed and cannot be re-priced: the cost acts by removing trades, and a
  trade that never happened has no P&L to charge.
  ⚠ **It deliberately does NOT report "setups never filled"**, the most informative column in the
  G5a table. Nothing in `Execution` counts a resting order that expired — that figure came from
  hand instrumentation nobody kept — and deriving a proxy from the trade list would answer a
  different question under the same heading, because with one position slot a refused setup lets a
  DIFFERENT setup take the slot. Add the counter to `Execution` if the column is wanted again.
  ⚠ Reads the R column only. Costs are size-independent in R while dollars compound, and this
  strategy's run-to-run spread is **sd 15.06R** (`jitter_audit.py`) — a smaller gap is noise.
- **`tools/verify_parity.py`** — the one "is everything in sync?" command. Point it at the TradingView
  export CSV(s) you just pulled; it runs every parity check (all nine engine `compare_*.py` + the
  mpc_sos_fade `compare_strategy.py` + the mpc_bleg `compare_bleg.py`) whose MARKER column is present in the CSV, and prints one
  GREEN/RED/SKIP table. Cold-start warmup is auto-detected by walking a capped ladder (≤25% of the
  file), so a genuine LATE drift can never be skipped away as warmup. It reports drift; it does not fix
  it (a real logic change is still a hand port, per drift). Run it after any `mpc_assistant.pine` /
  `mpc_strategy.pine` / `mpc_b_leg_strategy.pine` re-paste + re-export. Stdlib only.
  `verify_parity.py <csv> [csv ...]`, or no args = newest CSV in `backtest/`.
  Each registry row carries a MARKER column and a **VETO** column (added 2026-07-26): a check runs
  when its marker is present and its veto is absent. The veto exists because the two STRATEGY exports
  overlap — `mpc_b_leg_strategy_export.pine` plots `px_stages` too (the B leg arms off the A+
  sequence), so marker-alone would run the A+ check against a B-LEG export and produce a red that
  means nothing. `bl_bits` exists only in the B-LEG export, so it is the A+ check's veto and the
  B-LEG check's marker. Deliberately NOT solved by re-marking A+ on an A+-only column like
  `px_block`: that column landed 2026-07-25, so every older A+ export would silently stop being
  checked.
- **`tools/run_report.py`** — the "WHY did it make/lose money" run. Replays a `strategies/python/`
  bot over YEARS of broker bars and writes `trades.csv` (one row per trade, tagged with the
  `engines/regime/` label at entry, NY session/hour, and excursion in R) plus `setups.csv` (one row
  per A+ leg that reached SOS, traded or not, with the FIRST thing that stopped it). The second file
  is the point: a blocked or skipped setup places no order, so it leaves NO trace in any broker trade
  list — this is the only place it is countable. Reports in **R, never dollars** (a fixed-%-risk
  strategy earns exponentially more dollars at the same edge, so a dollar curve makes a flat early
  year look like a broken edge). `--set FIELD=VALUE` overrides any config field for A/B tests
  (frozen dataclass, applied via `replace`); `--no-regime` skips the tagging. Everything it adds is
  reporting-only — no tag feeds back into the strategy, so results are identical with or without it.
  Carries the timeframe-substitution guard described under *history depth* below.
  **`--start` defaults to the MEASURED floor** (`_default_start` → `history.floor_for`), fixed
  2026-07-29. It had been hardcoded to `2022-01-01` while the help text claimed "broker's earliest",
  so every default run silently reported 4.6 of the available 7.9 years — the quiet direction of the
  substitution trap: nothing errors, the equity curve looks fine, and the run just answers a
  narrower question than the one asked. When the agent is down the broker cannot be identified, so
  it refuses and asks for an explicit `--start` rather than guess. **Same rule as everywhere else in
  this package: never type a history depth, measure it.**
  🔴 **A CONFIG THIS TOOL CANNOT REPLAY IS REFUSED, NEVER SILENTLY DOWNGRADED (2026-08-16).**
  `exec_secondary` needs `run_dual(df15, df1m)`; calling `run(df15)` with the flag on produces a
  primary-only book that looks exactly like a run where the feature never fired — `optimizer.py`
  and `portfolio/legs.py` had already met this and refuse it. The tool now loads the 1m frame and
  calls `run_dual`, refuses when there is no `run_dual` or no fill-clock bars, and always PRINTS the
  secondary trade count so *0 secondaries* is a stated answer. ⚠ **`--no-secondary` SETS the flag
  False rather than only picking the fast path** — the config that is reported must be the config
  that RAN. ⚠ **THIS MOVED DOCUMENTED BASELINES**: every `mpc_sos_fade` figure this tool produced
  at the default config before that date is primary-only, valid as a MATCHED SET (rankings stand)
  but understating absolute totals — **MEASURED 2018-09-14 → 2026-08-14, bar fills, ONE window both sides: 189 trades /
  +164.4R with the secondary against 181 / +138.9R without — the gap being 8 secondary trades
  worth exactly +25.5R**. ⚠ **Dual costs ~50 min a
  full-history replay against ~3 min.** ✅ **BOTH FIGURES ARE SUPERSEDED — RE-MEASURED 2026-08-27:
  a full 6.6-year replay is 59.9s single-feed and 94.1s DUAL** (157,004 M15 + 471,830 M5 bars,
  200 trades). **The 471,830 extra bars cost 34 seconds.** ⚠ **Two separate reasons the old pair
  no longer applies, and they must not be collapsed**: the fill clock defaulted 1m → 5m on
  2026-08-21 (a fifth of the bars for 1.3% of accuracy), and the replay path itself got ~9x faster
  on 2026-08-26/27 (`HISTORY.md`). **So the ~50 min was a 1-minute clock on the old code and is
  not comparable to either number here.** 🔴 **The standing point is the one this file keeps
  making: a TIMING in a doc goes stale exactly like a measurement, and this one had been quoted as
  the reason not to run a dual replay.** Pinned by `tests/test_run_report_secondary.py` (7; 3
  watched RED against HEAD, the behavioural pair killed by 2 mutations). Story:
  `docs/BACKTEST_BUILD_NOTES.md` → *The secondary that never ran*.
- **`archive/`** — committed, frozen `run_report.py` output. `backtest/reports/` is git-ignored
  per-run scratch, which meant multi-year trade data existed only on the machine with a warm cache
  and a live agent; `archive/<date>_<symbol>_<tf>_<scope>/` is the copy that travels with a clone, so
  someone with no VPS and no MT5 can still analyse real trades. It is a SNAPSHOT, not a build
  artefact — nothing regenerates it, so any config change makes it stale. Each folder carries a
  README stating the window, fill model, config levers at run time, and open caveats; keep that
  honest or the numbers get quoted without them. Current: `2026-07-29_xauusd_15m_full_history/`
  (A+ and B-LEG, 2018-09-13 → 2026-07-29, bar fills).
- **`tools/overlap_audit.py`** — do two strategies actually trade DIFFERENT legs of the move? Replays
  two `strategies/python/` bots over ONE bar frame and reports the bars both held a position (split
  same-side vs opposite), which trades pair up, how far apart same-direction ENTRIES land (the direct
  test of "both fired on one structure break"), what a single account would have carried, and the
  monthly R correlation. **Built 2026-08-04 to close the standing A+/B-LEG overlap question**, which
  had been design intent in three CLAUDE.md files for a year and never measured; it passed —
  27 shared bars in 155,453, one same-direction cluster in 6.5 years. ⚠ **It deliberately does NOT
  net the two into a combined equity curve**: both bots are `self_sizing`, so running them on one
  account changes both bots' sizes from the first shared trade and the result is a third thing
  neither bot is. That question belongs to the unbuilt allocator (G10); this tool measures how often
  the allocator would have had anything to arbitrate. ⚠ **Re-run it after any entry-logic change on
  either bot** — the output is a fact about today's config. The bar arithmetic is unit-tested
  (`tests/test_overlap_audit.py`), because a slip in it would report "the legs never overlap" exactly
  as cleanly as the truth does.
- **`tools/jitter_audit.py`** — how much of a backtest survives a few cents of feed difference?
  Replays a `strategies/python/` bot over the same bars N times with a small random offset added to
  each BAR's four prices, and classifies every jittered trade against the baseline: **flipped** (the
  entry moved further than the noise can account for — a `exec_fib_nearest` rung change),
  **retimed** (same setup, filled within 16 bars), **lost** / **gained** (no twin at all), and
  **shifted** (moved by about the noise, which is expected). **Built 2026-08-05 to close G17**, the
  half of the shadow-diff finding that one live window could not answer. ⚠ **The offset varies per
  BAR and is applied to all four prices at once** — a constant offset translates the whole fib ladder
  and flips nothing, and independent per-price noise builds candles no feed can produce. ⚠ **The flip
  threshold is `2 * amp`, derived from the noise rather than picked.** ⚠ **`--amp` defaults to the
  MEASURED broker gap** (0.05; the shadow diff found Vantage above PU Prime by 0.04–0.05 on every one
  of 148 live bars), not a round number — raising it measures a broker nobody trades. ⚠ **Read the
  spread across seeds, never one seed**: the answer is a distribution, and a single jittered run is
  one draw from it. The classification is unit-tested (`tests/test_jitter_audit.py`) because a slip
  in it would report "the trade list is perfectly stable" exactly as cleanly as the truth would.
- **`tools/compare_feeds.py`** — feed-parity check: MT5 pull vs a TradingView export of the same
  symbol/TF/window. Reports **clock offset** (0 = aligned; non-zero = the broker-server-time bug
  that shifts every session — fix before demo), coverage, and OHLC drift. This is *data* parity, not
  *logic* parity (that's the strategy's `compare_strategy.py`) — MT5 and TradingView are different
  feeds and never match exactly; the tool measures the gap. **Not a per-backtest check.** Run it:
  once as a baseline, whenever the agent's time handling or the broker/terminal changes, at the start
  of each demo campaign then ~monthly, and any time trades look off vs the chart. Needs the MT5 agent
  + tunnel; the alignment math is unit-tested offline. Full rationale + cadence: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.

- **`tools/trigger_edge.py`** — **does a TRIGGER carry edge, before any strategy is built?** Added
  2026-08-06 to answer "which of the two continuation setups is worth pursuing" when NEITHER has a
  Python port, so neither could reach `optimizer.py`. It replays the canonical `market_structure` +
  `vwap` engines, finds the bar a trigger would actually be IN on, and asks only whether price reaches
  `+NR` before `-1R`. No sizing, no ladder, no costs; R is each trigger's own structural stop.
  🔴 **THE CONTROL IS THE TOOL.** Gold went 1,200 → 4,300 across the cached window, so a long-side
  "edge" is free and any harness without a control will find one. Every set is scored against random
  entries **matched on direction AND stop distance**, and the control landing on the theoretical
  breakeven with expectancy ~0.000 is what certifies the harness before any result is read off it.
  **If you add a trigger here, add its control in the same commit.**
  ✅ **Findings 2026-08-06** (186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07): the with-trend
  BOS → 0.5 retrace trigger is **+4.4% over control (+2.5σ, n=778)**; adding the **pro-trend session
  VWAP side** takes it to **+6.8% (+2.8σ, n=404)** with the median stop **38% tighter** (1.80 → 1.11
  ATR); the D strategy's counter-SOS → VWAP-reclaim trigger is **−0.4% (−0.3σ, n=833)**, i.e.
  indistinguishable from random, and goes significantly negative at long targets (−2.8%, −2.1σ at 4R).
  That is what put VWAP into `mpc_bos_strategy.pine` (F10) rather than leaving it in the D file.
  ⚠ **It measures SKELETONS, not the shipped strategies** — no FVG requirement, no Sniper Zone, no
  session filter, no min-stop guard, no real exit ladder. A result here is a prior for a TRIGGER,
  never a strategy's own number.
  🔴 **The look-ahead trap it already fell into, recorded because the symptom was being TOO GOOD
  rather than erroring:** reading the VWAP side off the close of the bar its limit FILLS on selects
  bars that recovered by their close, and reported the filter at **+15.9% / +5.0σ**; reading the
  PREVIOUS closed bar gives +6.8%. **Anything evaluated on the bar it acts on is look-ahead until
  proven otherwise** — see `prev_side`.
  ⚠ **It drops the coarse head of the cache before measuring.** `XAUUSD__M15.csv` opens with
  HOURLY bars — MT5 serving coarser data where it has no M15 history, exactly the silent-substitution
  trap this file documents below — so `drop_coarse()` keeps only the contiguous tail whose median
  spacing really is 15 minutes. Measuring the raw file would score eight years of one trigger against
  a different bar size.
  ⚠ **Stdlib only, on purpose** — it drives the engines directly and needs no pandas, so it runs on a
  bare interpreter. Run it: `python3 backtest/tools/trigger_edge.py` (~5s).

- **`tools/intraday_edge.py`** — **is there a SECOND, intraday strategy worth building?** The sibling
  of `trigger_edge.py`, same method (matched random control on direction AND stop distance, hard 8h
  horizon, nothing scored on the bar it acts on), eight intraday triggers. Added 2026-08-07.
  🔴 **Its headline finding is a REFUSAL and it is the useful half: there is no intraday edge to
  harvest on GOLD, and the reason is structural.** All eight triggers are NET NEGATIVE after cost over
  186,384 M15 bars; the best (`ORB_BREAK`, +2.6% / +2.4σ over control) lands at **−0.008R** — a real,
  statistically detectable effect almost exactly the size of the spread. **An intraday stop on gold is
  $1–7 against a ~$0.30 round trip, so cost is 4–37% of every R before the signal says anything.**
  That is why the SOS fade works and an intraday sibling does not: a median $8.88 stop puts cost at ~3%.
  ✅ **The same trigger clears cost comfortably on NAS100** (+4.0% / +3.6σ, cost 1.2% of R,
  **+0.049R**), which is the prediction the cost hypothesis makes and it holds — both sides positive
  with the SHORT side stronger, both halves positive, positive in 6 of 9 years, and the MIRROR
  (`ORB_FADE`) catastrophic at −15.2% / −18.9σ. ⚠ **Read it as a prior on a TRIGGER, never as a
  strategy's number** — no ladder, no staged stop, no position slot, no swap, and NAS100 has no
  history floor, no Pine parity and no strategy package here. Full record: `docs/INTRADAY_EDGE_STUDY.md`.
  ⚠ **Two triggers are significantly NEGATIVE on gold and that is knowledge worth keeping**: fading a
  VWAP stretch and fading the opening-range break both lose to random in 9 years out of 9. Gold does
  not mean-revert intraday. Do not build either. Stdlib only, runs off `backtest/cache/`.

- **`tools/sweep_edge.py`** — **the sweep-and-reclaim is one trigger. Which LEVEL should it sweep?**
  Added 2026-08-14 to settle structure-vs-session-vs-both with a number instead of a chart. Holds
  the trigger fixed and varies only the level across five families — `structure` (the protected
  iHL/iLH `mss_sweeps_mpc.pine` arms), `session`, `day`, `week`, and `h4` as an internal BASELINE.
  Stdlib only, runs off `backtest/cache/`. Full record: `docs/SWEEP_LEVEL_STUDY.md`.
  🔴 **ITS FINDING IS ABOUT THE TRIGGER, NOT THE LEVEL, WHICH IS NOT THE QUESTION IT WAS ASKED.**
  `--trigger wick` drops only the close-back requirement, and **every family goes negative — h4 at
  −2.2% / −5.3σ over 11,541 events.** Adding the reclaim is worth ~2 points of win rate to all five
  families alike. The ranking between levels (structure +5.3% / +2.1σ, session +1.6%, day +1.9%,
  week −0.6%, h4 +0.3%) is worth a fraction of that, falls to +1.5σ under `--min-risk-atr 0.5`,
  is negative in 2023, and peaks at exactly the 2R the table was scored on. **Keep the reclaim; do
  not add session levels to the MSS trigger on this evidence.**
  ⚠ **Confluence made it WORSE**: structure alone +7.2%, structure ∧ session +4.3%. "Both" is not
  the answer. ⚠ **The video's own headline rule — Asia high taken in London — is the WORST of the
  six session pairings** (−0.8%, and −3.9% under the stop guard) while Asia-in-NY is the best.
  That measures his LOCATION rule stripped of his M1 confirmation and his OB entry; it says the
  location carries no information alone, not that his book is fake.
  🔴 **The control is matched on THREE axes, not `trigger_edge.py`'s two.** Session sweeps land at
  specific HOURS and gold does not drift uniformly around the clock, so a control drawn from all
  hours would hand the session rows an edge made entirely of what time of day it is. Built by
  post-stratification over cached (direction, hour, 0.25-ATR stop) cells — resampling per table row
  was ~200M bar steps and the first draft did exactly that.
  🔴 **CONFLUENCE IS READ OFF A PRE-SWEEP SNAPSHOT, and the first version was ORDER-DEPENDENT.**
  Several families routinely hold a level at one price — a session low that is also PDL is one line
  on the chart — and scoring off the mutated live-level dict meant whichever fired first was the
  only one the next could still see: the four levels swept at 1192.89 reported four DIFFERENT
  confluence sets, descending as they were popped. The structure-vs-session-vs-both answer is
  decided entirely by that set.
  ⚠ **The engines own the LEVELS; this tool owns the TRIGGER.** `ev.mitigated` is deliberately NOT
  read — day/session/H4 mitigate on a bare wick while week mitigates on a close-through, so it
  would score five families on three different triggers and call the difference a level effect.
  Only `ev.created` / `ev.evicted` are consumed.
  ⚠ **Median stop is 0.69 ATR — a few dollars on gold against a $0.12–0.33 round trip.** The tool
  prints that warning itself and names `--min-risk-atr 0.5`. No costs, no ladder, no position slot:
  a prior for a LEVEL, never a strategy's number.
  ⚠ **`--min-risk-atr` defaults to 0** (honest for a study, wrong for a strategy) and it is the
  cut that decides whether structure's edge clears 2σ. Quote both.

- **`tools/pre_sos_leg_queued.py` and `tools/pre_sos_leg_tune.py`** (2026-08-25) — the one-position
  version of the study below, and the settings sweep built on it. Both IMPORT the study rather than
  restating any rule, so they cannot drift from it.
  🔴 **A STUDY WITH NO POSITION SLOT REPORTS AN UPPER BOUND, AND THE TOOL BELOW SAYS SO IN ITS OWN
  DOCSTRING WHILE ITS NUMBERS WERE QUOTED AS THE STRATEGY'S.** Measured: 228 setups → **200** a
  one-position strategy can reach, and the 28 it cannot are BETTER than average. **Ask what a study
  assumes about concurrency before quoting it at a strategy that holds one trade.**
  🔴 **SWEEP WITH THE SLOT ON — it changes which setting WINS, not just the score.** An exit that
  ends a trade sooner hands the slot back and buys the next setup, so it is worth more than its
  average outcome says: the winning exit here rates +0.349R against +0.310R with no slot (marginal)
  and +0.400R against +0.276R with one (decisive).
  🔴 **A ONE-AT-A-TIME SWEEP CANNOT SEE AN INTERACTION, SO ITS WINNERS ARE CANDIDATES.** The single
  best change measured alone — two liquidity levels agreeing — cut the return by more than half once
  the winning exit was also in, and its two time-halves fell apart. **Run the combination before
  believing any of it**, and re-check on both halves of the history.
  ⚠ The exit walks return the bar a trade was let go on, which is what the slot needs; that value
  was always computed and thrown away. Adding it moved no number the study reports — verified by
  re-running and diffing the whole report.
- **`tools/pre_sos_leg_grid.py`** (2026-09-01) — the cartesian product, the timeframe question, and
  the search for a rule that removes losers. Imports the study and the one-position rule; restates
  neither. 509,000 configurations run through it so far.
  🔴 **A SEARCH THIS SIZE HANDS BACK A WINNER WHATEVER THE DATA IS, so the tool is built around
  refusing to report the top row alone.** Three defences, and the middle one earned its keep on the
  first run: every configuration is scored on both calendar halves and ranked by the WORSE one; the
  winner's NEIGHBOURS are printed on every axis; and the shipped configuration is printed beside
  each ranking so "is this actually better" needs no arithmetic.
  🔴 **PRINTING THE NEIGHBOURS IS THE PART THAT CHANGED AN ANSWER.** A fine pass named a setting 4%
  better than shipped; its neighbours across single steps ran 74 / 87 / 83 / 75 / 77 / 74, so the
  axis moves 10R between adjacent values and the winner was a coin. **A hill and a spike look
  identical from the top — the only way to tell is to step sideways.**
  🔴 **A CHALLENGER MUST BE RE-TUNED BEFORE IT IS DISMISSED.** Holding one chart's settings and
  applying them to another only proves settings do not transfer, which nobody doubted. The
  30-minute chart got its own full 252,000 and still lost by more than half.
  🔴 **A CUT IS APPLIED BEFORE THE POSITION SLOT, NEVER BY DELETING ROWS FROM A RESULT.** Refusing a
  setup has to genuinely buy whatever came next; scoring it the other way measures a strategy that
  could see the future, and it flatters every cut ever tried.
  ⚠ **The loser-hunting stage is the most overfittable thing in the file and says so** — it searches
  for a NEW rule using the losses it is trying to remove as the thing that suggests it. Its axes are
  deliberately restricted to cuts a trader can state a reason for; an hour-by-hour cut is not
  offered, because it would win and it would mean nothing.
  ⚠ **The whole product finishes only because the exit re-walk is shared**: a filter cannot change
  when a trade ended, only which trades are looked at, so each pool is re-walked once per exit rule
  and every filter underneath reads the same answers. 252,000 configurations in 291 seconds.
  ⚠ **One real bug found and fixed here**: a target that lands a rounding error from the entry price
  divided by zero in the walk. It only reaches that state on same-frame pairs; the shipped pair
  re-ran byte-identical afterwards, so no documented baseline moves.
  ⚠ `MINUTES` in the study gained a 4-hour entry so the timeframe question could be ASKED. Additive
  only — every existing default names its own frame, so nothing that ran before runs differently.
  🔴 **`--stage ladder` GOT ITS ANSWER WRONG THE FIRST TIME, PURELY FROM ITS AXES.** It offered
  only two-stage exits whose second leg ran FURTHER than the shipped one; every one lost, by up to
  5.5R, because with a single slot the runner holds 625 minutes against 400 and blocks ten setups
  doing it. Widening the axes so a ladder could also finish SOONER moved the best from −5.5R to
  +1.8R. **A search that can only move a setting one way has decided the answer before it runs —
  ask which direction an axis is allowed to go before believing what it reports.** (The +1.8R was
  then refused anyway: its four nearest neighbours span +81.8R to +85.8R around a shipped +84.0R.)
  🔴 **`--stage costs` EXISTS BECAUSE THE PARENT STUDY CHARGES HALF THE SPREAD AT ENTRY AND NOTHING
  ELSE**, and that model was quoted at a strategy about to trade money. Measured on the live tier:
  the whole bill is 4.0R over eight years, ~4.6% of gross, and **financing is the largest part of it
  (2.46R) rather than commission (0.63R)**. ⚠ **The live account is CHEAPER than the feed every
  number was measured on** — half the spread beats the commission it charges — so the honest
  correction went the good way for once, and it also clears two extra setups because a tighter entry
  leaves the target further away in stops.
  ⚠ **The tier's spread goes into the COLLECTION, never on top of the result.** It moves the entry
  price, which moves how far the target is in stops, which moves what qualifies — re-pricing a
  finished trade list would miss all of that.
  ⚠ **The spread is charged twice for a loser and once for a winner**: entry is a market fill, the
  target is a resting limit that fills at its own price, the stop is a market order that pays again.
  ⚠ **Costs are in R and that makes a TIGHT stop expensive** — one lot risks the stop distance times
  the contract size, so a fixed commission is a far larger slice of a small risk.
  ⚠ **The cost constants are COPIED from `fills.py` rather than imported**, because that module
  needs the whole replay stack and this tool is stdlib-only by design. Each is quoted with its
  source. **Re-read them before quoting the table again — this symbol's swap moved 1.7% in three
  weeks with nothing to announce it.**
- **`tools/pre_sos_leg.py`** — **the leg BEFORE the shift of structure. The A+ bot waits for the
  shift and fades the retracement; this asks whether the move that CREATES it is tradeable.** Added
  2026-08-24 on Aaron's question. Stdlib only, runs off `backtest/cache/`. Full record:
  `docs/PRE_SOS_LEG_STUDY.md`.
  🔴 **THE EXTREME IS ONLY KNOWABLE AFTERWARDS, so the whole tool is about finding a REAL-TIME
  proxy for it.** The prize is real — measured over 811 external breaks, the extreme-to-break leg
  is a median **$20.55 / 7.7× ATR(50) / 36 bars, ~106 a year**. Getting on it is the entire problem.
  🔴 **CONFIRMING ON THE BASE FRAME IS DEAD, AND THE NUMBER THAT KILLS IT IS `medR 0.87`, NOT THE
  EDGE.** By the time the M15 changes character internally, the target sits CLOSER than the stop —
  the setup arrives having already spent its own reward. **A confirmation that is late is not a
  weak signal, it is an absent trade**, and a tool that only reported win rate would have scored it
  50.9% and looked fine. Report the R AVAILABLE beside every hit rate.
  ✅ **What survives: a 15m level swept, then a change of character on the 5m within 3h, the 15m
  trend still opposing, target ≥2 stops away.** n=228 over 9 years, hit 28.1% at medR 3.67,
  **+0.296R against a matched control at 21.6% (+2.2σ)**; two level families agreeing n=112,
  +0.386R (+2.4σ). ≈25 trades a year.
  🔴 **ITS ARMING RULE IS LOOSER THAN THE STRATEGY IT MEASURED, MEASURED 2026-09-01 BY DIFFING THE
  TWO, AND EVERY NUMBER ABOVE CARRIES IT.** Two differences, both in when a sweep counts as fresh:
  this tool dates a sweep at the BASE frame's bar CLOSE while the strategy dates it on the 5-minute
  bar that crossed (so the window reaches 5–15 minutes further back here), and this tool counts
  wall-clock MINUTES while the strategy counts BARS (they agree while bars are contiguous and part
  company across a weekend). ⚠ **Neither invalidates a result and both change what one DESCRIBES.**
  ⚠ **Do not "fix" this tool to match** — that silently re-bases every number already recorded
  against it. A study is allowed to be a study; what it may not be is undocumented. The thing that
  settles the question is the port's parity gate
  (`strategies/python/mpc_extreme_leg/tools/compare_extreme_leg.py`), not another run of this.
  🔴 **The SWEEP is the ingredient and it is not close: the identical trigger with no level under
  it is 18.2% and −0.186R.** Session (+14.4%) and daily (+16.7%) are the strong families, h4
  (+5.7%) the weak one that still works, weekly n=8 and unanswerable.
  ⚠ **Its confluence result CONTRADICTS `sweep_edge.py`'s** (stacking families helps here,
  monotonically; there it hurt) and neither is wrong — that study scored a fixed 2R target off a
  wick stop, this one a structural target off a faster-frame confirmation. **Confluence is not a
  property of the levels alone.** Re-quote either number only with the target it was measured on.
  ⚠ **Banking early buys nothing** — exiting anywhere from 0.5 to 1.0 of the way pays +0.31 to
  +0.35R, flat. And the failure shape is early: most losers die under 30% of the way, while a trade
  80% there finishes 87.8% of the time.
  🔴 **AN EARLY MOVE TO BREAKEVEN COSTS −0.217R A TRADE, AND THE BEST ARM POINT IS WORTH A
  ROUNDING ERROR.** Measured by re-walking every qualifying trade with the stop moving to entry at
  a given fraction: arming at 30% takes the win rate 28.1% → 16.2% while losses only fall
  71.9% → 50.9%, so **the trades a breakeven stop "saves" are overwhelmingly ones that were going
  to win** — this setup's retracements happen INSIDE the leg, not before it. The peak is ~70%
  (+0.024R) and 90% is +0.000R. **Leaving the stop alone entirely is within noise of the best
  setting and is one less thing to get wrong live.** ⚠ A scratch is booked at −(half spread)/risk,
  never at zero — the entry carries half the spread and exiting at entry returns the other half.
  ⚠ **The arm is decided on a BAR CLOSE, never intrabar**: nothing in a bar says which extreme came
  first, and arming intrabar exits at a price the model could not have known to place. That
  flatters the breakeven rows and they still lose.
  ⚠ **It reads ONE private field of the structure engine** (`_ext.ash`/`_ext.asl`) — the swing that
  is live RIGHT NOW, which the public stream cannot give because events fire on CHANGE, not on
  STATE. The alternative was rebuilding that state here, which is the second implementation rule 21
  exists to prevent. **Guarded: a rename raises on the first bar rather than quietly scoring zero.**
  🔴 **A FASTER CONFIRMATION FRAME IS NOT A CHEAPER VERSION OF THE SAME IDEA — `--confirm M1`
  gets the stop down $7.24 -> $4.35 and takes expectancy +0.296R -> +0.032R.** The hit rate falls
  faster than the payoff rises. ⚠ **And the M1 row carries the HIGHER SIGMA (+3.2σ vs +2.2σ),
  which is the trap**: σ scales with √n and M1 fires 12× as often, so ranking rows by significance
  picks the worse trigger. **Read the expectancy; sigma only says whether it is real.** ⚠ Per YEAR
  they look close (≈+7.5R vs ≈+9.9R gross) and COST is what separates them — `--spread 0.44`
  charges the whole round trip at entry and takes M1 to **+0.002R** while M5 is unmoved at
  +0.307R, because a full spread is ~1.5% of a $7.24 stop and ~5% of a $4.46 one. 🔴 **M1's edge
  over the control SURVIVES this (+2.3% / +3.1σ) — it really is detecting something, and it is
  still not worth trading, because what it detects is smaller than the cost of acting on it.
  "Beats random" and "worth trading" are different questions and only the second has a broker in
  it.** ⚠ Level-stacking helps M5 monotonically and does
  NOTHING on M1 — **a filter that works on one frame and not the other says the two triggers are
  not detecting the same event.**
  🔴 **`--trigger reclaim` AND `--entry-on-base-close` EXIST TO SETTLE AN ARCHITECTURE QUESTION
  BEFORE A LINE OF PINE IS WRITTEN, and both answers were needed.** The single-frame stand-in (a bar
  closing back beyond the sweep bar's extreme, no second engine) scores **+0.082R against the 5m
  change of character's +0.296R**, and filling on the next base close instead of the confirmation
  close costs about a quarter of the edge (**+0.223R, +3.1σ**). **So the faster engine is not a
  convenience somebody could skip — it is what carries the result**, and the Pine has to embed a
  second state-machine instance. ⚠ **Measure the cheap architecture before building the expensive
  one**; the reverse order is how a file gets written twice.
  ⚠ **228 trades, three losing years inside them** (2021, 2023, 2024) against a 2025-26 that carries
  half the result. Found on PU Prime, reproduced on Vantage; costs are half a spread on entry and
  **no commission, so the live ECN account is not modelled.** A study, never a backtest.

- **`tools/killzone_profile.py`** + **`tools/killzone_sweep.py`** — **is the New York kill zone
  special, or does it just look special because we watch it?** Added 2026-08-04, stdlib only, runs
  off `backtest/cache/`. The profile tool measures what price DOES in a window and reports the same
  statistics for every other NY hour, so nothing can look remarkable until you have seen the base
  rate. The sweep tool then replaces its crude "took out the last seven hours" proxy with the real
  `engines/liquidity/` levels — PDH/PDL, PWH/PWL, H4 sweep targets, each finished session's high and
  low — and asks which level, when taken, actually precedes a reversal.
  🔴 **The answer is a REFUSAL and it is unambiguous. There is no clock edge and no level edge in
  KZ1** (2,031 days, 2018-09-21 → 2026-08-11, re-run 2026-08-13). At +2h the 10:00–11:00 window
  reverses the leg into it **49.0% of the time — a coin flip, and the LOWEST rate of the twelve
  hours measured**, i.e. the hour everyone watches is the least reversal-prone one on the board.
  The naive fade is **−0.087R over 2,026 trades** and loses in eight of nine years.
  ⚠ **The interesting half is that REAL levels did not rescue it, and that is the whole point of
  the second tool.** A real level is swept in this window on 63.2% of days, and **every single level
  is negative** when you trade the sweep's own direction — H4 highs −0.083R, H4 lows −0.071R, and
  the "classic" ones are the worst of the lot (PDH **−0.264R**, Asia H −0.238R, London H −0.191R).
  The crude proxy's apparent lift (a losing fade −0.117R → −0.011R on swept days) does **not**
  survive being given actual liquidity levels. ⚠ **One cut is positive — "sweep OPPOSES the fade",
  +0.076R on 189 trades — and it is the only positive number in three tables of dozens. Treat it as
  what a search over many cuts produces by construction, not as a finding.** ⚠ These are two
  STUDIES, not strategies: no costs, no ladder, no confluence, stop wins any ambiguous bar. They say
  the trigger carries no information; they do not price a finished system.

- 🔴 **All three study tools above were BRICKED from the day `FEED_VERSION` went to 3 until
  2026-08-13, and the fix is a standing lesson about version pins.** `killzone_profile.py`,
  `killzone_sweep.py` and `h4_sweep_profile.py` each guard their clock arithmetic with a cache
  version check, because v1 bars are stamped in broker-local time and every session boundary would
  be silently wrong. Correct instinct. But all three wrote it as `if version != 2` — an EQUALITY —
  when what they meant was a FLOOR. **v2 → v3 added the VOLUME column and did not touch a single
  timestamp** (`backtest/data/cache.py`), and these three tools read price and the clock only, so v3
  is strictly better input than the v2 they demanded. They refused it. ⚠ **The refusal MESSAGE was
  worse than the refusal**: it said "version 1 bars are stamped in broker-local time", sending the
  reader off to re-pull 186k bars to fix a bug in one line — a diagnostic reporting on a hypothesis
  rather than on what it actually found. ✅ **The fix is proved, not assumed: `h4_sweep_profile.py`
  re-run on the v3 cache reproduces `docs/H4_SWEEP_STUDY.md` EXACTLY** — pivot reversal @2R, n=145,
  +0.210R gross, $5.75 median stop, **+0.151R net**, every figure identical to the v2-era run the
  doc records. That is the evidence the bump was orthogonal to the clock. **Pin a floor when you
  mean a floor, and ask what a version bump actually CHANGED before refusing on it.**

- **`tools/bos_sweep.py`** — ⚠ The Pine it is measured against is `indicators/strategies/mpc_bos_strategy.pine`
  since 2026-08-13; the `.pine` sources were split into `indicators/strategies/` and
  `indicators/engines/` by their DECLARATION, so a path here from before that date is stale.
  **Comment-only — no documented baseline in this file moves and no stored run re-prices.**
  🔴 **DO NOT QUOTE ITS NUMBERS. FALSIFIED 2026-08-07, the day it was
  written.** On the same symbol, timeframe and window, with the config confirmed identical by the
  Pine's own `[CFG]` echo, this tool reports **20 trades / 80% win / PF 2.97 / +102.5%** where the
  TradingView Strategy Tester reports **24 trades / 66.67% win / PF 1.043 / +5.01%**. The Tester is
  the ground truth. **Entries roughly agree; the EXIT LADDER does not** — this model extracts far
  more from its winners than the Pine does. It is kept because its METHOD is sound and reusable
  (matched drawdown budgets, paired jitter, resolvable-stop screening, matched random controls) and
  because fixing it is cheaper than rewriting it. **Every result must be treated as unverified
  until `compare_bos.py` is green.** See `docs/MPC_BOS_OPTIMIZATION.md` → Run 8.
  ⚠ **Its own docstring warned it was a model rather than the strategy, and that was not enough** —
  a table of numbers reads as a finding whatever caveat sits under it. The check that falsified it
  was ONE Strategy Tester run, available the entire day it went unrun.
  Added 2026-08-07; it chose that file's current defaults (Run 7 in `docs/MPC_BOS_OPTIMIZATION.md`), and it
  exists so that answer is reproducible rather than asserted. Stdlib only, same as `trigger_edge.py`,
  and it reuses that tool's `drop_coarse()` reasoning. Modes: `sensitivity` (one lever at a time),
  `frontier` (the cartesian, ranked at a matched drawdown budget), `settle` (paired jitter
  head-to-head). ~35,000 configurations over 186,384 M15 bars; `frontier` takes ~40s on 12 cores.
  ⚠ **It models ONE POSITION SLOT, because the Pine is a `strategy()`.** Scoring setups
  independently counts trades the strategy could never have taken and lets a winner and the trade it
  would have blocked BOTH score — the queue effect this repo has now measured three times, and twice
  the cheap estimate had the SIGN wrong.
  ⚠ **It charges spread AND swap per night held**, and swap keeps MT5's sign, so gold's short-side
  CREDIT stays a credit. A strategy that holds overnight cannot be ranked without it.
  🔴 **Its load-bearing output is not the R column — it is the TIGHTEST-TENTH STOP printed beside
  every row.** R = profit / stop, so a stop model that produces small stops inflates every R in the
  book without one extra dollar being made. The first leaderboard this tool ever produced was
  entirely configurations with a **median 74-cent stop** reading +250R to +450R, on an instrument
  whose spread is $0.22 — numbers a 15-minute bar cannot even resolve, since inside one bar price
  crosses that spread constantly. **Ranking on R alone cannot see this. Never rank a stop model on R.**
  ⚠ **Configurations are compared at a MATCHED DRAWDOWN BUDGET** (`risk_for_dd`), not at equal risk:
  summing R treats a 25R drawdown as three times worse than an 8R one, when at 10% risk it is the
  difference between giving back 30% and giving back 93%. It is the only way a 55-trade book and a
  600-trade one can be ranked together.
  ⚠ **That budget metric is NOISY — a factor of two across jitter seeds on one configuration** — so
  `settle` scores every finalist on the SAME jittered series and compares pairwise. Unpaired medians
  had the old and new defaults tied (42.8x vs 42.3x) purely because the real price series is unlucky
  for one and lucky for the other; pairing separated them 32-8.
  ⚠ **Two look-ahead traps are deliberately avoided and both were made and caught here**: the VWAP
  side is read off the PREVIOUS closed bar (reading it off the fill bar's own close selects bars that
  recovered — worth a fake +9%), and the FILL BAR MAY NOT STAGE THE STOP, which is
  `BUG_exit_fill_price_mismatch`.
  ⚠ **It is a MODEL of the Pine, not the Pine.** No `compare_bos.py` exists yet, so nothing here has
  been diffed against the strategy's own decision stream. Read its results as a strong prior.

## `setups.py` — the contract a strategy fills in to report what it is WATCHING (2026-08-13)

The SHAPE of a pre-trade setup alert, so `algos/live/setup_alerts.py` never knows which strategy
it is talking to. A strategy answers `live_setups()` / `drain_setups()`; nothing else changes when
a new bot wants alerts. Messages, wording and volume: `docs/LIVE_SETUP_ALERTS.md`. The build
narrative is in `docs/BACKTEST_BUILD_NOTES.md`.

- **`met`/`of` are DERIVED from the confluence list, never stored.** That is what stops "2 of 3"
  being a hardcoded number: a four-confluence strategy reports 3 of 4 with no change downstream.
- **It lives HERE because it is the one layer both `algos/live/` and `strategies/python/` already
  import, and a strategy must NEVER import `algos/`** — that points the deployable at the
  deployment.
- **`zone` and `entry` are different questions; neither substitutes for the other.** `zone` is
  `(shallow, deep)`, the whole tradeable range, known as soon as the setup arms — the thing worth
  saying BEFORE an order exists. `entry` is the one price an order rests at, `None` until there is
  one. No meaningful range ⇒ `zone=None`, never collapsed onto `entry`.
- **REPORTING ONLY, and proven by REPLAY rather than argued.** Adding it to a strategy means
  replaying full history at HEAD and at the working tree and requiring a byte-identical trade
  list. For `mpc_sos_fade`: 155,807 M15 bars, **159 trades / sum R +142.177389, SHA-256
  `b52816e7…` identical both sides** — the documented baseline to six decimals. **No stored run is
  re-priced and no documented baseline moves.**
- **`implements_contract` must not CALL the method.** A question about SHAPE may not execute
  strategy code, and a `try/except AttributeError` around a call swallows a genuine error inside a
  real implementation as "not implemented".
- 🔴 **`reports_setups = False` opts a subclass out, and it exists because INHERITANCE produced the
  empty-registry failure by itself.** `mpc_bleg` and `mpc_bos` subclass `mpc_sos_fade`'s
  `Execution` and both set `_records_misses = False` — the flag gating the one method that
  populates the setup context — so they inherited a `live_setups()` returning `[]` on every bar
  forever. A method-presence check called them supported. **An empty registry answering
  confidently, arriving through a base class rather than a literal `{}`.** It is DERIVED from
  `_records_misses`, so a new fork cannot acquire a silent, empty channel by forgetting a line.
- **`announce_resting` (2026-08-14) gates the "limit resting" MESSAGE and nothing else** — not the
  root, not the outcome, never a trade; the order is still placed the moment the setup arms.
  **The STRATEGY decides when its own resting order is worth announcing**, because only it knows its
  geometry — this layer has no price and must never learn what a fib is. ⚠ **Defaults True**, so a
  strategy that does not implement it announces as before; the opposite default would make a
  forgotten line look like a quiet market. 🔴 **Setting it False owes a guarantee that it goes True
  before any fill it would suppress**, or a real trade reaches the trades room unannounced —
  `alert_rate.py` checks exactly that, and it is `tradeable`'s failure mode one field along. For
  `mpc_sos_fade` the guarantee is geometric, not measured: the threshold is shallower than the 0.5
  entry band, so price cannot fill without crossing it. **No baseline moves — 155,807 M15 bars at
  HEAD and on the working tree give an identical 159-trade list, sum R +142.177389.**
- **`tradeable=False` means the strategy has ALREADY decided no price path reaches a fill**, and
  the alert layer suppresses those (Aaron: *"I should only be getting signals for the trades
  originating from my default settings"*). ⚠ **A merely-unmet confluence is NOT untradeable** — it
  is the normal state of every setup before it fills, and getting this wrong hides real signals
  silently. A rule that can lift while the setup is alive belongs in `blocked_by` instead.
- **`alert_rate.py` CHECKS the invariant that every trade was announced first** — 159 trades
  closed, 158 ENTERED, the one gap being the warm-up boundary. It prints 🔴 BROKEN above one,
  because that is precisely how `tradeable` fails: suppress one setup too many and a real trade
  reaches the broker never having been signalled, with nothing reporting a skipped message.
- 🔴 **A strategy that has not implemented it gets NO alerts and the runner SAYS SO by name at
  startup — never a silent `[]`.** That is the empty-registry shape that had three jobs here
  running for weeks reporting success; *no setups* and *cannot ask for setups* must not be the
  same value. **Do not stub it to make a bot "supported".**
- **`tools/alert_rate.py` measures the volume, and it drives the REAL pipeline** with the sender
  replaced by a collector — so it counts messages SENT, not transitions underneath them. 🔴 **Those
  differ by 2x and the spec's guess was wrong**: it inferred ~3/month for the resting-limit alert
  where raw transitions give 665 over 6.5 years and per SETUP it is 332 (4.2/month), because a
  limit is rebuilt every bar and flickers. End-to-end: **20.2 messages/month, one every 1.5 days,
  26% of announced setups became trades.** It also CHECKS the invariant that every trade was
  announced first (159 closed, 158 ENTERED — the one gap is the warm-up boundary) and prints
  🔴 BROKEN if more than one trade arrives unannounced. ⚠ **Re-run it per strategy and after any entry-logic
  change** — same standing as `overlap_audit.py`. It **REFUSES** for a strategy without the
  contract rather than printing a rate of zero, and it accepts EVERY Python strategy including
  those — an honest refusal naming why beats argparse rejecting the name as though the strategy
  did not exist.

## Portfolio stacking (`backtest/portfolio/`)

Stack several strategies onto ONE shared account — one balance, one live risk budget the legs
compete for. Design + plan: `command-center/docs/PORTFOLIO_STACKING*.md`. Pure, offline, app-agnostic
(same discipline as `output.py`). Phase 0 + Phase 1 built 2026-07-17; lab wiring (Phase 2+) is future.

- **`combine.py`** — the cheap SCREEN. `combine_runs(legs)` adds up finished STANDALONE runs (their
  stored `daily_pnl`): combined curve, daily-return correlation, diversification drawdown, per-leg
  contribution. Idealized UPPER BOUND — it assumes every leg trades a full account and never gets
  blocked, so it OVERSTATES the stack. A candidate screen, not the demo result.
- **`account.py`** — `PortfolioAccount` (the broker): one balance; open trades RESERVE risk measured
  to their CURRENT stop (→ 0 at breakeven, freeing room); cap = % of live balance; `request_fill`
  **scales the leg's own desired qty** to the room (shrink-to-floor) — it never re-derives the qty,
  which is what preserves strategy parity (the bot sized off the limit price at placement).
  `request_fills` batch-splits same-bar ties by weight. `book_pnl`/`close_position` (or `on_close`),
  `update_stop`, a `contention` log stamped with `now`. **`SoloAccount`** = one leg, no cap, always
  full size = standalone behaviour, and the parity anchor.
- **`clock.py`** — `merge_streams`: k-way merge of the legs' bar streams into time-ordered `Tick`s,
  co-timed bars grouped, stable leg order.
- **`simulator.py`** — `simulate(legs, account)`: steps the legs on the clock, orders
  **holders-before-flat legs** each tick so freed room is released before entries (release-before-entry
  without splitting the strategy's monolithic step), returns combined + per-leg trades + contention log.
  **v1 limit:** two flat legs filling on the EXACT same tick are first-come, not split-by-weight (the
  weighted split needs the strategy step split into decide/commit; `request_fills` is ready for it).
  **Optional `progress(tick_index)` / `should_cancel()` (2026-08-09)**, polled every `_CHECK_EVERY`
  (512) ticks, for a caller driving this from a UI — the lab does. ⚠ **A cancelled result is
  PARTIAL and says so (`cancelled=True`)**: it holds every trade closed up to the tick it stopped
  on, which reads exactly like a complete short backtest, so a caller must branch on the FLAG
  rather than on the trade list and must never persist a partial book as a finished one.

- **`legs.py`** — `StrategyLeg` / `build_leg`: one real `strategies/python/` bot wrapped as a leg
  the simulator can drive (an `EngineStack` plus the strategy, stepped exactly the way
  `optimizer._replay_one` steps it). **Each leg owns its own stack**, which is not an optimisation
  to remove: the two bots pin different engine inputs (`mpc_bleg` forces `eq_exempt_fvg` off where
  A+ forces it on), so one shared stack would replay at least one of them against a market it never
  saw. It uses `stack_config()`, never `engine_config()` — the second is the static Pine constants
  and a config whose POI source is order blocks needs the OB engine switched on. `exec_secondary`
  is **REFUSED**, the same call `run_sweep` makes: a leg is one bar frame, the re-entry needs
  `run_dual`, and replaying it single-stream returns a primary-only book that is then compared
  against controls that have the re-entries in them.
- **`runner.py`** — `run_stack(specs, balance=, risk_cap_pct=)`: build the account, build the legs,
  simulate, **and replay each leg SOLO on the same bars**. The solo control is not a convenience —
  without it a difference in the shared book is a mixture of *the cap bit* and *the shared balance
  re-sized everything*, and nothing afterwards separates them. Refuses two legs sharing a NAME:
  the account keys an open position by leg name, so a duplicate silently overwrites a live
  reservation and the cap under-counts the open risk while reporting itself enforced.
  ⚠ **A cancelled run SKIPS the solo controls** (2026-08-09), and that is the load-bearing half of
  the cancel path: a control's whole job is to be comparable to the shared book, and a control
  over the FULL history beside a book that stopped a year in is not a control — it is two
  different experiments in one table, and the screen-vs-shared delta would read the missing year
  as the cap's doing.
- 🔴 **`LegSpec.source` — a leg may READ ANOTHER LEG'S CLOSED TRADES (2026-08-21).** The mechanism
  the loss-recovery rule needs: it has no setups of its own and arms off a primary's losses, so it
  cannot be an ordinary leg. `source` names another leg in the same stack; `run_stack` builds
  sources first, hands the dependent that leg's **live trade list object**, and gives it the
  frame's last bar and bars-per-day for its time stop. **Defaults `None`, so every stored stack is
  byte-identical** — with no sources the build order, the solo controls and the simulate call are
  all unchanged.
  🔴 **The list must be the OBJECT, not a copy, and that is the whole failure mode.** The dependent
  arms when a source trade CLOSES, so it reads a list that grows under it during the replay. A copy
  taken at build time is empty forever and the leg returns an empty book — **indistinguishable from
  a rule that genuinely found no setups.** Pinned by
  `test_the_dependent_is_handed_the_LIVE_trade_list_not_a_copy`, watched RED by `list(...)`.
  🔴 **A sourced leg's SOLO CONTROL gets a PRIVATE copy of its source**, on its own account, so only
  the measured leg books onto the control's balance. A sourced leg alone has nothing to recover, and
  an empty control makes the shared result look like the whole of the leg's worth rather than the
  part that survived the competition. ⚠ **The private source's trades are discarded on purpose** —
  it exists to lose, and reporting it would put a second copy of the source's book in the run.
  ⚠ **Three refusals, each with a silent failure behind it**: a source not in the stack (the
  dependent reads nothing), a leg sourcing itself, and a CHAIN — chains are refused rather than
  supported because the moment they are legal so are cycles, and a cycle here builds forever rather
  than raising. ⚠ **A leg handed a source that does not implement the contract is refused**, or the
  source is dropped in silence.
  ⚠ **`bars_per_day` is read off the leg's own `execution.bar_ms`**, which `StrategyLeg.__init__`
  has already measured — two readings of one fact are how they come to disagree.
  **Where this is going:** `docs/RECOVERY_LEG_IN_COMMAND_CENTER.md`. 10 tests in
  `tests/test_stack_runner.py`, 4 mutations each reddening exactly its own case.
- 🔴 **`legs.py` REFUSES a leg whose `exec_recovery` is on, and the reason is that it does NOTHING
  here (2026-08-21).** That switch runs from a `finalize(df)` hook the simulator never calls — it
  steps bars and never drives `run()` — so the leg came back with its recovery trades **silently
  missing**. No error, no empty list to notice, just a smaller book than the same settings produce
  anywhere else, reaching a comparison table looking ordinary. It joins `exec_secondary` at the same
  seam, for the same class of reason. ⚠ **No stored stack moves** — checked, not assumed: 0 of the
  6 stored stack leg runs had it on. ⚠ **The recovery belongs in a stack as its own LEG**, which is
  the version that competes for the budget; the switch cannot compete by construction, because it
  reads a book that has already finished.
- **`tools/stack_run.py`** — the CLI. Prints the shared book beside the solo controls, what the
  account CARRIED, and the contention log.
- **The LAB drives the same object** (`command-center/backend/services/portfolio_runner.py`,
  2026-08-09) — it CALLS `run_stack` and owns no account model of its own. ⚠ **Anything tuned here
  is the rule the live allocator has to enforce**, or the stacked backtest stops predicting the
  stacked account.

### The shared-account run — MEASURED 2026-08-09

```
python backtest/tools/stack_run.py --start 2020-01-01 --end 2026-08-06 --balance 10000 --risk-cap 10
```

**155,807 M15 bars, A+ and B-LEG on one $10,000 account, cap 10% of the live balance:**

| leg | shared trades | shared R | solo trades | solo R | solo closing |
|---|---|---|---|---|---|
| `mpc_sos_fade` | 159 | +142.18 | 159 | +142.18 | $54,683,172 |
| `mpc_bleg` | 99 | +17.87 | 99 | +17.87 | $31,064 |
| **shared account** | **258** | **+160.04** | | | **$204,918,789** |

✅ **The seam is proven NEUTRAL, which is the whole point of the first run**: every leg posts the
SAME R shared as solo, because R is normalised to the trade's own risk and nothing was refused.
The shared account changed the DOLLARS — one balance compounding both legs — and moved no decision.
A+ also reproduces its documented 159 / +142.18R baseline to the cent, which is the cross-check
that this drives the real strategies and not a third thing.

🔴 **AND NOTHING WAS EVER BLOCKED IN 6.5 YEARS, WHICH IS THE FINDING.** Peak open risk touched
**exactly 10.00%** — the cap — with **2 of 2 legs holding at once**, and the contention log is
EMPTY. The reason is the reservation model and it is the part worth carrying: **open risk is
measured to each trade's CURRENT stop, so a stop moved to breakeven releases its room**, and
`mpc_sos_fade` touches breakeven on 161 of 161 trades at a median of ONE BAR (measured 2026-08-06).
So by the time the second leg wants in, the first is reserving nothing. ⚠ **Read that as "the
allocator would rarely have had anything to arbitrate", never as "a cap is unnecessary"** — it is
the overlap audit's shared-bars result arriving through the budget (27 when this was written,
**45 with ZERO same-side at the 2026-09-01 re-run** — `docs/LIVE_TRADING_PIPELINE.md` → G14), and
the window where two bots really do carry 2× risk is the bar before the stop stages.

⚠ **A cap BELOW a leg's own risk % does not arbitrate, it re-sizes.** At `--risk-cap 5` against two
bots each risking 10%, all 258 entries are shrunk and NONE is blocked — every position is halved,
R is unchanged (it is normalised) and the closing balance falls $204.9M → $4.7M. That is the
shrink-to-fit design working, and it is a different lever from the one Aaron asked for; **blocking
only happens when a leg asks while the budget is genuinely full.**

🔴 **THE CONTENTION RULE IS NOW A CHOICE, AND IT IS STATED RATHER THAN IMPLIED.**
`PortfolioAccount(all_or_nothing=...)`. **False (default) = shrink-to-fit**, the behaviour every
stored run used. **True = *risk is never layered***: an entry that cannot be granted in FULL is
refused outright and the budget stays with whoever already holds it. ⚠ **Both obey the cap** — the
rule decides WHICH TRADE you end up in, never how much is at risk. ⚠ **It defaults OFF on purpose**;
a default that changed it would re-write every recorded run rather than add an option.

⚠ **It is deliberately NOT an entry floor, and the floor route was tried and abandoned.** A floor is
ONE number for the whole account while legs risk different amounts, so any floor high enough to make
a 10% leg all-or-nothing also bans a 2.5% leg outright whatever the room — MEASURED at **64 refusals
and 0 trades**, identical at a 10% and a 12.5% cap, which reads like an allocator verdict and is a
size ban. Asking the account *"was this granted in full?"* needs no per-leg number and holds for any
number of legs. ⚠ It rides on `_is_shrunk`, so it inherits that method's tolerance ON PURPOSE — a leg
whose own risk equals the cap misses by a float's last bit, and without it the rule would refuse
every uncontested entry.

🔴 **MEASURED, and the result is the argument for building PRIORITY next.** 186,910 M15 bars,
`puprime_ecn`, A+ 10% under a 10% cap with the loss-recovery leg (`recovery_stack.py
--on-contention refuse`): **176 A+ entries refused, 0 shrunk, A+ 127.11R → 85.05R, and the account
ends $13.2M → $1.0M (−92%) with drawdown 50.2% → 55.2%.** The cause is structural rather than a
tuning miss: **A+ risks the cap in full, so it needs the ENTIRE budget to trade at all, and the
moment the other leg holds anything A+ is refused.** A leg worth **$14,025 standalone over eight
years** locks out the one carrying the return. ⚠ **The account has no notion of leg PRECEDENCE** —
whoever asks first takes the budget and the legs are treated as equals, which they are not. **Do not
enable this rule on a real comparison until precedence exists.**

🔴 **LEG PRECEDENCE, and it is what makes `all_or_nothing` usable at all.**
`PortfolioAccount(leg_priority=..., leg_risk_pct=...)` — lower rank number = higher precedence.
**It cannot be "the better leg wins the clash"**: by the time the priority leg asks, the other one
is already holding the budget, and the only way to take it back is closing a live trade. So
precedence acts BEFORE the clash — **a priority leg's declared risk stays RESERVED while it is
FLAT**, and lower legs get only what is genuinely spare (`room_for`, `_headroom_for`).
⚠ **A priority leg that is already HOLDING does not also get headroom** — its real reservation is
in `reserved()` and counting it twice would halve the room; that double count is pinned by test.
⚠ **A same-bar tie is settled BY RANK, not proportionally**, or a junior leg dilutes the one it
defers to on the one bar they arrive together. ⚠ **Both default empty**, so every stored run is
untouched.

🔴 **MEASURED, same window and tier, and it flips the verdict on the whole rule:**

| cap | precedence | A+ | recovery | combined | maxDD |
|---|---|---|---|---|---|
| 10% | none | 85.05R, 176 refused | 60 trades | **$1,043,054** | 55.2% |
| 10% | A+ first | **127.11R, 0 refused** | **0 trades, 65 refused** | $13,199,534 | 50.2% |
| 12.5% | A+ first | 127.11R, 0 refused | 60 trades, 0 refused | **$17,074,731 (+29.4%)** | 50.4% |

**At a 10% cap with A+ risking 10% there is NO spare room, so a deferring leg never trades — and
that is the honest answer to "is the recovery worth taking room off A+", not a bug to soften.**
The rule only earns its place given headroom of its OWN. ⚠ **And the gain is +14.77R against A+'s
own ~15R jitter floor, so the COMBINED improvement is not distinguishable from noise on this
history** — the recovery leg's own 60-trade book having positive expectancy is a separate and
weaker claim. ⚠ Dollar columns rank runs against each other and are NOT a forecast: the largest
position in these runs is 1,821 lots and the lab models no broker maximum.

⚠ **Neither contention rule touches the peak open risk, and that was checked rather than assumed.**
The peak is set by the balance FALLING under a reservation already granted — overnight financing is
the big one — not by contention. MEASURED: **A+ alone with no second leg in the run reproduces the
identical 2,984 over-cap ticks and the identical 10.9140% peak.** See
`docs/CARRY_COST_AND_THE_DAILY_RISK_RESET.md`.

⚠ **This is the BACKTEST side. The live side is unbuilt** (`docs/LIVE_TRADING_PIPELINE.md` → G10)
and cannot reuse this object — live bots are separate OS processes, so the live allocator has to
read the broker's real exposure across magic numbers. **Whatever rule is tuned here has to be the
rule it enforces, or the stacked backtest stops predicting the stacked account.**

🔴 **The run found a defect in the contention log on its first pass and it is the useful kind.**
Before `_GRANT_EPS`, that same 6.5-year run logged **11 contention events totalling $0.00 of
refused risk** — every one float noise. `granted = min(desired, cap − reserved)`, and a leg derives
its qty by DIVIDING by the stop distance while the account re-MULTIPLIES by it, so an entry that
exactly fills the cap disagrees in the last bit and reads as a shrink. **A log that reports
contention where none occurred is worse than a quiet one**: downstream it puts "this trade was
shrunk" markers on a chart for trades granted in full, and it hides the real events among the
noise. Fixed with a RELATIVE 1e-9 tolerance on the shrink TEST only — the granted qty is still
scaled exactly — and pinned by two tests at the seam (one ULP short is not contention; a
thousandth of a percent still is), each watched red against its own mutation. ⚠ **The first
attempt at that test was VACUOUS and passed against the bug**, because the numbers it chose
(10,000 × 0.10 = 1,000.0) are exact in binary — which is why it now tests the rule rather than
trying to synthesise a balance that happens to round.

`account.sample_exposure()` was added in the same pass and is sampled once per tick by the
simulator, because **the contention log answers "was anything refused" and cannot answer "what did
the account carry"** — a reservation is recomputed from live stops and leaves no trace once they
advance, so a book holding two full positions all day can log nothing at all.

The strategy seam lives in the strategy (`mpc_sos_fade/execution.py` takes an injected `account`,
default `SoloAccount`; both strategy constructors thread `account` / `leg` through as of
2026-08-09) — see that package's CLAUDE.md. `compare_strategy.py` staying exit 0 with the
SoloAccount is the gate that the seam didn't move standalone behaviour.

⚠ **`build_strategy` REFUSES a strategy that cannot accept the account**, and for a sharper reason
than the `cost_profile` refusal it sits beside: a dropped cost profile under-charges a run, while
a dropped ACCOUNT sends the leg back to its own `SoloAccount`, which has an **infinite** budget and
always grants full size. The run would then report a capped, shared portfolio while that leg sized
off the whole balance and contended with nobody — a risk cap claimed on screen and enforced nowhere.

## Data layer (A0) — how it works

`backtest.data.BarSource.load(symbol, timeframe, start_date, end_date)` is the one entry point:
1. `resolve_base_tf` picks the base timeframe to pull — the target itself if the broker serves it
   (M1/M5/M15/M30/H1/H4/D1), else the largest served timeframe that divides it.
2. Base bars are served cache-first (`BarCache`, one CSV per symbol+tf under `backtest/cache/`,
   git-ignored). A miss fetches the whole window from the MT5 agent (`Mt5Agent`, HTTP on
   localhost:8766 via the SSH tunnel) and records the fetched date range (`RangeCoverage`).
   ⚠ **This hop is why a running PYTHON job counts as MT5 traffic to the command center's agent
   supervisor** (`command-center/backend/services/agent_supervisor.py`, 2026-08-02): a python
   backtest runs locally and touches no VPS terminal, but a cache MISS pulls its bars through this
   tunnel, so restarting the tunnel or the MT5 agent mid-fetch kills the run. If the data layer ever
   stops going through the agent, that coupling in the supervisor goes stale — change both.
   The corollary is the good news: a fully CACHED window needs neither the tunnel nor the agent, so
   a replay over bars already on disk is unaffected by anything on the VPS.
3. `resample_up` aggregates to the target timeframe if base ≠ target — **never down**.
4. The result is sliced to `[start_date, end_date]` inclusive.

**One request can't exceed the terminal's bar cap — `Mt5Agent.bars()` chunks.** Past
"Max bars in chart" (the classic 65,000) MT5 does not clamp or answer partially: it fails the whole
call with `(-2, 'Terminal: Invalid params')`, which reaches the client as a bare 404 "no data" —
indistinguishable from a symbol with no history. Measured 2026-07-21 on XAUUSD.s M15: 64,837 bars
fine, ~70,000 (3 years) dead, so a 3-year backtest could not load bars at all. `bars()` now splits
any long window into chunks sized from the timeframe against a 24h day (`_MAX_BARS_PER_REQUEST`
60,000), fetches each, and stitches them (dropping the shared boundary bar). A window already small
enough still makes exactly one call. (The terminal's own "Max bars in chart" was later set to
unlimited — see *history depth* below — but the per-request chunking stays: it is what makes a
multi-year window loadable at all, and it must not depend on a terminal setting nobody can see from
here.) **An empty chunk is not an error when others returned data** —
broker history starts somewhere, so a 3-year request against a shallower symbol now returns the
history that exists instead of failing; only "no chunk served anything" raises. `_read_error` also
surfaces the agent's `mt5_error`, which is what distinguishes the two cases.

**Backtest broker = Vantage demo (backtest-ONLY; live trading is always PU Prime).** Chosen so bar +
tick data match the `VANTAGE_XAUUSD` TradingView feed the strategies are designed against. MT5_Lab is
logged into the Vantage demo (account 25893735, `VantageMarkets-Demo`); **gold symbol is `XAUUSD`, no
`.s` suffix** (that was PU Prime). See `algos/CLAUDE.md` for the MT5_Lab pin.

**Don't hand-feed broker facts — pull them.** The agent has two read-only endpoints that read the live
terminal so spread/commission/swap/symbol and history depth never have to be typed in:
- `GET /symbol_info?symbol=XAUUSD` → digits, point, contract size, volume steps, live spread, and
  swap long/short straight off the symbol Specification. This is how `backtest/fills.py`'s
  `vantage_demo` profile was built (2026-07-22): **commission 0.00** (it is a demo — demos never
  charge), swap **−74.84 long / +26.98 short**, triple-swap Wednesday. Spread is NOT stored — it is
  measured live from the Vantage bid/ask tick stream.
- `GET /data_availability?symbol=XAUUSD&timeframes=M1,M5,M15,M30,H1,H4` → earliest→latest served bar
  per timeframe (cheap: one bar from each end).

## A profile also states how its broker SPELLS a symbol (2026-08-26)

`AccountProfile.symbol_suffix` — `".p"`, `".s"`, or `""` for a broker quoting bare names. Identity,
never a cost. MEASURED 2026-08-08 across three PU Prime logins and re-confirmed on the ECN terminal
2026-08-26: **the suffix IS the tier, and neither account can see the other's symbol.**

- ⚠ **Three-state, and `None` means nobody recorded it** — not "bare". A caller must leave the
  symbol alone and say so. PU Prime Cent is `None`; nobody has logged into it, and `XAUUSD.crp` in
  another account's Market Watch is not evidence of what Cent quotes.
- ⚠ **Nothing in this package rebases anything.** The field is data; the lab resolves it at run
  creation (`command-center/backend` → *The BROKER spells the symbol*), reusing the live side's one
  rebase rather than adding a second.
- 🔴 This is the missing half of the partition below: the cache learned WHICH broker's bars it
  holds, and this is the broker saying what it calls them. A run that asks for a symbol the
  terminal does not quote gets the same empty frame a closed market returns — rule 2, one level
  down.

## Standard and Prime record their LOGINS (2026-08-26)

`account` was blank on both, so a lab pointed at either could not be confirmed as the attached
terminal and the page said *"cannot tell which terminal is connected"* about a terminal it could
name exactly. **They were never unknown** — MT5_Lab was signed into all three PU Prime demos in
turn on 2026-08-08 to measure their swaps and symbols, and that block names every login.

- 🔴 **The ACCOUNT is the only thing that separates these tiers** — all three live on
  `PUPrime-Demo`, and their spreads are 2.7x apart.
- ⚠ **Cent stays blank and that is the field WORKING.** Nobody has logged into it, so the lab will
  honestly say it cannot tell rather than blessing a tier.

## 🔴 The cache is partitioned by BROKER SERVER (2026-08-24)

**The filename was `(symbol, timeframe)` with no broker in it, for as long as the cache existed.**
That was survivable only because exactly one terminal ever filled it — every one of the 12 probed
history floors on this machine reads `VantageMarkets-Demo`, so nothing was ever mixed. It stopped
being survivable the moment the lab gained a reason to point at a second broker: **the second
broker would have read the first one's bars and been charged its own costs**, and there is nothing
in a trade list, an equity curve or a metrics panel that could show you that. The two feeds here
are MEASURED to differ by a systematic 4-5 cents on every bar (2026-08-04 shadow diff), so the
result would have been wrong by a real amount while looking completely normal.

Bars and ticks now live under `backtest/cache/<server>/`. ⚠ **Keyed on the SERVER, not the account
tier, and that is measured rather than tidy** — MT5 keys its own store by server, so PU Prime's
Prime and ECN logins (both `PUPrime-Demo`) genuinely share one history, and partitioning per tier
would triple a 1.28 GB download for byte-identical bars. **Costs are what differ per tier**, and
they are charged from `fills.PROFILES`, never from the cache.

⚠ **An unknown server REFUSES** (`UnknownBrokerError`) rather than falling back to a shared or
`default` folder. That is rule 1 applied to a filesystem path: "cannot ask" must never take the
same value as "the usual broker". An unreachable agent refuses for the same reason.

⚠ **An explicitly injected `BarCache`/`TickCache` is honoured and NOT partitioned.** That is what
every test in this package passes, and it is a deliberate statement about where those bars live.
⚠ **This file said "all 20 production call sites construct `BarSource()` bare, so production
always partitions — checked, not assumed" until 2026-08-25, and it was true when written and stale
within the day.** Seven of them pin a server now (the rerun, the price chart's feed and its
drill-down, the stack runner, the stack backfill); the hand-run tools under `tools/` stay bare on
purpose, because a person invoking one is pointing it at the terminal they have attached. **A count
of call sites is a fact with a shelf life — do not quote this line either, run the search.**

⚠ **Partitioning is LAZY, on the first `load()`.** Construction stays free of network calls, which
is the property `HistoryFloors` already had; a tool that dies while building an object reports the
failure in the wrong place.

🔴 **A RERUN READS THE BROKER THE RUN WAS MADE ON — `BarSource(server=...)`, added 2026-08-24 the
same day and reported from the screen.** Aaron: *"when we click rerun charged it should still rerun
against the broker that the data originated from — otherwise all of my backtests will be broken."*
Exactly right, and the partition is what made it urgent rather than what caused it: **before, the
flat cache served the old broker's bars whatever was attached — wrong, but in the silent
direction; after, an unpinned rerun looks in the ATTACHED broker's folder, misses, and tries to pull
the run's window from a terminal that may not even quote its symbol.** The lab pins it from the
run's own `broker_profile` (`python_runner.bar_server`), so a stored run replays its own history and
only a NEW run follows the attached terminal.

⚠ **The pin is checked at FETCH time, never at partition time**, so a fully cached window still
replays with the terminal unreachable — a property this package already had and the pin must not
cost. ⚠ **A fetch on a mismatched pin REFUSES and names both brokers.** Merging is the failure that
cannot be undone: the file is one CSV per (symbol, timeframe) and **nothing in a bar records which
broker served it**, so a single wrong fetch is permanent and invisible. ⚠ **Serving the short cached
span instead would be worse than the error** — a narrower window than the caller asked for, silently.
⚠ **A profile with no recorded server pins NOTHING rather than guessing one**, which is what every
pre-2026-08-02 row is.

🔴 **THE PIN WAS THREE CALL SITES SHORT FOR A DAY, AND THE PRICE CHART WAS ONE OF THEM (2026-08-25).**
A charged re-run of a Vantage run completed with 247 trades and drew an EMPTY chart, because the
chart's own bar fetch was still bare and resolved the attached terminal. Fixed in
`command-center/backend` (its CLAUDE.md owns the detail); recorded here because the lesson belongs
to the PARTITION rather than to the chart. ⚠ **When a shared store gains a partition, the audit is
every construction of the thing that reads it — not the ones the reported bug happened to touch.**

🔴 **A WRONG-PARTITION READ HAS TWO OUTCOMES AND ONLY ONE OF THEM IS LOUD.** Aaron asked the right
question about that empty chart: *was it drawing PU Prime's prices under my Vantage trades?* It was
not — but the reason is worth writing down, because it is **not** a safeguard. A partition holds one
file per EXACT symbol name, and PU Prime's gold carries a suffix Vantage's does not, so the lookup
found no file, the fetch was refused, and the chart came back blank. **Had both brokers used the
same symbol name and the wrong partition happened to cover the window, it would have served the
other broker's prices with nothing anywhere to flag it** — no error, no empty result, just a chart
and a replay quietly measured on a different market. ⚠ **So the loud failure everybody saw was luck
(a symbol suffix), not design.** The design answer is the pin, and it is why the pin belongs on
every reader rather than on the ones that have been seen to fail.

⚠ **A flat cache from before this change is INVISIBLE, not wrong** — every read is a miss and the
bars come down again from whatever broker is attached. That is the safe direction to fail in, and
it is why there is no automatic migration. To keep the existing 1.28 GB, a human asserts which
broker filled it:

```bash
python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo --dry-run
python backtest/tools/file_cache_by_broker.py --server VantageMarkets-Demo
```

**Guessing the server would have written the exact claim the partition exists to prevent** — a
folder labelled with a broker whose prices may never have been in it — so the name is a required
argument. The tool refuses to merge into an existing partition, moves rather than copies (a flat
shadow of a 1 GB tick store is a trap), and COPIES `history_floors.json` because that file is
keyed by server inside and stays valid in both places.

⚠ **PU Prime's recorded M15 floor is WRONG — see the two defects below before trusting it.**

⚠ **PU Prime's history depth is its own fact. It is now partly known and is still NOT a measured
floor** — say the difference out loud rather than letting the next reader read a bound as a bottom.
`XAUUSD.p` M15 is cached from **2019-01-01 23:00 to 2026-08-23 23:45, 180,619 bars with volume**
(pulled 2026-08-24 in ~28s, verified off disk here rather than taken on report). ⚠ **2019-01-01 is
the earliest date anybody ASKED for, so the real floor is at or before it and nobody has looked** —
recording it as the floor would be rule 3 exactly: what you requested written down as what you
received. Vantage gold bottoms out at 2018-09-13 on M15; do not carry that number across either.
The floor probe re-runs per server on its own — that part was already right.

⚠ **Bare `XAUUSD` does not exist on this broker.** PU Prime quotes `XAUUSD.p`, and a request for the
bare symbol returns nothing at any date (checked 2019 and 2024). Eight runs died on it in one
evening before anybody noticed, which is the loud failure working as intended — but every stored run
made against Vantage carries `instrument: XAUUSD`, so a rerun of one on this terminal cannot fetch.

✅ **The migration has RUN on this machine (2026-08-24): 42 entries, 1.28 GB, now under
`cache/VantageMarkets_Demo/`.** That the server name was `VantageMarkets-Demo` is not an assumption —
all 12 probed history floors in `history_floors.json` carry it, so exactly one terminal has ever
filled this cache.

🔴 **The partition SILENTLY SKIPPED four tests and the suite still printed green**, which is the
lesson worth more than the feature. `tests/test_reprice.py` looks for the reference bars at a fixed
path and skips when they are absent — so the moment the files moved, the four slowest and most
load-bearing tests in the package (the real two-year replays that prove re-pricing reproduces a
charged run to the cent) went from passing to SKIPPED with nothing to notice. **A missing file is
indistinguishable from a git-ignored one.** It searches the partitions now.

⚠ **A profile now records the SERVER and ACCOUNT it was measured on** (`fills.py` →
`AccountProfile.server` / `.account`). Identity, never a cost — nothing charges either. They exist
because the partition fixes the BARS and leaves the COSTS free to mismatch: a run can legitimately
replay PU Prime's bars and charge Vantage's spread, which is the same defect one level up. The
Command Center reads them to default its cost account to the attached terminal; rules there.
⚠ **The account is what separates PU Prime's tiers** — Prime and ECN share `PUPrime-Demo`, so a
server-only match would hand a run ECN's $0.12 spread while it sat on Prime.
⚠ **Blank/None means UNRECORDED, never "matches anything".**

⚠ **A floors entry is keyed on the SUFFIX-STRIPPED symbol, by design** (`_key` → `_norm`, which
splits on the dot, because `.s`/`.p`/`.a` are the same underlying instrument's history). So
`PUPrime-Demo|XAUUSD|15` is the record FOR `XAUUSD.p`, not for a bare symbol nobody can fetch.
**An earlier version of this paragraph read it the other way round and reported a phantom defect** —
corrected 2026-08-24 after a peer session checked the code rather than the filename. A probe that
fails writes nothing at all, so an entry can never exist for a symbol returning no data.

🔴 **STILL OPEN, and it is worse than the phantom was: `PUPrime-Demo|XAUUSD|15 → 2018-09-13` is a
GENUINELY BAD FLOOR, and both checks that exist to catch it pass.** That day is HALF SUBSTITUTED —
MEASURED against the live terminal: **2018-09-13 returns 38 bars for an M15 request, with 18 gaps of
60 minutes, one 75-minute seam, then 18 gaps of 15 minutes.** PU Prime's real M15 history starts
partway through that day and everything before the seam is H1 wearing an M15 label. A clean day is
92–96 (2018-10-15 measures 92, with 90 gaps of 15).

Two defects, both reproduced here rather than reasoned about:

1. **`_day_is_real` counts BARS and never looks at their SPACING.** The threshold is
   `_DENSITY_MIN 0.35 × 96 = 33.6`, and 38 clears it. Its docstring's reasoning — *"a coarser
   substitution fails by a factor"* — is sound for a CLEAN substitution (H1-as-M15 is 24/96 = 25%
   and fails) and does not hold for a day that is **half** real.
2. **`assert_bar_spacing` cannot catch it either, which is the surprising half.** Run on that exact
   frame: the gaps tie 18–18, `gaps.mode()` returns `[15, 60]`, `.iloc[0]` takes **15**, modal
   equals requested, and it PASSES. Its `closer` test only hunts gaps SMALLER than the interval —
   there is deliberately no check for a sustained run of LARGER ones, because weekends produce
   those legitimately. ⚠ **Over a LONG window it gets worse, not better**: the modal is dominated
   by the real days and the substituted region never moves it.

✅ **THE DEFECT IS NARROWER THAN "the density check is broken", and this is the part that makes a
future fix SCOPED rather than a risky tightening.** All three cases, arithmetic checked:

| the day | bars of 96 | verdict | right? |
|---|---|---|---|
| entirely H1 substituted | 24 (25%) | fails the 0.35 threshold | ✅ correct, and by a wide margin |
| a short holiday session in clean history | fewer, but correctly SPACED | fails → floor lands LATE | ✅ safe direction |
| **history starts MID-DAY** | **38 (40%)** | **passes** | 🔴 **the only broken case** |

**So the rule is: the check is wrong exactly where a broker's history STARTS PART-WAY THROUGH A
DAY**, and nowhere else. A fix therefore has to catch a frame that is half correctly-spaced without
refusing a genuinely short session — which is why "tighten `_DENSITY_MIN`" is the wrong instinct: it
would push every holiday-adjacent floor later while still passing 38.

⚠ **Impact today is nil and that is not a reason to leave it** — nobody is starting a run there. The
risk is that the recorded floor INVITES someone to start on 2018-09-13 and receive ~18 hourly bars
inside an otherwise clean frame **with no error raised**, which is precisely the fictional-backtest
failure this module's own docstring says it exists to prevent.

⚠ **NOT FIXED HERE, deliberately.** `history.py` is money-path code and a stricter density or
spacing rule can refuse legitimate short sessions and holidays, so it needs its own measurement
across brokers rather than a tightening bolted onto a cache change. ⚠ **Do not paper over it by
deleting the entry** — it re-appears on the next load, and the floor would still be wrong.

Proof: `tests/test_cache_broker_partition.py`, watched RED **by mutation** rather than by revert.
Reverting only produced an ImportError, which proves a symbol is new and nothing about whether the
assertions catch anything. Flattening `broker_cache_dir` in place fails the two data tests on
*"broker B served broker A's cached ticks"*; replacing the refusal with a `default` folder fails
the two refusal tests on DID NOT RAISE.

## History floors — MEASURED per broker, and ENFORCED (`data/history.py`)

**The floor is discovered, never hardcoded.** `HistoryFloors.floor(symbol, tf)` binary-searches the
live terminal for the earliest date with real bars and caches it keyed on
`(server, symbol, timeframe)`, where `server` is the agent's `/status` server name
(`VantageMarkets-Demo`). Point MT5_Lab at a broker with deeper history and the floor widens on its
own; point it at a shallower one and it tightens. A hardcoded date would fail in both directions —
needlessly truncating the deep broker, and fictionalising the shallow one.

Probing asks one question per candidate day — *"does this day return a plausible number of bars for
this timeframe?"* — because **bar density is the one thing that cannot lie** (see the substitution
table below). Two phases, deliberately with opposite error tolerances: a holiday-tolerant cluster
test for the binary search (a false "no data" on a single holiday would push the floor years late),
then a strict single-day forward scan to remove the early bias that tolerance creates. ~25 HTTP calls,
once per (broker, symbol, timeframe), then cached to `backtest/cache/history_floors.json`.
`refresh=True` re-probes (use after a broker back-fills).

**Two independent defences, both required:**
1. `HistoryFloors.assert_window()` — the measured floor, checked in `BarSource.load` **before any
   fetch**. Also read by the lab API so a user is stopped at the date picker, not 40 minutes into a run.
2. `assert_bar_spacing()` — pure, empirical, on what actually came back: the frame's MODAL gap must
   equal the requested timeframe. Backstop for an unprobed symbol, an unreachable agent, and the day a
   broker's depth shifts. Checked at the BASE timeframe, because resampling up would smooth a
   substitution into a plausible-looking frame.

**`floor()` returning `None` means UNKNOWN, never "unlimited"** — an unreachable agent, or a broker we
cannot identify. Nothing is refused on a guess; the spacing backstop still applies. The `_SEED`
fallback is tagged with the server it was measured on and is applied **only** to that broker.

**Enforcement points.** `BarSource.load` (every consumer — lab, optimizer, CLI) plus a 400 at each lab
trigger: `POST /backtests/run`, `POST /runs/{id}/retry` (period override), `POST /backtests/sweep`,
`POST /optimizations/run`, `POST /backtests/stacks`. Only the **python** runner is bounded —
NT8 and MT5 pull history from their own terminals, so their depth is a different question and claiming
a Vantage gold floor there would be a lie in the more dangerous direction.

**UI.** `GET /backtests/history-limit?instrument=&bar_type=&bar_value=&runner=` → `HistoryLimit`
(`earliest_date`, `broker`, `verified`, `source: probed|seed`, `note`) or `null` when unbounded.
`useHistoryLimit` feeds `PeriodPicker`, which sets `min` on both date inputs, **clamps the 1Y/3Y/5Y
presets** to the floor (so "5Y" on a 4-year broker asks for what exists), makes "All" mean *all there
is*, and shows a one-click "Start at <date>" fix — a native `min` stops the calendar but not a typed
or pasted date. `source: "seed"` renders as "last known — terminal unreachable" so a fallback is never
mistaken for a measurement. Tests: `backtest/tests/test_history.py` (20) — a fake agent with a settable
history start exercises the real probe, including deeper-broker, shallower-broker, and
broker-swap-does-not-inherit.

## Vantage XAUUSD history depth — and the silent-substitution trap

**MT5 does NOT error when a symbol has no history at the requested timeframe. It returns the nearest
COARSER timeframe's bars, still labelled as what you asked for.** This is the single most dangerous
behaviour in the data layer: a backtest fed daily bars as 15m does not crash — it produces a full
trade list, a clean equity curve, and a completely fictional answer. Verified 2026-07-26 on Vantage
XAUUSD by asking for one month (January 2010) at four timeframes:

| asked | bars returned | real count would be |
|---|---|---|
| M1  | 21 | ~29,000 |
| M15 | 21 | ~1,900 |
| H1  | 21 | ~480 |
| D1  | 21 | 21 ← the bars all four actually served |

21 = the trading days in that month. Every intraday request was handed D1. Single-day probes show the
same thing one level up: on 2018-09-11, M1/M5/M15/M30 each return an identical 23 bars of $1.88 median
range — H1 data, served four ways.

**Real depth (density-verified 2026-07-26, AFTER "Max bars in chart" was set to unlimited).** These
are a SNAPSHOT for orientation — the code probes rather than reading them, so do not treat them as the
contract:

| timeframe | real history starts | bars available |
|---|---|---|
| M1 · M5 · M30 · H1 · H4 | **2018-09-14** | ~2.8M / 570k / 95k / 47k / 12k |
| M15 | **2018-09-13** (probe; a partial 38-bar first day) | ~190k |
| D1 | 2007-06-21 | ~4,700 |

Every INTRADAY timeframe shares one floor — Vantage's gold intraday start. That common date is itself
the proof no bar cap is in play: a cap would exhaust M1 ~15× sooner than M15, and it does not.
**~7.9 years is the hard ceiling for any intraday backtest on this broker**; no MT5 setting moves it
(only a different broker or a paid feed would).

Note M15 starts one day earlier than hand-sampling found: the automated probe caught 2018-09-13 (38
real bars, $1.24 median range — history begins mid-day) where manual day-picking had tested 09-12 and
09-14 and missed the Thursday between. The `_SEED` fallback deliberately carries the LATER 2018-09-14
for all intraday: refusing one extra day costs nothing, allowing one day too early is the failure this
whole section exists to prevent.

**`GET /data_availability` CANNOT be trusted for depth.** It samples one bar from each end, so the
substitution above fools it completely — on 2026-07-26 it reported `earliest 2007-06-22` for **every**
timeframe including M1, which is false by ~11 years. The two previous depth figures in this file
(2026-07-21, 2026-07-22: "M1 from 2026-04-13", "M30/H1/H4 from 2007") came from that endpoint and were
wrong for the same reason. **Verify depth by BAR DENSITY — count bars per day and compare against the
timeframe's expected count — never by the earliest timestamp.**

**"Max bars in chart" must be unlimited in the MT5_Lab terminal.** Before it was raised (2026-07-25)
every timeframe capped at ~100,000 bars, which is 4.2 years on M15 but only ~3.5 months on M1 — the
old "M1 from 2026-04-13" reading was that cap, not the broker's history. Tools → Options → Charts.

**The guard now lives in the DATA LAYER, so every consumer inherits it** — `BarSource.load` calls both
`assert_window` and `assert_bar_spacing` (see *History floors* above), which closes the earlier gap
where only `run_report.py` was protected and the lab/optimizer were exposed. Verified firing: asking
for 15m over 2015 raises `HistoryFloorError: … most common spacing in the returned data is 1440m`.
`run_report.py` keeps its own copy of the spacing check so it fails with a CLI-shaped message before
loading, which is redundant by design — a duplicated refusal is cheap, a missed one is not.

**Cache isolation is by SYMBOL name, not broker** — files are keyed `(symbol, tf)` with no broker tag,
so Vantage `XAUUSD__*.csv` and any PU Prime `XAUUSD_s__*.csv` are naturally separate. The trap: if a
config still asked for `XAUUSD.s` the agent's suffix-strip fallback would pull Vantage bars and cache
them under the `.s` key — mixing brokers. The stale PU Prime cache was cleared 2026-07-22 and the
strategy default symbol is now `XAUUSD`, closing that path.

The agent's `/ticks` endpoint landed with A2; `Mt5Agent.ticks()` reads it, and `backtest/data/ticks.py`
caches by hour. Pull the SMALLEST window that answers the question — gold is ~690k ticks/day (~43MB,
~90s), while one 5m bar is ~260KB and under a second.

## Rules

- 🔴 **A gap that serves NO bars has two opposite causes and `source.py` must never guess between
  them.** The market was SHUT over it (a weekend, a holiday, or a window ending today before the
  session opens), or the data is MISSING (the 45-day M1 hole `covered_spans` records). Until
  2026-08-15 both raised, so **every backtest whose end date fell on a non-trading day failed
  outright** — the same window had completed the day before. `BarSource._market_was_shut` is the one
  thing allowed to tell them apart and it demands BOTH: the gap is no longer than
  `_MAX_CLOSURE_DAYS` (this module's own measured answer to how long this market can legitimately
  print nothing — 2 days observed, 4 with headroom), **and** a wider probe around it does serve
  bars, which proves the agent, the terminal, the symbol and the history are all fine and only the
  market was absent. ⚠ **The probe must be LONGER than any closure it excuses or it is not a probe**
  — it returns the same empty answer for both causes. `_PROBE_DAYS` is derived from
  `_MAX_CLOSURE_DAYS`, never picked, because the forward half is clamped at today and a symmetric
  reach collapsed to exactly the closure length in the one case that matters most. ⚠ **A probe that
  RAISES answers "not shut"** — cannot-ask is never no-market — and ⚠ **a closed span records NO
  coverage**, so nothing claims bars it does not hold. ⚠ **No stored result moves**: the only
  changed path is inside `except Mt5AgentError`, which previously always propagated, so any load
  that succeeded before is byte-identical. Tests: `tests/test_source_market_closed.py` (12; 4
  watched RED against HEAD, the other 8 killed by 4 mutations).
- **An engine input the decision stream does not export is a silent parity trap.** `EngineConfig`
  carries the engine-construction knobs, and a consumer replaying a specific Pine must pin every one
  that Pine does not leave at the engine's default — `EngineConfig`'s own defaults cannot be right for
  everyone, because the Pine files disagree with each other. Live example (caught 2026-07-26):
  `fvg_require_close` defaults **False** here, mirroring `mpc_assistant.pine` where it is an input and
  is off; but `mpc_strategy.pine` HARDCODES the check, so `mpc_sos_fade` pins it True. Unpinned, the
  engine created gaps that Pine never did and produced a phantom entry edge — invisible to
  `compare_strategy.py` until a fresh export happened to disagree, ~8 days after the engine made the
  gate optional. **When an engine default changes, audit every `engine_config()` that replays a Pine
  which does not share the new default.**
  **Second live example, and the nastier direction (caught 2026-07-31): the trap also fires on an input
  a consumer FORGOT to pin.** `EngineConfig` carried `fvg_max_count = 6` / `fvg_threshold_pct = 0.1`,
  two generations stale, and this file said so — flagged as harmless because "every real consumer pins
  its own". **That was half wrong.** `mpc_sos_fade` pinned `fvg_max_count` and `fvg_require_close` and
  never pinned `fvg_threshold_pct`, so it was silently inheriting the 0.1 — which happens to equal
  `mpc_strategy.pine`'s 15m floor, so the bot worked by coincidence rather than by decision. Anyone
  reconciling that "stale" default to the engine's would have moved the A+ bot's trades with **no test
  failing**. Verified by doing exactly that: `compare_strategy.py` failed on the first compared bar
  (`px_edge` py=3478.99 vs pine=3475.43). Fixed the right way round — **`EngineConfig` carries ENGINE
  defaults (8 / 0.0), each strategy pins what its own Pine uses**, and
  `test_engine_config_pins_every_input_the_pine_moved_off_its_default` now asserts all four pins so the
  shared default is free to move again. **Corollary: never "tidy" an `EngineConfig` default without
  first checking which consumers read it unpinned — a stale-looking default may be load-bearing.**
- **Never build a second copy of a canonical engine here.** This package *replays* `engines/`; it
  imports them, it does not reimplement structure/fib/fvg/rsi/liquidity/sessions detection.
- **Every write to `backtest/cache/` goes through `data/atomic.py`** — `atomic_write_*` for the
  bytes, `cache_lock(dir, symbol, tf)` around any read-modify-write. Both, never one: atomicity
  stops a torn file, the lock stops a lost update, and the lost update is the silent one. A new
  sidecar written with a plain `write_text` is a new hole of exactly the shape that destroyed the
  M1 and M15 caches on 2026-08-06. ⚠ **If a write and the record that DESCRIBES it are separate
  calls, hold one lock across both** — the invariant is that coverage never claims more than the
  bars on disk, and two individually-atomic writes leave a window where it does.
- **Resample only ever UP.** Building a lower timeframe from a higher one invents intrabar path —
  forbidden. Pull a smaller base instead, or use ticks.
- **Stdlib + pandas only** in the data layer (no parquet/pyarrow — the environment lacks it; CSV is
  the cache format). Keep the package dependency-light so it imports anywhere.
- **The cache is git-ignored broker data** — never commit anything under `backtest/cache/`.
- **Tests run offline.** Network (the MT5 agent) is injected, so tests use a fake. Run:
  `command-center/backend/.venv/bin/python -m pytest backtest/tests/ -q`.
- 🔴 **A REPLAY is the unit of cost in this suite, and two files were paying for the same one over
  and over.** `test_reprice.py` ran **8** full `mpc_sos_fade` replays over two years of M15 bars
  where it needs **4** — every case re-ran the identical FREE replay before its charged one — and
  `test_cache_concurrency.py` fired its 5-process × 250,000-row collision once per test where the
  three tests assert three properties of ONE outcome. **MEASURED: 182s → 80s and 86s → 25s;
  `pytest backtest ...` 431s → 202s.** ⚠ **Nothing about what is asserted changed and no stored run
  re-prices** — the reference tests demand exact equality against a real charged replay, so a cache
  that returned a different run could not pass. ⚠ **A cached replay is handed out as-is, so a test
  may not mutate one**, and ⚠ **the module-scoped collision fixture trades three chances at an
  intermittent race for one** — acceptable only because 250,000 rows reproduces it structurally
  rather than by luck; put it back per-test if `_ROWS_EACH` ever shrinks. ⚠ **These caches are
  MODULE-level, so a parallel runner must keep a file on ONE worker** (`--dist loadfile`) or every
  worker rebuilds them and the sharing is undone.
- **An unmeasured cost REFUSES — it never inherits a measured sibling's number.** Every PU Prime tier in `PROFILES` once shared ONE spread measured on a **Standard** demo — the single tier priced by a marked-up spread — so the other three were fiction and **nothing errored**. ✅ **ECN's sentinel was retired 2026-08-14 (`_SPREAD_XAUUSD_PUPRIME_ECN = 0.12`, 3.03M ticks / 5 days / all 23 traded hours). NO baseline moves** — the tier RAISED before, so nothing ever charged an ECN spread. 🔴 **Prime and Cent still refuse, and ECN's figure may NOT be copied onto Prime** — Prime is indistinguishable from ECN on every field the terminal publishes, so *"they look the same, so they are"* is available again, and that is the exact argument that put Standard's 0.32 on all four tiers and was wrong by 2.7x. **A terminal holds only the ticks of the account it is logged into: one tier measured is one tier measured.** ⚠ **A tick window straddling an account switch can silently MIX tiers** — MT5 keys its store by SERVER, not by login. Check a narrow unambiguous window against the wide one before trusting either. ⚠ **Only `--history-days` can settle a spread; `--sample` sees one session** — which is why two earlier live readings agreed at $0.12 and still could not retire this. Full record: `docs/BACKTEST_BUILD_NOTES.md`. ⚠ **The refusal is on the SPREAD specifically, not on the whole tier**; commission still charges, because a broker states it unambiguously per lot. ⚠ **And the swap half was MEASURED, not reasoned:** the assumption *"swap is a fact about the symbol, so it is the same across a broker's tiers"* was written down and disproved the same day — on ONE account `XAUUSD.s` and `XAUUSD.crp` are the same market (median M15 close difference **$0.08** over 200 shared bars) carrying **swaps 8.5x apart** with the short CREDIT gone entirely. This strategy trades both sides and its swap arithmetic rests on that credit. **Naming an assumption is not testing it** — it was checkable in one command the whole time, and it survived because no command existed. Full write-up: `docs/BACKTEST_BUILD_NOTES.md`.
- **A stack's blocked and missed setups come from the SHARED replay, never the solo control** — and read them with `getattr` and a default, because they are OPTIONAL on an execution. ⚠ **A strategy that records none has no such rule, rather than being one that could not be asked** — do not let those two states collapse into the same value. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **A bar INDEX is not a shared axis whenever the bar size can differ.** Check what two runs are actually indexed on before comparing them — this bites the moment a sweep replays one strategy across timeframes. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **Coverage has TWO rules and they are not alternatives.** *Is the whole window fetched* and *what did we actually receive* answer different questions; keeping only the first re-pulled six and a half years of bars to obtain one day, on every request that reached the live edge. A partial fetch is only safe because `BarCache.save` MERGES rather than overwrites. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **Bars are UTC**, timestamped at the bar OPEN (matching MT5), columns open/high/low/close plus
  an OPTIONAL `volume`. This line said "no volume (the A+ engines don't need it)" until
  2026-08-07 and was two generations stale: the data layer has carried volume since the
  2026-08-06 `FEED_VERSION` 3 pass, and `ReplayBar` carries it from 2026-08-07 for
  `strategies/python/mpc_bos/`, the first strategy that needs it (its session-VWAP filter).
  ⚠ **`ReplayBar.volume` is `Optional[float]` and `None` means THE FEED CARRIED NONE — never
  0.0.** A zero-volume bar is a real thing MT5 reports on a dead session, so filling the unknown
  with one puts a measurement where there is none, and a volume-weighted consumer averages
  straight through it without complaining. A NaN cell (one unknown bar inside an otherwise
  populated column) is `None` for the same reason. The A+ and B-LEG paths never read it, so
  their replays are byte-identical.

## Reading the numbers — two standing caveats

- **Annualized Sharpe is inflated across ALL runners (NT8/MT5/Python).** `output.py:build_daily_pnl`
  records only days that had a closed trade; flat days are deliberately absent (the trailing-drawdown
  engine walks the days that exist). `metrics.daily_sharpe` then annualizes those active days ×√252,
  as if every day looked like an active one. On a 22-trade / ~225-day run the shipped figure was
  **7.80** vs a true **~2.2** when every weekday is zero-filled (monthly-%, daily-%, and dollar
  variants all cluster ~2.0–2.6 — that cluster is the tell). KNOWN + MEASURED, deliberately NOT fixed
  (fixing it re-scores every historical run — Aaron's call). Treat Sharpe as a *relative* ranking
  between our own runs only; never quote it as an absolute, and never compare it raw to TradingView's.
  If ever fixed, build a separate zero-filled series for the Sharpe calc — do NOT change `daily_pnl`
  itself (the trailing-drawdown engine depends on the absent flat days).
- **Reconciling with TradingView's Strategy Tester — two conventions differ, both expected.**
  (1) TV counts each TP-ladder exit as its own closed trade, so it reports ~3× our position count
  (66 TV "trades" = our 22 positions; win RATE matches to 4 s.f. — compare the rate, never raw counts).
  (2) TV's Sharpe is a RAW MONTHLY figure — multiply by √12 (≈3.464) before comparing to our
  annualized daily one. Normalize for both before calling any TV-vs-lab gap a bug; `verify_parity.py`
  proves the SIGNALS match bar-for-bar, it does not make the two summary reports directly comparable.
- **If a real backtest must be run, the MT5 runner is much faster than NT8** (NT8's Strategy Analyzer
  is driven by slow pywinauto UI automation). Prefer an MT5-runner strategy/symbol when the goal allows.

---

## `tools/recovery_stack.py` — the loss-recovery rule as a LEG of a shared account (2026-08-20)

Runs `mpc_sos_fade` and `strategies/python/loss_recovery/` through `backtest/portfolio/` — one
balance both size against, one budget they compete for, one merged clock, one refusal log. It
exists because the lab's own `exec_recovery` toggle is a POST-PASS: the recovery sizes off the
running balance and the primary never sizes off the recovery, so recovery profit sits BESIDE the
curve instead of lifting it. Identical trades, **+3.8% that way against +44.8% on one compounding
balance**. The toggle is not wrong to be built that way — it is what stops a lab switch moving a
parity-gated A+ trade — but **it cannot answer "what would this have done on my account", and a
run made with it must not be read as if it did.**

🔴 **The answer is decided by HEADROOM, not by the rule.** A+ risks 10% and the default cap is 10%,
so the two legs at full size want 12.5% of a 10% budget and every overlap shrinks A+ by
construction. MEASURED over 186,910 M15 bars at `puprime_ecn`: **−29.9% at a 10% cap (25 A+ entries
shrunk), +29.4% at 12.5%.** `--aplus-risk-pct` and `--risk-cap-pct` are the levers; the tool prints
a warning when the two legs cannot both fit.

⚠ **The sweep that actually answers the question holds TOTAL risk fixed and moves the SPLIT**, and
its table lives in `strategies/python/loss_recovery/CLAUDE.md` rather than here. One result from it
belongs with the tool though: **the per-cell "+X% against its own control" line this tool prints is
NOT comparable across cells** — it rose +11.5% → +50.5% across four splits purely because the solo
control it divides by was shrinking, so the best-looking uplift in the sweep sat on the worst plan
in it. Read the absolute balances, or read pairs where one plan beats another on BOTH axes.

⚠ **`--on-contention refuse` REFUSES TO RUN.** `entry_floor_pct` is ONE number for the whole
account and these legs risk different amounts, so any floor making A+ all-or-nothing also bans
every 2.5% recovery entry — 64 refusals, 0 trades, the same output at two different caps. A real
refusal rule needs a PER-LEG floor. Never let *cannot express this* and *here are the numbers for
it* be the same output.

⚠ **It prints total R per leg, shared vs solo, and that check is the point.** R is normalised to
each trade's own risk, so a pure sizing change must leave it byte-identical — a difference is
either the cap biting (and then it is in the refusal log) or a decision moved. It has already
found one: A+ shifts −0.10R on the shrink path, unexplained, 0.08% of the book and far under the
15.06R jitter floor. Written down rather than rounded away.

## `output.py::_tp_targets` — a rung PRICE does not say whether an order sits there (2026-08-21)

The equity point's `tp_targets` used to be two bare prices copied off `t.tp1` / `t.tp2`. A price
alone cannot tell a profit target from a level that places no order at all and only steps the stop
— and at mpc_sos_fade's shipped `exec_tp1_pct = exec_tp2_pct = 0` **neither rung sells anything on
any trade**, so the price chart drew two targets that had never carried an order. Full finding:
`command-center/backend/CLAUDE.md` → *The exit ladder*.

Each rung is now `{"price", "banks"}` when the strategy reports how much it takes off (the
`tp_rungs` duck-type: `(price, banks_pct)` pairs), and a bare price when it does not.

🔴 **The two shapes must stay distinguishable, and `banks: false` may NEVER stand in for "not
reported".** Every run on disk before this date carries bare prices; emitting `false` for them
would tell the chart to redraw their targets as stop steps off a measurement nobody made. This is
rule 1 in the root file, one field further down the pipe.

⚠ **Duck-typed both ways, like every other rich field here.** `tp_rungs` is preferred, the
`tp1`/`tp2` pair is the fallback, and a strategy carrying neither ships `[]` rather than an
invented ladder. A rung priced at 0 is unset and is dropped in both shapes. Nothing here knows
which strategy produced the ladder or what its rungs mean.

⚠ **Ladder order is the STRATEGY's and is not sorted here.** A re-entry prices rung 1 off risk and
rung 2 off a fib, so rung 2 can be the nearer of the two — sorting would renumber the
strategy's own rungs.

Tests: `tests/test_output.py` (4, watched RED — 2 against HEAD, 2 by mutating the fallback to claim
`banks: False`).

## `output.py` — a trade can say what the trade BEFORE it did (2026-08-21)

`build_equity_curve` emits an optional `after` — `"breakeven"` | `"stopped"` | `"closed"` — off
`Trade.after`, for a strategy whose book contains RE-ENTRIES. Reporting-only, like every other
optional key here, and **absent unless the strategy recorded a real string**: a runner with no
re-entry layer, or one that cannot tell, writes nothing rather than a default. ⚠ **The absence is
the point** — the price chart falls back to a neutral tag on a missing one, so an empty string
shipped as a value would read as a fact nobody measured. Why it exists:
`strategies/python/mpc_sos_fade/CLAUDE.md` → *A re-entry records what the trade before it did*.

## `tools/run_report.py` — the second feed's timeframe belongs to the STRATEGY (2026-08-21)

The dual-replay path loaded `BarSource().load(symbol, 1, ...)` — a hardcoded 1-minute feed — for
as long as it existed. MEASURED on mpc_sos_fade over 7.9 years: 5m loads a fifth of the bars
(561,795 vs 2,804,720) and lands within 1.3% of the 1m result, where 15m is 7.6% off. So every run
anybody made paid 2.8M bars for 1.3%.

It now reads `getattr(cfg, "exec_sec_fill_tf_min", 1)` off the config it already built. ⚠ **The
fallback is 1, not 5** — a strategy that does not declare a fill clock has not been measured, and
absence must not be read as consent to coarsen it. Full table and the reasoning:
`strategies/python/mpc_sos_fade/CLAUDE.md` → *The re-entry's FILL CLOCK*.

⚠ **`_assert_timeframe` follows it.** It refused anything that was not 1m before; pinning it while
the loader moved would refuse every run, and pinning it the other way would let MT5's
coarser-bars-under-the-wrong-label substitution straight through.

## `portfolio/account.py` — the entry floor carries `_GRANT_EPS` (2026-08-20)

🔴 **The floor test was a bare `<` while the shrink test beside it had a tolerance, and setting a
floor equal to a leg's own risk % is what exposed it.** That is the natural way to express *risk is
never layered* — refuse anything the budget would shrink — and it puts `granted` and `floor` on
exactly the same number, reached by different arithmetic (a leg DIVIDES by the stop distance to get
a qty, the account re-MULTIPLIES). They differ in the last bit, so an entry nothing was competing
for was refused. **MEASURED: A+ at 10% under a 10% cap with a 10% floor was refused 3,650 times
over 7.9 years and took 31 trades instead of 181** — a book that reads like a savage allocator and
is a rounding error. ⚠ **No stored run moves**: `entry_floor_pct` defaults to 0.0 and both forms
answer identically at zero. Two tests at the boundary, both watched RED by their own mutation.

## `optimizer.py::_replay_one` finalizes the strategy (2026-08-20)

It drives the bar loop itself rather than calling `strategy.run()`, so it does **not** inherit
`run()`'s end-of-book passes. Without the `hasattr(strategy, "finalize")` call after the loop, a
sweep over a finished-book feature — `mpc_sos_fade`'s `exec_recovery` is the first — would grade
every combo on a book missing those trades and rank them confidently, the combos differing in a
field nothing consumed. Guarded because this optimizer is strategy-agnostic and only some
strategies have the hook; idempotent, so a strategy whose `run()` already finalized is unaffected.
⚠ **Any future runner that reproduces the bar loop needs the same line** — the failure is silent.

## Three tools for asking whether a SECOND leg is worth having (2026-08-24)

Built to answer one question — *can the setups the gap requirement refuses be traded for a small,
fixed R?* — and each is reusable for the next leg somebody proposes.

| tool | the question only it answers |
|---|---|
| `tools/nogap_scalp_audit.py` | what a whole grid of stop × target × breakeven × ladder rules would have made, without one replay per cell |
| `tools/ob_leg_replay.py` | what the ORDER LAYER makes of the winning cell, against the shipped bot on a basis identical by construction |
| `tools/drawdown_fill.py` | does a second leg put equity on the board while the FIRST one is bleeding — which total R cannot answer |

🔴 **THE FIRST TOOL IS A RECONSTRUCTION AND ITS BEST CELL WAS WRONG BY MORE THAN THE WHOLE
RESULT.** It prices entries off fib geometry instead of running the order layer, which is what
makes a grid affordable — and its +32.7R best cell replayed at **−6.6R**. Its bar-walk was
validated first, and thoroughly: the excursion it computes reproduces `Trade.mfe_price` on all 158
A+ trades to 0.0000R, with two mutations watched red. **That validation was real and it did not
transfer.** The arithmetic was right; the conclusion was not, because the reconstruction's pool and
its entry price both differed from anything the engine could actually run. ⚠ **Validate the walk,
then still replay the answer** — a grid tool proposes, it never concludes.

⚠ **`drawdown_fill.py`'s compounded row is an approximation and `portfolio/run_stack` is not.** It
sequences trades by EXIT and compounds them consecutively, so two positions open at once are
billed as if they were consecutive, which understates concurrent exposure. It exists to say
whether the real stack run is worth starting. **Do not quote its row as the stack's result.**

⚠ **A leg can be UNCORRELATED and still not help, and this is the case that proves it.** Monthly
correlation −0.09 over 76 months, with essentially all of the second leg's profit landing in the
32 months the first was down — and adding it made the account spend MORE days under water at every
risk weight (1813 → ~1920), with the worst drawdown flat or deeper. **Uncorrelated is necessary and
nowhere near sufficient; an edge too small and too lumpy is leverage, not a hedge.** Read
days-under-water beside the drawdown depth: they are different halves of "help me through the flat
spells" and a leg can improve one while worsening the other.

⚠ **`nogap_scalp_audit.py` needs a SECOND replay purely to see order blocks**, and the reason is
rule 8. The block engine is only built into the stack when the strategy's point-of-interest setting
asks for something other than gaps, so at shipped settings the block list is empty on every one of
155,807 bars. The first version of that audit reported *"no order block in the zone on any of the
146 setups"* off exactly that, and it read as a finding. A registry nobody populated answers
confidently and wrongly.

## The bar loop reads COLUMN ARRAYS, never `df.iterrows()` (2026-08-26)

`iter_bars` is the hot loop of the whole lab — every replay, every optimizer cell and every
portfolio leg goes through it once per bar. It walked `df.iterrows()`, which builds a fresh pandas
Series **per bar** (block manager, dtype resolution, `__finalize__`) so that five numbers can be
read off it and thrown away.

**MEASURED, the two implementations A/B'd ALTERNATELY in one process over 62,468 real M15 bars:
615 µs/bar → 60 µs/bar, ~10x, saving ~35s on a 2.5-year window.** ⚠ **The RATIO is the
measurement and the absolute figures are an upper bound** — this machine was under load from a
second session, identical end-to-end runs came back at 201s and 382s, and that is why the two were
interleaved and scored on the BEST pass rather than benchmarked one after the other. **Two
sequential benchmarks on a loaded machine each measure a different amount of the load.**

🔴 **The conversion is deliberately IDENTICAL rather than merely equivalent.** `.to_numpy()` is
called with NO dtype coercion and every element still goes through `float(...)` — the same call on
the same stored value `row["open"]` produced. Forcing `dtype="float64"` is faster again and is
REFUSED: on an object column it converts by a different route, and *slightly faster and
occasionally a different float* is not a trade anybody asked for.

⚠ **`pd.isna` on the raw volume element STAYS.** It is what keeps an absent volume `None` rather
than `0.0` — rule 1, and `ReplayBar.volume`'s own docstring says why that distinction is
load-bearing. A NaN test written as `raw != raw` is equivalent for floats and WRONG for an object
column carrying `None`.

✅ **PROVEN ON REAL BARS RATHER THAN ARGUED** — `replay_fingerprint.py` (below, same commit)
replayed 2.5 years before and after: bar-stream digest identical, all 66 trades identical on every
field. 539 strategy tests green.

### `tools/replay_fingerprint.py` — how a speed change proves it moved nothing

`capture` before the change, `compare` after. It hashes the BAR STREAM — by replaying the
iterator, never by hashing the frame, so it measures the thing under test — and every field of
every closed trade.

⚠ **A totals check is not this.** Two different books post the same net, so a change that merely
SWAPPED two trades passes a totals check in silence.

🔴 **It fingerprints the STRATEGY SOURCE and the resolved config into the basis, and REFUSES to
compare across a change in either.** Without that it reported a real difference that belonged to
somebody else: a second session edited `mpc_sos_fade.meta.json` between a capture and its
comparison, and the tool duly said the trades had moved. **They had — the strategy had.** *A
comparison harness that cannot see the thing underneath it changing will blame whichever change
you happen to be holding.*

⚠ **It REFUSES an empty trade book.** The first version read `strategy.trades`, a field that does
not exist (`strategy.execution.trades` is the real one), captured ZERO trades, and would have
compared equal to everything forever. ⚠ **And `_trade_rows` builds LISTS, not tuples** — JSON has
no tuple, so a reloaded baseline never equalled a freshly-built one and every trade read as
changed with no differing field to show for it. **Both failures are the same shape: a comparison
tool that is broken says EQUAL or says DIFFERENT, and neither answer looks like an error.**

### `--allow-strategy-change` — the door in the basis wall (2026-08-26)

A speed change INSIDE a strategy moves its source digest, so the basis guard refuses and the one
comparison the tool exists to make becomes the one it will not run. The flag waives
`strategy_source` **and nothing else**: `strategy_settings`, window, instrument, timeframe and
server still refuse, so a moved DEFAULT can never ride in under a performance claim.

⚠ **Passing it is a CLAIM — *I changed the code and assert it is inert* — and it prints a line
saying so above the verdict.** A CHANGED result underneath it is that claim being refuted, never
a tool malfunction. Same reasoning as `compare_strategy.py`'s `--allow-fast-timeframe`: a wall
with no door gets routed around in ways that leave no trace.

🔴 **Where a strategy exposes BOTH algorithms behind a flag, prefer forcing the flag over running
the tool twice** — one process, one binary, nothing else able to differ. That is how the bar-time
map's prune was proved (`strategies/python/mpc_sos_fade/CLAUDE.md`), and it needs no waiver at
all. ⚠ **Patch `type(strategy.execution)`, never the class imported by package path — the lab
loads that module twice and they are different class objects.** A patch on the wrong one hits
nothing and the comparison silently becomes a run against itself.

### Where the replay's time goes NOW, and why the optimisation stopped (2026-08-27)

After the four fixes above, a 23,539-bar profile is **8.7s and FLAT** — the largest single entry is
7.5% and everything else is under 4%. That is the signal to stop, and the reasoning is recorded so
the next person does not re-derive it:

| what is left | share | why it was not taken |
|---|---|---|
| the strategy's signal adapter | 7.5% | it is 71 dataclass field assignments per bar; making it faster means `__slots__` or a namedtuple, i.e. a wide refactor of a money path for ~4% |
| timezone conversion (10 `astimezone` per bar) | ~4.6% | spread across `sessions/`, `liquidity/`, `vwap/` and the strategy — **four canonical engines, four parity gates**, for a few percent |
| everything else | <4% each | no single item worth a gate |

🔴 **THE BAR IS NOT "IS THERE ANY TIME LEFT" — IT IS "WHAT DOES CLAIMING IT COST TO VERIFY".** Every
remaining candidate lives in a canonical engine, so rule 22 applies to each one: a real export, a
gate run before and after, and a byte-identical trade book. **A 3% gain that needs a TradingView
export somebody has to sit down and take is not a 3% gain, it is a 3% gain plus a human.**

⚠ **The four that WERE taken are not counter-examples to that bar, they are the reason it exists.**
Three of them were defects — work with no purpose, removable with the comparisons untouched — and
the fourth was a cache. **None of them required reading a strategy differently.** When the next
candidate does, the answer is no.

⚠ **Re-measure before re-opening this.** The table is one profile on one window, and cProfile
charges allocation pressure to whoever is running — the pivot fix returned four times its own
profile share for exactly that reason, so a small entry here is not proof a change would be small.
