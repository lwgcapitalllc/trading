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
    fibo_half_reached: bool
    fibo_618_ever_reached: bool
    fibo7_touched: bool

    # active FVGs overlapping consideration — (top, bottom, is_bullish)
    fvgs: List[Tuple[float, float, bool]] = field(default_factory=list)

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

    # Last CONFIRMED external swing high/low (Pine st.last_conf_high / st.last_conf_low) — the
    # anchor the STRUCTURE runner trail rides (`exec_runner_trail == "Structure (swing)"`).
    # Read only by `Execution._advance_stage` once a trade is past TP2, so with the trail on
    # "Fixed step" nothing in the decision stream touches them.
    last_conf_high: Optional[float] = None
    last_conf_low: Optional[float] = None


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

        # active FVGs (top, bottom, is_bullish)
        fvgs = [(g.top, g.bottom, g.is_bullish) for g in _active_fvgs(state.fvg)]

        # Macro POI (Pine 3700-3706): bull discount 0.618-0.886, short premium 0.382+
        poi_long = poi_short = False
        mac = state.macro
        if mac.active and mac.top is not None and mac.bot is not None:
            rp = mac.top - mac.bot
            if rp > 0:
                poi_long = low <= mac.top - rp * 0.618 and high >= mac.top - rp * 0.886
                poi_short = high >= mac.top - rp * 0.382

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
            fibo_half_reached=fibo_half, fibo_618_ever_reached=fibo_618_ever,
            fibo7_touched=fibo7_touched,
            fvgs=fvgs, poi_long_now=poi_long, poi_short_now=poi_short,
            bull_bos_high=ext.bull_bos_high, bull_bos_low=ext.bull_bos_low,
            bear_bos_high=ext.bear_bos_high, bear_bos_low=ext.bear_bos_low,
            last_conf_high=ext.last_conf_high, last_conf_low=ext.last_conf_low,
        )


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
