# CLAUDE.md — backtest/ (the Python backtest runner)

**Purpose:** Standing instructions for `backtest/`, the LWG Python bar-replay backtest runner.
**Scope:** This package only — the data layer, replay loop, fill/cost model, output adapter, and
local optimizer. It does NOT cover the engines it replays (`engines/`), the strategies it runs
(`strategies/python/`), or the lab that consumes it (`command-center/`).
**Status:** **Deliverable A COMPLETE 2026-07-16.** A0 (data layer) + A1 (replay loop) landed
2026-07-15; A2 (fill & cost model), A3 (output adapter), the lab's `runner="python"` adapter, and A4
(local optimizer) all landed 2026-07-16. See `docs/SOS_FADE_BUILD_PLAN.md`.
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
  `fvg_require_close` defaults **False** here, mirroring `mpc_jarvis.pine` where it is an input and
  is off; but `sos_fade_strategy.pine` HARDCODES the check, so `sos_fade` pins it True. Unpinned, the
  engine created gaps that Pine never did and produced a phantom entry edge — invisible to
  `compare_strategy.py` until a fresh export happened to disagree, ~8 days after the engine made the
  gate optional. **When an engine default changes, audit every `engine_config()` that replays a Pine
  which does not share the new default.**
  **Second live example, and the nastier direction (caught 2026-07-31): the trap also fires on an input
  a consumer FORGOT to pin.** `EngineConfig` carried `fvg_max_count = 6` / `fvg_threshold_pct = 0.1`,
  two generations stale, and this file said so — flagged as harmless because "every real consumer pins
  its own". **That was half wrong.** `sos_fade` pinned `fvg_max_count` and `fvg_require_close` and
  never pinned `fvg_threshold_pct`, so it was silently inheriting the 0.1 — which happens to equal
  `sos_fade_strategy.pine`'s 15m floor, so the bot worked by coincidence rather than by decision. Anyone
  reconciling that "stale" default to the engine's would have moved the SOS Fade bot's trades with **no test
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
  and over.** `test_reprice.py` ran **8** full `sos_fade` replays over two years of M15 bars
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
- ⚠ **`test_reprice.py`'s four replays run AT ONCE, in four spawned processes, the first time any
  case asks (2026-09-10).** MEASURED: 62s one after another (~15s each), and it was the root suite's
  critical path. Same strategy, window, profiles and warm-up, each replay still whole in its own
  process; only the trade list crosses back, because both tests read nothing else. ⚠ **The full run
  uses `--dist load`, so each worker that draws a case pays for all four** — CPU, never correctness.
- ⚠ **`test_stack_zone_band.py` steps the band-ON stack once and both tests read that record**
  (2026-09-10) — copied out as immutable tuples, so neither test can change what the other reads.
  The band never reaching the cap still reddens EACH test run alone (mutation map in the file).
- **An unmeasured cost REFUSES — it never inherits a measured sibling's number.** Every PU Prime tier in `PROFILES` once shared ONE spread measured on a **Standard** demo — the single tier priced by a marked-up spread — so the other three were fiction and **nothing errored**. ✅ **ECN's sentinel was retired 2026-08-14 (`_SPREAD_XAUUSD_PUPRIME_ECN = 0.12`, 3.03M ticks / 5 days / all 23 traded hours). NO baseline moves** — the tier RAISED before, so nothing ever charged an ECN spread. 🔴 **Prime and Cent still refuse, and ECN's figure may NOT be copied onto Prime** — Prime is indistinguishable from ECN on every field the terminal publishes, so *"they look the same, so they are"* is available again, and that is the exact argument that put Standard's 0.32 on all four tiers and was wrong by 2.7x. **A terminal holds only the ticks of the account it is logged into: one tier measured is one tier measured.** ⚠ **A tick window straddling an account switch can silently MIX tiers** — MT5 keys its store by SERVER, not by login. Check a narrow unambiguous window against the wide one before trusting either. ⚠ **Only `--history-days` can settle a spread; `--sample` sees one session** — which is why two earlier live readings agreed at $0.12 and still could not retire this. Full record: `docs/BACKTEST_BUILD_NOTES.md`. ⚠ **The refusal is on the SPREAD specifically, not on the whole tier**; commission still charges, because a broker states it unambiguously per lot. ⚠ **And the swap half was MEASURED, not reasoned:** the assumption *"swap is a fact about the symbol, so it is the same across a broker's tiers"* was written down and disproved the same day — on ONE account `XAUUSD.s` and `XAUUSD.crp` are the same market (median M15 close difference **$0.08** over 200 shared bars) carrying **swaps 8.5x apart** with the short CREDIT gone entirely. This strategy trades both sides and its swap arithmetic rests on that credit. **Naming an assumption is not testing it** — it was checkable in one command the whole time, and it survived because no command existed. Full write-up: `docs/BACKTEST_BUILD_NOTES.md`.
- **A stack's blocked and missed setups come from the SHARED replay, never the solo control** — and read them with `getattr` and a default, because they are OPTIONAL on an execution. ⚠ **A strategy that records none has no such rule, rather than being one that could not be asked** — do not let those two states collapse into the same value. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **A bar INDEX is not a shared axis whenever the bar size can differ.** Check what two runs are actually indexed on before comparing them — this bites the moment a sweep replays one strategy across timeframes. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **Coverage has TWO rules and they are not alternatives.** *Is the whole window fetched* and *what did we actually receive* answer different questions; keeping only the first re-pulled six and a half years of bars to obtain one day, on every request that reached the live edge. A partial fetch is only safe because `BarCache.save` MERGES rather than overwrites. Detail: `docs/BACKTEST_BUILD_NOTES.md`.
- **Bars are UTC**, timestamped at the bar OPEN (matching MT5), columns open/high/low/close plus
  an OPTIONAL `volume`. This line said "no volume (the SOS Fade engines don't need it)" until
  2026-08-07 and was two generations stale: the data layer has carried volume since the
  2026-08-06 `FEED_VERSION` 3 pass, and `ReplayBar` carries it from 2026-08-07 for
  `strategies/python/bos/`, the first strategy that needs it (its session-VWAP filter).
  ⚠ **`ReplayBar.volume` is `Optional[float]` and `None` means THE FEED CARRIED NONE — never
  0.0.** A zero-volume bar is a real thing MT5 reports on a dead session, so filling the unknown
  with one puts a measurement where there is none, and a volume-weighted consumer averages
  straight through it without complaining. A NaN cell (one unknown bar inside an otherwise
  populated column) is `None` for the same reason. The SOS Fade and B-LEG paths never read it, so
  their replays are byte-identical.

## Reading the numbers — standing caveats

<!-- ⚠ Deliberately NOT "two": it said that while carrying three, and now four. A count in a
     heading is a second claim about the list under it, and it is always the half that goes stale. -->


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
- 🔴 **A COMPOUNDED RUN EVENTUALLY ASKS FOR ORDERS THE BROKER WILL NOT ACCEPT. THE LAB MODELS THAT
  SINCE 2026-09-02 AND RESIZES THEM DOWN** (`portfolio/account.py` → `max_lots`, default 100 lots,
  every strategy). PU Prime's ceiling on `XAUUSD.p` is **100 lots** (min 0.01, step 0.01) —
  MEASURED live off account 700152905 that day, identical to the 2026-08-14 reading in the bot's
  own instance config. The live SOS Fade config replayed on its own two feeds from $10,000 asks for
  **more than 100 lots on 25 of its 205 trades (12.2%)**; the first at a balance of **$927,540**,
  the largest **742.60 lots — 7.4× the ceiling**. ⚠ **Below ~$927k nothing is touched**, which is
  why it never showed up.
  🔴 **WHAT THE CEILING COSTS, MEASURED BOTH WAYS ON THE SAME BARS: R IS IDENTICAL AND THE BALANCE
  IS NOT.** Uncapped and capped both take **205 trades for +107.36R**; the balances are
  **$11,528,822 vs $10,752,175**, a **−$776,647** difference (−6.7%). **R cannot see this and that
  is not a defect in R — it is what R is for.** The ceiling refuses nothing and changes no
  decision, so every trade's R is untouched; it only makes 25 positions smaller. **A run reported
  in R alone is therefore IDENTICAL with the ceiling on or off, and a reader comparing R would
  conclude the ceiling is free.** It is not: it costs compounding, which is a dollar effect.
  ⚠ **This is the one place in this file where the dollar column carries information the R column
  cannot**, and rule 6 still holds everywhere else.
  🔴 **DO NOT CARRY THE OLD "$4.9M OF PROFIT IN REFUSABLE TRADES" FIGURE ACROSS — IT ANSWERED A
  DIFFERENT QUESTION AND IS WRONG BY 6×.** That was the summed P&L of the over-ceiling trades under
  the old REFUSE rule. Resizing keeps those trades at reduced size, and the effect on a compounding
  balance is MULTIPLICATIVE rather than additive, so the real cost is $776,647, not $4.9M. **An
  absolute-dollar figure measured on one path does not transfer to another path.**
  ⚠ **Risk per trade FALLS past the ceiling**: on the largest ask the bot gets 13.5% of the size it
  wanted, so that trade risks **1.35% instead of 10%**; the mildest capped trade risks 9.66%. Size
  is frozen while the balance keeps growing, so **compounding becomes linear** — safe in the
  direction that matters, and the real cost of the cap.
- **If a real backtest must be run, the MT5 runner is much faster than NT8** (NT8's Strategy Analyzer
  is driven by slow pywinauto UI automation). Prefer an MT5-runner strategy/symbol when the goal allows.

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 210 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/architecture.md` — Build pieces — data layer, fill/cost model, output adapter, optimizer, EngineConfig

**Read before touching:** the fill or cost model, output.py's trade fields, the optimizer, or EngineConfig's engine-construction knobs.

- Build pieces (from the plan)
- `output.py::_tp_targets` — a rung PRICE does not say whether an order sits there (2026-08-21)
- `output.py` — a trade can say what the trade BEFORE it did (2026-08-21)
- `tools/run_report.py` — the second feed's timeframe belongs to the STRATEGY (2026-08-21)
- `optimizer.py` — `run_sweep(extract=…)`, and why it is not "just read the KPIs" (2026-09-07)
- `optimizer.py::_replay_one` finalizes the strategy (2026-08-20)
- An engine a strategy never READS is never RUN — `EngineConfig`'s switches (2026-09-10)

### `notes/tools.md` — Tools

**Read before touching:** using, extending, or trusting the output of any script under backtest/tools/.

- Tools
- `tools/zone_return_audit.py` — the RETURN into the zone, and the filter that stops the win rate and the reward-to-risk cancelling (2026-09-17, Run 39)

### `notes/regime-grading.md` — Grading the market-condition engine

**Read before touching:** `backtest/regime_study/`, or quoting any number it prints.

- Why "is the classifier accurate" has no answer, and the two questions that replace it
- 🔴 The bar-level bootstrap is a MOVING BLOCK one — the naive version's range is ~5-10x too narrow
- A trade is graded on the last bar that had already CLOSED, never the bar containing its entry
- Read the range, never the middle number — a range crossing zero means the reading told us nothing
- MEASURED 2026-09-17: the three shipped labels separate neither market behaviour nor money, and 78% of bars are called trending
- `tools/trade_export.py` — replay ANY registered strategy for its entry times and R, when the rich report's shape does not fit (2026-09-17)
- `replay/registry.py` — which packages declare the contract, in ONE place; being in it is not a promise every tool can drive it (2026-09-17)

### `notes/setups-contract.md` — The setups.py contract

**Read before touching:** a strategy's blocked/missed-setup reporting.

- `setups.py` — the contract a strategy fills in to report what it is WATCHING (2026-08-13)

### `notes/portfolio-stack.md` — Portfolio stacking and the venue ceiling

**Read before touching:** the portfolio stack, a shared account run, portfolio/account.py, or evaluating a second leg.

- Portfolio stacking (`backtest/portfolio/`)
- `tools/recovery_stack.py` — the loss-recovery rule as a LEG of a shared account (2026-08-20)
- `portfolio/account.py` — the entry floor carries `_GRANT_EPS` (2026-08-20)
- `portfolio/account.py` — the VENUE CEILING, and why a clamp is allowed here (2026-09-02)
- `portfolio/account.py` — the half-share minimum and the market-bot shrink; no stored run moves (2026-09-15)
- The contention log records the PLACEMENT gate too, and a row is an EPISODE (2026-09-16)
- Three tools for asking whether a SECOND leg is worth having (2026-08-24)

### `notes/broker-data.md` — Broker identity, symbols and the bar cache

**Read before touching:** adding a broker/account profile, touching the bar cache, or trusting a history-depth figure.

- A profile also states how its broker SPELLS a symbol (2026-08-26)
- Standard and Prime record their LOGINS (2026-08-26)
- 🔴 The cache is partitioned by BROKER SERVER (2026-08-24)
- Vantage XAUUSD history depth — and the silent-substitution trap

### `notes/performance-costs.md` — Replay performance and the scale-in cost defect

**Read before touching:** the bar loop's performance or the cost pill's scale-in charging.

- The bar loop reads COLUMN ARRAYS, never `df.iterrows()` (2026-08-26)
- 🔴 The Costs pill UNDER-CHARGED every trade that scaled in (2026-09-07)
