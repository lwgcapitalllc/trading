"""End-to-end driver smoke test — the full chain on the real engine stack.

Proves MpcSosFadeStrategy.run() drives SignalAdapter -> SosFadeSequence -> Execution over
synthetic multi-day bars without error, records one decision per (post-warmup) bar,
and never books an impossible trade (R is finite, equity stays a number).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from mpc_sos_fade import MpcSosFadeStrategy  # noqa: E402


def test_driver_runs_end_to_end():
    strat = MpcSosFadeStrategy().run(synth_bars(12), warmup=100)
    assert len(strat.decisions) == 12 * 96 - 100
    # equity is a finite number and every completed trade has a finite R
    assert isinstance(strat.execution.equity, float)
    for t in strat.execution.trades:
        assert t.r == t.r          # not NaN
        assert t.qty > 0


def test_driver_is_deterministic():
    a = MpcSosFadeStrategy().run(synth_bars(8))
    b = MpcSosFadeStrategy().run(synth_bars(8))
    assert [d.long_armed for d in a.decisions] == [d.long_armed for d in b.decisions]
    assert len(a.execution.trades) == len(b.execution.trades)


def test_engine_config_pins_every_input_the_pine_moved_off_its_default():
    """The Pine's engine inputs are NOT in the exported decision stream, so the bot has to
    pin them by hand — and an unpinned one is invisible until a fresh export disagrees.
    `fvg_require_close` cost exactly that on 2026-07-26: `mpc_strategy.pine` HARDCODES the
    middle-bar close-cleared check while the FVG engine defaults it off, so Python held gaps
    the Pine never created and produced a phantom entry edge.

    `fvg_threshold_pct` was the same trap one step quieter (found 2026-07-31): it was never
    pinned at all, and the bot only worked because `EngineConfig` happened to default to 0.1.
    That default was itself stale relative to the engine, so "tidying" it up would have
    silently moved this bot. Pinned now — an assertion here is what makes the shared default
    free to change. Lock all four."""
    ec = MpcSosFadeStrategy.engine_config()
    assert ec.fvg_max_count == 7           # Pine fvgMaxCount (engine default 8)
    assert ec.fvg_require_close is True    # Pine hardcodes close[1] past the gap
    assert ec.show_internal is False       # Pine "Show Internal Structure" defaults OFF
    assert ec.fvg_threshold_pct == 0.1     # Pine fvgThreshHTF at 15m (engine default 0.0)
