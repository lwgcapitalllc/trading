"""The deal stream mirrors MT5's account history into per-day files the sync can commit.

Watched RED: with `deal_history` writing a wall-clock `ts` on each row, the rewrite test fails
(every refresh changes the file); with `deals` missing from `STREAM_RE`, the backup test fails.
"""

import json
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from ledger import STREAM_RE, Ledger  # noqa: E402

Deal = namedtuple(
    "Deal",
    "ticket order time time_msc type entry position_id volume price profit swap commission symbol",
)


def _deals():
    return [
        Deal(2, 20, 1757980800, 1757980800500, 1, 0, 7, 0.2, 4300.0, 0.0, 0.0, -0.4, "XAUUSD.p"),
        Deal(1, 0, 1757894400, 1757894400000, 2, 0, 0, 0.0, 0.0, 10000.0, 0.0, 0.0, ""),
        Deal(3, 21, 1757984400, 1757984400000, 0, 1, 7, 0.2, 4310.0, -200.0, 0.0, -0.4, "XAUUSD.p"),
    ]


def test_one_file_per_deal_day_in_time_order(tmp_path):
    led = Ledger(tmp_path, "bot_a")
    assert led.deal_history(_deals(), 123) == 2
    rows = [json.loads(x) for x in (tmp_path / "deals-2025-09-16.jsonl").read_text().splitlines()]
    assert [r["ticket"] for r in rows] == [2, 3]
    assert all(r["account"] == 123 and r["kind"] == "deal" for r in rows)
    assert (tmp_path / "deals-2025-09-15.jsonl").exists()


def test_rewriting_the_same_history_changes_nothing(tmp_path):
    led = Ledger(tmp_path, "bot_a")
    led.deal_history(_deals(), 123)
    assert Ledger(tmp_path, "bot_a").deal_history(_deals(), 123) == 0


def test_a_new_deal_rewrites_only_its_day(tmp_path):
    led = Ledger(tmp_path, "bot_a")
    led.deal_history(_deals(), 123)
    more = _deals() + [
        Deal(4, 22, 1757988000, 1757988000000, 0, 0, 8, 0.1, 4305.0, 0.0, 0.0, 0.0, "XAUUSD.p")
    ]
    assert led.deal_history(more, 123) == 1


def test_the_backup_job_recognises_the_stream():
    import ledger_sync

    assert STREAM_RE.match("deals-2026-09-17.jsonl")
    assert ledger_sync.REMOTE_PATH_RE.match("sos_fade_1/ledger/deals-2026-09-17.jsonl")


def test_never_raises(tmp_path):
    assert Ledger(tmp_path, "bot_a").deal_history([object()], 123) == 0
