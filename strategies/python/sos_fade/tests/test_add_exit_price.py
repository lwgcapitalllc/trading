"""`add_exit_price()` — where the open scale-in lots bank on the next bar, or None to ride them.

Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The bridge
rests the answer on every add ticket as the broker's take-profit, so an add banked at the H4
high/low fills THERE rather than at market on the next 15-minute close (2026-09-26).

⚠ The dangerous direction is a STALE level: a price left over from lots already banked would
put a target on whatever is added next. Every test was watched RED by mutation.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution

from .test_full_exit_price import _long_in


def _ex():
    return Execution(SosFadeConfig(exec_scale_tp_mode="H4 H/L"), initial_capital=10_000.0)


def test_an_OPEN_add_answers_the_level_staged_for_the_next_bar():
    """MUTATION: return None unconditionally and this goes red."""
    ex = _ex()
    _long_in(ex)
    ex._adds = [[100.2, 20.0]]
    ex._add_tp_level = 101.7
    assert ex.add_exit_price() == 101.7


def test_BANKED_lots_leave_no_target_even_with_the_level_still_in_the_field():
    """`_bank_adds` zeroes each lot IN PLACE, so the list is not empty after a bank.

    MUTATION: test `self._adds` for emptiness instead of for a live lot and this goes red.
    """
    ex = _ex()
    _long_in(ex)
    ex._adds = [[100.2, 0.0]]
    ex._add_tp_level = 101.7
    assert ex.add_exit_price() is None


def test_FLAT_answers_None():
    """MUTATION: delete the `_pos_dir == 0` check and this goes red."""
    ex = _ex()
    _long_in(ex)
    ex._adds = [[100.2, 20.0]]
    ex._add_tp_level = 101.7
    ex._pos_dir = 0
    assert ex.add_exit_price() is None


def test_RIDE_answers_None_because_no_level_is_staged():
    ex = _ex()
    _long_in(ex)
    ex._adds = [[100.2, 20.0]]
    ex._add_tp_level = None
    assert ex.add_exit_price() is None
