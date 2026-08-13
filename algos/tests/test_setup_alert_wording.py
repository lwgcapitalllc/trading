"""What the four setup messages SAY — `algos/live/alerts.py`'s `format_*` half.

🔴 **This file exists because there was nothing here.** The formatters shipped on 2026-08-13 and
every one of them was rewritten later the same day to cut the verbosity, and **the full suite of
643 stayed green through a rewrite of every message the signals channel sends.** `test_setup_alerts.py`
covers the transition layer — which message fires, when, and in which thread — and asserts nothing
about the words. A message is not a side effect of this system, it IS the product: nobody sees a
`SetupSnapshot`, they see these lines.

The formatters are pure — no network, no state, no clock — so this is cheap and there is no excuse
for the gap. **Weighted toward the claims a message makes that could be FALSE**, not toward pinning
wording that is allowed to change. Renaming a label should not redden this file; saying something
untrue about an order should.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import alerts                                                          # noqa: E402
from backtest.setups import (Confluence, DEAD, FILLED, RESTING,        # noqa: E402
                             SetupSnapshot, WATCHING)


def snap(**kw) -> SetupSnapshot:
    base = dict(key="k", strategy="MpcSosFadeStrategy", symbol="XAUUSD.p", side=1,
                state=WATCHING)
    base.update(kw)
    return SetupSnapshot(**base)


def conf(zone_met: bool, zone_detail: str = "not tagged yet"):
    return (Confluence("Arm", True, "swept Day Low"),
            Confluence("Shift of structure", True, "confirmed"),
            Confluence("Retrace zone", zone_met, zone_detail))


# ── the claim that can be false ──────────────────────────────────────────────────────────────
def test_a_limit_resting_at_2_of_3_NAMES_what_is_still_missing():
    """🔴 THE load-bearing test in this file.

    The entry edge comes from a gap overlapping the 0.5-0.886 band, and a gap can be there before
    PRICE is — so the bot places a real limit while the retrace confluence is still outstanding.
    A message headed `ENTRY ZONE LIVE` with a price on it reads as *everything is met and we are
    waiting on a fill*, and for these it is not true.

    The first version listed only the MET confluences, which hid exactly this. The second listed
    all three, one per line. This one names only what is outstanding — same property, one line —
    and the property is what is pinned here, never the layout that carries it.
    """
    out = alerts.format_entry_zone(snap(state=RESTING, confluences=conf(False),
                                        entry=3279.6, stop=3270.9))
    assert "2 of 3" in out
    assert "Retrace zone" in out, f"an order resting at 2 of 3 must say what is missing:\n{out}"


def test_a_limit_resting_at_3_of_3_does_NOT_claim_something_is_missing():
    """The other direction, and it is the one that goes wrong when the check above is written as
    an unconditional line. A message saying `Still missing:` with nothing after it is worse than
    saying nothing — it invites a reader to go looking for a confluence that is met."""
    out = alerts.format_entry_zone(snap(state=RESTING, confluences=conf(True, "0.5-0.886 tagged"),
                                        entry=3279.6, stop=3270.9))
    assert "3 of 3" in out
    assert "missing" not in out.lower(), out


def test_every_blocking_rule_is_carried_not_just_the_first():
    """A reader asking *is this rule earning its keep* needs the whole set, and "blocked by the
    veto" has to stay true on a setup the final-hour rule was also refusing. The Pine reports one
    because a chart tag has room for one line; Telegram does not have that excuse."""
    rules = ("Divergence / extreme-RSI veto", "Final hour (16:00-18:00 New York)",
             "HTF breakout / bias filter")
    out = alerts.format_blocked(snap(confluences=conf(True), blocked_by=rules))
    for r in rules:
        assert r in out, f"{r!r} was dropped:\n{out}"


def test_the_death_sentence_is_the_STRATEGYS_and_is_not_reworded():
    """Two explanations for one death can disagree and a reader cannot tell which is the bot's.
    `format_resolved` copies `snap.reason` and composes nothing."""
    reason = "No retrace — Price never retraced into the 0.5-0.886 band."
    assert reason in alerts.format_resolved(snap(state=DEAD, confluences=conf(False),
                                                 reason=reason))


def test_a_zone_prints_low_to_high_whichever_side_it_came_from():
    """A long's zone runs 0.5 DOWN to 0.886 and a short's runs UP, so the stored pair arrives in
    either order. Rendering it as stored puts `3,418.60 – 3,405.10` on one side and the reverse on
    the other, and a reader comparing two messages reads the inconsistency as a bug in the SETUP.
    """
    long_out = alerts.format_watching(snap(side=1, confluences=conf(False),
                                           zone=(3312.4, 3298.15)))
    short_out = alerts.format_watching(snap(side=-1, confluences=conf(False),
                                            zone=(3401.8, 3417.25)))
    assert "3,298.15 – 3,312.40" in long_out, long_out
    assert "3,401.80 – 3,417.25" in short_out, short_out


def test_the_projected_stop_is_carried_because_it_is_why_the_message_is_worth_reading():
    """Aaron's brief: *"a valid entry zone anywhere between the most shallow area to the deepest
    area and the potential stop loss is this"*. A forming message without the stop is a headline.
    """
    out = alerts.format_watching(snap(confluences=conf(False), zone=(3312.4, 3298.15),
                                      stop=3297.65))
    assert "3,297.65" in out, out


# ── the head, and what it is allowed to fall back to ─────────────────────────────────────────
def test_the_bots_display_name_is_used_when_it_is_given():
    """A strategy only knows its CLASS name. `MpcSosFadeStrategy` is not what the same bot is
    called in every other message this suite sends, and one system should not have two names for
    one bot in one chat."""
    out = alerts.format_watching(snap(confluences=conf(False)), display="MPC SOS Fade")
    assert "MPC SOS Fade" in out
    assert "MpcSosFadeStrategy" not in out, out


def test_it_falls_back_to_the_class_name_rather_than_rendering_a_nameless_setup():
    """⚠ The fallback direction matters: a caller that forgets to pass a display name must get a
    name that is TRUE and ugly, never a blank. An unnamed setup in a chat that will one day carry
    more than one bot is a message you cannot act on."""
    out = alerts.format_watching(snap(confluences=conf(False)))
    assert "MpcSosFadeStrategy" in out, out


# ── the shapes a terser strategy can hand it ─────────────────────────────────────────────────
def test_a_confluence_with_no_detail_still_renders_its_NAME():
    """`_confluence_line` prints the strategy's `detail` because that is the readable half. A
    strategy that supplies none must not produce a stray ` · · ` — it gets the name instead."""
    bare = (Confluence("Sweep", True), Confluence("Shift", True))
    out = alerts.format_watching(snap(confluences=bare))
    assert "Sweep" in out and "Shift" in out
    assert " ·  · " not in out, out


def test_a_setup_with_no_zone_yet_does_not_print_an_empty_price_line():
    """`zone` is `None` until the fib levels exist. Every price line is conditional on the value
    being there, so this renders short rather than rendering `Zone None – None`."""
    out = alerts.format_watching(snap(confluences=conf(False), zone=None))
    assert "None" not in out, out
    assert "Zone" not in out, out


def test_no_message_ever_renders_a_blank_or_whitespace_only_line():
    """Telegram collapses nothing; a blank line is visible padding in a channel whose whole
    complaint was verbosity. `alert()` drops empties, and this asserts every formatter actually
    benefits from that rather than building its own blanks."""
    cases = [
        alerts.format_watching(snap(confluences=conf(False), zone=(3312.4, 3298.15), stop=3297.7)),
        alerts.format_entry_zone(snap(state=RESTING, confluences=conf(True), entry=3279.6,
                                      stop=3270.9, targets=(3296.1, 3311.75))),
        alerts.format_blocked(snap(confluences=conf(True), blocked_by=("Final hour",))),
        alerts.format_resolved(snap(state=FILLED, confluences=conf(True))),
        alerts.format_resolved(snap(state=DEAD, confluences=conf(False), reason="No retrace.")),
    ]
    for out in cases:
        assert all(ln.strip() for ln in out.split("\n")), repr(out)


def test_the_messages_are_plain_text_because_a_lone_underscore_kills_the_send():
    """Every message here carries a strategy name, a symbol or a broker string, and those are full
    of underscores. A lone `_` opens an italic that never closes and Telegram rejects the WHOLE
    message — measured on the first real send, 2026-07-31. Nothing here may add markdown of its
    own; the underscores that arrive in the DATA are exactly why."""
    out = alerts.format_watching(snap(confluences=conf(False)))
    assert "*" not in out and "`" not in out, out
