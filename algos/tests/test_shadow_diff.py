"""The join between the live decision stream and a lab replay of the same window.

The replay and the ledger are both tested elsewhere. What is tested here is everything
BETWEEN them — and that is where a shadow diff goes quietly wrong, because its output is a
set of confident counts nobody can check by eye against 148 bars.

Two failure directions, and both are silent:

- **A join that matches too little** reports drift that is really a bookkeeping mistake. The
  B-LEG harness did exactly this: 2,409 comparisons failed at one flat index offset while the
  logic was bar-for-bar identical, and it looked like a real divergence.
- **A join that matches too much** — or a comparison that treats `None` as equal to a price —
  reports parity that was never checked. That one ships a bot.

So the cases below are mostly about what must NOT be quietly waved through.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "shadow_diff", _REPO / "algos" / "tools" / "shadow_diff.py")
sd = importlib.util.module_from_spec(_spec)
sys.modules["shadow_diff"] = sd
_spec.loader.exec_module(sd)


# ── reading the ledger ───────────────────────────────────────────────────────────

def _write(dir_: Path, name: str, rows: list[dict]) -> None:
    dir_.joinpath(name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_only_bar_records_are_read_and_they_come_back_in_time_order(tmp_path):
    # The ledger interleaves bar / blocked / missed / trade / event in one file, and the daily
    # files are read in filename order, which is not necessarily time order once a bot has
    # restarted. Sorting here is what lets the caller trust `live[0]` and `live[-1]`.
    _write(tmp_path, "decisions-2026-08-02.jsonl", [
        {"kind": "bar", "bar_time": 300}, {"kind": "blocked", "bar_time": 301},
        {"kind": "event", "warmed": 1},
    ])
    _write(tmp_path, "decisions-2026-08-01.jsonl", [
        {"kind": "bar", "bar_time": 100}, {"kind": "trade", "bar_time": 150},
        {"kind": "bar", "bar_time": 200},
    ])
    rows = sd._load_ledger(tmp_path)
    assert [r["bar_time"] for r in rows] == [100, 200, 300]


def test_a_bar_record_with_no_timestamp_is_dropped_not_joined_at_None(tmp_path):
    # `bar_time` is read defensively by the ledger (`getattr(sig, "time_ms", None)`), so a
    # strategy with a different Signals shape writes a null. Joining on None would bucket
    # every such row together and compare them against one arbitrary lab bar.
    _write(tmp_path, "decisions-2026-08-01.jsonl", [
        {"kind": "bar", "bar_time": None}, {"kind": "bar", "bar_time": 100},
    ])
    assert [r["bar_time"] for r in sd._load_ledger(tmp_path)] == [100]


def test_an_empty_ledger_directory_refuses_rather_than_reporting_a_clean_run(tmp_path):
    # Zero bars compared and "no mismatches" are the same output if you are not careful, and
    # the second one reads as a pass.
    with pytest.raises(SystemExit):
        sd._load_ledger(tmp_path)


# ── comparing prices ─────────────────────────────────────────────────────────────

def test_two_prices_inside_the_tolerance_are_the_same_price():
    assert sd._same_price(4052.13, 4052.1309)


def test_a_cent_apart_is_NOT_the_same_price():
    # The tolerance exists for float noise, never for a real quote difference. A cent on gold
    # is a different fib level's worth of nothing — but it is real, and hiding it here would
    # hide exactly the feed drift this tool is for.
    assert not sd._same_price(4052.13, 4052.14)


def test_None_on_both_sides_is_a_match():
    assert sd._same_price(None, None)


def test_None_against_a_price_is_a_MISMATCH_in_both_directions():
    # The one that matters. "The bot had no entry edge" and "the bot had an edge at 4052" are
    # opposite facts, and a truthiness check would call the pair equal in one direction and
    # crash in the other.
    assert not sd._same_price(None, 4052.13)
    assert not sd._same_price(4052.13, None)


def test_a_price_of_zero_is_not_treated_as_absent():
    # `0.0 or None` is the classic way this breaks. Zero is not a plausible gold price, but the
    # comparator is generic and the next strategy through here may report a spread or an offset.
    assert not sd._same_price(0.0, None)
    assert sd._same_price(0.0, 0.0)


# ── the field roster ─────────────────────────────────────────────────────────────

def test_no_field_is_compared_twice_under_two_kinds():
    fields = sd._BOOL_FIELDS + sd._INT_FIELDS + sd._PRICE_FIELDS
    assert len(fields) == len(set(fields))


def test_every_compared_field_exists_on_the_real_Decision():
    # A typo'd field name would read `getattr(d, name)` as None on the lab side and silently
    # report the live value as a mismatch on every bar — or, worse, match None to None and
    # report a field as verified that was never looked at.
    sys.path.insert(0, str(_REPO))
    from strategies.python.mpc_sos_fade.execution import Decision

    d = Decision(index=0)
    for f in sd._BOOL_FIELDS + sd._INT_FIELDS + sd._PRICE_FIELDS:
        assert hasattr(d, f), f"{f} is compared but is not a Decision field"


def test_the_uncompared_fields_are_NOT_on_the_Decision():
    # They come off the sequence object. If one ever moves onto Decision it becomes comparable,
    # and leaving it in the "not compared" footnote would understate the check from then on.
    sys.path.insert(0, str(_REPO))
    from strategies.python.mpc_sos_fade.execution import Decision

    d = Decision(index=0)
    for f in sd._UNCOMPARED:
        assert not hasattr(d, f), f"{f} is on Decision now — move it into the compared roster"
