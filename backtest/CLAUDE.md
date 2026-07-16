# CLAUDE.md — backtest/ (the Python backtest runner)

**Purpose:** Standing instructions for `backtest/`, the LWG Python bar-replay backtest runner.
**Scope:** This package only — the data layer, replay loop, fill/cost model, output adapter, and
local optimizer. It does NOT cover the engines it replays (`engines/`), the strategies it runs
(`strategies/python/`), or the lab that consumes it (`command-center/`).
**Status:** In build. A0 (data layer) + A1 (replay loop) landed 2026-07-15; A2–A4 pending. See `docs/MPC_APLUS_BUILD_PLAN.md`.
**Last reviewed:** 2026-07-15

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
- **A2 — Fill & cost model** *(pending)*. Real-tick intrabar limit fills + spread/commission/slippage.
- **A3 — Output adapter** *(pending)*. Emit the lab's `{equity_curve, daily_pnl, kpis, engine_trades}`.
- **A4 — Local optimizer** *(pending)*. In-memory parameter sweep, no VPS lock.

## Tools

- **`tools/compare_feeds.py`** — feed-parity check: MT5 pull vs a TradingView export of the same
  symbol/TF/window. Reports **clock offset** (0 = aligned; non-zero = the broker-server-time bug
  that shifts every session — fix before demo), coverage, and OHLC drift. This is *data* parity, not
  *logic* parity (that's the strategy's `compare_strategy.py`) — MT5 and TradingView are different
  feeds and never match exactly; the tool measures the gap. **Not a per-backtest check.** Run it:
  once as a baseline, whenever the agent's time handling or the broker/terminal changes, at the start
  of each demo campaign then ~monthly, and any time trades look off vs the chart. Needs the MT5 agent
  + tunnel; the alignment math is unit-tested offline. Full rationale + cadence: `docs/MPC_APLUS_BUILD_PLAN.md`.

## Data layer (A0) — how it works

`backtest.data.BarSource.load(symbol, timeframe, start_date, end_date)` is the one entry point:
1. `resolve_base_tf` picks the base timeframe to pull — the target itself if the broker serves it
   (M1/M5/M15/M30/H1/H4/D1), else the largest served timeframe that divides it.
2. Base bars are served cache-first (`BarCache`, one CSV per symbol+tf under `backtest/cache/`,
   git-ignored). A miss fetches the whole window from the MT5 agent (`Mt5Agent`, HTTP on
   localhost:8766 via the SSH tunnel) and records the fetched date range (`RangeCoverage`).
3. `resample_up` aggregates to the target timeframe if base ≠ target — **never down**.
4. The result is sliced to `[start_date, end_date]` inclusive.

**PU Prime demo facts (probed 2026-07-15, XAUUSD.s):** bars pull directly — M1 ~30d, M5 ~240d,
M15 ~2yr; real ticks go back 2+ years. Broker symbol carries a `.s` suffix. See the plan's Phase-0
findings. The agent has **no /ticks endpoint yet** — adding one is A2, not A0.

## Rules

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
