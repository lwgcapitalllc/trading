"""`exec_sec_tp2_pct` — how much of a RE-ENTRY comes off at its second target.

Watched RED against HEAD: the field did not exist, so every test failed at construction. The
guarantees were then re-proved BY MUTATION against the real implementation.

⚠ The point of the setting is a DESIGN one: a re-entry is a recovery trade, not a second A+
setup, so the rest of it should come OFF at a level rather than ride a trail. These tests pin
the ladder that design produces, and the one that says risk falls TWICE is the load-bearing one.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Decision, Execution, _Pending

ENTRY, STOP, FIB1, FIB2 = 100.0, 98.0, 105.0, 106.0
FIRST = 102.5           # the shipped 1.25R re-entry rung


def _fill(kind="secondary", direction=1, entry=ENTRY, sl=STOP, tp1=FIB1, tp2=FIB2, **cfg_kw):
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg)
    pend = _Pending(direction, entry, 100.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind=kind)
    return ex


def _ladder(ex):
    return [(name, px, round(q, 6)) for name, px, q in ex._remaining_brackets()]


def test_it_inherits_by_default_so_no_stored_figure_moves():
    assert SosFadeConfig().exec_sec_tp2_pct == -1.0
    assert _ladder(_fill()) == [("L-TP1", FIRST, 50.0), ("L-RUN", None, 50.0)]


def test_setting_it_brings_the_REST_off_at_the_second_target_instead_of_trailing():
    """🔴 THE TEST THIS FILE EXISTS FOR — the runner is replaced by a second bank."""
    ex = _fill(exec_sec_tp2_pct=50)
    assert _ladder(ex) == [("L-TP1", FIRST, 50.0), ("L-TP2", FIB2, 50.0)]
    assert not any(name.endswith("RUN") for name, _, _ in _ladder(ex))


def test_the_two_percentages_and_the_placement_are_ONE_design():
    """Half off at the first target, the rest off at a chosen multiple of it, nothing trailing."""
    ex = _fill(exec_sec_tp1_pct=50, exec_sec_tp2_pct=50, exec_sec_tp2_x=2.0)
    assert _ladder(ex) == [("L-TP1", FIRST, 50.0), ("L-TP2", 105.0, 50.0)]


def test_RISK_FALLS_TWICE_and_the_first_bank_is_what_stages_the_stop():
    """The first bank takes size off AND arms breakeven at the same price, so the trade is free
    from there. An all-out design banks nothing early and has nothing to stage the stop with —
    that is the difference this setting exists to make available."""
    ex = _fill(exec_sec_tp2_pct=50, exec_sec_tp2_x=2.0)
    assert ex._stage_rungs()[0] == FIRST          # the first bank IS the stage-1 trigger
    ex._advance_stage(SimpleNamespace(index=2, time_ms=60_000, open=ENTRY, high=FIRST,
                                      low=ENTRY, close=ENTRY,
                                      last_conf_high=None, last_conf_low=None))
    assert ex._stage >= 1
    assert ex._current_stop() >= ENTRY            # breakeven or better — the trade cannot lose

    allout = _fill(exec_sec_tp1_pct=100)
    assert _ladder(allout) == [("L-TP1", FIRST, 100.0)]
    assert allout._stage_rungs()[0] == FIRST      # nothing arms before the exit itself


def test_a_hundred_percent_at_the_second_target_leaves_nothing_behind():
    ex = _fill(exec_sec_tp1_pct=0, exec_sec_tp2_pct=100, exec_sec_tp2_x=2.0)
    assert _ladder(ex) == [("L-TP2", 105.0, 100.0)]


def test_it_mirrors_for_a_short():
    ex = _fill(direction=-1, entry=100.0, sl=102.0, tp1=95.0, tp2=94.0,
               exec_sec_tp2_pct=50, exec_sec_tp2_x=2.0)
    assert _ladder(ex) == [("S-TP1", 97.5, 50.0), ("S-TP2", 95.0, 50.0)]


def test_a_PRIMARY_never_reads_it():
    """The primary ladder is the ported path the parity gate checks."""
    ex = _fill(kind="primary", exec_sec_tp2_pct=50)
    assert _ladder(ex) == [("L-RUN", None, 100.0)]


def test_the_CLOSED_TRADE_RECORD_carries_the_resolved_percentage():
    """🔴 Watched RED by mutation: asserting the helper alone let a mutation that reported the
    SHARED value on the record survive. The record is what the chart draws and what a reader
    reconstructs an exit from, so reporting 0 while the trade banked 50 makes the record disagree
    with the trade — and nothing else in the system would say so."""
    ex = _fill(exec_sec_tp2_pct=50)
    bar = SimpleNamespace(index=9, time_ms=540_000, open=ENTRY, high=ENTRY, low=ENTRY,
                          close=ENTRY, last_conf_high=None, last_conf_low=None)
    ex._close_at(bar, FIB2, "TEST", Decision(index=9))
    rungs = ex.trades[0].tp_rungs
    assert [pct for _, pct in rungs] == [50.0, 50.0]

    prim = _fill(kind="primary", exec_sec_tp2_pct=50)
    prim._close_at(bar, FIB2, "TEST", Decision(index=9))
    assert [pct for _, pct in prim.trades[0].tp_rungs] == [0.0, 0.0]


def test_the_UI_contract_carries_it_ungreyed():
    import json
    p = Path(__file__).resolve().parents[1] / "mpc_sos_fade.meta.json"
    row = [x for x in json.loads(p.read_text())["params"] if x["name"] == "exec_sec_tp2_pct"]
    assert len(row) == 1
    assert row[0]["show_if"] == {"exec_secondary": True}
    assert "disable_if" not in row[0]
