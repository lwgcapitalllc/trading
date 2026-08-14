"""
market_structure/types.py — plain data containers for the structure engine.

No behavior lives here. See engine.py for the state machine that produces these.

Every field pair below (`<name>` / `<name>_price` / `<name>_index`) corresponds to exactly one
`label.new(...)` call in indicators/engines/structure_engine.pine — see the mapping table in
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

    # The full impulse LEG of the break — both endpoints of the move that broke, fired on the
    # break bar only (None otherwise). For a bull BOS: high = the ASH that broke, low = the swing
    # low the impulse launched from; for a bear BOS: low = the ASL that broke, high = the swing
    # high it launched from. The `_loc` fields are the bar index of each endpoint. These are what
    # the Sniper-fib anchor needs (0.382–0.5 zone drawn across this leg) — the plain bull_bos_price
    # above is only the broken level, not the leg. Ported from structure_engine.pine's
    # bull_bos_high/h_loc/low/l_loc + bear mirror (the port originally dropped them).
    bull_bos_high: Optional[float] = None
    bull_bos_h_loc: Optional[int] = None
    bull_bos_low: Optional[float] = None
    bull_bos_l_loc: Optional[int] = None
    bear_bos_high: Optional[float] = None
    bear_bos_h_loc: Optional[int] = None
    bear_bos_low: Optional[float] = None
    bear_bos_l_loc: Optional[int] = None

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
    #
    # On an SOS the mid-pullback extreme promoted by the break is NOT confirmed — it becomes the
    # new active swing and is classified by the NEXT break in that direction. Those bars carry
    # "ASH"/"ASL" instead of a confirmed label. Consumers keying off "HH"/"LH"/"HL"/"LL" must
    # treat "ASH"/"ASL" as "not yet classified", not as an unknown value.
    broken_high_label: Optional[str] = None   # "HH" | "LH" | "ASH"
    broken_high_price: Optional[float] = None
    broken_high_index: Optional[int] = None
    broken_low_label: Optional[str] = None    # "HL" | "LL" | "ASL"
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

    # The BAR the broken level sits on — the wick that made `*_bos_price` / `*_sos_price`. The
    # external engine has carried this since it was written (`bull_bos_h_loc` / `bear_bos_l_loc`);
    # the internal engine emitted the four prices with no bar beside them, so a consumer that
    # needed to DRAW a break had nothing to anchor it to and reached for `ifib_seed_*_loc` instead.
    #
    # 🔴 **That substitution is wrong at exactly ONE of the six break sites, and it went unnoticed
    # because the other five agree by coincidence.** The fib seed is a LEG (a low and a high), and
    # at five sites the end of that leg happens to be the level that broke. At the first bear-iSOS
    # branch it is not: the break is `i_last_hl` while the seed's bottom is `i_tracked_ext` — a
    # different price on a different bar. MEASURED over 2.5 years of real M5 bars (169 internal
    # breaks): iBOS bull 65/65, iBOS bear 57/57 and iSOS bull 22/22 land on the broken wick, while
    # **iSOS bear is 3/25** — 22 drawn at a price that is not the level that broke, by up to
    # $18.47. Reported by Aaron off the chart, and the visible symptom is not the price: the wrong
    # bar can land ON the break bar, so the line has ZERO LENGTH and does not render at all
    # (12.4% of all internal breaks drew a line 1 bar or shorter).
    #
    # ⚠ **`int_break_origin_loc` is NOT this and cannot substitute for it** — it is the
    # order-block scan origin, and measured over the same 169 breaks it lands on the broken wick
    # **zero** times in every category.
    #
    # Capture-only: nothing in the engine reads these back, so no structure decision depends on
    # them — the same additive pattern as `int_break_origin_loc`, `i_confirmed_*` and
    # `ifib_seed_*` above. None off the break bar.
    bull_bos_loc: Optional[int] = None
    bear_bos_loc: Optional[int] = None
    bull_sos_loc: Optional[int] = None
    bear_sos_loc: Optional[int] = None

    # Order-block creation gate for the INTERNAL engine — mirrors mpc_assistant.pine's
    # int_bull_break / int_bear_break / int_break_origin_loc (~lines 1115-1275). These fire on the
    # same bar as bull_bos/bear_bos/bull_sos/bear_sos, but are kept as separate fields because the
    # OB anchor is a distinct location from the break price: int_break_origin_loc is the bar the
    # order_blocks engine scans back from to find the OB candle — i_tracked_ext_loc on an iBOS,
    # i_sw_loc on an iSOS. None off the break bar. Consumed only by order_blocks/ (not the fibs).
    int_bull_break: bool = False
    int_bear_break: bool = False
    int_break_origin_loc: Optional[int] = None

    # Latest CONFIRMED internal swing point (price + bar loc), captured on the bar an iSH/iSL
    # confirms — mpc_assistant.pine's `i_confirmed_high_price/loc` (set at the iSH confirm, ~line
    # 1299) and `i_confirmed_low_price/loc` (iSL confirm, ~line 1350). Consumed by the External
    # ("Structure") fib only, which adopts a more-extreme internal swing as its pull anchor. Fired
    # on the confirm bar only (None otherwise); the consumer latches + resets them (Pine keeps them
    # as a top-level `var` reset by the fib's origin change). Capture-only — no structure logic
    # depends on them, same additive pattern as int_break_origin_loc above.
    i_confirmed_high_price: Optional[float] = None
    i_confirmed_high_loc: Optional[int] = None
    i_confirmed_low_price: Optional[float] = None
    i_confirmed_low_loc: Optional[int] = None

    # Internal-Fib SEED — the anchor pair (low + high + direction) of the internal leg that just
    # broke, emitted on the bar an iBOS/iSOS fires (None off the break bar). Mirrors
    # mpc_assistant.pine's `iFib_asl/asl_loc/ash/ash_loc/dir` assignments at the six internal-break
    # sites (bull/bear iBOS + the four iSOS branches). Consumed by the new Internal fib, which runs
    # its own live-extend + touch machine off this seed. Capture-only exposure of state the internal
    # engine already computes at break time, before the state reset — same pattern as
    # int_break_origin_loc. `ifib_seed_dir` is 1 (bull leg) or -1 (bear leg) on the break bar.
    ifib_seed_dir: Optional[int] = None
    ifib_seed_asl: Optional[float] = None
    ifib_seed_asl_loc: Optional[int] = None
    ifib_seed_ash: Optional[float] = None
    ifib_seed_ash_loc: Optional[int] = None


@dataclass
class StructureEvents:
    external: ExternalEvents
    internal: InternalEvents
