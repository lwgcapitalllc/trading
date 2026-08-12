"""The spread sampler has to tell a SHUT MARKET from a symbol nobody is watching.

🔴 **Written after the tool got this wrong on a live terminal.** On 2026-08-12 the bot's account
was switched from the PU Prime Standard demo to the ECN one, which quotes `XAUUSD.p` rather than
`XAUUSD.s`. `broker_facts.py --sample 300` then ran for five full minutes in the middle of the
London/NY overlap and reported **"no fresh ticks - market shut?"** — because MT5 streams ticks only
for symbols in Market Watch, and the new account had never been asked to watch that one.

The symbol specification read fine throughout (`symbol_info` does not need Market Watch), so every
other line of the report was correct and current. Only the measurement that the tool exists for
came back empty, wearing a message that points at the market.

Both tests here are about the same rule this repo keeps re-learning: **"no" and "cannot ask" must
never be the same value.** A tick that never arrived and a tick that never moved are different
failures with different fixes, and the version that collapsed them sent the reader at the exchange
instead of at the terminal.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from algos.tools.broker_facts import sample_spread  # noqa: E402


class _Tick:
    def __init__(self, bid: float, ask: float, time_msc: int):
        self.bid, self.ask, self.time_msc = bid, ask, time_msc


class _FakeMt5:
    """A terminal that streams a symbol only once it has been SELECTED.

    ⚠ This is the half a laxer fake would have got wrong. A fake whose `symbol_info_tick` always
    answers cannot express the defect at all — the tool would have passed its tests and failed on
    the only account it was pointed at.
    """

    def __init__(self, *, quotes: bool = True, moving: bool = True):
        self._quotes = quotes          # does this account quote the symbol at all
        self._moving = moving          # is the market actually printing new ticks
        self._watched: set[str] = set()
        self._n = 0
        self.select_calls: list[tuple[str, bool]] = []

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        self.select_calls.append((symbol, enable))
        if not self._quotes:
            return False
        self._watched.add(symbol)
        return True

    def symbol_info_tick(self, symbol: str):
        if symbol not in self._watched:
            return None
        if self._moving:
            self._n += 1
        return _Tick(4000.00, 4000.12, 1_000 + self._n)


def test_an_unwatched_symbol_is_reported_as_not_streaming_never_as_a_shut_market():
    m = _FakeMt5(quotes=False)

    d = sample_spread(m, "XAUUSD.p", seconds=0.1, point=0.01)

    assert d["n"] == 0
    assert d["none_reads"] > 0, "the terminal answered nothing and that has to be counted"
    assert d["stale_reads"] == 0, "nothing repeated — there was no tick to repeat"
    assert d["selected"] is False
    assert "not streaming" in d["note"]
    assert "Market Watch" in d["note"]
    assert "NOT a shut market" in d["note"]
    # The old message, and the whole reason this test exists.
    assert "market shut" not in d["note"].lower()


def test_a_repeated_tick_is_still_reported_as_a_shut_market():
    """The other direction, so the fix does not simply rename one wrong answer into another."""
    m = _FakeMt5(quotes=True, moving=False)

    d = sample_spread(m, "XAUUSD.p", seconds=2.5, point=0.01)

    assert d["n"] <= 1, "the first read has nothing to compare against; every later one repeats"
    assert d["stale_reads"] > 0
    assert d["selected"] is True


def test_the_symbol_is_selected_before_sampling():
    m = _FakeMt5()

    sample_spread(m, "XAUUSD.p", seconds=0.1, point=0.01)

    assert m.select_calls == [("XAUUSD.p", True)]


def test_a_watched_moving_symbol_measures_its_spread():
    m = _FakeMt5()

    d = sample_spread(m, "XAUUSD.p", seconds=0.1, point=0.01)

    assert d["n"] >= 1
    assert d["none_reads"] == 0
    assert round(d["median"], 2) == 0.12
    assert round(d["median_points"]) == 12
