"""The New York no-entry window.

Aaron, 2026-09-23: refuse New York entries 11:30-15:30. One module decides "inside the window"
for BOTH entry paths (`entry_window.py`); these tests pin that module, the config's refusals and
the first-entry gate. The re-entry path is proven by the replay instead: zero fills inside the
window on the fast clock, checked trade by trade.

WATCHED RED against HEAD: the module did not exist (`ModuleNotFoundError`), the config refused the
two keywords, and `Execution` had no `_entry_window_block`.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.entry_window import in_window, parse_hhmm
from strategies.python.sos_fade.execution import Execution, _block_codes

NY = ZoneInfo("America/New_York")


def _ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


# ── the clock ────────────────────────────────────────────────────────────────

def test_parse():
    assert parse_hhmm("11:30") == 690
    assert parse_hhmm("") is None
    for bad in ("11.30", "24:00", "7:30", "11:60", "noon"):
        with pytest.raises(ValueError):
            parse_hhmm(bad)


@pytest.mark.parametrize("h,m,inside", [
    (11, 29, False), (11, 30, True), (13, 0, True), (15, 29, True), (15, 30, False)])
def test_the_window_is_half_open(h, m, inside):
    assert in_window("11:30", "15:30", _ms(2024, 3, 5, h, m)) is inside


@pytest.mark.parametrize("month", [1, 7])
def test_it_reads_new_york_time_in_both_halves_of_the_year(month):
    # MUTATION PROOF: read the clock in UTC instead and one of these goes red — 12:00 New York
    # is 17:00 UTC in winter and 16:00 in summer, both outside the window.
    assert in_window("11:30", "15:30", _ms(2024, month, 10, 12, 0)) is True


def test_a_window_may_wrap_midnight():
    assert in_window("22:00", "02:00", _ms(2024, 3, 5, 23, 0)) is True
    assert in_window("22:00", "02:00", _ms(2024, 3, 5, 1, 0)) is True
    assert in_window("22:00", "02:00", _ms(2024, 3, 5, 12, 0)) is False


def test_off_is_never_inside():
    assert in_window("", "", _ms(2024, 3, 5, 12, 0)) is False


# ── the config ───────────────────────────────────────────────────────────────

def test_off_by_default_so_no_stored_run_moves():
    # MUTATION PROOF: give either default a time and this goes red.
    c = SosFadeConfig()
    assert c.exec_entry_block_from == "" and c.exec_entry_block_to == ""


@pytest.mark.parametrize("frm,to", [("11:30", ""), ("", "15:30")])
def test_a_half_set_window_is_refused(frm, to):
    with pytest.raises(ValueError, match="set together"):
        SosFadeConfig(exec_entry_block_from=frm, exec_entry_block_to=to)


def test_an_empty_window_is_refused():
    with pytest.raises(ValueError, match="empty window"):
        SosFadeConfig(exec_entry_block_from="12:00", exec_entry_block_to="12:00")


def test_a_malformed_time_is_refused():
    with pytest.raises(ValueError, match="HH:MM"):
        SosFadeConfig(exec_entry_block_from="11.30", exec_entry_block_to="15:30")


# ── the first-entry gate tests the time the order would be LIVE ──────────────

class _Sig:
    def __init__(self, ms):
        self.time_ms = ms


def _ex():
    return Execution(SosFadeConfig(exec_min_atr_pct=0.0, exec_entry_block_from="11:30",
                                   exec_entry_block_to="15:30"))


def _feed(ex, *hm):
    out = None
    for h, m in hm:
        out = ex._entry_window_block(_Sig(_ms(2024, 3, 5, h, m)))
    return out


def test_the_bar_opening_1115_is_refused_because_its_order_would_rest_on_1130():
    # MUTATION PROOF: test the bar's OPEN instead of its close and this goes red — the order
    # decided at the 11:15 bar's close would then rest on, and fill during, the 11:30 bar.
    assert _feed(_ex(), (11, 0), (11, 15)) is True


def test_the_bar_opening_1100_is_allowed():
    assert _feed(_ex(), (10, 45), (11, 0)) is False


def test_the_bar_opening_1515_is_allowed_because_its_order_is_live_at_1530():
    assert _feed(_ex(), (15, 0), (15, 15)) is False


def test_a_weekend_gap_cannot_widen_the_spacing():
    """The spacing is the SMALLEST gap seen. Friday 16:45 -> Monday 11:15 is not a bar.

    MUTATION PROOF: keep the LATEST gap instead and this goes red — the Monday 11:15 bar's order
    would be tested ~66 hours later, on Wednesday morning, and allowed to rest on 11:30. The first
    version of this test fed Monday 11:00, which is allowed either way, so it passed against the
    mutation; it was rewritten rather than kept.
    """
    ex = _ex()
    ex._entry_window_block(_Sig(_ms(2024, 3, 1, 16, 30)))
    ex._entry_window_block(_Sig(_ms(2024, 3, 1, 16, 45)))
    assert ex._entry_window_block(_Sig(_ms(2024, 3, 4, 11, 15))) is True


def test_off_means_the_gate_never_refuses():
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0))
    assert _feed(ex, (12, 0), (12, 15)) is False


# ── the refusal is REPORTED as what it is ────────────────────────────────────

def test_a_window_refusal_gets_its_own_code_not_the_final_hour_one():
    # A window refusal booked as "final hour" would tell the reader a 16:00 rule refused a
    # 12:00 setup — a label describing a rule the code does not have.
    codes = _block_codes(False, False, False, False, False, False, entry_window=True)
    assert codes == [11]
