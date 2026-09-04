"""
session_volume_profile/ — the Session Volume Profile (SVP) engine subsystem.

Turns the bar stream into the Asia session POINT-OF-CONTROL — the "MV" line — plus its confirmation.
On each Asia session (0900-1800 Asia/Tokyo) close the engine builds a 50-row volume profile over the
session's range, spreading each bar's volume across the rows its high/low span, and reports the
mid-price of the highest-volume row as the POC. Ported line-by-line from the SESSION VOLUME PROFILE
block in indicators/engines/mpc_jarvis.pine (line ~2554) plus its confirmation-table "MV slot" (line
~2772).

Composes engines/sessions/ for the Asia window/edges (the same pattern engines/liquidity/ uses), and
— like engines/vwap/ — needs the bar's VOLUME. Emits events (the POC value + form/sweep edges), never
the histogram drawing.

Public API:
    from session_volume_profile import SvpEngine, SvpEvents

    sv = SvpEngine()                     # Pine defaults: Asia 0900-1800 Asia/Tokyo, 50 rows, keep 2 POCs
    # each closed intraday bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
    ev = sv.update(bar.index, bar.timestamp_ms, bar.open, bar.high, bar.low, bar.close, bar.volume)
    ev.poc         # the current Asia POC / MV line (None until the first session closes)
    ev.formed      # did a fresh POC form this bar (Asia just closed)? (edge)
    ev.swept       # has the current POC been tapped since it formed? (state)
    ev.confirmed   # did price tap the POC for the first time this bar? (edge)
"""

from .engine import SvpEngine
from .types import SvpEvents

__all__ = [
    "SvpEngine",
    "SvpEvents",
]
