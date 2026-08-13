"""The house shape every Telegram message in this repo is rendered in.

**Why a shared formatter exists at all.** Each notifier had grown its own voice: the bot wrote
seven-line trade slips, the watchdog wrote bold headlines over bullet lists, the reviewer wrote a
title and a paragraph. Read in one chat they looked like five systems, and each one buried the
actionable part somewhere different. Aaron's brief (2026-08-05), after picking from rendered
samples in Telegram: concise, but never so concise you cannot diagnose it; facts that belong
together on one line, facts that do not on the next.

The tests below pin the three properties a message can silently lose:

1. the header is short enough to read on a lock screen;
2. an absent fact is ABSENT, never rendered as an empty line or a fabricated zero;
3. no message carries its own timestamp — Telegram already prints one, in the reader's clock.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "shared"))

import alert_format as af  # noqa: E402


# ── the shape ────────────────────────────────────────────────────────────────────
def test_the_header_is_icon_label_subject():
    msg = af.alert("⛔", "HALTED", "MPC SOS Fade", "Broker and emulator disagree.")
    assert msg.splitlines()[0] == "⛔ HALTED · MPC SOS Fade"


def test_a_subject_is_optional():
    """A threaded trade exit has no subject — the entry it replies to already named the trade,
    and repeating it is the noise the reply was supposed to remove."""
    assert af.alert("✅", "WIN", "", "Made $368.00 · +1.84R") == "✅ WIN\nMade $368.00 · +1.84R"


def test_each_group_of_facts_gets_its_own_line():
    msg = af.alert("📈", "ENTRY", "LONG XAUUSD.s",
                   "Entry 3,290.00 · Stop 3,280.00",
                   "Size 0.42 lots · Risking $200.00 (10%)")
    assert msg.splitlines() == [
        "📈 ENTRY · LONG XAUUSD.s",
        "Entry 3,290.00 · Stop 3,280.00",
        "Size 0.42 lots · Risking $200.00 (10%)",
    ]


def test_a_missing_fact_is_absent_not_a_blank_line():
    """A caller passes what it has. Rendering `None` as an empty line would put a hole in the
    middle of the message and make every sender grow its own branching — which is the layout
    drift this module exists to end."""
    msg = af.alert("🟢", "ONLINE", "MPC SOS Fade", "live", None, "", "  ", "$2,000.00")
    assert msg == "🟢 ONLINE · MPC SOS Fade\nlive\n$2,000.00"


def test_the_header_stays_short_enough_for_a_lock_screen():
    for label in ("ONLINE", "STOPPED", "HALTED", "NO MT5 LINK", "WILL NOT START", "REVIEW",
                  "SETTINGS NOT APPLIED", "STALLED", "RECOVERED", "RESTARTED"):
        head = af.alert("⚠️", label, "MPC SOS Fade").splitlines()[0]
        assert len(head) <= 45, f"{label!r} makes a {len(head)}-char header: {head!r}"


# ── the money rule ───────────────────────────────────────────────────────────────
def test_an_unknown_balance_is_not_rendered_as_zero():
    """The repo's most-repeated rule, and the one that cost 50 minutes of blind trading on
    2026-08-04: never let "no" and "cannot ask" be the same value. A blind terminal returns no
    balance, and `$0.00` in a startup banner would be a measurement nobody made."""
    assert af.money(None) == "unknown"
    assert af.money(0.0) == "$0.00"
    assert af.money(2000.0) == "$2,000.00"


def test_joined_drops_what_is_missing():
    assert af.joined(["live", None, "XAUUSD.s M15", "", "$2,000.00"]) == \
        "live · XAUUSD.s M15 · $2,000.00"


# ── timestamps ───────────────────────────────────────────────────────────────────
#: ⚠ Pinned rather than left to the wall clock. `when()` renders a date once the moment is not
#: today, so a test asserting on the bare time has to say which day it is being read on — left
#: floating it would pass on 2026-08-05 and fail on every other day of the decade.
_SAME_DAY = datetime(2026, 8, 5, 23, 0, tzinfo=timezone.utc)


def test_a_past_moment_is_rendered_in_the_local_clock_with_the_zone_named():
    """The ONE case that needs an explicit time: a message about something that happened
    earlier. The zone is named because the ledger and the logs are UTC, and a bare "1:06" would
    be an hour of arithmetic away from the record it points at."""
    out = af.when(datetime(2026, 8, 5, 18, 6, tzinfo=timezone.utc), now=_SAME_DAY)
    assert "1:06 PM" in out
    assert "C" in out.split()[-1]           # CDT or CST depending on the date


def test_the_hour_has_no_leading_zero_and_the_format_string_is_portable():
    """🔴 It was `%-I` — a glibc extension that works on a Mac and raises
    `ValueError: Invalid format string` on Windows, where the equivalent is `%#I`. The suite was
    green here and `log_review.py` crashed on the VPS on its first run. The stripping is done in
    Python so one string works on both."""
    assert af.when(datetime(2026, 8, 5, 6, 6, tzinfo=timezone.utc),
                   now=_SAME_DAY).startswith("1:06")
    assert af.when(datetime(2026, 8, 5, 18, 6, tzinfo=timezone.utc),
                   now=_SAME_DAY).startswith("1:06")
    assert af.when(datetime(2026, 8, 5, 15, 6, tzinfo=timezone.utc),
                   now=_SAME_DAY).startswith("10:06")


def test_a_naive_timestamp_is_read_as_utc():
    """Every timestamp in the ledger is UTC. Reading a naive one as local would shift the same
    event by hours depending on which machine rendered it."""
    assert af.when(datetime(2026, 8, 5, 18, 6)) == af.when(
        datetime(2026, 8, 5, 18, 6, tzinfo=timezone.utc))


def test_an_iso_string_is_accepted_because_that_is_what_the_ledger_holds():
    assert "1:06 PM" in af.when("2026-08-05T18:06:00+00:00")


def test_an_unparseable_timestamp_is_returned_rather_than_raising():
    """A notifier that can be brought down by a bad timestamp is worse than one printing a stamp
    it could not read — the message it was carrying is the point."""
    assert af.when("not a time") == "not a time"
    assert af.when(None) == "None"


# ── which DAY the past moment was on ─────────────────────────────────────────────
#
# 🔴 Every test below exists because of one burst of nine Telegram messages on 2026-08-13.
# `log_review.py` looks back TWO days and renders each finding with `when()`, which printed a
# bare clock time. Four findings were from that afternoon and five were from the day before, and
# in the chat they were indistinguishable — "4 starts since 11:12 AM CDT" read as this morning
# when it meant yesterday morning. Every stamp was CORRECT and the reader still concluded the
# wrong thing, which is the repo's standing rule about metrics arriving one layer up.
_REVIEW_RAN = datetime(2026, 8, 13, 21, 20, tzinfo=timezone.utc)      # 4:20 PM CDT


def test_a_moment_from_an_EARLIER_DAY_carries_its_date():
    """The finding that was actually misread: a start at 11:12 AM CDT on the 12th."""
    out = af.when(datetime(2026, 8, 12, 16, 12, tzinfo=timezone.utc), now=_REVIEW_RAN)
    assert out.startswith("Aug 12, 11:12 AM"), out


def test_a_moment_from_TODAY_carries_no_date():
    """The common case stays exactly as it was. A date on every stamp would be noise on the 95%
    of messages that are about the last few minutes, and noise is what gets a channel muted."""
    out = af.when(datetime(2026, 8, 13, 20, 31, tzinfo=timezone.utc), now=_REVIEW_RAN)
    assert out.startswith("3:31 PM"), out
    assert "Aug" not in out


def test_the_day_is_decided_in_the_READING_zone_never_in_UTC():
    """⚠ The two disagree for five hours out of every twenty-four, which is most of a US evening.

    01:00 UTC on the 13th is 8pm CDT on the 12th — the same wall-clock evening as the events
    around it. Comparing the UTC dates would stamp it "Aug 13" and send the reader to the wrong
    day's log, which is worse than the bare time this replaced.
    """
    late_evening = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)   # 8:00 PM CDT on the 12th
    reading_it = datetime(2026, 8, 13, 2, 0, tzinfo=timezone.utc)     # 9:00 PM CDT on the 12th
    out = af.when(late_evening, now=reading_it)
    assert out.startswith("8:00 PM"), out
    assert "Aug" not in out, "same local evening, different UTC dates — this is not another day"


def test_the_day_of_the_month_has_no_leading_zero_either():
    """Same portability trap as the hour, one field along: `%-d` is glibc and raises on Windows,
    where the scheduled task that sends these actually runs."""
    out = af.when(datetime(2026, 8, 5, 16, 12, tzinfo=timezone.utc), now=_REVIEW_RAN)
    assert out.startswith("Aug 5, "), out


def test_an_unparseable_timestamp_still_comes_back_unchanged_with_a_clock_supplied():
    """The date logic must not introduce a raise on the path whose whole job is not to raise."""
    assert af.when("not a time", now=_REVIEW_RAN) == "not a time"


# ── the mirror ───────────────────────────────────────────────────────────────────
def _mirror():
    """The command center's copy, loaded by PATH rather than imported — that app is not on this
    suite's sys.path and must not be put there, which is the whole point of the boundary."""
    import importlib.util
    path = _REPO / "command-center" / "backend" / "services" / "alert_format.py"
    spec = importlib.util.spec_from_file_location("cc_alert_format", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_command_center_describes_the_same_shape():
    """`command-center/backend/services/alert_format.py` is a deliberate second implementation —
    the two subsystems may share a data file and may not import each other's code. Two copies of
    one rule is two rules that can drift, so the contract is compared rather than trusted to a
    comment on each side."""
    assert _mirror().SPEC == af.SPEC, "the two alert_format modules describe different shapes"


def test_the_mirror_renders_an_identical_message():
    """The stronger half: agreeing on a docstring is not agreeing on output. These are the exact
    edge cases — an absent fact and a whitespace-only one — where two hand-written copies of a
    layout diverge first."""
    cc = _mirror()
    args = ("⏹", "STOPPED", "MPC SOS Fade", "Stopped from the command center.", None, "  ")
    assert cc.alert(*args) == af.alert(*args)
    assert cc.alert("✅", "WIN", "", "Made $368.00") == af.alert("✅", "WIN", "", "Made $368.00")
    assert cc.joined(["a", None, "b", ""]) == af.joined(["a", None, "b", ""])
