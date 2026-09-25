"""FFT's setup reporting (`setups.py`) — driven by the REAL strategy over real PU Prime bars.

No fake strategy here, on purpose: the watch reads the strategy's own decision, touches and fill,
and a stand-in built for the test would answer whatever its author believed those were (root
`CLAUDE.md` rule 13). Every test runs `FftStrategy` itself.

⚠ Each "Mutation:" line was RUN on 2026-09-24 and went RED (rule 12). Run mutations with
PYTHONDONTWRITEBYTECODE=1 — see `test_fft.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest.setups import DEAD, FILLED, RESTING, implements_contract  # noqa: E402

from fft import FftStrategy  # noqa: E402

_CACHE = _ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
pytestmark = pytest.mark.skipif(not _CACHE.exists(), reason="no PU Prime M1 cache on this machine")


def _bars(start: str, end: str):
    import pandas as pd

    df = pd.read_csv(_CACHE, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    return df[(df.time >= start) & (df.time < end)].set_index("time").astype(float)


def _replay(df, *, watch: bool = True):
    """Step the strategy the way the live runner does, draining setups after every minute."""
    from backtest.replay import EngineStack, iter_bars

    s = FftStrategy()
    s.execution.bar_ms = 60_000
    if not watch:
        s.setup_watch.observe = lambda *a, **k: None
    stack = EngineStack(s.engine_config())
    snaps = []
    for bar in iter_bars(df):
        s.step(stack.step(bar))
        snaps += [(bar.timestamp_ms, x) for x in s.execution.drain_setups()]
    return s, snaps


@pytest.fixture(scope="module")
def run():
    return _replay(_bars("2025-09-01", "2025-12-01"))


def test_the_runner_sees_fft_as_reporting_setups():
    """Mutation: delete `live_setups` from `FftExecution` → the runner's health-room notice returns."""
    ex = FftStrategy().execution
    assert implements_contract(ex)
    assert ex.setup_key_scheme == "fft-time-v1"


def test_every_trade_was_announced_with_its_limit_before_it_filled(run):
    """Mutation: open the setup only in step 1 (at the touch) → no RESTING before any fill."""
    s, snaps = run
    assert s.execution.trades, "the window must hold trades or this test proves nothing"
    filled = {sn.key: ms for ms, sn in snaps if sn.state == FILLED}
    for t in s.execution.trades:
        keys = [k for k, ms in filled.items() if ms == t.entry_ms]
        assert len(keys) == 1, f"trade at {t.entry_ms} has no ENTERED reply"
        rested = [ms for ms, sn in snaps if sn.key == keys[0] and sn.state == RESTING]
        assert rested and min(rested) < t.entry_ms


def test_each_setup_ends_once_and_is_never_reported_after(run):
    """Mutation: drop the `_open.pop` in `_end` → the setup is re-reported after it ended."""
    _, snaps = run
    ended = {}
    for ms, sn in snaps:
        assert sn.key not in ended, f"{sn.key} reported after it ended"
        if sn.state in (FILLED, DEAD):
            ended[sn.key] = sn.reason
    assert ended and all(ended.values()), "every ending must say why"


def test_reporting_moves_no_trade_and_no_touch(run):
    """The watch on or off, the same trades and the same spent legs, field for field.
    Mutation: `strat._decision = None` at the end of `observe` → trades vanish, RED."""
    s_on, _ = run
    s_off, _ = _replay(_bars("2025-09-01", "2025-12-01"), watch=False)

    def trades(s):
        return [(t.entry_ms, t.dir, t.entry_price, t.exit_ms, t.exit_price, t.qty)
                for t in s.execution.trades]

    def touches(s):
        return [(x.ts_ms, x.dir, x.kind, x.traded, x.why) for x in s.touches]

    assert trades(s_on) == trades(s_off)
    assert touches(s_on) == touches(s_off)


def test_a_setup_keeps_its_key_when_the_bot_warms_from_a_different_start():
    """A live re-warm renumbers every bar. The same setup must carry the same key, or a restart
    posts a second root for it. Mutation: key on the 5m anchor INDEX → the keys differ, RED."""
    df = _bars("2025-08-01", "2025-10-15")
    _, a = _replay(df)
    _, b = _replay(df[df.index >= "2025-08-12"])
    cut = 1_757_000_000_000  # 2025-09-04, well after both warm-ups
    ka = {sn.key for ms, sn in a if ms >= cut}
    kb = {sn.key for ms, sn in b if ms >= cut}
    assert ka and ka == kb
