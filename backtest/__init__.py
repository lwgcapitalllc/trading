"""backtest — the LWG Python backtest runner.

Strategy- and instrument-agnostic backtest infrastructure, the same character as
`engines/`: a shared library, not owned by any one app. It pulls broker data,
replays it bar-by-bar through the canonical `engines/`, simulates fills against
real ticks, and emits the `{equity_curve, daily_pnl, kpis, engine_trades}` shape
the command-center lab already consumes (registered there as `runner="python"`).

Subpackages:
    data/   — the data layer (A0): broker-bar pull, disk cache, resample-up, ticks.

Everything is importable standalone (CLI, the /audit-strategy parity harness, CI)
without dragging in the FastAPI app. See docs/MPC_SOS_FADE_BUILD_PLAN.md.
"""
