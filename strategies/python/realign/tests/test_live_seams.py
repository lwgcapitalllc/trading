"""The seams that let `algos/live/` drive realign — and the proof they move no replayed trade.

🔴 **The runner never calls `RealignStrategy.step`.** It drives `signals` → `sequence` →
`execution.step(sig, seq)`, and until 2026-09-16 this strategy exposed its SOS Fade stages under
those names, so a live bot would have skipped the 15m frame and the tracker and crashed on the
first bar. The headline test below replays the committed golden export BOTH ways and requires the
same trades, bar for bar.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_PYPKGS), str(_ROOT / "engines")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from live_contract import verify_live_ready  # noqa: E402
from sos_fade.execution import Decision  # noqa: E402

from realign import LAB_STRATEGY  # noqa: E402
from realign.config import RealignConfig  # noqa: E402
from realign.execution import RealignExecution  # noqa: E402
from realign.tracker import RealignState  # noqa: E402

_RUNNER = _ROOT / "algos" / "live" / "runner.py"
_GOLDEN = Path(__file__).resolve().parents[1] / "exports" / "golden" / "VANTAGE_XAUUSD_M5_21327bars.csv"


def _runner_call_shape() -> list:
    """The three per-bar calls the live runner makes, READ FROM ITS SOURCE.

    ⚠ Parsed rather than imported: a strategy test must not drag in the live import graph. It
    REFUSES rather than returning empty, so the replay below cannot pass by imitating nothing.
    """
    text = _RUNNER.read_text(encoding="utf-8")
    m = re.search(r"def drain_primary\(self\):(.*?)return out", text, re.S)
    assert m, "drain_primary not found in the runner — has it been renamed?"
    calls = re.findall(r"self\._st\.(\w+)\.(\w+)\(", m.group(1))
    assert calls, "no strategy calls parsed from drain_primary"
    return calls


def test_the_runner_still_drives_the_three_stages_this_file_imitates():
    """If the runner changes its call shape, the replay below imitates a runner that no longer
    exists. MUTATION: rename `sequence` in the expected list and this goes red."""
    assert _runner_call_shape() == [
        ("signals", "update"), ("sequence", "update"), ("execution", "step")]


def test_this_strategy_satisfies_the_live_contract():
    """Presence only (see `verify_live_ready`). MUTATION: delete `entry_style` and it names it."""
    st = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"]())
    assert verify_live_ready(st) == []


def test_it_declares_a_market_entry():
    """🔴 Inheriting SOS Fade's "resting" halts the live bot on its first trade.
    MUTATION: remove the class constant — this reads "resting" and goes red."""
    assert RealignExecution.entry_style == "market"


def test_the_live_step_refuses_the_retest_entry():
    """A resting limit under a market declaration is a state the bridge cannot tell from a
    divergence. MUTATION: drop the check — the step runs and nothing raises."""
    cfg = dataclasses.replace(RealignConfig(symbol="XAUUSD"), realign_entry_mode="retest")
    st = LAB_STRATEGY["strategy"](cfg)
    with pytest.raises(RuntimeError, match="only the market"):
        st.execution.step(object(), None)


def test_a_market_entry_states_its_stop_on_the_bar_it_opens():
    """🔴 The bridge sends a market order WITH its stop, read off this bar's decision, and refuses
    a missing one — so an unset stop halts the bot on trade one. MUTATION: remove the
    `dec.stop = ...` line and this reads None."""
    ex = RealignExecution(RealignConfig(symbol="XAUUSD"), initial_capital=10_000.0)
    ex.mom_dir = -1   # a down move, so the shipped momentum filter keeps this long

    class _Sig:
        index, time_ms = 100, 1_600_000_000_000
        open = high = low = close = 100.0

    ex._state = RealignState(trigger_dir=1, trigger_stop=98.0, trigger_target=110.0,
                             trigger_level=99.0)
    dec = Decision(index=100)
    ex._place_entries(_Sig(), None, dec, None, None)
    assert ex._pos_dir == 1, "the market entry did not open"
    assert [f.kind for f in dec.fills] == ["entry"]
    assert dec.stop is not None and dec.stop < 100.0


@pytest.mark.skipif(not _GOLDEN.exists(), reason="golden export not present")
def test_the_live_call_shape_books_exactly_the_replayed_trades():
    """🔴 THE PROOF. The committed golden export replayed by `run()` and by the runner's three
    calls must book the same trades at the same bars and prices. MUTATION: make the public
    `signals` the real SOS Fade adapter again (the pre-fix wiring) — this crashes on the third
    argument; skip the tracker in the live path — it books no trades and goes red."""
    from gate_common import drop_live_final_bar
    from sos_fade.tools.compare_strategy import load_export

    from backtest.replay import EngineStack, iter_bars

    df = drop_live_final_bar(load_export(_GOLDEN))[["open", "high", "low", "close"]]
    cfg = RealignConfig(symbol="XAUUSD")
    strat = LAB_STRATEGY["strategy"]

    ref = strat(cfg, initial_capital=10_000.0)
    ref.run(df)

    live = strat(cfg, initial_capital=10_000.0)
    live.execution.bar_ms = 5 * 60_000
    stack = EngineStack(live.engine_config())
    for bar in iter_bars(df):
        state = stack.step(bar)
        sig = live.signals.update(state)
        seq = live.sequence.update(sig)
        live.execution.step(sig, seq)

    def book(s):
        return [(t.dir, t.entry_index, t.entry_price, t.exit_index, round(t.r, 6))
                for t in s.execution.trades]

    assert len(book(ref)) > 0, "the golden export booked no trades — the comparison is vacuous"
    assert book(live) == book(ref)
