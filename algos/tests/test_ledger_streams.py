"""The two ledger streams must not overlap, and every event must be deliberately routed.

**Why this file exists.** Aaron's instruction on 2026-08-05: the daily record has to answer two
different questions — *is the process healthy* and *why did it trade or not* — and *"nothing
[should be] overlapping on each other."* One file answering both is what the ledger was, and it
meant "did anything die today" was a grep through a 100 KB stream of per-bar decisions.

The tests here are about the SEAM rather than the payloads. Three things can go wrong and none
of them raises at runtime:

1. a record lands in the wrong file (the reader looks in the right place and finds nothing);
2. a NEW event nobody classified defaults into health and reads as a process fault;
3. the silent-death detector answers "clean" when it actually could not tell.

The third is this repo's standing rule — *never let "no" and "cannot ask" be the same value* —
arriving in a fourth place, and it is the one that would be most reassuring when wrong.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent.parent
_LIVE = _REPO / "algos" / "live"
if str(_LIVE) not in sys.path:
    sys.path.insert(0, str(_LIVE))

from ledger import DECISIONS, HEALTH, Ledger, _DECISION_EVENTS   # noqa: E402


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _streams(tmp_path: Path) -> tuple[Path, Path]:
    return (tmp_path / f"decisions-{_today()}.jsonl",
            tmp_path / f"health-{_today()}.jsonl")


# ── the split itself ─────────────────────────────────────────────────────────
def test_trade_records_go_only_to_decisions(tmp_path):
    led = Ledger(tmp_path, "bot")
    led.bar(SimpleNamespace(l_stage=1), SimpleNamespace(time_ms=1), SimpleNamespace())
    led.blocked(SimpleNamespace(dir="long", time_ms=2, edge=1.0, sos_bar=0,
                                codes=[7], labels=["x"], reasons=["y"]))
    led.missed(SimpleNamespace(dir="short", time_ms=3))
    led.trade_opened(ticket=1, direction="long", symbol="XAUUSD", lots=0.1,
                     price=100.0, stop=99.0)
    led.trade_closed(ticket=1, direction="long", symbol="XAUUSD", price=101.0,
                     pnl_usd=10.0, r_multiple=1.0, reason="tp")

    dec, health = _streams(tmp_path)
    assert [r["kind"] for r in _rows(dec)] == ["bar", "blocked", "missed", "trade", "trade"]
    assert _rows(health) == [], "a trade record leaked into the health stream"


def test_lifecycle_records_go_only_to_health(tmp_path):
    led = Ledger(tmp_path, "bot")
    led.event("startup", version="1")
    led.event("mt5_link_lost")
    led.event("rewarm", missed_bars=9)
    led.event("halted", reason="disagreement")
    led.event("shutdown", exit_code=0)
    led.pulse(link=True, balance=2000.0)

    dec, health = _streams(tmp_path)
    assert _rows(dec) == [], "a process record leaked into the decision stream"
    assert [r.get("event") or r["kind"] for r in _rows(health)] == [
        "startup", "mt5_link_lost", "rewarm", "halted", "shutdown", "pulse"]


def test_order_events_are_decisions_because_they_are_about_a_setup(tmp_path):
    """The broker refusing an order is the answer to "why is there no trade on that setup",
    which is the decision stream's question. `halted` is the answer to "why is there no trading
    at all", which is the process's."""
    led = Ledger(tmp_path, "bot")
    led.event("order_placed", ticket=5)
    led.event("order_refused", reason="no money")
    led.event("halted", reason="disagreement")

    dec, health = _streams(tmp_path)
    assert [r["event"] for r in _rows(dec)] == ["order_placed", "order_refused"]
    assert [r["event"] for r in _rows(health)] == ["halted"]


def test_every_event_written_in_algos_live_is_classified():
    """🔴 THE GUARD. An event nobody routed falls to health and reads as a process fault, and
    nothing raises — the same silent shape as the news calendar's polarity keys matching none of
    the real titles. So the source is the corpus: every `ledger.event("name")` call in
    `algos/live/` must be a name this module has an opinion about.

    ⚠ It fails in BOTH directions on purpose. A name in `_DECISION_EVENTS` that no longer
    appears in the source is a routing rule for an event that no longer exists — dead, and the
    next person to read the table would take it as documentation of live behaviour.
    """
    written = set()
    for path in sorted(_LIVE.glob("*.py")):
        written |= set(re.findall(r'ledger\.event\(\s*"([a-z_]+)"', path.read_text("utf-8")))

    assert written, "found no ledger.event() calls at all — the pattern stopped matching"

    stale = _DECISION_EVENTS - written
    assert not stale, (f"_DECISION_EVENTS routes {sorted(stale)}, which nothing in algos/live/ "
                       f"writes any more")

    # Everything else is health by default, which is correct — but it has to be a CHOICE. The
    # health names are listed here so adding an event makes somebody name it in one of the two
    # places rather than discovering the routing later from a file that grew a stranger.
    known_health = {
        "startup", "startup_failed", "shutdown", "version_mismatch", "warmed", "rewarm",
        "bar_error", "loop_error", "mt5_link_lost", "mt5_link_restored",
        "config_applied", "config_change_refused", "halted", "went_live",
        # HEALTH rather than a decision, and the line is the usual one: it is about the
        # machinery correcting its own book-keeping, not about a setup. No order changes
        # because of it — the next one is merely sized off a number that is true.
        "equity_reanchored",
        # The account-level risk cap's state, written once per start — capped or NOT. HEALTH by
        # the same rule: it describes what the machinery is configured to enforce, not a setup.
        # The order the cap actually refuses is a DECISION and goes out as `order_refused`
        # carrying its own code, which is the pair worth noticing: one subject, seen from the
        # two sides of this file's dividing line.
        "risk_cap",
        # The fleet switch firing. HEALTH, and the subject test settles it cleanly: this is why
        # the bot is not trading AT ALL, which is a fact about the machinery, where "why no trade
        # on THAT setup" is the decision stream's question. Same side of the line as `halted`,
        # which it routes through.
        "fleet_halt",
        # The bot has no account, so it declined to start. HEALTH by the subject test: it is why
        # this bot is not trading AT ALL — the same side of the line as `halted` — where the
        # decision stream answers "why no trade on THAT setup". It also has to be written rather
        # than merely logged, because the run ends immediately afterwards and the invariant that
        # makes silence meaningful ("no shutdown record ⇒ killed or crashed") only holds if every
        # deliberate ending leaves one.
        "not_assigned",
    }
    unclassified = written - _DECISION_EVENTS - known_health
    assert not unclassified, (
        f"unrouted ledger event(s): {sorted(unclassified)}. Add each to _DECISION_EVENTS in "
        f"algos/live/ledger.py if it is about a SETUP or an ORDER, or to `known_health` here "
        f"if it is about the PROCESS.")


# ── the silent-death detector ────────────────────────────────────────────────
def test_a_run_that_shut_down_reads_as_clean(tmp_path):
    led = Ledger(tmp_path, "bot")
    led.event("startup")
    led.event("shutdown", exit_code=0)

    assert led.previous_run_was_clean() is True


def test_a_run_that_was_killed_reads_as_not_clean(tmp_path):
    """A `taskkill /f` writes nothing at all — that is what makes it silent. The evidence is the
    ABSENCE of a closing record after the last startup, and only the next run can see it."""
    led = Ledger(tmp_path, "bot")
    led.event("startup")
    led.pulse(link=True)          # ran for a while, then the process vanished

    assert led.previous_run_was_clean() is False
    assert led.last_run_status()["event"] == "startup"


def test_no_history_is_unknown_and_not_clean(tmp_path):
    """⚠ The rule this repo has now met four times: `None` = could not tell, and it must never
    collapse into the reassuring answer. A first-ever start has no previous run to judge."""
    led = Ledger(tmp_path, "bot")

    assert led.previous_run_was_clean() is None


def test_a_torn_last_line_does_not_hide_the_record_before_it(tmp_path):
    """The sync copies today's file while the bot is appending to it, so a half-written last
    line is expected rather than exceptional. It must skip that line, not give up on the day —
    giving up would report a clean shutdown as "no history", i.e. unknown."""
    led = Ledger(tmp_path, "bot")
    led.event("startup")
    led.event("shutdown", exit_code=0)
    _, health = _streams(tmp_path)
    with health.open("a", encoding="utf-8") as f:
        f.write('{"ts": "2026-08-05T12:00:00+00:00", "kind": "pu')      # cut mid-write

    assert led.previous_run_was_clean() is True


def test_the_previous_run_is_found_in_an_earlier_days_file(tmp_path):
    """A bot started yesterday and killed overnight has its last record in yesterday's file.
    Reading only today's would report every morning's first start as "no history"."""
    (tmp_path / "health-2026-08-03.jsonl").write_text(
        json.dumps({"ts": "2026-08-03T10:00:00+00:00", "kind": "event", "event": "startup"})
        + "\n", encoding="utf-8")
    led = Ledger(tmp_path, "bot")

    assert led.previous_run_was_clean() is False


def test_an_unreadable_health_file_is_unknown_not_clean(tmp_path, monkeypatch):
    led = Ledger(tmp_path, "bot")
    led.event("shutdown", exit_code=0)

    def _boom(*a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _boom)
    assert led.previous_run_was_clean() is None, "an unreadable file answered 'clean'"


# ── rotation ─────────────────────────────────────────────────────────────────
def test_the_two_streams_rotate_on_the_same_day_boundary(tmp_path):
    """One day of text log, one day of decisions and one day of health must cover the same
    window, or reading them side by side means joining on a shifting boundary."""
    led = Ledger(tmp_path, "bot")
    led.event("startup")
    led.bar(SimpleNamespace(), SimpleNamespace(time_ms=1), SimpleNamespace())

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [f"decisions-{_today()}.jsonl", f"health-{_today()}.jsonl"]


def test_stream_names_match_the_shared_pattern(tmp_path):
    """`tools/log_backup.py` imports `STREAM_RE` rather than restating the filename shape. If
    the writer's names and that pattern drift, the backup silently skips a whole stream."""
    from ledger import STREAM_RE

    led = Ledger(tmp_path, "bot")
    led.event("startup")
    led.bar(SimpleNamespace(), SimpleNamespace(time_ms=1), SimpleNamespace())

    for path in tmp_path.iterdir():
        m = STREAM_RE.match(path.name)
        assert m, f"{path.name} is not recognised by the pattern the backup job reads"
        assert m[1] in (DECISIONS, HEALTH)
