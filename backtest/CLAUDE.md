# CLAUDE.md — backtest/ (the Python backtest runner)

**Purpose:** Standing instructions for `backtest/`, the LWG Python bar-replay backtest runner.
**Scope:** This package only — the data layer, replay loop, fill/cost model, output adapter, and
local optimizer. It does NOT cover the engines it replays (`engines/`), the strategies it runs
(`strategies/python/`), or the lab that consumes it (`command-center/`).
**Status:** **Deliverable A COMPLETE 2026-07-16.** A0 (data layer) + A1 (replay loop) landed
2026-07-15; A2 (fill & cost model), A3 (output adapter), the lab's `runner="python"` adapter, and A4
(local optimizer) all landed 2026-07-16. See `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
**Last reviewed:** 2026-08-05 — 🟢 **THE JITTER AUDIT RAN, AND THE THING IT WAS BUILT TO MEASURE TURNED OUT TO BE THE SMALL ONE.** `tools/jitter_audit.py` closes G17: the shadow diff proved that four cents of broker quote difference can move a resting entry by $10.08 (a `exec_fib_nearest` rung flip), and one leg cannot say how OFTEN that happens. **MEASURED on 186,220 M15 bars (2018-09-13 → 2026-08-04), baseline 183 trades / +134.75R, 12 jittered replays at ±$0.05 per bar.** 🔴 **Rung flips are RARE — 1.4 per run, 0.8% of trades — and the real sensitivity is the FILL, an order of magnitude bigger: ~10.7 trades lost and ~10.4 gained per run, i.e. about 6% of the trade list changes.** Not because the strategy decided differently; because every entry here is a resting limit at an exact price, and five cents decides whether price reaches it. ✅ **The edge survives comfortably: every one of the 12 seeds finished POSITIVE (+92.24R to +148.13R), mean +131.74R, sd 15.06R.** ✅ **And the baseline is not optimistic — median jittered +134.52R against a +134.75R baseline**, i.e. the shipped number sits mid-distribution rather than at the top of it, which was not guaranteed and is the reassuring half. ⚠ **So "the strategy transfers" and "the trade list transfers" are different claims, and only the first is supported.** Expect the live trade list to be a cousin of the backtest's, not a twin. ⚠ **THE JITTER MODEL IS THE DESIGN, and the obvious version measures nothing**: a CONSTANT price offset cannot flip a rung — every fib level translates with it — so the offset is redrawn PER BAR, which is what moves a gap edge relative to a ladder anchored on different bars. One offset applied to all four of a bar's prices, so `high >= max(open, close)` still holds; jittering O/H/L/C independently would build candles no feed can produce and measure the engines on impossible data. ⚠ **The flip threshold is DERIVED, not chosen** — an offset drawn from [−amp, +amp] can move a price by at most `amp`, so two runs differ by at most `2*amp` from noise alone and anything beyond that is a different decision. ⚠ **A trade that merely fills a bar or two later is RETIMED, not lost-and-gained**, and that distinction moved the headline: the first pass counted them as one trade destroyed plus one invented and reported ~9% churn where the honest figure is ~6%. Retimed pairs are matched one-to-one nearest-first (52 across the 12 seeds) — without that, one jittered trade would be claimed as the twin of two baseline trades and BOTH counts would collapse toward zero, i.e. the tool would report perfect stability by double-counting. ⚠ **The flip count is a FLOOR**: a flip that also moves the entry bar lands in retimed or lost+gained, never in flipped. ⚠ **When a flip does fire it is violent — median 31% change in the 1R stop distance, max 84.5%** — and since the trade is sized to its stop, the nominal R is unchanged while the POSITION SIZE and the fill probability both move. **Read a flip as a size event, not a return event.** 28 tests (`tests/test_jitter_audit.py`), weighted toward the two silent errors: calling noise a flip, and calling a flip noise. Earlier: 2026-08-04 — 🔴 **THE BAR CACHE RECORDED WHAT IT WAS ASKED FOR, NOT WHAT CAME BACK, AND HAD BEEN SILENTLY TRUNCATING EVERY RUN THAT REACHED THE LIVE EDGE.** `_load_base` fetched, saved, and then called `coverage.record(start_date, end_date)` — **the REQUEST**. Ask for bars up to a date the broker does not have yet (every `--end today`, every `end = last_bar + 1 day`) and that date is marked fetched **forever**; the next request reads as a cache HIT and returns a frame that stops where the old fetch stopped. **No error, no warning, and nothing in the returned frame to tell you** — the caller gets a clean DataFrame that simply ends early. ✅ **MEASURED on the live cache, not reasoned about: the sidecar claimed history through 2026-08-06 while the CSV held nothing past 2026-08-03 03:45, and the agent was serving the missing 170 bars on request the whole time.** Found by the shadow diff, which could only compare 66 of 148 live bars and said so. **Fixed in `_covered_end`, two clamps:** never past the last bar actually returned, and **never into today** — because a day that is still filling is indistinguishable from a complete one by looking at the bars (a frame ending 00:15 on the last day is either *the broker stops here* or *it is 00:20 right now*), so the live edge is never marked covered and simply refetches until it is genuinely in the past. ⚠ **A window ending in the past is unaffected and does no extra work** — pinned by a test, because a fix that made every historical run pay an agent call would get reverted. ⚠ **The start side needs no clamp**: `assert_window` already refuses a window before the measured floor. This is that same defect arriving from the OTHER END of the window. 5 new tests in `tests/test_source.py`. **The standing lesson is this repo's own, and it is the third distinct route to it: the system quietly answered a NARROWER question than the one asked.** The hardcoded history floor did it at the start of the window, `run_report.py`'s default `--start` did it by defaulting, and this did it at the end — and all three shared the property that the RESULT looks perfect. **Never record what you requested as though it were what you received.** Same day: **`tools/overlap_audit.py`** landed (do two strategies trade different legs of the move — see the tools section). Earlier: **`reprice.py` AUDITED LAYER BY LAYER AGAINST REAL CHARGED REPLAYS, and the biggest layer turned out to be the untested one.** `test_repricing_reproduces_a_real_charged_replay` was parametrized over `spread` and `commission` only — the two EXACT layers — so the suite proved the cheap half and left **swap**, which is **6.41R of the reference run's 12.08R against the spread's 5.67R**, and the only layer whose docstring makes a numeric accuracy claim, resting on nothing. Now covered. ✅ **MEASURED over the full 2020→2026 window (155,453 M15 bars, 161 trades), re-price vs a real charged replay: spread `0.0000R`, commission `0.0000R`, swap `−0.0376R`** — and the swap error is **exactly one trade**, the long held **2022-12-28 → 2023-01-03**, where `rollovers_between` books a New Year night the replay never charged because no bar existed to charge it on. That is precisely the holiday supersede this module's docstring names, so the ~0.3% claim is now a verified number rather than an estimate: **0.03% of the R, 0.32% of the final balance.** ⚠ **The test's swap tolerance (0.05R) is a MEASURED bound, not a loosened one — if it starts failing, that is a real divergence in the swap model; do not widen it.** ⚠ **`equity_rel` is a SEPARATE parameter from the R tolerance**, because a tiny R error COMPOUNDS through the balance re-walk (0.0376R → 0.32% of final equity); one shared bound would either let a real R divergence through or fail the exact layers on dollars. ⚠ **`RepricedRun.total_cost_usd` had no docstring, and that is how it came to be rendered captioned "after compounding" in the lab** — it is the FEES, not how much smaller the run finished; those differ by **55x** on the reference run ($332,371 vs $18,200,741). It says so now. Earlier the same day: **`reprice.py` charges costs onto a run that ALREADY HAPPENED, from its stored trades, without replaying it.** The lab's run page needed to switch costs on and off after the fact, and the obvious objection is that it cannot be done: a charged run compounds differently, so every later trade is a different SIZE, and you cannot price a position the stored run never sized. **The way out is that each re-priceable cost is, in R, INDEPENDENT of size.** A trade risking `dist * qty` and charged `spread * qty` loses `spread / dist` of R whatever `qty` is; commission and swap cancel the same way. So the R is knowable and the dollars follow from re-walking the balance. ⚠ **Proven against real replays, not argued** — `tests/test_reprice.py` replays `mpc_sos_fade` free and charged, throws the charged replay away, rebuilds it from the free run's curve, and demands equality; on the live 161-trade lab run it lands **37¢ out on $16.3M**. ⚠ **`bid_ask_fills` and `slippage` are REFUSED, never approximated** — the first changes which setups fill (161 → 159, with four that never existed on the free path) and the second depends on which exits were market orders; no arithmetic over a trade list can produce either, and the caller is told to re-run. ⚠ **Swap is ACCURATE, NOT EXACT (~0.3%)**: the replay charges swap on the first BAR after a rollover and latches once, so any rollover in a stretch with no bars is superseded — Friday and Saturday always (gold shuts AT Friday's rollover; the weekend rides on the triple-swap Wednesday), and holidays unpredictably. **Mirroring the replay's source line-for-line would be the WRONG answer** — its `_last_rollover_before` skips Saturday only, and charging Friday books 8 nights a week instead of 7, measured at 0.74R too expensive. ⚠ **`build_equity_curve` now carries `r` and `risk_usd` per trade**, COPIED from the strategy: recovering them from a 2dp `profit` and a 5dp `stop_price` is correct but lossy and compounds to ~0.02% of final equity. A run predating them still re-prices, flagged `derived_basis`, and the caller must caption it. Earlier: 2026-08-02 — **`AccountProfile` learned the two costs BAR MODE could always have priced and never did: the SPREAD and the OVERNIGHT SWAP.** Two new fields, `spread` (price units) and `bid_ask_fills`, both bar-mode-only (tick mode has the real book) and both defaulting to the honest zero, so a profile built before they existed is byte-identical and no historical result moves. Swap needed **no new code at all** — `_charge_swap` has run on every bar since A2 and was dead only because callers passed `swap=None`. ⚠ **The two spread fields are ALTERNATIVES, not layers that stack**: a flat charge, or transacting on the real side of the book. Running both bills one spread twice, and the strategy's `_charge_spread` refuses the second. ⚠ **They do not agree, and the gap is the finding rather than a defect** — a flat charge is the MARKET-ORDER intuition, and a strategy whose entries and exits all name a PRICE feels the spread as fill TIMING instead; measured on `mpc_sos_fade` the flat charge costs 5.7R and the fill model costs none, because the whole burden lands on shorts (which buy the ask to exit). ⚠ **Spread is a fact about the SYMBOL as much as the account** — the `PROFILES` values are XAUUSD's, measured per broker off that broker's own cached ticks (**Vantage 0.22 over 1.49M ticks, PU Prime 0.33 over 688k**; quoting one for the other is a 50% error), exactly as `swap` already was. `bid_ask_fills` validates that `spread > 0`, because an ask equal to the bid would silently do nothing while claiming the fills are modelled. 386 tests green. Earlier: 2026-07-31 — `EngineConfig`'s FVG defaults reconciled to the ENGINE (`fvg_max_count` 6→8, `fvg_threshold_pct` 0.1→0.0), and doing it exposed that `mpc_sos_fade` had been reading the old `0.1` **unpinned** — a stale-looking default that was actually load-bearing. The unpinned-engine-input rule below gained that second example and its corollary: never tidy an `EngineConfig` default without checking which consumers read it unpinned. Both strategy parity gates re-verified green afterwards. Earlier: 2026-07-29 — `run_report.py --start` now defaults to the MEASURED broker floor instead of a hardcoded `2022-01-01`, and `backtest/archive/` was added for committed multi-year trade data. Earlier: 2026-07-27 — `build_results` gained `blocked_setups` and `missed_setups`; 2026-07-26 — `EngineConfig` gained `fvg_require_close` (see the unpinned-engine-input rule below); `verify_parity.py` gained a veto column and now runs the B-LEG parity check too

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
  engines in Pine order (structure → fib{structure/sniper/macro/internal} → FVG → RSI-divergence →
  liquidity → sessions) and returns a `BarState`; `run(df, warmup=…)` is the convenience iterator.
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

The strategy seam lives in the strategy (`mpc_sos_fade/execution.py` takes an injected `account`,
default `SoloAccount`) — see that package's CLAUDE.md. `compare_strategy.py` staying exit 0 with the
SoloAccount is the gate that the seam didn't move standalone behaviour.

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
logged into the Vantage demo (account 25815745, `VantageMarkets-Demo`); **gold symbol is `XAUUSD`, no
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
- **Resample only ever UP.** Building a lower timeframe from a higher one invents intrabar path —
  forbidden. Pull a smaller base instead, or use ticks.
- **Stdlib + pandas only** in the data layer (no parquet/pyarrow — the environment lacks it; CSV is
  the cache format). Keep the package dependency-light so it imports anywhere.
- **The cache is git-ignored broker data** — never commit anything under `backtest/cache/`.
- **Tests run offline.** Network (the MT5 agent) is injected, so tests use a fake. Run:
  `command-center/backend/.venv/bin/python -m pytest backtest/tests/ -q`.
- **Bars are UTC**, timestamped at the bar OPEN (matching MT5), columns open/high/low/close, no
  volume (the A+ engines don't need it).

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
