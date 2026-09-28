"""
session_volume_profile/engine.py — the Session Volume Profile (SVP) / Asia POC ("MV" line) state machine.

One stateful streaming engine, fed one closed bar at a time (index + UTC timestamp + high/low/close/
open + volume), returning that bar's SVP EVENTS: the current Asia POC price, whether a fresh POC
formed on this bar, and the MV confirmation (has price tapped the POC since it formed). Ported
line-by-line from the SESSION VOLUME PROFILE block in indicators/engines/mpc_jarvis.pine (line ~2554) plus
its confirmation-table "MV slot" (line ~2772).

What a Session Volume Profile is
--------------------------------
While the Asia session (0900-1800 Asia/Tokyo — the same window as the sessions engine's Asia) is open the
Pine tracks the session high/low. When the session closes it builds a 50-row volume profile over
[low, high]: each session bar's volume is spread evenly across the price rows the bar's range spans,
and the row that accumulated the most volume is the POINT OF CONTROL. Its mid-price is the "MV" line
— a magnet/level the bot watches. Only the POC price is consumed downstream; the histogram itself is
a drawing and is dropped (see below).

    range      = sessionHigh - sessionLow
    per bar b:  rLo = clamp(floor((low_b  - sessionLow)/range*50), 0, 49)
                rHi = clamp(ceil ((high_b - sessionLow)/range*50) - 1, 0, 49)
                span = max(1, rHi - rLo + 1);  add volume_b/span to every row in [rLo, rHi]
    POC row    = argmax over rows of (bull volume + bear volume), first max wins (strict >)
    POC price  = sessionLow + (pocRow + 0.5) * (range / 50)

--------------------------------------------------------------------------------------------------
COMPOSES THE SESSIONS ENGINE for Asia detection (same pattern as engines/liquidity/)
--------------------------------------------------------------------------------------------------
The Asia session window, its running high/low and its open/close edges are NOT recomputed here — they
come from the canonical engines/sessions/ engine, which this engine composes and drives internally.
Pine's own svp_hi/svp_lo/svp_startBar (2592-2602) are exactly the sessions engine's Asia SessionRange
(first in-session bar's H/L, expanded each bar, finalized on the close edge — Pine-parity-validated
there). On the bar Asia closes we get that finalized range and replay the session's bars to build the
profile.

--------------------------------------------------------------------------------------------------
TWO PINE QUIRKS PORTED EXACTLY
--------------------------------------------------------------------------------------------------
1. The profile INCLUDES the close bar. Pine's `svp_sLen = bar_index - svp_startBar + 1` and its loop
   `for b = 0 to svp_sLen-1` reach from the close bar (the first OUT-of-session bar, b=0) back to the
   session's first bar — so the bar the session closes ON is folded into the profile even though it is
   outside the session window. We replicate this by appending the current (close) bar to the buffered
   session bars before binning.
2. Newest-first, two-array summation. Pine walks b=0 (newest) → older and keeps bull volume
   (`close>=open`) and bear volume in SEPARATE arrays, summed into the row total only at the end. We
   keep that exact structure and order (not to draw the up/down colours — that drawing is dropped —
   but because float addition is not associative: collapsing the two arrays or reversing the order
   could flip a near-tie POC row and break the exact-price parity).

--------------------------------------------------------------------------------------------------
VOLUME + TIMEFRAME
--------------------------------------------------------------------------------------------------
Like VWAP, this engine needs the bar's VOLUME (for XAUUSD, tick volume — what Pine's `volume` reads).
It is an intraday feature: Pine gates the whole block on `timeframe.isintraday`, and the Asia window
is a sub-day session, so feed intraday bars (the parity run is 5m). A bar with na volume contributes
nothing.
"""

from __future__ import annotations

import math
from collections import deque
from typing import List, Optional, Tuple

from sessions import SessionEngine, SessionSpec

from .types import SvpEvents

# Asia session window the Pine SVP block keys off (SVP_SESSION / SVP_TZ, mpc lines 4863-4864) — the
# same window the sessions engine's Asia tracker already validates.
# Re-synced 2026-07-31 from "2000-0500"/"GMT-4". **This is a pure re-expression, not a behaviour
# change:** Japan has no DST and GMT-4 is a fixed offset, so both forms are 00:00-09:00 UTC in every
# season. It is restated in the Pine's new words so a future diff against mpc reads clean. The other
# two mpc sessions (London, New York) DID move in the same paste — see engines/sessions/CLAUDE.md —
# which is why liquidity is stale and this engine is not.
_ASIA_SPEC = SessionSpec.from_pine("Asia", "0900-1800", "Asia/Tokyo")

_SVP_ROWS = 50  # Pine svpRows — fixed row count of the profile (was 100 pre-2026-07-08); held to the Pine by engines/tests/
_SVP_HISTORY = 2  # svpHistory input default (mpc line 224) — FIFO cap on kept POCs
# Pine caps the replay at `math.min(svp_sLen - 1, 1490)`, i.e. the newest 1491 bars of the session.
# On a 5m feed the Asia session is ~108 bars so this never bites, but it is ported for fidelity.
_SVP_BAR_CAP = 1491

# One buffered session bar: (open, high, low, close, volume).
_Bar = Tuple[float, float, float, float, Optional[float]]


def range_poc(bars, low: float, high: float, rows: int = _SVP_ROWS) -> Optional[float]:
    """The POINT OF CONTROL of any price range: the mid-price of its highest-volume row.

    `bars` is chronological `(open, high, low, close, volume)`; each bar's volume is spread evenly
    over the rows its high/low span, and the first (lowest) row wins a tie. This is the SAME
    arithmetic the Asia profile uses — `_build_profile` calls it — so a consumer that needs a
    profile over another range (a structure leg, a day) reads it here rather than building a
    second one. None for a range with no height.

    ⚠ Walked NEWEST-FIRST with bull and bear volume in separate arrays, summed only at the end.
    That is Pine's order, and float addition is not associative, so it is what keeps a near-tie
    POC row on the parity gate's side (quirk #2 in this package's CLAUDE.md).
    """
    rng = high - low
    if rng <= 0:
        return None
    row_up = [0.0] * rows
    row_dn = [0.0] * rows
    for o, h, l, c, v in reversed(bars):
        vol = v if v is not None else 0.0
        bull = c >= o
        r_lo = max(0, min(math.floor((l - low) / rng * rows), rows - 1))
        r_hi = max(0, min(math.ceil((h - low) / rng * rows) - 1, rows - 1))
        span = max(1, r_hi - r_lo + 1)
        per_row = vol / span
        for r in range(r_lo, r_hi + 1):
            if bull:
                row_up[r] += per_row
            else:
                row_dn[r] += per_row
    max_vol = 0.0
    poc_row = 0
    for r in range(rows):
        rv = row_up[r] + row_dn[r]
        if rv > max_vol:  # strict > -> first (lowest) row wins a tie
            max_vol = rv
            poc_row = r
    return low + (poc_row + 0.5) * (rng / rows)


class SvpEngine:
    """Streaming Session Volume Profile (Asia POC / MV line).

    Build one per symbol/timeframe and feed it one closed intraday bar at a time, in order. It
    composes and drives its own sessions engine for the Asia session edges + range, buffers the
    session's bars, and on each Asia close resolves the POC and tracks the MV confirmation.

    Public output per bar is an SvpEvents (see types.py): the current POC, whether one formed this
    bar, and the sweep state/edge — all Pine-validated.
    """

    def __init__(
        self, history: int = _SVP_HISTORY, session_engine: Optional[SessionEngine] = None
    ) -> None:
        # Compose a sessions engine tracking only Asia (the one window SVP needs). Injectable so a
        # consumer can share one sessions engine if it ever wants to.
        self._sessions = (
            session_engine if session_engine is not None else SessionEngine(sessions=[_ASIA_SPEC])
        )
        self._buffer: List[_Bar] = []  # this Asia session's bars, chronological
        self._poc_px: "deque[float]" = deque(maxlen=history)  # recent POCs, FIFO (Pine svp_poc_px)
        self._swept = False  # Pine mv_swept

    # ------------------------------------------------------------------
    def update(
        self,
        index: int,
        timestamp_ms: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: Optional[float],
    ) -> SvpEvents:
        """Feed one closed bar: its index, UTC open time (epoch milliseconds, == Pine `time`), the
        bar's open/high/low/close, and its volume. Returns this bar's SvpEvents."""
        ev = SvpEvents()

        # Drive the composed sessions engine — it owns the Asia window, its running H/L and the
        # open/close edges (Pine svpNew / inSVP / svpEnd, and svp_hi/svp_lo/svp_startBar).
        sess = self._sessions.update(index, timestamp_ms, high, low)
        asia_closed = next((r for r in sess.closed if r.name == "Asia"), None)

        # Buffer the session's bars. Start fresh on the open edge, append every in-session bar.
        svp_new = "Asia" in sess.opened  # Pine svpNew — first bar of a new Asia session
        if svp_new:
            self._buffer = []
        if sess.in_asia:
            self._buffer.append((open_, high, low, close, volume))

        svp_end = asia_closed is not None
        if svp_end:  # Asia just closed → build the profile
            self._build_profile(index, asia_closed, (open_, high, low, close, volume), ev)
            self._buffer = []

        # ── MV slot (mpc 2772-2786): the current POC is always the most recent one. ──
        poc = self._poc_px[-1] if self._poc_px else None
        ev.poc = poc
        if poc is not None and not self._swept and high >= poc and low <= poc:
            self._swept = True
            ev.confirmed = True
        if svp_new:  # reset on the NEXT Asia OPEN (Pine svpNew, not
            self._swept = False  # svpEnd) — the confirmed/swept state now
            ev.confirmed = False  # persists all day until the next session opens
        ev.swept = self._swept
        return ev

    # ------------------------------------------------------------------
    def _build_profile(self, index: int, rng, close_bar: _Bar, ev: SvpEvents) -> None:
        """Resolve the POC for the just-closed Asia session (Pine 2604-2650). `rng` is the sessions
        engine's finalized Asia SessionRange (== Pine svp_hi/svp_lo/svp_startBar); `close_bar` is the
        current out-of-session bar, which Pine folds into the profile (quirk #1)."""
        svp_lo, svp_hi = rng.low, rng.high
        svp_range = svp_hi - svp_lo
        if svp_range <= 0:  # Pine `if svp_range > 0` guard (degenerate day)
            return

        # profile_bars == the whole session plus the close bar, chronological; == svp_sLen entries.
        profile_bars = self._buffer + [close_bar]
        svp_slen = index - rng.start_index + 1  # Pine bar_index - svp_startBar + 1
        window = profile_bars[-min(svp_slen, _SVP_BAR_CAP) :]  # newest 1491 bars (Pine cap)

        poc_px = range_poc(window, svp_lo, svp_hi)
        self._poc_px.append(poc_px)  # deque(maxlen) == Pine shift-then-push FIFO
        ev.formed = True

    # ------------------------------------------------------------------
    def poc(self) -> Optional[float]:
        """The current Asia POC / MV line (state read); None until the first session profile forms."""
        return self._poc_px[-1] if self._poc_px else None
