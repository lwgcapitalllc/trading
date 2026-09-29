"""Tests for `backtest/tools/study_vs_lab.py` — the study-against-lab trade match-up.

Pure functions only; the lab fetch is a thin `urllib` call and is exercised by the reconciliation
recorded in `backtest/notes/study-reconciliation.md`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "study_vs_lab.py"
_spec = importlib.util.spec_from_file_location("study_vs_lab", _TOOL)
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)

M = 60_000


def _t(entry, d=1, r=1.0, exit_=None, **kw):
    return dict(entry_ms=entry * M, dir=d, r=r, exit_ms=(exit_ or entry + 30) * M, **kw)


def test_a_match_needs_the_same_DIRECTION_as_well_as_the_same_minute():
    """RED against dropping the direction test — a long and a short at one minute are two trades."""
    pairs, s_only, l_only = sv.match([_t(10, 1)], [_t(10, -1)], 0)
    assert pairs == [] and len(s_only) == 1 and len(l_only) == 1


def test_the_tolerance_is_honoured_and_zero_means_the_same_minute():
    assert sv.match([_t(10)], [_t(11)], 0)[0] == []
    assert len(sv.match([_t(10)], [_t(11)], 1 * M)[0]) == 1


def test_each_trade_is_used_ONCE_and_the_NEAREST_pair_wins():
    """RED against first-come pairing: study 10 would take lab 11 and leave lab 10 unmatched."""
    study = [_t(10), _t(11)]
    lab = [_t(11), _t(10)]
    pairs, s_only, l_only = sv.match(study, lab, 2 * M)
    assert sorted((p[0]["entry_ms"], p[1]["entry_ms"]) for p in pairs) == [
        (10 * M, 10 * M),
        (11 * M, 11 * M),
    ]
    assert s_only == [] and l_only == []


def test_a_study_only_trade_inside_a_lab_position_is_explained_as_the_lab_holding_one():
    lab = [_t(0, exit_=100)]
    s_only = [_t(50)]
    sv.explain(s_only, [], lab, [])
    assert s_only[0]["why"].startswith("lab was holding a position")


def test_a_study_only_trade_while_the_lab_is_flat_is_NOT_explained_away():
    """RED against treating the entry minute itself as "holding" — flat is the unexplained case."""
    lab = [_t(0, exit_=50)]
    s_only = [_t(50)]
    sv.explain(s_only, [], lab, [])
    assert s_only[0]["why"] == "lab was flat"


def test_a_lab_only_trade_is_tied_to_the_latest_same_side_setup_and_timed_against_its_start():
    """The finding this tool was built from: a lab entry BEFORE the study started watching."""
    setups = [
        dict(setup="A", dir=1, sos_ms=0, start_ms=100 * M),
        dict(setup="B", dir=1, sos_ms=200 * M, start_ms=210 * M),
        dict(setup="S", dir=-1, sos_ms=60 * M, start_ms=70 * M),
    ]
    early, late = _t(80), _t(150)
    sv.explain([], [early, late], [], setups)
    assert (early["setup"], early["why"]) == ("A", "entered BEFORE the study's start point")
    assert (late["setup"], late["why"]) == ("A", "entered AFTER the study's start point")


def test_a_lab_only_trade_with_no_study_setup_says_so():
    x = _t(5)
    sv.explain([], [x], [], [dict(setup="Later", dir=1, sos_ms=10 * M, start_ms=12 * M)])
    assert x["why"] == "no study setup"
