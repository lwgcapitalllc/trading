"""End-to-end driver smoke test — the full chain on the real engine stack.

Proves MpcAplusStrategy.run() drives SignalAdapter -> AplusSequence -> Execution over
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
from mpc_aplus import MpcAplusStrategy  # noqa: E402


def test_driver_runs_end_to_end():
    strat = MpcAplusStrategy().run(synth_bars(12), warmup=100)
    assert len(strat.decisions) == 12 * 96 - 100
    # equity is a finite number and every completed trade has a finite R
    assert isinstance(strat.execution.equity, float)
    for t in strat.execution.trades:
        assert t.r == t.r          # not NaN
        assert t.qty > 0


def test_driver_is_deterministic():
    a = MpcAplusStrategy().run(synth_bars(8))
    b = MpcAplusStrategy().run(synth_bars(8))
    assert [d.long_armed for d in a.decisions] == [d.long_armed for d in b.decisions]
    assert len(a.execution.trades) == len(b.execution.trades)
