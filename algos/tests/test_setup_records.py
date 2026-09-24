"""The setups the box announces are now WRITTEN DOWN, one row per live setup per bar.

🔴 **The gap this closes.** The signals room has said `Sweep · Day Low · SOS confirmed · not
tagged yet` and `Zone 4,251.87 – 4,308.23` since 2026-08-13, and thirty seconds later that message
was the only copy in existence: nothing on disk held which level was swept, what the tradeable band
was, or that the setup had happened at all. The user asked for a student feed carrying the same
content (`algos/tools/rev_setup_feed.py`), and there was nothing to read — so the runner records
each snapshot to the decision stream. An audit of how many setups become trades, and any later
study of refusals, wanted the same record.

🔴 **It is OFF by default and that is a PERMISSION default, not a risk one.** `algos/live` is
frozen into each bot's snapshot, so a default of True would start writing these rows on the other
owner's LIVE bots at his next promote without him having chosen it — the user's rule, same day:
*"Never touch anything with his live trading that I may be working on without his permission."*

**Watched RED (2026-09-23), four mutations:**
- removing the `_record_setups()` call from `_settle_primary`'s `finally` -> the first test;
- swapping `live_setups()` for `drain_setups()` -> the test that the alert layer still gets the
  terminal snapshot (the closing message would be stolen from the room it belongs to);
- letting the exception out instead of warning -> the test that a broken strategy cannot break
  the bar loop;
- defaulting `record_setups` to True -> the test that a bot which has not asked records nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ALGOS = Path(__file__).resolve().parent.parent
_REPO = _ALGOS.parent
for _p in (_REPO, _ALGOS / "live", _ALGOS / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import runner as live_runner  # noqa: E402

from backtest.setups import DEAD, WATCHING, Confluence, SetupSnapshot  # noqa: E402


def _snap(**over):
    """A snapshot shaped like the one `sos_fade` really publishes — the message the user pasted."""
    fields = dict(
        key="sos_fade:long:5065",
        strategy="SOS Fade",
        symbol="XAUUSD.p",
        side=1,
        state=WATCHING,
        confluences=(
            Confluence("Arm", True, "Sweep · Day Low"),
            Confluence("Shift of structure", True, "SOS confirmed"),
            Confluence("Retrace zone", False, "not tagged yet"),
        ),
        zone=(4308.23, 4251.87),
        entry=None,
        stop=4251.87,
        blocked_by=("Final hour (16:00-18:00 New York)",),
    )
    fields.update(over)
    return SetupSnapshot(**fields)


class _Ledger:
    def __init__(self):
        self.rows = []

    def event(self, name, **fields):
        # Round-tripped through JSON, because that is what the real ledger does and a tuple that
        # only survives in memory would pass here and come back a list on the box.
        self.rows.append(json.loads(json.dumps({"event": name, **fields}, default=str)))

    def bar(self, *a, **k):
        pass


class _Log:
    def __init__(self):
        self.warnings = []

    def warning(self, m, *a, **k):
        self.warnings.append(str(m))

    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Execution:
    """A strategy execution that answers the contract, and remembers what was drained."""

    def __init__(self, *snaps):
        self._snaps = list(snaps)
        self.drained = 0

    def live_setups(self):
        return list(self._snaps)

    def drain_setups(self):
        self.drained += 1
        out = list(self._snaps)
        self._snaps = []
        return out


class _Strategy:
    def __init__(self, execution):
        self.execution = execution


class _Cfg:
    """The one live-config field this reads. Default ON here because every test below is about a
    bot that has asked for the records; the OFF default is its own test."""

    record_setups = True


def _runner(strategy, record=True):
    r = live_runner.LiveRunner.__new__(live_runner.LiveRunner)
    r.strategy = strategy
    r.ledger = _Ledger()
    r.log = _Log()
    cfg = _Cfg()
    cfg.record_setups = record
    r.cfg = cfg
    return r


def test_a_watched_setup_is_recorded_with_the_fields_the_message_SHOWS():
    """The two fields that exist nowhere else: the swept level's NAME, inside the confluence
    detail, and the tradeable BAND.

    MUTATION: delete the `_record_setups()` call in `_settle_primary` -> red.
    """
    r = _runner(_Strategy(_Execution(_snap())))
    r._record_setups()
    assert len(r.ledger.rows) == 1
    row = r.ledger.rows[0]
    assert row["event"] == "setup"
    assert row["setup_key"] == "sos_fade:long:5065" and row["side"] == 1
    assert row["state"] == WATCHING and (row["met"], row["of"]) == (2, 3)
    assert ["Arm", True, "Sweep · Day Low"] in row["confluences"]
    assert ["Retrace zone", False, "not tagged yet"] in row["confluences"]
    assert row["zone"] == [4308.23, 4251.87] and row["stop"] == 4251.87
    assert row["blocked_by"] == ["Final hour (16:00-18:00 New York)"]
    assert r.log.warnings == []


def test_the_BAR_PATH_is_what_calls_it(monkeypatch):
    """🔴 Rule 7: a recorder nothing calls is a label with no code behind it. This drives the
    real `_settle_primary` and asserts the row appears, so the wiring is pinned and not just the
    method.

    MUTATION: delete the `_record_setups()` call from `_settle_primary`'s `finally` -> red.
    """
    ex = _Execution(_snap())
    r = _runner(_Strategy(ex))
    r.setup_alerts = None
    r._drain_records = lambda: None  # its own subject, and it needs the whole strategy

    class _Bridge:
        state = None

        def sync(self, dec, sig):
            self.synced = True

    class _Primary:
        dec = sig = seq = None

    r.bridge = _Bridge()
    r._settle_primary(_Primary())
    assert [row["event"] for row in r.ledger.rows] == ["setup"]
    assert getattr(r.bridge, "synced", False), "the bar path did not run to the broker sync"


def test_the_record_does_NOT_drain_so_the_alert_layer_still_gets_the_closing_message():
    """🔴 Terminal snapshots are cleared by whoever drains them, and that must stay the alert
    layer — a setup that ended would otherwise be recorded here and never announced, leaving its
    Telegram thread open forever (the failure of 2026-09-16, from the other direction).

    MUTATION: call `drain_setups()` in `_record_setups` -> red.
    """
    ex = _Execution(_snap(state=DEAD, reason="the 15m flipped"))
    r = _runner(_Strategy(ex))
    r._record_setups()
    assert ex.drained == 0
    assert len(ex.drain_setups()) == 1, "the alert layer found nothing left to announce"


def test_a_strategy_that_cannot_report_setups_records_NOTHING_and_says_nothing():
    """`b_leg`, `bos` and `realign` inherit a contract that answers nothing. The startup banner
    already names that state, so this must not add a warning per bar for the life of the run."""

    class _Bare:
        pass

    r = _runner(_Strategy(_Bare()))
    r._record_setups()
    assert r.ledger.rows == [] and r.log.warnings == []


def test_a_strategy_that_RAISES_cannot_break_the_bar():
    """It runs in the bar loop's `finally` beside the alert call and follows the same rule: a
    recorder that can stop a bot managing a live trade is worse than a missing line.

    MUTATION: drop the try/except -> red.
    """

    class _Angry(_Execution):
        def live_setups(self):
            raise RuntimeError("the fib went away")

    r = _runner(_Strategy(_Angry()))
    r._record_setups()  # must not raise
    assert r.ledger.rows == []
    assert len(r.log.warnings) == 1 and "setups" in r.log.warnings[0]


def test_the_row_carries_no_account_number_at_all():
    """What lets a students' channel publish these rows as they are. The snapshot has no lot size
    and no money in it to begin with — the alert layer adds lots to its resting message from the
    bridge — and this pins that the flattening does not invent one."""
    row = live_runner._setup_row(_snap(entry=4308.23, targets=(4200.0, 4100.0)))
    for banned in ("lots", "risk_pct", "risk_usd", "pnl_usd", "balance", "equity", "ticket"):
        assert banned not in row
    assert "$" not in json.dumps(row)


def test_a_bot_that_has_not_ASKED_records_nothing():
    """🔴 The permission default. A bot whose config does not ask writes no rows and says nothing
    — so the other owner's live bots cannot inherit this at his next promote.

    MUTATION: default `record_setups` to True, or drop the check -> red.
    """
    r = _runner(_Strategy(_Execution(_snap())), record=False)
    r._record_setups()
    assert r.ledger.rows == [] and r.log.warnings == []


def test_the_field_ships_OFF():
    """Pin the default where it is declared, not just where it is read."""
    import dataclasses

    import live_config

    field = {f.name: f for f in dataclasses.fields(live_config.LiveConfig)}["record_setups"]
    assert field.default is False


def test_a_runner_with_NO_such_setting_records_nothing_and_does_not_raise():
    """🔴 This is the shape that broke three of the alert tests for one commit: the check sat
    OUTSIDE the try, so a runner built without a config raised straight into the bar loop's
    `finally`. Nothing in this method may reach the caller.

    MUTATION: default the `getattr` to True, or move the check out of the try -> red.
    """

    class _NoCfg:
        pass

    r = _runner(_Strategy(_Execution(_snap())))
    r.cfg = _NoCfg()
    r._record_setups()
    assert r.ledger.rows == []
    del r.cfg
    r._record_setups()  # not even a config attribute — still silent
    assert r.ledger.rows == [] and len(r.log.warnings) == 1
