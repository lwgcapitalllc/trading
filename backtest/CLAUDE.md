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
  is **REFUSED**, the same call `run_sweep` makes: a leg is one bar frame, the 1m re-entry needs
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
the overlap audit's 27-shared-bars result arriving through the budget, and the window where two
bots really do carry 2× risk is the bar before the stop stages.

⚠ **A cap BELOW a leg's own risk % does not arbitrate, it re-sizes.** At `--risk-cap 5` against two
bots each risking 10%, all 258 entries are shrunk and NONE is blocked — every position is halved,
R is unchanged (it is normalised) and the closing balance falls $204.9M → $4.7M. That is the
shrink-to-fit design working, and it is a different lever from the one Aaron asked for; **blocking
only happens when a leg asks while the budget is genuinely full.**

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
