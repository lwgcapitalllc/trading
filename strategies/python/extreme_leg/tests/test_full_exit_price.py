"""`full_exit_price()` — the price this strategy closes the WHOLE position at, or None.

Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The bridge
hands the answer to the broker so the exit fills AT that price rather than at market when the
5-minute bar shuts.

🔴 **THIS STRATEGY HAS ONE KIND OF TARGET AND IT ALWAYS TAKES THE LOT**, so its implementation is
two lines where SOS Fade's needs a branch per trade kind. The cases worth pinning are therefore
the two ways there is NO price to give: flat, and a target that is infinite.

⚠ **The infinite one is a real state this strategy produces, not a defensive flourish** — `_close`
and the trade record both test `math.isfinite` for exactly it. Passed through, the bridge would
hand a venue an infinity.

Every test was watched RED by mutation — see this package's CLAUDE.md.
"""

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from extreme_leg import ExtremeLegConfig  # noqa: E402
from extreme_leg.execution import ExtremeLegExecution, _Open  # noqa: E402


def _ex():
    return ExtremeLegExecution(ExtremeLegConfig(), initial_capital=10_000.0)


def _open(take_profit):
    return _Open(
        dir=1, entry_index=10, entry_ms=1_700_000_000_000, entry_price=4361.86,
        qty=29.0, stop=4340.44, open_stop=4340.44, take_profit=take_profit,
    )


def test_FLAT_has_no_target_because_there_is_no_trade_to_have_one():
    """Answering the last trade's price would put a target on whatever opened next."""
    assert _ex().full_exit_price() is None


def test_an_open_trade_answers_its_target_because_that_target_takes_everything():
    """The live case. This bot's open trade on 2026-09-09 carried exactly this shape."""
    ex = _ex()
    ex.pos = _open(4406.895)
    assert ex.full_exit_price() == 4406.895


def test_an_INFINITE_target_answers_None_rather_than_passing_infinity_to_a_venue():
    """🔴 A state this strategy really produces — its own `_close` and trade record both test
    for it. A price here would reach MT5 as an infinity and be refused as a number nobody chose.

    MUTATION: drop the finite check and this goes red.
    """
    ex = _ex()
    ex.pos = _open(math.inf)
    assert ex.full_exit_price() is None


def test_a_ZERO_target_answers_None_because_zero_is_not_a_price():
    """Zero reaches MT5 as *no take-profit at all*, which is a real instruction rather than a
    price — so it must never be handed over as one."""
    ex = _ex()
    ex.pos = _open(0.0)
    assert ex.full_exit_price() is None
