# Notes — Build pieces — data layer, fill/cost model, output adapter, optimizer, EngineConfig

The A0-A4 build pieces (data layer, fill/cost model, output adapter, local optimizer), the output.py trade/TP-rung and run_report.py timeframe notes, and EngineConfig's per-engine gating switches. Moved VERBATIM out of `backtest/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

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
  tuning fields on `EngineConfig`** — every OB constant is HARDCODED in `mpc_jarvis.pine` rather
  than exposed as an `input.*`, so a config field could never be carried by an export column and no
  parity gate could check it (the `BosConfig` rule, 2026-08-07). The engine's defaults ARE the Pine's
  constants. If mpc re-exposes one as an input, add the field then, with its export column.
  ⚠ **The position in `step()` is the Pine's** (`extendOBs` then the push/turn creation sites, right
  after `st.process`) and is currently behaviour-NEUTRAL — the engine is standalone and nothing
  downstream reads it — so do not "tidy" it: the day something reads a block, the order is already
  right. Pinned by `tests/test_replay_order_blocks.py` (8 tests, all 8 watched RED against HEAD),
  whose load-bearing case asserts that enabling it leaves all ten other `BarState` fields
  byte-identical — every measured figure in this repo was produced by a stack with no OB engine in it.
  🔴 **The equal-highs/lows knobs on `EngineConfig` moved to the INDICATOR's values on
  2026-09-09: `eq_atr_mult` 0.1 → 0.25 and `eq_max_levels` 6 → 14.** They had never matched
  `mpc_jarvis.pine`, so every replay through this stack — and the LIVE SOS Fade bot, which turns
  `eq_exempt_fvg` ON — used a narrower equality band and a shallower level cap than the chart the
  setups are read off. ⚠ **MEASURED before the switch, 157,004 M15 bars: the trade list is
  IDENTICAL either way (244 rows) and four SETUP rows move.** The four are what make the run
  believable — a change that moved nothing would equally mean the config never reached the engine.
  ⚠ **These are defaults on a dataclass, so nothing fails when they disagree with Pine** — the
  parity gate cannot see them either, which is this file's own *an engine input the decision stream
  does not export is a silent parity trap*, arriving from the config end instead. Full record:
  `engines/equal_highs_lows/CLAUDE.md`.
  ✅ **Since 2026-09-10 `EngineConfig` types no engine default of its own** — every field that means
  *the engine's default* READS the engine's `DEFAULT_*` constant, and
  `engines/tests/test_defaults_mirror_the_indicator.py` holds those to the Pine. So the dataclass can
  no longer disagree with the engine, and the engine cannot disagree with the indicator without a red.
  ⚠ It changes nothing a strategy pins: a bot replaying its own Pine still overrides these.
  ⚠ **The gap cap moved 8 → 7 with the engine the same day** and reached no trade: every bot that
  reads gaps pins its own cap, and the extreme leg runs no gap engine. Its overlap entry was
  re-measured anyway, because step 17 records the engine config and a moved default is a moved
  setting whether or not anything reads it.
  **`fvg_exempt_zone` (2026-09-10, default OFF, OFF in every strategy)** is mpc's fib ENTRY-BAND
  exemption on the gap cap. It exists in `mpc_jarvis.pine` and in no strategy Pine, so it is a
  MEASUREMENT switch for a proposed change, not a mirror of one. 🔴 **The stack builds a one-bar LAG
  on purpose**: mpc's gap block runs ~800 lines above its fib, so the cap reads LAST bar's band, while
  here the fib runs first inside one `step` — the natural wiring is a look-ahead that passes every
  engine test. `tests/test_stack_zone_band.py` replays the committed zone export through the whole
  stack (its own structure and fib computing the band) and matches Pine's gap list on **all 20,187
  bars from bar 0**; watched RED — reading this bar's band instead diverges on 2,972. ⚠ The band
  publishes only while the fib is active and HOLDS otherwise, as mpc's `var` globals do. ⚠ Refused
  without `fvg` and `fib`, the same shape as `eq_exempt_fvg`. **What it does to the SOS Fade bot, and
  why it stays off: `engines/fair_value_gaps/CLAUDE.md` → *Measured on the bot*.**
  `EngineConfig` carries the engine-construction knobs; note `show_internal` (default True): the
  `market_structure` engine always computes internal structure, but a consumer whose Pine has
  "Show Internal Structure" OFF sets this False, which blanks the snapshot's internal-derived fields
  (`i_confirmed_*` / `ifib_seed_*`) so the Structure fib does not adopt an internal-swing anchor. The
  sos_fade bot pins it False; the engine parity harnesses keep it True (they validated internal ON).
- **A2 — Fill & cost model** *(done 2026-07-16; bar-mode costs added 2026-08-01)*.
  `backtest/fills.py` + the tick seam in `sos_fade/execution.py`. **Two fill models, and the
  distinction is load-bearing:** `fill_model="bar"` (default) is the strategy's own bar-level
  intrabar-path GUESS, and it matches what the Pine assumes, so it is the ONLY model
  `compare_strategy.py` may diff. **Bar mode charges zero costs BY DEFAULT — which is not the same
  as charging none by construction, and until 2026-08-01 the two were confused.** A caller may
  now hand `SosFadeStrategy(..., cost_profile=<AccountProfile>)` and have commission and a
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
  TIMING instead — measured on `sos_fade`, the flat charge costs 5.7R and the fill model costs
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
  `strategies/python/sos_fade/CLAUDE.md` → `### Wrong-side stop fills`.
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
  `strategies/python/sos_fade/CLAUDE.md` → *The RETRACE a miss was waiting on*. **`None` means
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

## `output.py::_tp_targets` — a rung PRICE does not say whether an order sits there (2026-08-21)

The equity point's `tp_targets` used to be two bare prices copied off `t.tp1` / `t.tp2`. A price
alone cannot tell a profit target from a level that places no order at all and only steps the stop
— and at sos_fade's shipped `exec_tp1_pct = exec_tp2_pct = 0` **neither rung sells anything on
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
`strategies/python/sos_fade/CLAUDE.md` → *A re-entry records what the trade before it did*.

## `tools/run_report.py` — the second feed's timeframe belongs to the STRATEGY (2026-08-21)

The dual-replay path loaded `BarSource().load(symbol, 1, ...)` — a hardcoded 1-minute feed — for
as long as it existed. MEASURED on sos_fade over 7.9 years: 5m loads a fifth of the bars
(561,795 vs 2,804,720) and lands within 1.3% of the 1m result, where 15m is 7.6% off. So every run
anybody made paid 2.8M bars for 1.3%.

It now reads `getattr(cfg, "exec_sec_fill_tf_min", 1)` off the config it already built. ⚠ **The
fallback is 1, not 5** — a strategy that does not declare a fill clock has not been measured, and
absence must not be read as consent to coarsen it. Full table and the reasoning:
`strategies/python/sos_fade/CLAUDE.md` → *The re-entry's FILL CLOCK*.

⚠ **`_assert_timeframe` follows it.** It refused anything that was not 1m before; pinning it while
the loader moved would refuse every run, and pinning it the other way would let MT5's
coarser-bars-under-the-wrong-label substitution straight through.

## `optimizer.py` — `run_sweep(extract=…)`, and why it is not "just read the KPIs" (2026-09-07)

An optional callable handed each combo's FINISHED strategy; its return value arrives on that row
as `extra`. It exists because `build_kpis` reports TOTALS, and an out-of-sample split needs each
trade's own entry time — so without it every caller wanting a calendar half has to write its own
bar loop.

🔴 **That second bar loop is the thing this hook prevents, and the failure it prevents is silent.**
`_replay_one` is not `strategy.run()`: it sets `bar_ms` off the frame and calls `finalize()`
afterwards, and the section below already records that a runner forgetting the second one grades
every combo on a book missing an end-of-book pass, confidently. **A hook is cheaper than a fourth
copy of this loop.**

⚠ **The key is ABSENT when nobody asked, never `None`.** A row carrying `extra: None` cannot be
told apart from one whose extractor genuinely found nothing — rule 1, one field along.

⚠ **It is PICKLED to the workers**, so it must be a module-level function returning small plain
data, and the parallel path is tested separately: a hook that works only serially stops working
the moment a grid is big enough to fan out.

✅ **NO DOCUMENTED BASELINE MOVES AND NO STORED RUN RE-PRICES.** The parameter defaults to `None`,
which is the path every existing caller takes, and on that path the row is byte-identical to what
it has always been. 4 tests in `tests/test_optimizer.py`; 3 mutations watched RED, each reddening
exactly its own case (the extraction taken before `finalize`, the absent key emitted as `None`,
the worker dropping the extractor).

## `optimizer.py::_replay_one` finalizes the strategy (2026-08-20)

It drives the bar loop itself rather than calling `strategy.run()`, so it does **not** inherit
`run()`'s end-of-book passes. Without the `hasattr(strategy, "finalize")` call after the loop, a
sweep over a finished-book feature — `sos_fade`'s `exec_recovery` is the first — would grade
every combo on a book missing those trades and rank them confidently, the combos differing in a
field nothing consumed. Guarded because this optimizer is strategy-agnostic and only some
strategies have the hook; idempotent, so a strategy whose `run()` already finalized is unaffected.
⚠ **Any future runner that reproduces the bar loop needs the same line** — the failure is silent.

## An engine a strategy never READS is never RUN — `EngineConfig`'s switches (2026-09-10)

**Eight new booleans on `EngineConfig` — the structure fib, the sniper zone, the macro fib, the
internal fib, the gaps, the RSI divergence, the liquidity levels and the sessions engine — each
deciding whether that engine is BUILT and STEPPED at all. Every one defaults ON, so a stack built
the way every existing caller builds it is byte-identical to the one this package has always had.
A STRATEGY turns off what it never reads, in its own `engine_config()`.**

🔴 **THE COST WAS NEVER SMALL AND WAS NEVER SHARED.** `order_blocks` has carried this argument
since 2026-07-31 — an unused engine still costs a per-bar pass on every replay, sweep combo and
optimizer core in the repo — and it was the only engine acting on it. **MEASURED on the two live
bots' own stack (`st_e358caddd0`, PU Prime `XAUUSD.p`, 2020-01-01 → 2026-09-06, both legs, no solo
controls): 277.5s → 182.6s, a 1.52x speed-up, with the 361-trade book IDENTICAL on every field of
every record.** Per engine, on 190,159 real M5 bars, best of three interleaved runs: the full stack
26.91s, the two engines `extreme_leg` reads **11.89s (44.2%)**, the seven `sos_fade` reads 22.01s
(81.8%).

⚠ **The 5-minute frame is the expensive one and it carries the bot that reads the least.** Three
bars for every one on 15m, and `extreme_leg` reads the bar, the external structure events and the
mitigated liquidity levels — nothing else.

⚠ **A skipped engine's events are `None`, never an empty events object.** That is the
`order_blocks` rule applied to seven more fields: `None` means THE QUESTION WAS NEVER ASKED, an
empty list means the engine RAN and found nothing this bar. A strategy reading `state.sessions.in_ny`
off a stack that never ran it gets an AttributeError, which is loud; an empty events object reads as
*no session here* and the bot refuses every setup while looking perfectly healthy. **Rule 1, and
this repo has already paid for it on a dead terminal, an empty registry and an unfetched calendar.**

⚠ **A switch here is NOT a tuning input and needs no Pine input behind it** — same standing as
`order_blocks`. It cannot change what any engine EMITS; it can only decide whether that engine is
asked. Every field above them in the dataclass is a value the Pine sets and a parity gate can see;
these are not, and no `cfg_` column could ever carry one.

⚠ **The structure engine has NO switch.** The snapshot is built from it and every strategy here
reads one, so a switch would be a branch nothing can take.

🔴 **THEY GO IN `engine_config()`, NOT `stack_config()`, AND THE DIFFERENCE IS THE GATE.** The
parity harnesses call `engine_config()` off the CLASS — and so do `optimizer._replay_one`,
`python_runner._replay` and `algos/live/runner.py`, all three of which build their own stack. In
`stack_config()` — the per-INSTANCE layer — the gate would keep replaying the full stack while
production replayed a narrower one, which is a fixture more capable than production, i.e. rule 13.

🔴 **`eq_exempt_fvg=True` with `fvg=False` RAISES rather than being quietly resolved.** The
equal-highs/lows engine exists only to exempt gaps from the FVG cap, so that pair asks for an
exemption on an engine that never runs. Building EQ anyway costs a per-bar ATR and pivot scan for
output nothing can read; skipping it silently leaves a config saying the exemption is on beside a
replay where it never was.

⚠ **Two bots gate today and three do not.** `sos_fade` switches off the internal fib and the
sessions engine; `extreme_leg` switches off everything but liquidity. `b_leg`, `bos` and
`realign` are untouched and still run the full stack — they are not slower than they were, they
simply have not been measured, and each needs its own read of what it consumes before it gates.

**TESTED:** `tests/test_replay_engine_gates.py`, 25 tests, **7 mutations run and 7 killed** —
building a skipped engine anyway, reading the wrong gate when stepping, dropping the EQ refusal, a
switch defaulting off, the gate feeding back into the snapshot, a bot gating an engine it reads,
and the source probe finding nothing.

🔴 **The test that matters is the one asking whether a bot READS what it has switched off**, and it
scans the strategy package's parsed AST rather than its text, so a mention in a comment cannot make
an engine look needed. **It is deliberately conservative in one direction**: a false positive says
*enable this engine*, which costs time; a false negative says *safe to skip* about one that is
read, which is the failure. ⚠ **It carries a self-test**, because otherwise *nobody reads it* and
*the scanner is broken* are the same green — the exact defect it exists to stop.

**PARITY: NEITHER strategy gate has run for this change.** 🔴 **This said `compare_strategy.py`
exited 0 on `engines/VANTAGE_XAUUSD, 15_e98ec.csv` — a gap-harness export with no decision column, so
the gate compared nothing** (such a file is refused since 2026-09-10:
`strategies/python/sos_fade/CLAUDE.md`). No SOS Fade or extreme-leg strategy export is on this
machine. `scripts/run_all_tests.sh` all green, 11 of 11 golden engine gates included. **The 6.6-year
A/B above is the evidence for both bots, and it is a different claim from a parity pass.**
