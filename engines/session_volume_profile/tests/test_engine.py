"""
Hand-traced tests for the SVP (Session Volume Profile / Asia POC) engine.

These pin the mechanics against explicit bars: the 50-row volume profile + its POC, the Pine quirk
that the session-close bar is folded into the profile, the FIFO history, and the MV confirmation
(sweep) state/edge. Full Pine-parity validation of the POC lives in tools/compare_svp.py against a
real TradingView export; these lock the logic so a regression is caught without an export.

Timestamps are in UTC. The Asia window is 0900-1800 Asia/Tokyo == 0000-0900 UTC, so a bar whose UTC hour
is in [0, 9) is in-session; [9, 24) is out. A session needs an out-of-session bar first (to prime
the "was out" edge), then in-session bars, then an out-of-session bar to close it.
"""

from datetime import datetime, timezone

import pytest
from session_volume_profile import SvpEngine


def ums(y, mo, d, h, mi=0):
    """Epoch milliseconds for a UTC wall-clock time."""
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


# A tiny helper so tests read as a list of (index, ts, o, h, l, c, volume) bars.
def feed(engine, bars):
    ev = None
    for b in bars:
        ev = engine.update(*b)
    return ev


# UTC timestamps: an OUT bar to prime, then Asia-in bars, then an OUT bar to close.
_PRIME = ums(2024, 7, 1, 12)  # out of Asia (primes was_out)
_OPEN = ums(2024, 7, 2, 0)  # 20:00 GMT-4 — Asia opens
_MID = ums(2024, 7, 2, 3)  # 23:00 GMT-4 — in Asia
_CLOSE = ums(2024, 7, 2, 9)  # 05:00 GMT-4 — Asia closes (first out bar)


# ── the profile + POC ────────────────────────────────────────────────────────


def test_no_poc_until_first_session_closes():
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 5),
            (1, _OPEN, 100, 105, 95, 100, 10),  # Asia opens — still no POC
        ],
    )
    assert ev.poc is None
    assert ev.formed is False


def test_poc_forms_on_asia_close():
    # Session hi/lo = 105/95 (range 10 → 0.2-wide rows). bar2's heavy volume sits in the 99-101 band
    # (rows 20-29); the wide bar1 spreads a thin 0.2 across all rows. POC row = 20 → 95 + 20.5*0.2.
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 105, 95, 100, 10),  # in-session — sets range 95..105
            (2, _MID, 100, 101, 99, 100, 100),  # in-session — heavy volume 99..101
            (
                3,
                _CLOSE,
                100,
                100,
                100,
                100,
                0,
            ),  # out — closes; volume 0 so the close bar adds nothing
        ],
    )
    assert ev.formed is True
    assert ev.poc == pytest.approx(99.1)
    assert sv.poc() == pytest.approx(99.1)


def test_close_bar_is_included_in_profile():
    # Only one in-session bar (range 90..110). The heavy volume is on the CLOSE bar (out of session).
    # Pine folds the close bar into the profile (svp_sLen = bar_index - startBar + 1), so its 99..101
    # band (rows 22-27) wins → POC 99.0. If the close bar were excluded, the POC would be 90.2.
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 110, 90, 100, 1),  # sole in-session bar — range 90..110, thin volume
            (2, _CLOSE, 100, 101, 99, 100, 1000),  # out — closes, but its heavy volume IS counted
        ],
    )
    assert ev.formed is True
    assert ev.poc == pytest.approx(99.0)


def test_degenerate_range_no_form():
    # A flat session (high == low) has zero range → Pine's `if svp_range > 0` guard skips it.
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 100, 100, 100, 50),  # flat in-session bar
            (2, _CLOSE, 100, 100, 100, 100, 50),
        ],
    )
    assert ev.formed is False
    assert ev.poc is None


def test_na_volume_contributes_nothing():
    # bar1 and the close bar have na volume (contribute 0); only bar2's real volume shapes the POC.
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 110, 90, 100, None),  # in-session — sets range 90..110, but no volume
            (
                2,
                _MID,
                100,
                101,
                99,
                100,
                50,
            ),  # in-session — the only volume, band 99..101 (rows 22-27)
            (3, _CLOSE, 100, 95, 95, 100, None),  # out — na volume, adds nothing
        ],
    )
    assert ev.formed is True
    assert ev.poc == pytest.approx(99.0)


# ── the MV confirmation (sweep) ──────────────────────────────────────────────


def _formed_engine():
    """An engine that has just formed the POC 99.1 (as in test_poc_forms_on_asia_close)."""
    sv = SvpEngine()
    feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 105, 95, 100, 10),
            (2, _MID, 100, 101, 99, 100, 100),
            (3, _CLOSE, 100, 100, 100, 100, 0),
        ],
    )
    return sv


def test_form_bar_confirms_when_it_straddles():
    # A close/form bar that straddles the freshly-formed POC now CONFIRMS on that bar. The reset
    # moved from svpEnd (this bar) to the next svpNew (2026-07-06), so it no longer wipes the tap.
    sv = SvpEngine()
    ev = feed(
        sv,
        [
            (0, _PRIME, 100, 100, 100, 100, 0),
            (1, _OPEN, 100, 105, 95, 100, 10),
            (2, _MID, 100, 101, 99, 100, 100),
            (3, _CLOSE, 100, 100, 99, 100, 0),  # this bar straddles the fresh POC (~99.1)
        ],
    )
    assert ev.formed is True
    assert ev.confirmed is True  # no same-bar reset anymore → the tap confirms
    assert ev.swept is True


def test_confirmed_edge_on_first_tap():
    sv = _formed_engine()
    ev = sv.update(4, ums(2024, 7, 2, 10), 100, 100, 99, 100, 5)  # straddles 99.1
    assert ev.confirmed is True
    assert ev.swept is True


def test_confirmed_fires_only_once():
    sv = _formed_engine()
    sv.update(4, ums(2024, 7, 2, 10), 100, 100, 99, 100, 5)  # first tap
    ev = sv.update(5, ums(2024, 7, 2, 11), 100, 100, 99, 100, 5)  # second tap
    assert ev.confirmed is False  # edge only on the first tap
    assert ev.swept is True  # state stays set


def test_no_confirm_when_price_misses_poc():
    sv = _formed_engine()
    ev = sv.update(4, ums(2024, 7, 2, 10), 98, 98, 97, 98, 5)  # entirely below 99.1
    assert ev.confirmed is False
    assert ev.swept is False


def test_swept_resets_on_next_session_open():
    sv = _formed_engine()  # POC ~99.1, not yet swept
    ev = sv.update(4, ums(2024, 7, 2, 10), 100, 100, 99, 100, 5)  # tap → swept True
    assert ev.swept is True
    # the swept state now PERSISTS past the Asia close (no reset there anymore)...
    ev = sv.update(5, ums(2024, 7, 2, 12), 100, 100, 99, 100, 5)  # still out, later same day
    assert ev.swept is True
    # ...until the NEXT Asia session OPENS (Pine svpNew), which resets it.
    ev = sv.update(6, ums(2024, 7, 3, 0), 100, 98, 97, 98, 10)  # Asia opens; bar misses the POC
    assert ev.swept is False  # reset on the next session OPEN
    assert ev.confirmed is False


# ── edges / bookkeeping ──────────────────────────────────────────────────────


def test_formed_false_on_non_close_bars():
    sv = SvpEngine()
    evs = []
    for b in [
        (0, _PRIME, 100, 100, 100, 100, 0),
        (1, _OPEN, 100, 105, 95, 100, 10),
        (2, _MID, 100, 101, 99, 100, 100),
    ]:
        evs.append(sv.update(*b))
    assert all(e.formed is False for e in evs)  # nothing forms until the session closes


def test_history_fifo_keeps_last_two():
    # Three sessions with distinct POCs; the deque caps at 2 but `poc` always reads the most recent.
    sv = SvpEngine()
    bars = []
    idx = 0

    def session(day, hi, lo):
        nonlocal idx
        out = []
        out.append((idx, ums(2024, 7, day, 12), 100, 100, 100, 100, 0))
        idx += 1  # out prime
        out.append((idx, ums(2024, 7, day + 1, 0), 100, hi, lo, 100, 10))
        idx += 1  # open
        out.append(
            (idx, ums(2024, 7, day + 1, 3), 100, (hi + lo) / 2 + 1, (hi + lo) / 2 - 1, 100, 100)
        )
        idx += 1
        out.append((idx, ums(2024, 7, day + 1, 9), 100, 100, 100, 100, 0))
        idx += 1  # close
        return out

    for day in (1, 3, 5):
        bars += session(day, 105 + day, 95 - day)
    feed(sv, bars)
    assert len(sv._poc_px) == 2  # FIFO cap honoured
    assert sv.poc() == sv._poc_px[-1]  # read is the most recent POC
