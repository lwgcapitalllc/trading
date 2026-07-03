"""
market_structure/types.py — plain data containers for the structure engine.

No behavior lives here. See engine.py for the state machine that produces these.

Every field pair below (`<name>` / `<name>_price` / `<name>_index`) corresponds to exactly one
`label.new(...)` call in indicators/structure_engine.pine — see the mapping table in
MARKET_STRUCTURE_ENGINE.md for the full label-text -> field cross-reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Bar:
    index: int
    open: float
    high: float
    low: float
    close: float


@dataclass
class SwingLevel:
    """A price level tracked by either engine (ASH/ASL externally, iSH/iSL internally).

    `locked` mirrors Pine's `ash_type == "LOCKED"` / `asl_type == "LOCKED"` — True once the
    level was produced by pullback confirmation (or, for the external engine, promoted
    immediately by an opposing break mid-pullback) rather than by a raw pivot/seed/scan. Note
    that the mid-pullback promotion locks the level but does NOT raise `new_swing_high`/
    `new_swing_low` in ExternalEvents — see the note on those fields.
    """
    price: float
    index: int
    locked: bool = False


@dataclass
class ExternalEvents:
    """One entry per external-structure label Pine can draw on a given bar. All *_price /
    *_index fields are None unless the corresponding bool/label field is truthy this bar."""

    # BOS / CHoCH ("BOS" or "SOS" text) — a body close beyond the active swing level.
    bull_bos: bool = False
    bull_bos_price: Optional[float] = None    # the ASH level that broke
    bull_sos: bool = False                    # True only when the break also flips the trend (CHoCH)
    bear_bos: bool = False
    bear_bos_price: Optional[float] = None    # the ASL level that broke
    bear_sos: bool = False

    # New swing high/low, pullback-confirmed (locked) — Pine's "ASH"/"ASL" text with
    # ash_type/asl_type == "LOCKED", solid line. Fires ONLY via a normal 3-qualifying-candle
    # pullback confirmation (Pine lines 174 / 216). It does NOT fire on break-promotion (when an
    # opposing break locks an in-progress pullback mid-way — see engine.py
    # _on_ash_broken/_on_asl_broken): Pine draws that promoted swing's line + HH/LH/HL/LL label
    # but never sets this flag there, because it is the signal that seeds the internal engine,
    # and Pine deliberately seeds internal only off clean pullback-confirmed swings. Matching
    # that exactly is what closed the last Pine↔Python parity gap on the XAUUSD-15m export.
    new_swing_high: bool = False
    new_swing_high_price: Optional[float] = None
    new_swing_high_index: Optional[int] = None
    new_swing_low: bool = False
    new_swing_low_price: Optional[float] = None
    new_swing_low_index: Optional[int] = None

    # A fresh but *unconfirmed* ASH/ASL candidate — Pine's "ASH"/"ASL" text with
    # ash_type/asl_type == "", dashed line. Fires on initial bootstrap seed, on the
    # opposite-side bootstrap scan, when an unconfirmed swing floats up to a bigger pivot
    # before any break has occurred, and on the bounded rescan right after a break (before
    # pullback locks the new side).
    unconfirmed_high_set: bool = False
    unconfirmed_high_price: Optional[float] = None
    unconfirmed_high_index: Optional[int] = None
    unconfirmed_low_set: bool = False
    unconfirmed_low_price: Optional[float] = None
    unconfirmed_low_index: Optional[int] = None

    # Reclassification fired on the swing that just broke: "HH"/"LH" (a high) or "HL"/"LL"
    # (a low). This is a *label*, distinct from the BOS/SOS break label above, even though
    # both fire on the same bar and often at the same price.
    broken_high_label: Optional[str] = None   # "HH" | "LH"
    broken_high_price: Optional[float] = None
    broken_high_index: Optional[int] = None
    broken_low_label: Optional[str] = None    # "HL" | "LL"
    broken_low_price: Optional[float] = None
    broken_low_index: Optional[int] = None


@dataclass
class InternalEvents:
    """One entry per internal-structure label Pine can draw on a given bar. All *_price /
    *_index fields are None unless the corresponding bool/label field is truthy this bar."""

    # New internal swing high/low, pullback-confirmed — "iSH"/"iHH" or "iSL"/"iLL" text.
    # NOTE: swing_high_label is only ever "iSH" (first swing since seeding) or "iHH" (every
    # swing after) — it never becomes "iLH" despite the source's comment implying it should;
    # same for swing_low_label, which never becomes "iHL". This is a bug in the *original*
    # Pine source (mpc_assistant.pine), ported faithfully. See engine.py for the exact lines.
    new_swing_high: bool = False
    new_swing_high_price: Optional[float] = None
    new_swing_high_index: Optional[int] = None
    swing_high_label: Optional[str] = None    # "iSH" | "iHH" (never "iLH" — see NOTE above)
    new_swing_low: bool = False
    new_swing_low_price: Optional[float] = None
    new_swing_low_index: Optional[int] = None
    swing_low_label: Optional[str] = None     # "iSL" | "iLL" (never "iHL" — see NOTE above)

    # iBOS ("iBOS" text) — internal continuation break.
    bull_bos: bool = False
    bull_bos_price: Optional[float] = None
    bear_bos: bool = False
    bear_bos_price: Optional[float] = None

    # The pullback low/high being tracked at the moment an iBOS fires gets classified and
    # labeled here — "iHL" text alongside a bullish iBOS, "iLH" text alongside a bearish one.
    # This is the label that was previously dropped entirely by the port (see CLAUDE.md).
    demoted_low_label: Optional[str] = None   # "iHL"
    demoted_low_price: Optional[float] = None
    demoted_low_index: Optional[int] = None
    demoted_high_label: Optional[str] = None  # "iLH"
    demoted_high_price: Optional[float] = None
    demoted_high_index: Optional[int] = None

    # iSOS ("iSOS" text) — internal change-of-character (watches the last iHL/iLH, or a
    # second-level watched extreme after a prior iSOS). Pine draws all four watch-branches
    # with the same "iSOS" text; only the price differs, which is what this field captures.
    bull_sos: bool = False
    bull_sos_price: Optional[float] = None
    bear_sos: bool = False
    bear_sos_price: Optional[float] = None


@dataclass
class StructureEvents:
    external: ExternalEvents
    internal: InternalEvents
