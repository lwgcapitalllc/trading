"""Realign's setup reporting (`setups.py`) — driven by the REAL strategy over real PU Prime bars.

No stand-in strategy: the watch reads the tracker's armed setups and what the order layer did, and
a fake built for the test would answer whatever its author believed those were (root `CLAUDE.md`
rule 13). Every test steps `RealignStrategy` through the live contract, as the runner does, with
`realign_1`'s own settings.

⚠ Each "Mutation:" line was RUN on 2026-09-24 and went RED (rule 12), with
PYTHONDONTWRITEBYTECODE=1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS), str(_ROOT / "engines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest.setups import DEAD, FILLED, WATCHING, implements_contract  # noqa: E402

from realign import LAB_STRATEGY  # noqa: E402

_CACHE = _ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M5.csv"
_BOT = _ROOT / "algos" / "markets" / "fx" / "instances" / "realign_1" / "config.json"
pytestmark = pytest.mark.skipif(not _CACHE.exists(), reason="no PU Prime M5 cache on this machine")


def _strategy():
    params = dict(json.loads(_BOT.read_text())["strategy_params"])
    s = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"](**params), initial_capital=10_000.0)
    s.execution.bar_ms = 300_000
    return s


def _bars(start: str, end: str):
    import pandas as pd

    df = pd.read_csv(_CACHE, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    return df[(df.time >= start) & (df.time < end)].set_index("time").astype(float)


def _replay(df, *, watch: bool = True):
    from backtest.replay import EngineStack, iter_bars

    s = _strategy()
    if not watch:
        s.setup_watch.observe = lambda *a, **k: None
    stack = EngineStack(s.engine_config())
    snaps = []
    for bar in iter_bars(df):
        sig = s.signals.update(stack.step(bar))
        s.execution.step(sig, s.sequence.update(sig))
        snaps += [(bar.timestamp_ms, x) for x in s.execution.drain_setups()]
    return s, snaps


@pytest.fixture(scope="module")
def run():
    return _replay(_bars("2024-01-01", "2025-01-01"))


def test_the_runner_sees_realign_as_reporting_setups():
    """It inherits SOS Fade's reporting, switched off. Mutation: drop the `reports_setups`
    override → the runner says "no setup messages" again, RED."""
    ex = _strategy().execution
    assert implements_contract(ex)
    assert ex.setup_key_scheme == "realign-arm-time-v1"


def test_every_trade_is_an_ENTERED_reply_the_alert_layer_will_send(run):
    """⚠ Real bars cannot make this go red: over 2020-2026 no trade filled on a setup that was not
    already announced, so making a fill follow the momentum rule stays GREEN here (run 2026-09-24).
    That guarantee is pinned directly by the next test."""
    s, snaps = run
    assert s.execution.trades, "the window must hold trades or this test proves nothing"
    filled = {ms for ms, sn in snaps if sn.state == FILLED and sn.tradeable}
    for t in s.execution.trades:
        assert t.entry_ms in filled, f"trade at {t.entry_ms} has no ENTERED reply"


def test_a_FILL_is_always_announced_even_when_the_setup_never_was():
    """The guarantee real bars never reached: a fill on a setup the momentum rule kept silent must
    still post (as the root and ENTERED together). Mutation: drop `state == FILLED or` → RED."""
    from types import SimpleNamespace

    from realign.tracker import Armed

    s = _strategy()
    a = Armed(dir=1, armed_ms=1_700_000_000_000, target=2100.0)
    strat = SimpleNamespace(execution=SimpleNamespace(mom_dir=1))  # momentum WITH the long
    w = s.setup_watch
    assert w._tradeable(strat, a, WATCHING) is False  # silent while it would be refused
    assert w._tradeable(strat, a, FILLED) is True  # but a trade is never unannounced


def test_a_setup_is_announced_only_while_momentum_would_let_it_trade(run):
    """The measured lever (`notes/setup_alerts.md`). Mutation: `ok = True` for every watch →
    setups with the momentum WITH the trade are announced, RED."""
    _, snaps = run
    first = {}
    for ms, sn in snaps:
        if sn.state == WATCHING and sn.tradeable and sn.key not in first:
            first[sn.key] = sn
    assert first
    for sn in first.values():
        mom = next(c for c in sn.confluences if c.name.endswith("momentum"))
        assert mom.met, f"{sn.key} announced with the momentum with the trade"


def test_an_announced_setup_always_closes_its_thread_and_a_silent_one_stays_silent(run):
    """Mutation: drop `key in self._announced` → announced setups that die after momentum turns
    never post their NO TRADE, and the thread is left open forever, RED."""
    _, snaps = run
    announced, ended = set(), {}
    for ms, sn in snaps:
        if sn.state == WATCHING and sn.tradeable:
            announced.add(sn.key)
        if sn.state in (FILLED, DEAD):
            assert sn.key not in ended, f"{sn.key} ended twice"
            ended[sn.key] = sn
    for key in announced & set(ended):
        assert ended[key].tradeable and ended[key].reason
    silent = [sn for k, sn in ended.items() if k not in announced and sn.state == DEAD]
    assert silent and not any(sn.tradeable for sn in silent)


def test_reporting_moves_no_trade(run):
    """Mutation: clear `tracker._armed` at the end of `observe` → trades vanish, RED."""
    s_on, _ = run
    s_off, _ = _replay(_bars("2024-01-01", "2025-01-01"), watch=False)

    def book(s):
        return [(t.dir, t.entry_ms, t.entry_price, t.exit_ms, t.exit_price, t.qty)
                for t in s.execution.trades]

    assert book(s_on) == book(s_off)


def test_a_setup_keeps_its_key_when_the_bot_warms_from_a_different_start():
    """A live re-warm renumbers every bar; the arm TIME does not move. Mutation: key on the arm
    record's identity (`id(a)`) → the two runs disagree, RED."""
    df = _bars("2024-01-01", "2024-06-01")
    _, a = _replay(df)
    _, b = _replay(df[df.index >= "2024-01-20"])
    cut = 1_709_251_200_000  # 2024-03-01, well past both warm-ups
    ka = {sn.key for ms, sn in a if ms >= cut}
    kb = {sn.key for ms, sn in b if ms >= cut}
    assert ka and ka == kb
