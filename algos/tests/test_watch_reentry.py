"""The re-entry watch must speak exactly three times, and stay quiet the rest of the time.

🔴 **WHY THIS FILE EXISTS.** A watcher's normal state is silence, so a working one and a dead one
look identical from outside for weeks at a stretch. Every test here drives a path that is
invisible in ordinary operation:

  - it SENDS when a re-entry opens, and again when it closes (two halves, two verdicts);
  - it does NOT re-send what it has already reported;
  - it SAYS SO when it cannot run at all — the case where silence would be a lie;
  - it writes a health record on EVERY run, so a gap in that file is the evidence.

⚠ **The last one is the load-bearing test.** Without the health record, this tool's only output on
a quiet day is nothing, and nothing is what a crashed scheduled task also produces.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_TOOLS = _REPO / "algos" / "tools"
for _p in (str(_TOOLS), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_reentry as audit  # noqa: E402
import watch_reentry as watch  # noqa: E402

PARAMS = {
    "exec_risk_pct": 10.0,
    "exec_sec_risk_pct": 50.0,
    "exec_tp1_pct": 0.0,
    "exec_tp2_pct": 0.0,
    "exec_sec_tp1_pct": 0.0,
}


def _opened(ticket=901, **over):
    row = dict(
        ts="2026-09-03T10:00:00+00:00",
        kind="trade",
        event="opened",
        ticket=ticket,
        dir="LONG",
        symbol="XAUUSD.p",
        intent="secondary",
        lots=0.25,
        price=3300.0,
        intended_price=3300.0,
        stop=3280.0,
        risk_pct=10.0,
        risk_usd=500.0,
        risk_pct_realised=5.0,
    )
    row.update(over)
    return row


def _closed(ticket=901, **over):
    row = dict(
        ts="2026-09-03T14:00:00+00:00",
        kind="trade",
        event="closed",
        ticket=ticket,
        dir="LONG",
        symbol="XAUUSD.p",
        intent="secondary",
        lots=0.25,
        price=3320.0,
        pnl_usd=490.0,
        r=1.0,
        reason="target",
        gross_usd=500.0,
        swap_usd=-5.0,
        commission_usd=-5.0,
        entry_price=3300.0,
    )
    row.update(over)
    return row


@pytest.fixture
def box(tmp_path, monkeypatch):
    """A throwaway trading box: one bot, one config, one ledger directory.

    ⚠ Both modules are re-pointed. `watch_reentry` finds the state file through its own `_REPO`
    and `audit_reentry` finds the ledger through ITS own — a fixture that moved one and not the
    other would read a real bot's ledger into a test.
    """
    inst = tmp_path / "algos" / "markets" / "fx" / "instances" / "bot"
    (inst / "ledger").mkdir(parents=True)
    (inst / "config.json").write_text(json.dumps({"strategy_params": PARAMS}), encoding="utf-8")
    monkeypatch.setattr(watch, "_REPO", tmp_path)
    monkeypatch.setattr(audit, "_REPO", tmp_path)

    sent: list[str] = []
    monkeypatch.setattr(watch, "_send", lambda text, dry: sent.append(text))
    return type("Box", (), {"inst": inst, "sent": sent})()


def _write(box, *rows):
    path = box.inst / "ledger" / "decisions-2026-09-03.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _health_rows(box):
    out = []
    for p in (box.inst / "ledger").glob("health-*.jsonl"):
        out += [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln]
    return out


# ── the three things it says ─────────────────────────────────────────────────
def test_an_open_re_entry_is_reported_immediately(box):
    """The message this whole tool exists to send.

    ⚠ A test with a docstring and no body sat here for about a minute and passed for free. It
    counted as coverage of exactly this rule while asserting nothing — which is worse than no test,
    because the next reader sees a name that says the case is covered.

    MUTATION: report only once a trade has closed, and this goes red — an open re-entry would then
    go unmentioned for as long as it runs, which can be days.
    """
    _write(box, _opened())
    assert watch.run("bot") == 0
    assert len(box.sent) == 1
    assert "still open" in box.sent[0]


def test_the_SAME_open_trade_is_not_reported_again(box):
    """Re-sending every hour for the life of a trade is how a channel gets muted before the day
    it matters.

    MUTATION: stop writing `reported[str(ticket)]` and this goes red with two identical messages.
    """
    _write(box, _opened())
    watch.run("bot")
    watch.run("bot")
    assert len(box.sent) == 1


def test_the_CLOSE_is_reported_as_a_SECOND_message(box):
    """🔴 Half the checks — the exit reason, R against the prices, the costs — cannot be answered
    while the position is on. Reporting once at the open and calling it audited files a verdict on
    the half of the trade that had happened.

    MUTATION: key the state on the ticket alone rather than on the half, and this goes red with
    the close never reported.
    """
    _write(box, _opened())
    watch.run("bot")
    _write(box, _opened(), _closed())
    watch.run("bot")

    assert len(box.sent) == 2
    assert "still open" in box.sent[0]
    assert "now closed" in box.sent[1]
    assert "R matches the prices" not in box.sent[0], "an open trade has no exit to grade"


def test_a_closed_trade_is_not_reported_a_third_time(box):
    _write(box, _opened(), _closed())
    watch.run("bot")
    watch.run("bot")
    assert len(box.sent) == 1


def test_a_FAILED_check_leads_the_message(box):
    """A person reads this on a phone. The verdict has to be the first thing, not a count at the
    bottom — a re-entry sized like a full trade is money, and it must not arrive as '8 passed'."""
    _write(box, _opened(risk_pct_realised=10.0), _closed())
    watch.run("bot")
    assert "SOMETHING IS WRONG" in box.sent[0]
    assert "risk sized correctly" in box.sent[0]


def test_a_clean_trade_says_so_without_crying_wolf(box):
    _write(box, _opened(), _closed())
    watch.run("bot")
    assert "RE-ENTRY CHECKED" in box.sent[0]
    assert "SOMETHING IS WRONG" not in box.sent[0]


# ── silence, and the one case where silence would be a lie ───────────────────
def test_a_quiet_run_sends_NOTHING(box):
    """Most days. A message nobody needs, every hour, is a channel nobody reads."""
    _write(box, {"kind": "bar", "ts": "2026-09-03T10:00:00+00:00"})
    assert watch.run("bot") == 0
    assert box.sent == []


def test_a_PRIMARY_trade_is_not_mistaken_for_a_re_entry(box):
    """⚠ Not decoration: the live bot takes primaries constantly, and a watcher that reported
    every one would be muted within a day and useless on the day it mattered."""
    _write(box, _opened(intent="primary"), _closed(intent="primary"))
    watch.run("bot")
    assert box.sent == []


def test_a_watch_that_CANNOT_RUN_says_so_rather_than_going_quiet(box, monkeypatch):
    """🔴 THE LOAD-BEARING CASE. A crashed watcher and a quiet market produce the same silence,
    and this repo has paid for that shape more than once. It must announce its own failure.

    MUTATION: let the exception propagate instead of catching it, and this goes red — the
    scheduled task dies into a log nobody opens and the channel stays silent.
    """

    def boom(*a, **k):
        raise RuntimeError("ledger is unreadable")

    monkeypatch.setattr(audit, "load_ledger", boom)
    assert watch.main(["--bot", "bot"]) == 1
    assert len(box.sent) == 1
    assert "NOT RUNNING" in box.sent[0]
    assert "ledger is unreadable" in box.sent[0]
    assert "does NOT mean nothing happened" in box.sent[0]


def test_a_broken_NOTIFIER_still_reports_failure_through_the_exit_code(box, monkeypatch):
    """⚠ The last line of defence. If Telegram itself is down, the exit code is all that is left —
    so the send must not be able to swallow it."""

    def boom(*a, **k):
        raise RuntimeError("no ledger")

    monkeypatch.setattr(audit, "load_ledger", boom)
    monkeypatch.setattr(watch, "_send", lambda *a, **k: (_ for _ in ()).throw(OSError("no net")))
    assert watch.main(["--bot", "bot"]) == 1


# ── the health record, which is what makes the silence auditable ─────────────
def test_EVERY_run_writes_a_health_record_even_a_quiet_one(box):
    """🔴 Without this the tool's only output on a quiet day is nothing, and nothing is what a
    crashed scheduled task produces too. **A gap in this file is the evidence.**

    MUTATION: write the record only when a message is sent, and this goes red — which is the
    version that leaves a dead watcher indistinguishable from a calm month.
    """
    _write(box, {"kind": "bar"})
    watch.run("bot")
    rows = _health_rows(box)
    assert len(rows) == 1
    assert rows[0]["event"] == "reentry_watch"
    assert rows[0]["messages_sent"] == 0
    assert rows[0]["ledger_rows"] == 1, "it must record that the file was actually READ"


def test_a_FAILED_run_still_writes_a_health_record(box, monkeypatch):
    """The run that most needs a trace is the one that crashed."""
    monkeypatch.setattr(audit, "load_ledger", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    watch.main(["--bot", "bot"])
    rows = _health_rows(box)
    assert rows and "error" in rows[0]


def test_the_health_record_goes_to_HEALTH_and_never_to_the_decisions_file(box):
    """The subject test the ledger applies everywhere: this is an observation about the machinery
    that watches, never a decision the bot made."""
    _write(box, {"kind": "bar"})
    watch.run("bot")
    decisions = (box.inst / "ledger" / "decisions-2026-09-03.jsonl").read_text(encoding="utf-8")
    assert "reentry_watch" not in decisions


# ── the state file ───────────────────────────────────────────────────────────
def test_an_UNREADABLE_state_file_repeats_rather_than_swallowing(box):
    """⚠ The two failure directions are not equal. Re-sending one message is an annoyance;
    treating a corrupt file as 'everything already reported' swallows the one message this tool
    exists to send.

    MUTATION: raise on a corrupt file, or return a sentinel meaning 'all reported', and this
    goes red.
    """
    _write(box, _opened())
    watch.run("bot")
    (box.inst / watch.STATE_NAME).write_text("{ this is not json", encoding="utf-8")
    watch.run("bot")
    assert len(box.sent) == 2, "a corrupt state file must lose nothing"
