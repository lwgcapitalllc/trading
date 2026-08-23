"""The hold's WORST price can never be past the price the stop would have closed at.

🔴 THIS FAILS SILENTLY WHEN IT BREAKS. The excursion is reporting-only — no decision reads it —
so a wrong value changes no trade, no R and no equity curve. It surfaces as a chart drawing a
drawdown marker ABOVE its own stop line, and as an adverse-excursion figure of 2.22R on a trade
that lost exactly 1.0R. Both of those shipped (run `976aff9ec279`, 77 of 77 stopped-out trades).

The rule is DETERMINATE, not a guess about what happened first inside the bar: the stop is
triggered BY the adverse move, so any price past it necessarily came at or after the fill.

⚠ The favourable side is deliberately NOT bounded — a target is partial, so price past it is
still the trade's own move. `test_the_favourable_side_is_left_alone` pins that.

⚠ The ENTRY bar is deliberately NOT bounded either, and that is not an oversight — the stop is
not managed until the next bar (the one-bar order delay every fill model here is built on), so a
first-bar excursion past the stop is real exposure the trade genuinely sat through. Measured over
2020-01-01 → 2026-08-22 that is all 4 of the remaining cases, down from 54.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))

from mpc_sos_fade.execution import Execution  # noqa: E402


def _bar(high: float, low: float, open_: float) -> SimpleNamespace:
    return SimpleNamespace(high=high, low=low, open=open_)


def _widen(direction: int, stop: float, bar, *, ext_high: float, ext_low: float, adj: float = 0.0):
    """Call the bar-widen with nothing but the state it reads. A real `Execution` needs a config,
    a fib, an engine stack and a filled position to reach this line; the arithmetic under test
    needs four numbers."""
    fake = SimpleNamespace(
        _pos_dir=direction,
        _ext_high=ext_high,
        _ext_low=ext_low,
        _current_stop=lambda: stop,
    )
    return Execution._widen_hold(fake, bar, adj)


def test_a_short_cannot_record_a_price_above_its_stop():
    """The bar that stopped the trade out: high 5100.35, stop 5086.62. The trade was closed at
    5086.62, so 5100.35 is price after it was flat — the exact shape on run `976aff9ec279`."""
    hi, lo = _widen(-1, 5086.62, _bar(5100.35, 5070.0, 5080.0), ext_high=5075.36, ext_low=5068.37)
    assert hi == 5086.62


def test_a_long_cannot_record_a_price_below_its_stop():
    hi, lo = _widen(1, 1965.96, _bar(1970.0, 1957.87, 1967.0), ext_high=1967.79, ext_low=1966.5)
    assert lo == 1965.96


def test_a_bar_that_OPENS_past_the_stop_is_bounded_by_the_OPEN_not_the_stop():
    """The stop fills at the open when the bar gaps through it (`_fill_price`), and that fill is
    worse than the stop and real. Bounding at the stop here would report a better worst price than
    the trade actually got — a lie in the flattering direction, which is the worse one."""
    hi, lo = _widen(1, 1965.96, _bar(1966.0, 1957.87, 1964.16), ext_high=1967.79, ext_low=1967.0)
    assert lo == 1964.16


def test_a_bar_that_never_reaches_the_stop_is_untouched():
    """The bound must be a CEILING, not a replacement. A quiet bar has to keep its own extreme, or
    every open trade would report its worst price as the stop."""
    hi, lo = _widen(-1, 5086.62, _bar(5080.0, 5070.0, 5075.0), ext_high=5076.0, ext_low=5072.0)
    assert hi == 5080.0


def test_the_hold_only_ever_WIDENS():
    """A later, milder bar must not shrink the worst price already recorded."""
    hi, lo = _widen(-1, 5086.62, _bar(5078.0, 5074.0, 5076.0), ext_high=5083.0, ext_low=5070.0)
    assert hi == 5083.0
    assert lo == 5070.0


def test_the_favourable_side_is_left_alone():
    """A short's favourable side is the LOW, and a target banks only a portion — the runner stays
    open, so price past TP1 is still this trade's move. Only the stop closes everything."""
    hi, lo = _widen(-1, 5086.62, _bar(5100.35, 5000.0, 5080.0), ext_high=5075.36, ext_low=5068.37)
    assert lo == 5000.0


def test_the_ASK_adjustment_moves_the_bound_with_the_bar():
    """A short is managed on the ask, so the bar is shifted and the comparison has to be made in
    the same currency. Bounding a shifted high against an unshifted stop is an off-by-a-spread."""
    hi, lo = _widen(-1, 5086.62, _bar(5085.0, 5070.0, 5080.0), ext_high=5075.0, ext_low=5070.0,
                    adj=0.5)
    assert hi == 5085.5  # 5085 + 0.5 ask, still under the stop — not clamped
    hi2, _ = _widen(-1, 5086.62, _bar(5090.0, 5070.0, 5080.0), ext_high=5075.0, ext_low=5070.0,
                    adj=0.5)
    assert hi2 == 5086.62  # 5090.5 is past the stop, so the stop is the answer
