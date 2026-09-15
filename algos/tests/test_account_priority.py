"""Which bot on an account sizes first when two close a bar together (2026-09-15)."""

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# ⚠ Stated here, not borrowed: run alone, this file could not import its subject — it only ever
# passed because another module had put the path in first.
_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import account_priority as ap  # noqa: E402
from account_priority import Peer, wait_seconds  # noqa: E402

M15_CLOSE = 1_757_937_600_000  # 2025-09-15 12:00:00 UTC — a 15-minute (and 5-minute) close
M5_ONLY_CLOSE = M15_CLOSE + 5 * 60 * 1000  # 12:05 — a 5-minute close that is NOT a 15-minute one


def _wait(my_rank, others, *, close=M15_CLOSE, after_s=3.0, poll=10):
    return wait_seconds(
        my_rank=my_rank,
        others=others,
        bar_close_ms=close,
        now_ms=close + after_s * 1000,
        poll_seconds=poll,
    )


def test_a_bot_with_NO_place_in_the_order_never_waits():
    assert _wait(None, [Peer("a", 1, 900)]) == 0.0


def test_the_TOP_bot_never_waits():
    assert _wait(1, [Peer("b", 2, 300)]) == 0.0


def test_the_second_bot_waits_one_poll_plus_the_margin_FROM_THE_CLOSE():
    """Timed from the close, not from noticing it: 3s after the close it waits the other 17s."""
    assert _wait(2, [Peer("a", 1, 900)]) == pytest.approx(10 + ap.STEP_MARGIN_SECONDS - 3.0)


def test_a_bar_the_higher_bot_does_NOT_share_is_not_waited_on():
    """An M5 bot below an M15 bot waits only on the M5 closes that are also M15 closes."""
    assert _wait(2, [Peer("a", 1, 900)], close=M5_ONLY_CLOSE) == 0.0


def test_every_TIER_ahead_adds_one_step():
    step = 10 + ap.STEP_MARGIN_SECONDS
    assert _wait(3, [Peer("a", 1, 900), Peer("b", 2, 300)], after_s=0) == pytest.approx(2 * step)


def test_an_UNRANKED_bot_on_the_account_counts_as_ahead_because_it_never_waits():
    assert _wait(2, [Peer("x", None, 300)], after_s=0) > 0.0


def test_CANNOT_TELL_who_is_there_waits_as_if_every_better_rank_were():
    """Rule 1: an unreadable roster is never "nobody ahead"."""
    step = 10 + ap.STEP_MARGIN_SECONDS
    assert _wait(3, None, after_s=0) == pytest.approx(2 * step)


def test_a_bar_already_past_its_turn_does_not_wait_again():
    assert _wait(2, [Peer("a", 1, 900)], after_s=60) == 0.0


def test_the_wait_is_CAPPED():
    assert _wait(50, None, after_s=0) == ap.MAX_WAIT_SECONDS


def test_bar_seconds_trusts_only_closes_on_the_UTC_clock():
    assert ap.bar_seconds("M5") == 300
    assert ap.bar_seconds("m15") == 900
    assert ap.bar_seconds("H1") == 3600
    assert ap.bar_seconds("H4") is None, "H4 follows the broker's day"
    assert ap.bar_seconds("D1") is None
    assert ap.bar_seconds(None) is None


def _bot(root, key, **cfg):
    d = root / key
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"bot_key": key, **cfg}))


def test_peers_are_the_OTHER_bots_on_THIS_account_read_fresh_off_disk(tmp_path):
    _bot(tmp_path, "me_bot", account=1, account_priority=2, timeframe="M5")
    _bot(tmp_path, "top_bot", account=1, account_priority=1, timeframe="M15")
    _bot(tmp_path, "elsewhere", account=2, account_priority=1, timeframe="M5")
    rank, others = ap.peers("me_bot", root=tmp_path)
    assert rank == 2
    assert others == [Peer("top_bot", 1, 900)]


def test_a_peer_config_that_will_not_read_makes_the_roster_UNKNOWN(tmp_path):
    _bot(tmp_path, "me_bot", account=1, account_priority=2, timeframe="M5")
    (tmp_path / "bad_bot").mkdir()
    (tmp_path / "bad_bot" / "config.json").write_text("{not json")
    rank, others = ap.peers("me_bot", root=tmp_path)
    assert rank == 2 and others is None


def _runner():
    from runner import LiveRunner

    r = LiveRunner.__new__(LiveRunner)
    r.bridge = object()
    r.cfg = SimpleNamespace(bot_key="me_bot", poll_seconds=10)
    r.log = SimpleNamespace(info=lambda m: None, warning=lambda m: None)
    return r


def test_the_runner_WAITS_its_turn_timed_from_the_bar_close(monkeypatch):
    import runner as rn

    monkeypatch.setattr(ap, "peers", lambda key: (2, [Peer("top_bot", 1, 900)]))
    slept = []
    monkeypatch.setattr(rn.time, "sleep", slept.append)
    monkeypatch.setattr(rn.time, "time", lambda: M15_CLOSE / 1000.0 + 3.0)
    _runner()._wait_for_priority(M15_CLOSE)
    assert slept == [pytest.approx(10 + ap.STEP_MARGIN_SECONDS - 3.0)]


def test_the_runner_waits_BEFORE_it_reads_the_room():
    """The whole mechanism is ordering: waiting after the room was read would size against the
    room the higher bot had not yet taken."""
    from runner import LiveRunner

    src = inspect.getsource(LiveRunner._on_bar)
    assert "_wait_for_priority(" in src
    assert src.index("_wait_for_priority(") < src.index("_refresh_account_room()")


def test_a_rank_that_is_not_a_positive_whole_number_is_NO_rank(tmp_path):
    _bot(tmp_path, "me_bot", account=1, account_priority=True, timeframe="M5")
    assert ap.peers("me_bot", root=tmp_path)[0] is None
