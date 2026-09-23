"""The trade alert templates.

These are the messages Aaron actually reads, so the wording is part of the contract, not an
implementation detail. The tests below assert on the things a person would notice: that the
verdict is honest, that a scratch is not filed as a loss, that the numbers are the ones the
broker reported, and that nothing here can throw inside a trading loop.

**Rewritten 2026-08-05 to the house shape** (`shared/alert_format.py`), which Aaron picked from
rendered samples in Telegram. Three changes carry a reason worth keeping, and each has a test
below that would fail if it were undone:

* **No timestamp.** Telegram already prints the send time in each reader's own local clock, right
  above the message, and a bot cannot do better — it sends one string to a group and has no idea
  where anyone is reading it. A second clock was duplication.
* **The exit does not restate what was risked.** It posts as a reply to the entry, which said so.
* **The stop distance in pips is gone.** 1,725 pips on gold answered a question nobody asks;
  `Entry 3,290.00 · Stop 3,280.00` says the same thing in the reader's own units.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "live"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))
import alerts  # noqa: E402

_WHEN = datetime(2026, 7, 31, 1, 45, tzinfo=timezone.utc)


# ── entry ───────────────────────────────────────────────────────────────────────
def test_entry_carries_everything_asked_for():
    """Aaron's list: strategy, direction, symbol, entry, stop, size, and what it costs to be
    wrong."""
    msg = alerts.format_entry(
        strategy="SOS Fade",
        symbol="XAUUSD.s",
        direction="LONG",
        entry=4094.87,
        stop=4077.62,
        lots=0.05,
        risk_usd=200.0,
        risk_pct=10,
        when=_WHEN,
    )
    for expected in (
        "SOS Fade",
        "XAUUSD.s",
        "LONG",
        "4,094.87",
        "4,077.62",
        "0.05 lots",
        "$200.00",
        "10%",
    ):
        assert expected in msg, f"missing {expected!r} from:\n{msg}"


def test_the_entry_states_the_risk_because_the_exit_will_not():
    """Aaron, 2026-08-05: the exit replies to this message, so repeating "on $200 risked" there
    is repeating what is one tap up the thread. That makes THIS the only place it is said, and a
    silent regression here would leave it said nowhere."""
    msg = alerts.format_entry(
        strategy="S",
        symbol="X",
        direction="LONG",
        entry=1.0,
        stop=0.9,
        lots=1,
        risk_usd=200.0,
        risk_pct=10,
        when=_WHEN,
    )
    assert "Risking $200.00 (10%)" in msg


def test_an_unknown_risk_is_omitted_rather_than_printed_as_zero():
    """The repo's standing rule: never let "no" and "cannot ask" be the same value. A bot whose
    stop distance could not be measured must not report `Risking $0.00`, which reads as a free
    trade."""
    msg = alerts.format_entry(
        strategy="S", symbol="X", direction="LONG", entry=1.0, stop=0.9, lots=1, when=_WHEN
    )
    assert "Risking" not in msg
    assert "$0.00" not in msg
    assert "Size 1 lots" in msg


def test_prices_are_grouped_together_and_size_is_on_its_own_line():
    """Aaron's brief: facts that belong together on one line, facts that do not on the next. The
    two prices define the trade; the size is a different question."""
    msg = alerts.format_entry(
        strategy="SOS Fade",
        symbol="XAUUSD.s",
        direction="LONG",
        entry=4094.87,
        stop=4077.62,
        lots=0.05,
        risk_usd=200.0,
        risk_pct=10,
        when=_WHEN,
    )
    lines = msg.splitlines()
    assert lines[1] == "Entry 4,094.87 · Stop 4,077.62"
    assert lines[2].startswith("Size 0.05 lots")


def test_direction_is_visible_without_opening_the_message():
    """The first line is what a notification preview shows."""

    def first(d):
        return alerts.format_entry(
            strategy="S", symbol="X", direction=d, entry=1.0, stop=0.9, lots=1, when=_WHEN
        ).splitlines()[0]

    assert "LONG" in first("LONG") and "📈" in first("LONG")
    assert "SHORT" in first("SHORT") and "📉" in first("SHORT")


def test_lot_size_does_not_print_trailing_zeros():
    msg = alerts.format_entry(
        strategy="S", symbol="X", direction="LONG", entry=1.0, stop=0.9, lots=0.5, when=_WHEN
    )
    assert "Size 0.5 lots" in msg


def test_a_zero_width_stop_does_not_crash_the_alert():
    """It should never happen — the minimum-stop guard and the broker both refuse it — but an
    alert that raises would take down the loop that was reporting a trade."""
    msg = alerts.format_entry(
        strategy="S", symbol="X", direction="LONG", entry=1.0, stop=1.0, lots=1, when=_WHEN
    )
    assert "Entry 1.00 · Stop 1.00" in msg


# ── verdict ─────────────────────────────────────────────────────────────────────
def test_win_and_lose_follow_the_money():
    assert alerts.verdict(292.65, 3.39) == alerts.WIN
    assert alerts.verdict(-84.10, -1.0) == alerts.LOSE


def test_a_scratch_is_breakeven_even_though_it_lost_money():
    """The exact case Aaron named. A stop moved to entry and hit is a scratch, but spread and
    commission still leave it a few dollars down. Filing that as a LOSE would put a working risk
    rule in the same bucket as real losers and make the win rate read worse than the strategy
    behaves — while the dollar figure stays honest about the cost."""
    assert alerts.verdict(-0.62, r_multiple=-0.01) == alerts.BREAKEVEN
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=4094.87, pnl_usd=-0.62, r_multiple=-0.01, when=_WHEN
    )
    assert "BREAKEVEN" in msg
    assert "$0.62" in msg  # the money is never rounded away to make it look clean


def test_a_real_loss_is_not_excused_as_breakeven():
    assert alerts.verdict(-410.0, r_multiple=-1.0) == alerts.LOSE


def test_the_scratch_band_comes_from_the_strategy():
    """`exec_scratch_r` is the strategy's own definition of "nothing happened". Hardcoding a
    band here would disagree with the backtest that produced the numbers being compared."""
    assert alerts.verdict(-5.0, r_multiple=-0.30, scratch_r=0.15) == alerts.LOSE
    assert alerts.verdict(-5.0, r_multiple=-0.30, scratch_r=0.50) == alerts.BREAKEVEN


def test_verdict_falls_back_to_the_pnl_when_r_is_unknown():
    """R needs the risk that was actually attached. When that is missing, the sign of the money
    is the most that can honestly be claimed."""
    assert alerts.verdict(50.0, None) == alerts.WIN
    assert alerts.verdict(-50.0, None) == alerts.LOSE
    assert alerts.verdict(0.0, None) == alerts.BREAKEVEN


def test_the_label_is_a_noun_while_the_value_stays_the_verb():
    """The message says LOSS because it describes an outcome; `verdict()` still returns `LOSE`,
    which the bridge, the ledger and these tests compare against. Merging the two would make a
    wording change a behaviour change."""
    assert alerts.LOSE == "LOSE"
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=-84.10, r_multiple=-1.0, when=_WHEN
    )
    assert msg.splitlines()[0] == "❌ LOSS"


# ── exit ────────────────────────────────────────────────────────────────────────
def test_exit_carries_everything_asked_for():
    """Aaron's list: verdict, dollar amount, R, exit price."""
    msg = alerts.format_exit(
        strategy="SOS Fade",
        symbol="XAUUSD.s",
        exit_price=4153.40,
        pnl_usd=292.65,
        r_multiple=3.39,
        when=_WHEN,
    )
    for expected in ("WIN", "Made $292.65", "+3.39R", "4,153.40"):
        assert expected in msg, f"missing {expected!r} from:\n{msg}"


def test_the_exit_does_not_restate_what_was_risked():
    """Aaron, 2026-08-05: "these messages are gonna reply to the initial message… so I already
    know how much I risked". The entry says it once."""
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=292.65, r_multiple=3.39, when=_WHEN
    )
    assert "risked" not in msg.lower()
    assert "Risking" not in msg


def test_a_loss_says_lost_rather_than_printing_a_minus_sign_on_made():
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=-84.10, r_multiple=-1.0, when=_WHEN
    )
    assert "Lost $84.10" in msg
    assert "-1.00R" in msg
    assert "❌" in msg


def test_the_exit_reason_separates_a_scratch_from_a_real_stop_out():
    """Both exited at a stop and only one of them is the risk rule working. Without the reason
    the reader has to infer it from the R, which is exactly the sort of arithmetic an alert
    exists to save."""
    scratch = alerts.format_exit(
        strategy="S",
        symbol="X",
        exit_price=4094.87,
        pnl_usd=-0.62,
        r_multiple=-0.01,
        exit_reason="stop moved to entry",
        when=_WHEN,
    )
    stopped = alerts.format_exit(
        strategy="S",
        symbol="X",
        exit_price=1.0,
        pnl_usd=-84.10,
        r_multiple=-1.0,
        exit_reason="stop",
        when=_WHEN,
    )
    assert "Exit 4,094.87 (stop moved to entry)" in scratch
    assert "Exit 1.00 (stop)" in stopped


def test_an_exit_with_no_reason_does_not_print_empty_brackets():
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=1.0, r_multiple=1.0, when=_WHEN
    )
    assert "Exit 1.00" in msg
    assert "()" not in msg


def test_the_outcome_is_the_first_thing_on_the_line():
    msg = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=292.65, r_multiple=3.0, when=_WHEN
    )
    assert msg.splitlines()[0].startswith("✅ WIN")


def test_a_threaded_exit_does_not_repeat_the_entrys_header():
    """It posts as a reply, so the strategy and symbol are one tap away. Aaron's call."""
    msg = alerts.format_exit(
        strategy="SOS Fade",
        symbol="XAUUSD.s",
        exit_price=4153.40,
        pnl_usd=292.65,
        r_multiple=3.39,
        when=_WHEN,
    )
    assert msg.splitlines()[0] == "✅ WIN"
    assert "SOS Fade" not in msg
    assert "XAUUSD.s" not in msg


def test_an_unthreaded_exit_names_the_trade_it_closed():
    """No entry alert was sent, so there is nothing to reply to — a bare 'WIN' in the group
    would name no trade at all."""
    msg = alerts.format_exit(
        strategy="SOS Fade",
        symbol="XAUUSD.s",
        exit_price=4153.40,
        pnl_usd=292.65,
        r_multiple=3.39,
        threaded=False,
        when=_WHEN,
    )
    assert msg.splitlines()[0] == "✅ WIN · XAUUSD.s"


# ── the house shape ─────────────────────────────────────────────────────────────
def test_no_message_carries_a_timestamp():
    """Telegram stamps every message in the reader's own local time, immediately above it. A
    second clock is duplication, and one in UTC beside Telegram's local one invites the reader to
    reconcile two times for one event."""
    entry = alerts.format_entry(
        strategy="S", symbol="X", direction="LONG", entry=1.0, stop=0.9, lots=1, when=_WHEN
    )
    exit_ = alerts.format_exit(
        strategy="S", symbol="X", exit_price=1.0, pnl_usd=1.0, r_multiple=1.0, when=_WHEN
    )
    for msg in (entry, exit_):
        assert "UTC" not in msg
        assert "2026" not in msg


def test_no_markdown_syntax_in_either_template():
    """These messages carry strategy names and broker symbols, which are full of underscores.
    Telegram rejects an unbalanced Markdown entity and drops the WHOLE message — so an alert
    must not depend on the sender's plain-text rescue."""
    entry = alerts.format_entry(
        strategy="sos_fade_demo",
        symbol="XAUUSD.s",
        direction="LONG",
        entry=1.0,
        stop=0.9,
        lots=1,
        when=_WHEN,
    )
    # threaded=False so the exit actually CARRIES the underscore-heavy name — the threaded form
    # omits it, which would make this assertion pass without testing anything.
    exit_ = alerts.format_exit(
        strategy="sos_fade_demo",
        symbol="XAUUSD.s",
        exit_price=1.0,
        pnl_usd=1.0,
        r_multiple=1.0,
        threaded=False,
        when=_WHEN,
    )
    for msg in (entry, exit_):
        assert "*" not in msg
        # 2, not 3: `sos_fade_demo` carries two underscores where `mpc_sos_fade_demo` carried
        # three. ⚠ **The PARITY of that count decided whether a Markdown send failed loudly or
        # corrupted silently** — odd is unbalanced and Telegram rejects the whole message (the
        # rescue then delivers it), even parses fine and eats the underscores. The trade path no
        # longer asks for Markdown at all (`runner._notify`), so neither can happen.
        assert msg.count("_") == msg.count("sos_fade_demo") * 2  # only the name's own


def test_every_message_opens_with_an_icon_a_label_and_stays_short():
    """The shape a reader relies on: the first line is the whole message in a few words, because
    that is what a lock screen shows."""
    msgs = [
        alerts.format_entry(
            strategy="SOS Fade",
            symbol="XAUUSD.s",
            direction="LONG",
            entry=4094.87,
            stop=4077.62,
            lots=0.05,
            risk_usd=200.0,
            risk_pct=10,
            when=_WHEN,
        ),
        alerts.format_exit(
            strategy="S", symbol="X", exit_price=1.0, pnl_usd=1.0, r_multiple=1.0, when=_WHEN
        ),
    ]
    for msg in msgs:
        head = msg.splitlines()[0]
        assert head[0] in "📈📉✅❌➖"
        assert len(head) < 45, f"header too long to read at a glance: {head!r}"
        assert len(msg.splitlines()) <= 4


# ── how a trade is MANAGED, between the fill and the outcome (2026-09-22) ────────────────────
#
# Aaron: *"if a trade moves to break even I should get an alert saying move to break even... it
# should alert me all the way of how the trade is being managed."* These pin the three things
# that can happen to a stop, the honest R, and the two size events.
#
# **PROVED BY MUTATION, 2026-09-22** — there was no bug to watch these go red against, so each
# one was made to fail by breaking the thing it claims to pin:
#   * `stop_locked_r` made to substitute a stand-in distance instead of answering `None` →
#     `test_an_unknown_opening_stop_prints_no_R_at_all` red on `risk now 0.00R` appearing. That
#     mutation IS the "no" / "cannot ask" collapse rule 1 exists to stop.
#   * `stop_move_kind` made to ignore the PREVIOUS stop → the trail test red, reporting every
#     later ratchet as a fresh breakeven.
#   * `stop_move_kind` made to read a short's prices the long way round → the tighten test red,
#     reporting a trade being taken off risk as one tightened into it.


def test_a_stop_reaching_entry_is_reported_as_BREAKEVEN_in_those_words():
    """The message Aaron asked for by name. It must say breakeven, and it must not claim more
    safety than a stop can give — a gap fills through one."""
    msg = alerts.format_stop_moved(direction=1, entry=3290.0, was=3280.0, now=3290.0)
    assert msg.startswith("🛡 STOP AT BREAKEVEN")
    assert "Stop 3,280.00 → 3,290.00 (entry)" in msg
    assert "gaps through the stop" in msg


def test_a_stop_that_JUMPS_PAST_entry_still_reports_the_breakeven_crossing():
    """A buffered breakeven lands beyond the entry. It is still the move that took the risk off,
    so it is still the message — reporting it as a trail would lose the one event he named, and
    the R says where the stop actually is."""
    msg = alerts.format_stop_moved(
        direction=1, entry=3290.0, was=3280.0, now=3294.0, opening_stop=3280.0
    )
    assert msg.startswith("🛡 STOP AT BREAKEVEN")
    assert "locking +0.40R" in msg
    assert "(entry)" not in msg  # it is NOT at the entry, and must not say so


def test_a_later_move_in_profit_is_a_TRAIL_and_says_what_it_locks():
    msg = alerts.format_stop_moved(
        direction=1, entry=3290.0, was=3290.0, now=3301.5, opening_stop=3280.0
    )
    assert msg.startswith("🪜 STOP TRAILED")
    assert "Stop 3,290.00 → 3,301.50 · locking +1.15R" in msg


def test_a_stop_still_behind_entry_is_a_TIGHTEN_and_states_the_RISK_not_the_lock():
    """`locking -0.50R` is a sentence the reader has to translate. Below the entry the number
    means what is still on the line, so the message says that instead."""
    msg = alerts.format_stop_moved(
        direction=-1, entry=3290.0, was=3300.0, now=3296.0, opening_stop=3302.0
    )
    assert msg.startswith("🔒 STOP TIGHTENED")
    assert "risk now 0.50R" in msg
    assert "locking" not in msg


def test_a_short_reads_its_prices_the_other_way_round():
    """Below entry is PROFIT on a short. A sign error here would report a trade being taken off
    risk as one being tightened into it."""
    msg = alerts.format_stop_moved(
        direction=-1, entry=3290.0, was=3300.0, now=3290.0, opening_stop=3300.0
    )
    assert msg.startswith("🛡 STOP AT BREAKEVEN")


def test_an_unknown_opening_stop_prints_no_R_at_all():
    """Rule 1. A trade restored from a record written before its opening stop was kept has no
    yardstick, and `0.00R` would be a measurement nobody took."""
    msg = alerts.format_stop_moved(direction=1, entry=3290.0, was=3290.0, now=3301.5)
    assert "R" not in msg.replace("STOP TRAILED", "")
    assert "Stop 3,290.00 → 3,301.50" in msg


def test_an_unthreaded_stop_move_names_the_trade_it_is_about():
    """The same rule the exit already follows: with no entry message to hang under, a bare
    `STOP TRAILED` floating in the group names no trade at all."""
    msg = alerts.format_stop_moved(
        direction=1, entry=3290.0, was=3290.0, now=3301.5, symbol="XAUUSD.s", threaded=False
    )
    assert msg.startswith("🪜 STOP TRAILED · LONG · XAUUSD.s")


def test_a_banked_partial_says_what_is_left_and_where_it_filled():
    """The size still running is the fact the reader acts on. The fill note is there because the
    bridge banks at market on a closed bar and the lab fills at the rung — a divergence that is
    hunted for hours if the message does not name it."""
    msg = alerts.format_partial_banked(lots_banked=0.17, lots_before=0.42, lots_after=0.25)
    assert msg.startswith("💰 PART BANKED")
    assert "Took 0.17 of 0.42 lots off · 0.25 still running" in msg
    assert "market on the bar's close" in msg


def test_a_scale_in_restates_the_SIZE_the_entry_message_can_no_longer_be_trusted_for():
    """The entry message stated a size and a risk. An add makes both of them stale, so this one
    carries the new total — and calls its price an estimate, because the bridge sends an add at
    market and never reads the deal back."""
    msg = alerts.format_scaled_in(lots_added=0.2, lots_now=0.62, price=3305.0, stop=3296.0)
    assert msg.startswith("➕ ADDED TO POSITION")
    assert "Added 0.20 lots at about 3,305.00" in msg
    assert "0.62 lots now open · every lot on the same stop 3,296.00" in msg


def test_no_management_message_carries_markdown_that_telegram_would_reject():
    """The rule that costs a whole message when it is broken: a lone underscore opens an italic
    Telegram never closes. Every one of these carries a symbol, and symbols have suffixes."""
    msgs = [
        alerts.format_stop_moved(
            direction=1, entry=3290.0, was=3280.0, now=3290.0, symbol="XAUUSD.s", threaded=False
        ),
        alerts.format_partial_banked(
            lots_banked=0.17, lots_before=0.42, lots_after=0.25, symbol="XAUUSD.s", threaded=False
        ),
        alerts.format_scaled_in(
            lots_added=0.2, lots_now=0.62, price=3305.0, symbol="XAUUSD.s", threaded=False
        ),
    ]
    for m in msgs:
        assert "*" not in m and "`" not in m
