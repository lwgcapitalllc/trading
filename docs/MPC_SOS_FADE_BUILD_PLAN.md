# MPC SOS Fade — Build Plan

**Goal:** port the MPC SOS Fade strategy (`indicators/mpc_strategy.pine`) to a Python bot, backtest it
in the command-center lab against XAUUSD (and any market/timeframe), and forward-test it on an MT5
demo account.
**Method:** S.Y.S.T.E.M. (`docs/BOT_DEVELOPMENT_METHOD.md`) under the strategy framework
(`docs/LWG_Strategy_Framework.md`).
**Status:** building — spec approved, Phase-0 probe done, **A0 (data layer) + A1 (replay loop) landed
2026-07-15**, **B-Y (the A+ strategy) landed 2026-07-15** (`strategies/python/mpc_sos_fade/`, 18 offline
tests). **Parity harness BUILT 2026-07-15** — `indicators/mpc_strategy_export.pine` (strategy +
appended decision-stream plot block), `strategies/python/mpc_sos_fade/tools/compare_strategy.py` (the
diff tool, round-trip-tested), and the `/audit-strategy` slash command. **Next: RUN the parity gate —
BLOCKED on a TradingView CSV export** of `mpc_strategy_export.pine` (5m XAUUSD) from Aaron/brother.
Only that run confirms the intrabar fill assumption. See build order.

---

## What the strategy is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence:
**Arm** (RSI divergence, default — or a liquidity sweep) → **SOS** (a same-side external structure
break in the trade direction, inside a staleness window) → **Zone + FVG** (price retraces into the
0.5–0.886 fib band and a live FVG overlaps it). Entry is a resting limit at the FVG's near edge,
clamped into the band. Stop = fib 1.0 (leg origin) + buffer. Exit = fib TP ladder (30% / 40% /
runner) with stop→breakeven on TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. In
framework terms this is the **mean-reversion bucket** (bucket #1).

## Decisions already locked
- **Backtest** — Python bar-replay through the validated engines; **live** — the same Python bot
  driving MT5. No MQL5 port for forex/metals. (Futures live = a later one-time NinjaScript port of
  a proven winner.)
- **Sizing** — reproduce the Pine's fixed %-risk first (clean parity), then swap in the dynamic
  sizing engine before demo.
- **Session** — force-flat before the 17:00 NY close (intraday-only rule wins over the Pine's
  overnight runner).
- **Timeframe** — a runtime parameter, never baked in. The one timeframe-aware bit of the strategy
  is the Macro fib (on at ≤5m only) — real behavior, kept, driven by the true timeframe.
- **Data** (RESOLVED 2026-07-15 by a live PU Prime probe — see below). Pull bars **directly** from
  the broker in correctly-sized windows: M1 ~30d, M5 ~240d, M15 ~2yr. Cache to disk (parquet),
  reuse. Resample only ever UP (e.g. 30m/1h from M15). **Real ticks go back 2+ years** — the true
  floor: they let us (a) build any timeframe exactly and (b) model limit fills honestly at tick
  resolution instead of guessing intrabar path. The old "pull M1 and resample up" premise is
  dropped — the broker serves M5/M15 bars directly, and ticks sit below every bar.

## Phase-0 findings (PU Prime demo, XAUUSD.s, probed 2026-07-15)
Account #700119432 (PUPrime-Demo). Broker symbol is `XAUUSD.s` (`.s` suffix).
- **Bars, direct pull** (`copy_rates_range` in a sized window): M1 available ~30d, M5 ~240d
  (8 months, oldest 2025-11-17), M15 ~720d (2 years, oldest 2024-07-25). `copy_rates_from_pos`
  errors on this terminal — always use a dated range.
- **Ticks** (`copy_ticks_range`, real bid/ask): 2yr back = 192k/day, 1000d = 232k/day, ~5yr = 105k/day
  (a single-day probe at 1460d hit a thin/weekend day and read 0 — tick history is deep but patchy,
  so never treat one empty day as the edge).
- **Spread** on gold ~$0.33 (33 points) — small against the A+ strategy's multi-dollar fib targets.
- **"Suspicious" M5 gaps** are largely the daily 17:00-NY 1-hour gold break — the exact gap we
  flatten before — not data holes.
- **History depth:** 15m ≈ 2yr of bars; 5m ≈ 8 months of bars (extendable via ticks); parity at 5m
  is directly served. No M1-resample needed.

## File locations (DECIDED 2026-07-15)
- **Runner** → a new top-level **`backtest/`** package. Strategy- and instrument-agnostic shared
  infra, same character as `engines/`; importable standalone (CLI, the `/audit-strategy` parity
  harness, CI) without the FastAPI app. The lab consumes it through a thin `runner="python"` adapter
  in `runner_dispatch` — the same thin-shim pattern engines already use.
- **Strategy logic** → **`strategies/python/mpc_sos_fade/`**, fitting the existing "strategies organized
  by platform" convention. One copy, imported by both the runner (backtest) and the future live bot.

---

## Two deliverables, kept separate

**A — The Python runner** (shared backtest infra — instrument- and strategy-agnostic; every future
Python strategy reuses it).
**B — The MPC SOS Fade bot** (the strategy logic on top of the canonical engines).

The runner is built once. The bot is one of many that will run on it.

### B-Y build (landed 2026-07-15) — `strategies/python/mpc_sos_fade/`
Five modules, a line-for-line port of `mpc_strategy.pine`'s A+ block + execution layer:
- `config.py` — `SosFadeConfig`: every trade-affecting Pine input toggle, same name + default (toggle parity).
- `signals.py` — `SignalAdapter`: replay `BarState` → the Pine-named per-bar inputs. Two non-trivial
  reconstructions: `recentSSL`/`recentBSL` (H4>Day>session priority off the liquidity sweep events) and
  `bullDivActive`/`longVeto` (recomputed WITH the structure-break staleness the standalone RSI engine can't
  see — do NOT use the engine's convenience `bull_active`).
- `sequence.py` — `SosFadeSequence`: the Stage 1→4 state machine + retro-link + sequence-death + arm-source snapshot.
- `execution.py` — `Execution`: entry edge → resting limit → TP1/TP2/runner ladder → staged stop + ratchet →
  %-risk sizing → graded R, on a broker emulator that reproduces TradingView's calc-on-close one-bar delay and
  its intrabar path assumption (open nearer high ⇒ targets fill before stop). **The intrabar assumption is the
  #1 parity risk — only `compare_strategy.py` confirms it.**
- `strategy.py` — `MpcSosFadeStrategy`: the driver (`run(df, warmup=…)` / `step(bar_state)`), collects the
  per-bar decision stream + trade list.
15 offline tests green: `command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_sos_fade/tests/`.
**No `algos/shared/` shims were needed** — the strategy reads `backtest.replay` output, which already imports
the engines by bare name.

---

## Deliverable A — The Python runner

Six pieces, each testable alone.

- **A0 — Data layer.** *(Phase-0 probe DONE — see findings above.)* Pull broker bars directly at the
  base timeframe (M5/M15/M1) via the MT5 agent, cache to disk as parquet (pull once, reuse).
  Resample-UP helper for any higher TF. Lazy **tick** fetch (2yr available) for the fill model.
  Timeframe + symbol are inputs.
- **A1 — Replay loop.** *(DONE 2026-07-15 — `backtest/replay/`.)* Feed bars one at a time through
  the engine stack in Pine order — structure → fib → FVG → RSI-divergence → liquidity → sessions —
  producing per-bar engine state (`BarState`). `iter_bars(df)` → `ReplayBar` (0-based index +
  epoch-ms UTC); `EngineStack.step` / `run(df, warmup=…)`. Imports the canonical engines by bare
  name (`engines/` on `sys.path`) — no `algos/shared/` shim needed for the backtest path.
- **A2 — Fill & cost model.** Simulate limit fills using **real ticks** within each bar (honest
  intrabar path, not a wick guess); charge spread + commission + a pessimistic slippage cushion.
  Produces the trade list. (This is the honest-assumption layer; demo confirms it.)
- **A3 — Output adapter.** Emit the exact `{equity_curve, daily_pnl, kpis, engine_trades}` shape
  `backtest_runner._handle_complete` already consumes. Register as `runner="python"` in
  `runner_dispatch`, next to `"mt5"`/`"ninjatrader"`.
- **A4 — Local sweep / optimizer.** Run the whole thing over a parameter grid in memory — no VPS,
  no terminal lock. Replaces the native optimizer for Python strategies.

**Reused untouched from the lab (do NOT rebuild):** every KPI (canonical Sharpe, Calmar, PF, max
DD, profit concentration, expectancy), regime tagging, the ruleset evaluator, worthiness tiers,
Monte Carlo, walk-forward, sensitivity, A–F grading, the dynamic sizing engine + decision log, the
news/holiday filter, and the entire frontend. A3 is the only seam — everything downstream is the
lab's existing lens.

---

## Deliverable B — The MPC SOS Fade bot (S.Y.S.T.E.M.)

- **S — Spec.** One page of exact, machine-followable rules for the A+ sequence, stop, TP ladder,
  sizing, and the flat-by-close rule. *Sign-off gate — nothing is built until this is approved.*
- **Y — Build.** The A+ state machine + execution, on the engines. First add the missing
  `algos/shared/` shims (fibonacci, fvg, rsi_divergence, liquidity, sessions — only structure has
  one today).
- **Parity gate (LWG-specific).** `compare_strategy.py`: replay a TradingView export through the
  Python bot and prove the same entries/exits/R as `mpc_strategy.pine`. **Nothing is trusted until
  this is exit 0** — the same discipline as every engine port. This is not a one-time gate; it
  becomes the standing regression harness below.
- **S — Stress test.** Backtest years of XAUUSD; honest KPIs vs the framework floor (Sharpe ≥ 1,
  Calmar ≥ 1, profit concentration < 60%, expectancy > 0 after costs).
- **T — Threshold.** Parameter-sensitivity sweep + walk-forward. Confirm a plateau, not a spike.
- **E — Evaluate.** MT5 demo forward-test, 30–60 days, live conditions, via the algos bridge.
- **M — Master.** Deploy with discipline. Futures, if ever, is the one-time NinjaScript port here.

---

## Two different "parity" checks — don't confuse them

There are **two** parities, and they answer different questions. Both matter; they run on very
different cadences.

| | **Logic parity** | **Feed parity** |
|---|---|---|
| Question | Does the Python make the *same decisions* as the Pine? | Do MT5's bars *line up* with TradingView's? |
| Tool | `compare_strategy.py` / `/audit-strategy` | `backtest/tools/compare_feeds.py` |
| Input | TradingView's **own** exported bars, replayed through Python | An MT5 pull vs a TradingView export of the same window |
| Target | **Exact** — exit 0, or it's a bug | **Approximate** — measure the gap, don't eliminate it |
| Cadence | Every time the Pine changes (see below) | Baseline + config-change + demo campaigns (see below) |

**Exact bar-for-bar price match between MT5 and TradingView is not realistic** — different brokers,
different feeds; gold differs by cents bar to bar. So feed parity never gates logic. The logic gate
replays TradingView's *own* bars, so it's independent of the feed.

## Feed parity (MT5 vs TradingView) — `compare_feeds.py`

Reads a TradingView "Export chart data" CSV, pulls the matching MT5 window (same symbol/TF/dates)
through `backtest.data.BarSource`, aligns the two on timestamp, and reports:
1. **Clock offset** — the whole-hour shift that best aligns the timestamp grids. `0` = aligned.
   Anything else is the thing that silently breaks the session/liquidity/VWAP engines: MT5 returns
   **broker-server** time and our agent labels it UTC, so a UTC+2 server puts every session 2h off.
   A non-zero offset is a real bug to fix in the agent's time handling **before** demo (exit 2).
2. **Coverage** — matched / TV-only / MT5-only bar counts (data holes, the daily 17:00-NY gold gap).
3. **OHLC drift** — mean/max |Δ| on matched bars + close drift as a % of price. Gold's ~$0.30
   spread is normal; a structural mismatch (wrong symbol, wrong session offset) is not (exit 2 past
   `--warn-pct`, default 0.05%).

Pure alignment math (parse / infer-TF / detect-offset / diff) is unit-tested offline in
`backtest/tests/test_compare_feeds.py`; only the live pull touches the network (needs the MT5 agent
+ SSH tunnel — see `backtest/CLAUDE.md`).

**How often to run it (it is NOT a per-backtest check — the feed doesn't move bar to bar):**
- **Once now, as a baseline** — record the offset (expect 0 after any agent fix) and the typical
  gold drift, so a future change has something to diff against.
- **Whenever the MT5 agent's time handling changes, or the broker/terminal is upgraded** — a server
  timezone change would shift the clock offset silently; this is the guard against that.
- **At the start of every demo/live campaign, then ~monthly during it** — confirms the feed the bot
  executes on still matches the research chart within tolerance.
- **Any time live/backtest trades look off vs the TradingView chart** — first thing to rule out.

The final proof the small feed gap doesn't hurt the edge is the **demo forward-test (E)** — same
code, real PU Prime fills.

### Baseline result (2026-07-15, XAUUSD.s vs `VANTAGE_XAUUSD, 15` export, ~12.8k M15 bars, Dec 2025→Jul 2026)
- **Feed quality: excellent.** After alignment, full coverage (12805/12805 matched, 0 missing) and
  close drift **$0.14 mean = 0.0030% of price** (open a touch higher at $0.24 — different session-open
  ticks between brokers). PU Prime and the TradingView feed agree; the feed gap is a non-issue.
- **Clock offset: a real bug to fix, found.** MT5 timestamps run **+2h (winter) / +3h (summer)** ahead
  of true UTC — the broker server clock is on **DST (MetaTrader EET/EEST, UTC+2/UTC+3)**, and the
  agent (`algos/markets/fx/tools/mt5_agent.py`, `datetime.utcfromtimestamp(r["time"])`) labels that
  broker time as UTC. So every bar we pull is stamped 2–3h wrong.
- **Why it matters / who's affected:** the *logic* parity harness is unaffected (it replays
  TradingView's own true-UTC bars). But any **time-driven engine on live/backtest MT5 data**
  (sessions, liquidity, VWAP, SVP, news) would fire 2–3h off. **OWED before demo (E):** make the
  agent return **true UTC, DST-aware** (not a constant offset). Re-run `compare_feeds.py` after the
  fix → expect a flat 0h across the whole window. Tracked as an A2/agent-fix item.

---

## Keeping Pine and Python in lockstep (the regression harness)

You and your brother edit `mpc_strategy.pine` in TradingView constantly — flipping toggles to see
trade count / P&L move. Whenever the Pine changes, you need a one-command way to prove the Python
(MT5) bot is still 100% identical, under *whatever* toggles you used. This is the same pattern as
the engine parity checks (`compare_fib.py`, etc.), applied to the whole strategy.

**Three parts:**
1. **`mpc_strategy_export.pine`** — an instrumented copy of the strategy (kept byte-identical to the
   trade logic, drawing removed) that `plot()`s a per-bar **decision stream**: `longArmed` /
   `shortArmed`, `longEdge` / `shortEdge`, entry fills, exit fills (TP1/TP2/RUN price + bar), stop,
   stage, veto, and R. It **also plots the value of every input toggle** as a column, so the export
   carries its own config.
2. **`compare_strategy.py`** — reads the CSV, reads the toggle columns, configures the Python bot to
   the **exact same settings**, replays the same bars, and diffs the decision stream + trade list.
   Exit 0 = identical. On a mismatch it names the **first bar** and field that diverged, so you know
   exactly where the Pine and Python parted.
3. **`/audit-strategy`** — a slash command in `.claude/commands/audit-strategy.md`, parallel to
   `/audit-engines`. Typing it pulls the latest export, runs `compare_strategy.py`, and reports
   parity or the pinpointed diff. Created in the parity-gate phase (it orchestrates that script), so
   it exists the moment the harness does — not before (no broken button).

**Toggle parity is a hard requirement:** the Python bot must declare **every** Pine input — same
name, same default — so any config you and your brother pick reproduces exactly. A new toggle in the
Pine is a new toggle in the bot.

**The loop when the Pine changes:**
1. Brother edits `mpc_strategy.pine` in TradingView.
2. Re-paste it into the repo (git) — same re-paste discipline the engine already uses.
3. Update `mpc_strategy_export.pine` to match (only if the trade logic changed).
4. Export a CSV (or a few, under different toggle sets) from TradingView.
5. Run the wrapper → exit 0 (parity holds) or a pinpointed diff.
6. If it diverged, update the Python bot to match, re-run until exit 0.

A parity failure is the harness doing its job — it catches a Pine change the Python doesn't have yet.

## Build order (how A and B interleave)

1. **B-S** — write + approve the A+ spec.
2. **A0 + A1** — data layer and replay loop (needs the engine shims from B-Y, so shims come here).
3. **B-Y** — the A+ state machine + execution.
4. **A2 + A3** — fill/cost model + output adapter → first end-to-end backtest.
5. **Parity gate** — `compare_strategy.py` green before any result is trusted.
6. **A4** — local optimizer.
7. **B stress → threshold → demo.**

Parity first. Then does the edge survive honest costs. Then does it survive data it wasn't tuned
on. Then does it survive real fills on demo. Only then, real capital.
