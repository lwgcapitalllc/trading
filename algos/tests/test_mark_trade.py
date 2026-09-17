"""`tools/mark_trade.py` — a mark must say truthfully whether the bot still manages the trade.

Watched RED: with `still_managed_by_the_bot` hardcoded True (the tool before 2026-09-17), the
closed-trade test fails; with `action="append"` removed, the several-tickets test fails.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import mark_trade  # noqa: E402


def _run(monkeypatch, tmp_path, *args):
    (tmp_path / "bot_a" / "ledger").mkdir(parents=True)
    monkeypatch.setattr(mark_trade, "INSTANCES", tmp_path)
    monkeypatch.setattr(sys, "argv", ["mark_trade.py", "--bot", "bot_a", *args])
    mark_trade.main()
    (f,) = (tmp_path / "bot_a" / "ledger").glob("decisions-*.jsonl")
    return json.loads(f.read_text().splitlines()[-1])


def test_an_open_trade_is_still_managed(monkeypatch, tmp_path):
    row = _run(monkeypatch, tmp_path, "--ticket", "5", "--why", "dup")
    assert row["still_managed_by_the_bot"] is True
    assert row["ticket"] == 5 and row["counts_as_strategy_performance"] is False


def test_a_closed_trade_is_not_claimed_as_managed(monkeypatch, tmp_path):
    row = _run(monkeypatch, tmp_path, "--ticket", "5", "--closed", "--why", "probe")
    assert row["still_managed_by_the_bot"] is False


def test_several_tickets_go_in_one_mark(monkeypatch, tmp_path):
    row = _run(monkeypatch, tmp_path, "--ticket", "5", "--ticket", "6", "--closed", "--why", "p")
    assert row["tickets"] == [5, 6] and "ticket" not in row
