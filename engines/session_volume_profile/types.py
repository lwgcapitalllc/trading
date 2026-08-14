"""
session_volume_profile/types.py — plain data container for the Session Volume Profile (SVP) engine.

One container, no behaviour:

  SvpEvents — the engine's per-bar OUTPUT: the current Asia session POC (point-of-control) price
    — the "MV" line — whether a fresh POC formed on this bar (the Asia session just closed), and the
    MV confirmation state/edge (has price tapped the POC since it formed).

WHAT IS PINE-VALIDATED
----------------------
All four fields are ported from indicators/engines/mpc_assistant.pine and checked at Pine parity:
  * `poc` + `formed` come from the SESSION VOLUME PROFILE block (line ~2554): the POC price the
    profile resolves on each Asia session close, and the FIFO history it is pushed into (`mv_pocPrice`
    always reads the most recent).
  * `swept` + `confirmed` come from the confirmation-table "MV slot" (line ~2772): `mv_swept` /
    `mv_status = "Confirmed"` — price straddling the POC, reset when the next Asia session closes.
Unlike the VWAP engine (whose cross was a derived add-on), every SVP field has a Pine counterpart, so
there is no derived-vs-validated split here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SvpEvents:
    """The SVP engine's per-bar output.

    poc       — the current Asia POC price (the "MV" line): the most recent finalized session
                point-of-control. None until the first full Asia session inside the feed closes
                (Pine `na` mv_pocPrice). Persists between sessions until the next POC forms.
    formed    — did a NEW Asia POC finalize on this bar? True only on the bar the Asia session closes
                with a non-degenerate range (edge). `poc` carries the new value on this bar.
    swept     — has the current POC been tapped (a bar straddled it: high >= poc and low <= poc)
                since it formed? State; resets to False on each Asia session close (Pine mv_swept).
    confirmed — did the current POC get tapped for the FIRST time on this bar (edge)? Mirrors the
                mv_status "Confirmed" transition. False on the bar a POC forms (the close-bar reset
                wins, exactly as in the Pine source).
    """

    poc: Optional[float] = None
    formed: bool = False
    swept: bool = False
    confirmed: bool = False
