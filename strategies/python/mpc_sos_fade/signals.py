"""SignalAdapter — turns a replay `BarState` into the exact Pine-named inputs the
A+ sequence and execution layers read.

The A+ block in `mpc_strategy.pine` does not read the engines directly; it reads a
set of derived globals (`st.bull_sos`, `recentSSL`/`recentSSL_bar`, `fibo_dir`,
`fiboP1..P10`, `fiboHalfReached`, `bullDivActive`, `longVeto`, `nyHour`, …). Those
globals are computed in the indicator body from the engine outputs. This adapter
reproduces exactly that computation, so `sequence.py` / `execution.py` can be a
line-for-line port that reads Pine names.

Two computations here are NON-trivial and must stay faithful:

1. **recentSSL / recentBSL** (mpc_strategy.pine 3324-3373 + 3606-3636) — the "most
   recent swept liquidity pool" on each side, resolved from ten per-source swept
   slots (H4 / Day / Asia / London / NY high & low) by *latest sweep bar*, with the
   session slots suppressed once the Day slot is filled. Stateful: each slot latches
   on the bar its level is swept and holds until re-swept (H4 also clears each new H4
   bar). Rebuilt here from `LiquidityEvents.mitigated` / `.evicted`.

2. **bullDivActive / bearDivActive / longVeto / shortVeto** (1941-1954) — the Pine's
   `bullDivActive` is STRICTER than the RSI engine's convenience `bull_active`: it
   also requires `not bullDivStale`, i.e. no external structure break AND no opposite
   divergence has confirmed since the divergence's pivot. The standalone RSI engine
   cannot know about structure breaks, so we recompute the active flags here from the
   raw pivot bars + `lastExtBreakBar` (tracked off structure), never from the engine's
   `bull_active`.

The adapter is a streaming state machine (like the engines): feed one `BarState` per
`update()`, in order.
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Signals:
    """One bar's worth of Pine-named inputs — the seam the A+ layers read."""

    index: int
    time_ms: int
    open: float
    high: float
    low: float
    close: float
    session_gap_bar: bool          # Pine sessionGapBar
    ny_hour: int                   # Pine nyHour (America/New_York)

    # structure (st.*)
    bull_sos: bool
    bear_sos: bool
    bull_bos: bool
    bear_bos: bool

    # liquidity — most-recent swept pool per side (name + bar it was swept on)
    recent_ssl: str                # "" | "H4 Low" | "Day Low" | "Asia Low" | "Ldn Low" | "NY Low"
    recent_ssl_bar: Optional[int]
    recent_ssl_time: Optional[int]  # ms the winning pool was swept (for the daily-too-old check)
    recent_bsl: str                # mirror on the high side
    recent_bsl_bar: Optional[int]
    recent_bsl_time: Optional[int]

    # RSI divergence
    last_bull_div_bar: Optional[int]
    last_bear_div_bar: Optional[int]
    bull_div_active: bool
    bear_div_active: bool
    veto_on: bool                  # showDiv and divVeto — the veto is switched on at all
    veto_rsi_ob: bool              # divRsi >= divExtremeOB (blocks longs, LIVE, never exempt)
    veto_rsi_os: bool              # divRsi <= divExtremeOS (blocks shorts)

    # Structure fib
    fibo_dir: int
    fibo_p1: Optional[float]        # 0.382
    fibo_p2: Optional[float]        # 0.5
    fibo_p3: Optional[float]        # 0.618 (E1)
    fibo_p4: Optional[float]        # 0.702
    fibo_p5: Optional[float]        # 0.786
    fibo_p6: Optional[float]        # 0.886
    fibo_p7: Optional[float]        # 0.0  (swing extreme / TP3)
    fibo_p10: Optional[float]       # 1.0  (leg origin)
    # The leg anchors the fiboP* above were built from (Pine fibo_ash / fibo_asl). Only the
    # Custom SL level reads them, to price a ratio that has no fiboP* of its own. None on the
    # same bars every fiboP* is None, which is what keeps a Custom stop on the same leg as the
    # entry — Pine gets that for free by assigning fiboPSl inside the fib block; here it comes
    # from the engine reporting the anchors only on its active path.
    fibo_ash: Optional[float]       # swing HIGH anchor
    fibo_asl: Optional[float]       # swing LOW anchor
    fibo_half_reached: bool
    fibo_618_ever_reached: bool
    fibo7_touched: bool

    # active FVGs overlapping consideration — (top, bottom, is_bullish, born_index).
    # `born_index` is the bar the gap PRINTED, read only by the `exec_fvg_pre_zone` gate
    # (Pine's parallel `fvgBorn` array). It shares an origin with `index` and with
    # `fibo_half_bar` below — every comparison is between two bars of the SAME run, so the
    # origin itself never matters (which is what keeps this safe against a partial export).
    fvgs: List[Tuple[float, float, bool, int]] = field(default_factory=list)

    # Live ORDER BLOCKS, in the IDENTICAL shape as `fvgs` above — (top, bottom, is_bullish, born)
    # — so `exec_poi_source` can hand either list to the same confluence and entry-edge loops
    # without a second implementation of the rules. See `pois_for()`.
    #
    # ⚠ `born` is the block's **created_index**, not its origin candle: the anchor can be ~10 bars
    # older than the bar the engine can first report it on, and the `exec_fvg_pre_zone` gate asks
    # whether the zone was ALREADY THERE when price arrived. Answering with the anchor bar would
    # credit a setup with a zone nothing could yet have seen.
    obs: List[Tuple[float, float, bool, int]] = field(default_factory=list)

    # Did the ORDER-BLOCK ENGINE actually run this bar? `False` = the stack was built without it,
    # so `obs` being empty means THE QUESTION WAS NEVER ASKED — not "there are no blocks".
    # `pois_for()` refuses on that combination rather than silently trading as if FVG-only, which
    # is this repo's standing rule that "no" and "cannot ask" must never be the same value. It
    # defaults False so a hand-built Signals in a test cannot accidentally claim coverage.
    obs_available: bool = False

    # The bar price first tagged 0.5 on THIS leg (Pine `fiboHalfBar`) — i.e. the bar price
    # entered the entry zone. Latched once and reset with the leg, exactly like
    # `fibo_half_reached`, so it is scoped to the same fib whose band a gap is judged against.
    # `None` = price has not reached the zone yet, which makes `exec_fvg_pre_zone` inert
    # (every gap trivially pre-dates a moment that has not happened). It defaults None rather
    # than being required so a hand-built Signals in a test gets that inert behaviour.
    fibo_half_bar: Optional[int] = None

    # Macro-fib POI (confluence flag only; on at <=5m)
    poi_long_now: bool = False
    poi_short_now: bool = False

    # HTF established-context (only read when an HTF toggle is on; "" = neutral/off)
    w_est_state: str = ""
    d_est_state: str = ""
    w_est_desc: str = ""
    d_est_desc: str = ""

    # Structure break-leg endpoints (st.bull_bos_high/low + bear mirror) — the 0.0/1.0
    # anchors of the leg an SOS broke. The A+ path does not read them (so they cannot move
    # compare_strategy.py); the B-LEG bot's band-freeze reads them off each SOS bar.
    bull_bos_high: Optional[float] = None
    bull_bos_low: Optional[float] = None
    bear_bos_high: Optional[float] = None
    bear_bos_low: Optional[float] = None

    # The TIMES of those four endpoints (`st.bull_bos_h_loc` / `l_loc` + bear mirror), epoch ms.
    # REPORTING ONLY, on the same footing as `fibo_ash_ms`/`fibo_asl_ms` below and for the same
    # reason: the B-LEG bot prices its whole trade off a fib on this leg, and the lab's chart draws
    # that fib from the bar the leg STARTED on — which two prices cannot say. No decision reads
    # them on either bot, so they cannot move `compare_strategy.py` or `compare_bleg.py`.
    # ⚠ Times, deliberately not bar INDICES — see the note on `fibo_ash_ms`.
    bull_bos_high_ms: Optional[int] = None
    bull_bos_low_ms: Optional[int] = None
    bear_bos_high_ms: Optional[int] = None
    bear_bos_low_ms: Optional[int] = None

    # The Sniper Zone — the 0.382-0.5 pocket of the break leg, re-anchored on every BOS
    # (Pine sniperZoneTop / sniperZoneBot / sz_bar / sz_bullish). The A+ path does not read
    # them (`exec_conf_sz` is unported there), so they cannot move compare_strategy.py; the
    # BOS bot's entry ladder uses the zone to price a leg that had no qualifying FVG.
    sniper_zone_top: Optional[float] = None
    sniper_zone_bot: Optional[float] = None
    sz_bar: Optional[int] = None       # the bar the current zone was anchored on
    sz_bullish: bool = True            # Pine seeds `var bool sz_bullish = true`

    # Last CONFIRMED external swing high/low (Pine st.last_conf_high / st.last_conf_low) — the
    # anchor the STRUCTURE runner trail rides (`exec_runner_trail == "Structure (swing)"`).
    # Read only by `Execution._advance_stage` once a trade is past TP2, so with the trail on
    # "Fixed step" nothing in the decision stream touches them.
    last_conf_high: Optional[float] = None
    last_conf_low: Optional[float] = None

    # The TIMES of the two leg anchors above (`fibo_ash` / `fibo_asl`), in epoch ms. REPORTING
    # ONLY — no decision reads them, so they are parity-safe in the same way `Trade.mfe_usd` is.
    # They exist because a fib is a leg, not just a price ladder: the lab's price chart draws each
    # trade's own fib from the bar the leg STARTED on, and two prices cannot say where that is.
    # ⚠ Times, deliberately not bar INDICES. An index is relative to the window that produced it,
    # and this repo has already been bitten once by diffing a Pine `bar_index` across two windows
    # (`strategies/CLAUDE.md` → the B-LEG harness bug). A timestamp survives being shipped to a
    # chart that trimmed its candles. None on the same bars `fibo_ash`/`fibo_asl` are None.
    fibo_ash_ms: Optional[int] = None
    fibo_asl_ms: Optional[int] = None

    # HTF liquidity levels usable as a SCALE-IN TARGET — the Pine `w_hPrice` / `w_lPrice`,
    # `d_hPrice` / `d_lPrice` and `h4TrackHigh` / `h4TrackLow` variables, mirrored by name.
    #
    # 🔴 Mirrored as NAMED SCALARS rather than handed over as the engine's `active` list, and
    # that is a parity decision rather than a style one. Pine holds exactly these six variables;
    # a Python side that instead searched "the nearest active level" would be free to pick a
    # level Pine has no variable for, and the two would diverge on a bar neither implementation
    # looks wrong on. Mirror the variable, not the concept.
    #
    # Each carries the level's price only while it EXISTS and is still UNMITIGATED; None
    # otherwise. A mitigated level is one price has already taken, so it is no longer somewhere
    # to bank against — and `None` here means "no level to aim at", which is the same thing a
    # fresh run says before its first week has completed. Nothing but `exec_scale_tp_mode`
    # reads them, so with that input on "Ride" they cannot move `compare_strategy.py`.
    liq_w_high: Optional[float] = None
    liq_w_low: Optional[float] = None
    liq_d_high: Optional[float] = None
    liq_d_low: Optional[float] = None
    liq_h4_high: Optional[float] = None
    liq_h4_low: Optional[float] = None


# Pine fib level name -> the engine's `levels` dict key (see fibonacci/engine.py _RATIO).
# Prices coincide where a retrace and a target share a ratio (0.5, 0.382), so the key
# is unambiguous.
_FIB_KEY = {
    "p1": "TP2",    # 0.382
    "p2": "TP1",    # 0.5
    "p3": "E1",     # 0.618
    "p4": "E2",     # 0.702
    "p5": "E3",     # 0.786
    "p6": "E4",     # 0.886
    "p7": "TP3",    # 0.0
    "p10": "1.0",   # 1.0
}


class _LiqSlot:
    """One swept-liquidity slot (e.g. Day High) — the Pine `liq_dh` string + bar."""

    __slots__ = ("name", "bar", "price", "time")

    def __init__(self) -> None:
        self.name = ""       # "" until swept; then the display name ("Day High")
        self.bar: Optional[int] = None
        self.price: Optional[float] = None
        self.time: Optional[int] = None

    def set(self, name: str, bar: int, price: float, t: int) -> None:
        self.name, self.bar, self.price, self.time = name, bar, price, t

    def clear(self) -> None:
        self.name, self.bar, self.price, self.time = "", None, None, None


class SignalAdapter:
    """Streaming BarState -> Signals adapter. One instance per backtest run."""

    def __init__(self, config) -> None:
        from zoneinfo import ZoneInfo  # stdlib

        self._cfg = config
        self._ny = ZoneInfo("America/New_York")

        # session-gap detector needs the previous two bar timestamps (Pine time[1]/time[2])
        self._prev_time: Optional[int] = None
        self._prev_prev_time: Optional[int] = None

        # Bar index -> that bar's epoch ms, appended once per bar. The ONLY reason it exists is
        # `fibo_ash_ms`/`fibo_asl_ms`: the fib engine reports its leg anchors as bar INDICES, and
        # a consumer downstream of this run needs times. An anchor can sit thousands of bars back,
        # so a bounded window would not do. `array("q")` rather than a list because it is a dense
        # table of one int per bar — 8 bytes each, ~1.2 MB over a 155k-bar replay, against ~5 MB
        # of boxed ints. Reporting-only, like the two fields it feeds.
        self._bar_ms = array("q")

        # liquidity swept slots (Pine liq_* vars): highs -> BSL, lows -> SSL
        self._bsl = {k: _LiqSlot() for k in ("h4", "day", "asia", "london", "ny")}
        self._ssl = {k: _LiqSlot() for k in ("h4", "day", "asia", "london", "ny")}
        # Reconstruction of Pine's per-slot mitigation VARIABLE (`d_lMit` / `h4HighSwept` …),
        # keyed "<slot>_<side>". Pine records a sweep only on `mit and not mit[1]` — a
        # false->true edge measured against the PREVIOUS bar's close. That variable, NOT the
        # level object, is what Pine keys off: it is reset to false only when a fresh level
        # of that slot is CREATED (`d_lMit := false`), set true when the level is taken, and
        # LEFT ALONE when the mitigated level's line is later deleted on the new-day tidy.
        # The engine models levels (create / mitigate / EVICT), so we must mirror that
        # variable ourselves: eviction of a spent level must not drop the state, or a level
        # that rolls and is re-taken on its own creation bar would falsely re-fire the edge.
        # `_slot_mit` = the live variable; `_slot_mit_prev` = its value at the last bar close.
        self._slot_mit: dict = {}
        self._slot_mit_prev: dict = {}

        # divergence / structure-break tracking (Pine lastBullDivBar / lastExtBreakBar)
        self._last_bull_div_bar: Optional[int] = None
        self._last_bear_div_bar: Optional[int] = None
        self._last_ext_break_bar: Optional[int] = None

        # Sniper Zone anchor bar (Pine `var int sz_bar`) — set on the bar a fresh zone is
        # created, i.e. on every BOS. The engine reports the creation as an EVENT, so the
        # bar has to be latched here.
        self._sz_bar: Optional[int] = None

        # Zone-entry bar (Pine `var int fiboHalfBar`) — the bar 0.5 was first tagged on the
        # current leg. Latched here for the same reason as `_sz_bar`: the fib engine reports
        # `half_reached` as a state, not the bar it flipped on.
        self._half_bar: Optional[int] = None

    # ── liquidity helpers ──────────────────────────────────────────────────────
    _HIGH_NAME = {"h4": "H4 High", "day": "Day High", "asia": "Asia High",
                  "london": "Ldn High", "ny": "NY High"}
    _LOW_NAME = {"h4": "H4 Low", "day": "Day Low", "asia": "Asia Low",
                 "london": "Ldn Low", "ny": "NY Low"}

    @staticmethod
    def _liq_key(level) -> Optional[Tuple[str, str]]:
        """Map a LiquidityLevel to (slot_key, side) or None if it's not one of the
        ten A+ pools. side ∈ {"high","low"}."""
        kind = level.kind
        side = level.side  # "high" | "low"
        if kind == "h4":
            return ("h4", side)
        if kind == "daily":
            return ("day", side)
        if kind == "session":
            sn = (level.session_name or "").lower()
            if sn.startswith("asia"):
                return ("asia", side)
            if sn.startswith("london") or sn.startswith("ldn"):
                return ("london", side)
            if sn.startswith("ny") or sn.startswith("new york"):
                return ("ny", side)
        return None

    # The `Signals.liq_*` slot each level kind/side feeds. Session levels are deliberately
    # ABSENT: they measured worst of every family as a scale-in target (Run 22), and Pine holds
    # six separate session variables that would each need mirroring for a target nobody should
    # pick. Adding them later is a Pine change, not just a Python one.
    _TGT_SLOT = {("weekly", "high"): "w_high", ("weekly", "low"): "w_low",
                 ("daily", "high"): "d_high", ("daily", "low"): "d_low",
                 ("h4", "high"): "h4_high", ("h4", "low"): "h4_low"}

    def _target_levels(self, liq_events) -> dict:
        """The still-standing HTF levels, by `Signals.liq_*` slot name.

        Only UNMITIGATED levels are reported: once price has taken a level it is no longer
        somewhere to bank against, and Pine's own `w_hMit` / `d_hMit` / `h4HighSwept` flags gate
        the mirror on the other side. A slot with no live level stays absent, and the caller
        reads that as None — the same answer a run gives before its first week has completed.
        """
        out: dict = {}
        for lvl in liq_events.active:
            if lvl.mitigated:
                continue
            slot = self._TGT_SLOT.get((lvl.kind, lvl.side))
            if slot is not None:
                out[slot] = lvl.price
        return out

    def _update_liquidity(self, index: int, t: int, liq_events) -> None:
        """Reproduce mpc_strategy.pine 3343-3374: latch each source's swept slot on
        the bar it is mitigated, then clear the H4 slots when the H4 level rolls."""
        # 1. Creation resets the slot's mit variable (Pine `d_lMit := false` in the daily-level
        #    recreate block; `h4HighSwept := false` on an H4 roll). Done first, matching Pine's
        #    order (recreate before the mitigation check), so a level created and taken on the
        #    same bar ends the bar mitigated.
        for lvl in liq_events.created:
            key = self._liq_key(lvl)
            if key is not None:
                self._slot_mit[f"{key[0]}_{key[1]}"] = False

        # 2. Mitigation. Record the swept slot ONLY on a genuine false->true edge measured
        #    against the PREVIOUS bar's close (Pine `mit and not mit[1]`). A level that rolls
        #    and is re-taken on its own creation bar has `mit[1]` (the prior bar, the old level)
        #    still true, so no edge fires — the guard below reproduces that. Either way the
        #    variable ends the bar true.
        for lvl in liq_events.mitigated:
            key = self._liq_key(lvl)
            if key is None:
                continue
            slot_key, side = key
            skey = f"{slot_key}_{side}"
            if not self._slot_mit_prev.get(skey, False):
                if side == "high":
                    self._bsl[slot_key].set(self._HIGH_NAME[slot_key], index, lvl.price, t)
                else:
                    self._ssl[slot_key].set(self._LOW_NAME[slot_key], index, lvl.price, t)
            self._slot_mit[skey] = True

        # 3. H4 rolls each new H4 bar -> both H4 slot NAMES reset (Pine 3371-3374): the H4
        #    name is cleared on every roll so recentSSL/BSL ignores it until re-swept. This
        #    is separate from the mit variable above (which the creation reset already handled)
        #    — eviction must NOT touch `_slot_mit`, or the edge state would be lost.
        for lvl in liq_events.evicted:
            key = self._liq_key(lvl)
            if key is not None and key[0] == "h4":
                self._bsl["h4"].clear()
                self._ssl["h4"].clear()

        # 4. Snapshot the mit variable at THIS bar's close, for the next bar's edge test.
        self._slot_mit_prev = dict(self._slot_mit)

    def _resolve_recent(self, slots) -> Tuple[str, Optional[int], Optional[int]]:
        """mpc_strategy.pine 3606-3636 — pick the pool swept on the LATEST bar, in
        priority H4 > Day > (session, only if Day empty) Asia > London > NY."""
        show_sess = slots["day"].name == ""  # Pine showSessH = liq_dh == ""
        name, bar, t = "", -1, None
        order = [("h4", True), ("day", True),
                 ("asia", show_sess), ("london", show_sess), ("ny", show_sess)]
        for k, allowed in order:
            s = slots[k]
            if allowed and s.name != "" and s.bar is not None and s.bar > bar:
                name, bar, t = s.name, s.bar, s.time
        return (name, None if bar < 0 else bar, t)

    # ── main step ───────────────────────────────────────────────────────────────
    def update(self, state) -> Signals:
        bar = state.bar
        index, t = bar.index, bar.timestamp_ms
        o, high, low, c = bar.open, bar.high, bar.low, bar.close

        # Index -> time, for `_bar_time` below. Written by index rather than appended so a caller
        # that steps the same bar twice cannot desync the table from the engine's bar numbering.
        while len(self._bar_ms) <= index:
            self._bar_ms.append(t)
        self._bar_ms[index] = t

        # session-gap bar (Pine 3726-3728): a time jump > 2x the normal spacing
        bar_gap = 0 if self._prev_time is None else t - self._prev_time
        normal_gap = 0 if (self._prev_time is None or self._prev_prev_time is None) \
            else self._prev_time - self._prev_prev_time
        session_gap_bar = normal_gap > 0 and bar_gap > normal_gap * 2

        # NY hour (Pine nyHour = hour(time, "America/New_York")). Bars are UTC epoch-ms.
        from datetime import datetime, timezone
        ny_hour = datetime.fromtimestamp(t / 1000.0, tz=timezone.utc) \
            .astimezone(self._ny).hour

        # structure
        ext = state.snapshot
        bull_sos, bear_sos = ext.bull_sos, ext.bear_sos
        bull_bos, bear_bos = ext.bull_bos, ext.bear_bos
        if bull_sos or bear_sos or bull_bos or bear_bos:
            self._last_ext_break_bar = index  # Pine lastExtBreakBar (1941-1943)

        # liquidity -> recentSSL / recentBSL
        self._update_liquidity(index, t, state.liquidity)
        recent_ssl, recent_ssl_bar, recent_ssl_time = self._resolve_recent(self._ssl)
        recent_bsl, recent_bsl_bar, recent_bsl_time = self._resolve_recent(self._bsl)
        # ...and the same levels again as PRICES, for the scale-in target (see Signals.liq_*).
        # A different question from the one above: `recent_*` asks which pool was last SWEPT,
        # this asks which is still STANDING and therefore still somewhere to aim at.
        liq_tgt = self._target_levels(state.liquidity)

        # RSI divergence: last confirmed pivot bar per side (Pine lastBull/BearDivBar)
        for d in state.rsi.detected:
            if d.is_bullish:
                self._last_bull_div_bar = d.pivot_bar
            else:
                self._last_bear_div_bar = d.pivot_bar
        lb, lbe = self._last_bull_div_bar, self._last_bear_div_bar
        leb = self._last_ext_break_bar
        vb = self._cfg.div_valid_bars

        # bullDivStale / bearDivStale (Pine 1945-1946)
        bull_stale = (leb is not None and lb is not None and leb > lb) or \
                     (lbe is not None and lb is not None and lbe > lb)
        bear_stale = (leb is not None and lbe is not None and leb > lbe) or \
                     (lb is not None and lbe is not None and lb > lbe)
        show_div = self._cfg.show_div
        bull_div_active = show_div and lb is not None and not bull_stale and index - lb <= vb
        bear_div_active = show_div and lbe is not None and not bear_stale and index - lbe <= vb

        # Veto PARTS, not the veto itself. The finished veto is SOS-aware as of the
        # 2026-07-21 Pine change, and the SOS bar lives in the sequence layer — see
        # `sos_aware_veto()` at the bottom of this module. divRsi = current RSI.
        div_rsi = state.rsi.rsi
        veto_on = show_div and self._cfg.div_veto
        veto_rsi_ob = div_rsi is not None and div_rsi >= self._cfg.div_extreme_ob
        veto_rsi_os = div_rsi is not None and div_rsi <= self._cfg.div_extreme_os

        # Structure fib -> fibo_dir / fiboP* / latches
        fib = state.fib
        lv = fib.levels
        fibo_dir = fib.direction if fib.active else 0
        p = {name: (lv.get(key) if fib.active else None) for name, key in _FIB_KEY.items()}
        touched = fib.touched_so_far
        fibo_618_ever = "E1" in touched      # gate ever reached (see engine.py)
        fibo7_touched = "TP3" in touched      # 0.0 hit
        fibo_half = fib.half_reached

        # Pine 2649-2650: latch the bar 0.5 was first tagged, never refresh it. Pine clears it in
        # the same block that clears `fiboHalfReached` on a new leg (`fiboOriginChanged`), and
        # `f_checkTouch` only ever SETS that flag — so "clear whenever half_reached is false" is
        # the same rule stated from this side, without needing the engine to expose the leg change.
        if not fibo_half:
            self._half_bar = None
        elif self._half_bar is None:
            self._half_bar = index

        # active FVGs (top, bottom, is_bullish, born_index)
        fvgs = [(g.top, g.bottom, g.is_bullish, g.born_index) for g in _active_fvgs(state.fvg)]

        # active ORDER BLOCKS, adapted into the gap's own shape — see `Signals.obs`.
        # `state.order_blocks is None` means the stack was built with `order_blocks=False`, i.e.
        # the engine never ran; an OrderBlockEvents with empty lists means it ran and found none.
        obs: List[Tuple[float, float, bool, int]] = []
        obs_available = state.order_blocks is not None
        if obs_available:
            obs = [(b.top, b.bottom, b.is_bullish, b.created_index)
                   for b in (list(state.order_blocks.active_bull)
                             + list(state.order_blocks.active_bear))]

        # Macro POI (Pine 3700-3706): bull discount 0.618-0.886, short premium 0.382+
        poi_long = poi_short = False
        mac = state.macro
        if mac.active and mac.top is not None and mac.bot is not None:
            rp = mac.top - mac.bot
            if rp > 0:
                poi_long = low <= mac.top - rp * 0.618 and high >= mac.top - rp * 0.886
                poi_short = high >= mac.top - rp * 0.382

        # Sniper Zone (Pine 2984-2989): the zone object persists, `sz_bar` latches on creation.
        sz = state.sniper
        if sz.created:
            self._sz_bar = index

        self._prev_prev_time = self._prev_time
        self._prev_time = t

        return Signals(
            index=index, time_ms=t, open=o, high=high, low=low, close=c,
            session_gap_bar=session_gap_bar, ny_hour=ny_hour,
            bull_sos=bull_sos, bear_sos=bear_sos, bull_bos=bull_bos, bear_bos=bear_bos,
            recent_ssl=recent_ssl, recent_ssl_bar=recent_ssl_bar, recent_ssl_time=recent_ssl_time,
            recent_bsl=recent_bsl, recent_bsl_bar=recent_bsl_bar, recent_bsl_time=recent_bsl_time,
            last_bull_div_bar=lb, last_bear_div_bar=lbe,
            bull_div_active=bull_div_active, bear_div_active=bear_div_active,
            veto_on=veto_on, veto_rsi_ob=veto_rsi_ob, veto_rsi_os=veto_rsi_os,
            fibo_dir=fibo_dir,
            fibo_p1=p["p1"], fibo_p2=p["p2"], fibo_p3=p["p3"], fibo_p4=p["p4"],
            fibo_p5=p["p5"], fibo_p6=p["p6"], fibo_p7=p["p7"], fibo_p10=p["p10"],
            fibo_ash=(fib.ash if fib.active else None),
            fibo_asl=(fib.asl if fib.active else None),
            fibo_half_reached=fibo_half, fibo_618_ever_reached=fibo_618_ever,
            fibo7_touched=fibo7_touched, fibo_half_bar=self._half_bar,
            liq_w_high=liq_tgt.get("w_high"), liq_w_low=liq_tgt.get("w_low"),
            liq_d_high=liq_tgt.get("d_high"), liq_d_low=liq_tgt.get("d_low"),
            liq_h4_high=liq_tgt.get("h4_high"), liq_h4_low=liq_tgt.get("h4_low"),
            fvgs=fvgs, obs=obs, obs_available=obs_available,
            poi_long_now=poi_long, poi_short_now=poi_short,
            bull_bos_high=ext.bull_bos_high, bull_bos_low=ext.bull_bos_low,
            bear_bos_high=ext.bear_bos_high, bear_bos_low=ext.bear_bos_low,
            bull_bos_high_ms=self._bar_time(ext.bull_bos_h_loc),
            bull_bos_low_ms=self._bar_time(ext.bull_bos_l_loc),
            bear_bos_high_ms=self._bar_time(ext.bear_bos_h_loc),
            bear_bos_low_ms=self._bar_time(ext.bear_bos_l_loc),
            last_conf_high=ext.last_conf_high, last_conf_low=ext.last_conf_low,
            sniper_zone_top=sz.zone_top, sniper_zone_bot=sz.zone_bot,
            sz_bar=self._sz_bar, sz_bullish=(sz.direction != -1),
            fibo_ash_ms=(self._bar_time(fib.ash_loc) if fib.active else None),
            fibo_asl_ms=(self._bar_time(fib.asl_loc) if fib.active else None),
        )

    def _bar_time(self, loc: Optional[int]) -> Optional[int]:
        """A bar index the fib engine reported -> that bar's epoch ms, or None if it is not in
        this run's window. Out of range is a real answer, not an error: a fib anchored on a bar
        the replay started after (a warm-up-era leg) has no time here, and inventing one would
        put a drawing on the wrong candle."""
        if loc is None or loc < 0 or loc >= len(self._bar_ms):
            return None
        return int(self._bar_ms[loc])


class PoiSourceUnavailable(RuntimeError):
    """`exec_poi_source` asks for order blocks and the engine stack never built them."""


# Every accepted value of `exec_poi_source`, and which lists it reads. A dict rather than an
# if-chain so an unrecognised value RAISES instead of quietly falling through to gaps — a typo
# that silently ran the default would make a whole replay a lie about what it tested.
#
# ⚠ "Order block (no FVG)" reads the GAP list without ever trading a gap. It needs it to answer
# the only question that mode asks — *is a qualifying gap already here?* — because a gap in the
# band means the setup belongs to the FVG leg and this one must stand down. Reading a list it
# cannot trade looks wrong until you know that; it is not a leftover.
POI_SOURCE_OB_NO_FVG = "Order block (no FVG)"

_POI_SOURCES = {
    "FVG": (True, False),
    "Order block": (False, True),
    "Either": (True, True),
    "FVG first": (True, True),
    POI_SOURCE_OB_NO_FVG: (True, True),
}

# The PRECEDENCE tiers, read only by "FVG first" (2026-08-09, Aaron: "if there is fair value
# gaps, take those preferentially over order blocks... if a fair value gap and an order block
# overlap, that's the most preferred fair value gap to take").
#
# A rank is a RANKING, never a filter: a lower tier is used whenever no higher one qualifies, so
# an order block still prices an entry on a leg that has no usable gap at all. That is the
# difference between this and "FVG" — and the whole point of the mode, since requiring a block
# measured WORSE than requiring nothing (see this bot's CLAUDE.md).
#
# ⚠ The tiers are compared AFTER the eligibility gates, in the entry-edge loop — see
# `Execution._entry_edges`. An FVG that the deep-only or pre-zone gate refuses must not suppress
# an order block the entry may legitimately use, and it cannot, because it never enters the
# comparison. Ranking before gating would turn a REFUSED gap into a veto on the fallback.
POI_RANK_OB = 0          # an order block: the fallback, used only when no gap qualifies
POI_RANK_FVG = 1         # a plain fair value gap: preferred over any block
POI_RANK_FVG_ON_OB = 2   # a gap an order block sits on: the strongest tier

# Every other mode returns ONE flat tier, so every candidate ties and the consumers fall straight
# back to their original nearest-first choice. That is what keeps "FVG" / "Order block" / "Either"
# byte-identical to before this mode existed, rather than merely intended to be.
_POI_RANK_FLAT = 0

# The modes that RANK rather than pool. Both need the same union and the same tiers; they differ
# only in what the consumer does when a GAP tier wins — "FVG first" rests an entry on it,
# `POI_SOURCE_OB_NO_FVG` stands the whole leg down (`Execution._entry_edges`).
_POI_RANKED = frozenset({"FVG first", POI_SOURCE_OB_NO_FVG})


def poi_rank_is_fvg(rank: int) -> bool:
    """Did this tier come from a fair value gap rather than an order block?

    One predicate rather than `rank > POI_RANK_OB` written at each call site, because there are
    TWO gap tiers (a plain gap and a gap on a block) and a reader comparing against the wrong one
    would silently let gaps-on-blocks through the stand-down — the exact overlap case the mode
    exists to hand to the other leg.
    """
    return rank in (POI_RANK_FVG, POI_RANK_FVG_ON_OB)


def _zones_overlap(a_top: float, a_bot: float, b_top: float, b_bot: float) -> bool:
    """Do two zones share price? Inclusive at the edges, matching every other band test in this
    package (`bot <= p2 and top >= p6`), so a block whose top is exactly a gap's bottom counts."""
    return min(a_top, b_top) >= max(a_bot, b_bot)


def pois_for(cfg, sig) -> List[Tuple[float, float, bool, int, int]]:
    """The zones this setup may use as its point of interest, per `exec_poi_source`.

    **This is THE seam, and it exists so there is exactly one of it.** Both consumers of a zone —
    the confluence flag in `sequence.py` and the entry-edge loop in `execution.py` — call this and
    then run their unchanged logic, so an order block is filtered by the deep-only rule, judged by
    the pre-zone gate and priced by the four entry rules through the SAME code a gap goes through.
    That is what makes "order blocks obey the same rules as a gap" true by construction. Adding a
    third consumer means calling this, never reading `sig.fvgs` directly.

    ⚠ **Refuses rather than degrading.** Asking for blocks on a stack built without the engine
    would otherwise return `[]` and trade exactly like a Require-FVG run that found no gap — a
    silently different strategy reporting itself as the one you configured. `obs_available` is the
    only thing that separates *found none* from *never asked*, and this is the one place it is
    read.

    Returns `(top, bottom, is_bullish, born, rank)`. The RANK is the "FVG first" precedence tier
    (`POI_RANK_*` above); every other mode returns one flat tier so nothing can move.
    """
    try:
        want_fvg, want_ob = _POI_SOURCES[cfg.exec_poi_source]
    except KeyError:
        raise ValueError(
            f"exec_poi_source={cfg.exec_poi_source!r} is not one of {sorted(_POI_SOURCES)}"
        ) from None
    if want_ob and not sig.obs_available:
        raise PoiSourceUnavailable(
            f"exec_poi_source={cfg.exec_poi_source!r} needs order blocks, but the engine stack was "
            f"built without them (state.order_blocks was None). Build the stack with "
            f"EngineConfig(order_blocks=True) — MpcSosFadeStrategy.run() does this from the config, "
            f"so a caller passing its own engine_config must too."
        )
    if cfg.exec_poi_source not in _POI_RANKED:
        pois = []
        if want_fvg:
            pois += [(t, b, d, n, _POI_RANK_FLAT) for (t, b, d, n) in sig.fvgs]
        if want_ob:
            pois += [(t, b, d, n, _POI_RANK_FLAT) for (t, b, d, n) in sig.obs]
        return pois

    # The RANKED modes — the same UNION as "Either", ranked rather than pooled. Order is gaps then
    # blocks purely to match "Either" and the Pine seam; with tiers in play it cannot decide an
    # outcome, because a strictly-higher tier replaces outright and a tie is resolved by a
    # min/max that does not care what order it saw its candidates in.
    #
    # ⚠ The confirming block must point the SAME WAY as the gap. In a long setup we are looking
    # for demand, and a bearish (supply) block sitting on a bullish gap is the opposite of
    # confirmation — ranking that gap TOP would promote the worst candidate on the leg. Aaron's
    # rule said "a gap and an order block overlap" without naming direction; this is the reading
    # taken, and it is one predicate to flip if the undirected version is wanted instead.
    pois = [
        (t, b, d, n, POI_RANK_FVG)
        if not any(od == d and _zones_overlap(t, b, ot, ob) for (ot, ob, od, _on) in sig.obs)
        else (t, b, d, n, POI_RANK_FVG_ON_OB)
        for (t, b, d, n) in sig.fvgs
    ]
    pois += [(t, b, d, n, POI_RANK_OB) for (t, b, d, n) in sig.obs]
    return pois


def _active_fvgs(fvg_events):
    """The live (unmitigated) FVGs the Pine's fvgBoxes/fvgTops/fvgBots/fvgIsBull arrays
    hold. FvgEvents exposes an `active` list; each gap carries top/bottom/is_bullish."""
    return getattr(fvg_events, "active", []) or []


def sos_aware_veto(sig: Signals, l_sos_bar, s_sos_bar) -> Tuple[bool, bool]:
    """Pine `longVetoA` / `shortVetoA` (mpc_strategy.pine ~3701, changed 2026-07-21).

    A divergence that prints AFTER the SOS no longer vetoes its own setup: once stage 2
    is live the setup is deliberately waiting on a retrace, and an opposing divergence
    formed during that retrace IS the pullback — weakness in the counter-move, not a
    reversal of the leg we just broke with. Only a divergence already live at or before
    the SOS bar still blocks the side; with no SOS yet, nothing changes.

    Extreme RSI keeps blocking LIVE — the exemption covers divergence only.

    Lives here rather than in `SignalAdapter.update()` because the SOS bar is sequence
    state, which the adapter has not computed yet. Both the primary execution layer and
    the (Python-only) secondary re-entry read it, so it is one function, not two copies.
    """
    long_veto = sig.veto_on and (
        sig.veto_rsi_ob
        or (sig.bear_div_active and (l_sos_bar is None or sig.last_bear_div_bar <= l_sos_bar))
    )
    short_veto = sig.veto_on and (
        sig.veto_rsi_os
        or (sig.bull_div_active and (s_sos_bar is None or sig.last_bull_div_bar <= s_sos_bar))
    )
    return long_veto, short_veto
