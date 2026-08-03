"""BosExecution — the MPC BOS order layer.

A thin SUBCLASS of `mpc_sos_fade.execution.Execution`, the same shape as `BLegExecution`.
Everything from `_open_position` onward — the fill emulator, the TP ladder, the stop
staging, the %-risk sizing, the R grading, the runner trail — is direction- and
setup-agnostic and is REUSED wholesale. Four things differ:

  * `_entry_edges` prices the A+ entry ladder off the **BOS leg** instead of the SOS leg
    (spec §5: "use the A+ strategy's entry methods exactly as they are"), and adds the two
    sources the A+ has switched off — the Sniper Zone and the gap straddling 0.5.
  * `_place_entries` is the BOS arm + the five-way stop model (spec §6) + the TP ladder.
  * `_open_position` bumps F6's per-regime trade counter on the tracker.
  * `step` runs F5b, the divergence KILL on an OPEN trade (spec §4a).

There is no A+ path and no B-LEG path in this fork, so the parent's `_armed` never runs and
its blocked / missed markers are both off: their codes answer "how far did this **A+** setup
get before it was refused", which here would describe a trade that was never on the table.

Ports `indicators/mpc_bos_strategy.pine` 3437-3643 + 3745-3767 + 3932-3945.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.execution import Execution, _Pending  # noqa: E402


class BosExecution(Execution):
    """BOS-entry-only execution. Reuses the parent's whole broker emulator + exit ladder."""

    _bos = None            # the bar's BosState, set by step() before the parent needs it
    _tracker = None        # the BosTracker, so a fill can bump F6's counter
    _records_misses = False

    # Reporting only — which source priced each side this bar (mirrors the Pine's
    # longFvgOk / longEdgeSz, which feed the confluence label).
    _l_from_fvg = False
    _l_from_sz = False
    _s_from_fvg = False
    _s_from_sz = False

    def step(self, sig, seq, bos):  # type: ignore[override]
        self._bos = bos
        dec = super().step(sig, seq)

        # ── F5b — the divergence KILL on an OPEN trade (Pine 3932-3945) ──────────
        # An opposing divergence means the move is overextended and is setting up the NEXT
        # shift of structure, and a continuation trade is the worst thing to be holding into
        # that. CONFIRMED divergence only, never extreme RSI: an overbought RSI is the normal
        # state of a healthy long continuation, and closing on it would flatten the runner on
        # every winner (spec §10a).
        #
        # Deliberate deviation, shared with the parent's `exec_close_opp_sos`: Pine's
        # `strategy.close()` fills at the NEXT bar's open, this closes at THIS bar's close.
        if self._cfg.bos_close_opp_div and self._pos_dir != 0 and self._entry_kind != "secondary":
            if (self._pos_dir > 0 and sig.bear_div_active) or \
               (self._pos_dir < 0 and sig.bull_div_active):
                self._close_at(sig, sig.close, "opp-div", dec)
        return dec

    # ── the entry ladder, on the BOS leg (Pine 3458-3522) ────────────────────────
    def _entry_edges(self, sig) -> Tuple[Optional[float], Optional[float]]:
        """The resting-limit price on each side. First source that prices the leg wins:

          1. FVG edge — a live gap overlapping the 0.5-0.886 band, clamped to 0.5; with
             `exec_fvg_deep_only` the WHOLE gap must sit past 0.5, never straddling it.
          2. Deep-fib re-price (Method 3) — when the gap's NEAR edge sits deeper than 0.618,
             rest at the nearest fib just shallower instead (the level price reaches first).
          3. Sniper Zone — only on a leg with no qualifying gap, and only a zone anchored at
             or after THIS BOS's bar rather than left over from an earlier leg.
          4. A gap STRADDLING 0.5 → the limit rests at 0.5. Ranks last by construction.
          5. The plain fib — unless `exec_req_fvg` says no gap means no trade.

        0.5 is the floor (no candidate may rest shallower) and anything past 0.886 is refused.
        """
        cfg = self._cfg
        bos = self._bos
        self._l_from_fvg = self._l_from_sz = False
        self._s_from_fvg = self._s_from_sz = False
        if bos is None:
            return None, None
        L, S = bos.long, bos.short
        long_edge = short_edge = None

        # 1 + 2 — the FVG edge, optionally re-priced to the nearest shallower fib
        if cfg.bos_use_fvg:
            for top, bot, is_bull, _born in sig.fvgs:
                if (L.on and L.fibs_ready and is_bull and bot <= L.p2 and top >= L.p6
                        and (not cfg.exec_fvg_deep_only or top <= L.p2)):
                    self._l_from_fvg = True
                    df = self._deep_fib_leg(bot, top, True, L) if cfg.exec_deep_fib else None
                    e = min(top, L.p2) if df is None else df
                    long_edge = e if long_edge is None else max(long_edge, e)  # price reaches it FIRST
                if ((not is_bull) and S.on and S.fibs_ready and top >= S.p2 and bot <= S.p6
                        and (not cfg.exec_fvg_deep_only or bot >= S.p2)):
                    self._s_from_fvg = True
                    df = self._deep_fib_leg(bot, top, False, S) if cfg.exec_deep_fib else None
                    e = max(bot, S.p2) if df is None else df
                    short_edge = e if short_edge is None else min(short_edge, e)

        # 3 — the Sniper Zone, standing in for a missing gap (Pine 3489-3499)
        if (cfg.bos_use_fvg and cfg.exec_conf_sz2 and cfg.exec_conf_sz
                and sig.sniper_zone_top is not None and sig.sniper_zone_bot is not None
                and sig.sz_bar is not None):
            if (long_edge is None and L.on and L.fibs_ready and sig.sz_bullish
                    and L.bar is not None and sig.sz_bar >= L.bar):
                e = min(sig.sniper_zone_bot, L.p2)
                if e >= L.p6:
                    long_edge, self._l_from_sz = e, True
            if (short_edge is None and S.on and S.fibs_ready and not sig.sz_bullish
                    and S.bar is not None and sig.sz_bar >= S.bar):
                e = max(sig.sniper_zone_top, S.p2)
                if e <= S.p6:
                    short_edge, self._s_from_sz = e, True

        # 4 — the least-favourable gap entry: a body straddling 0.5 (Pine 3503-3513)
        if cfg.bos_use_fvg and cfg.exec_fvg_50:
            for top, bot, is_bull, _born in sig.fvgs:
                if long_edge is None and L.on and L.fibs_ready and is_bull \
                        and bot <= L.p2 and top >= L.p2:
                    long_edge, self._l_from_fvg = L.p2, True
                if short_edge is None and S.on and S.fibs_ready and not is_bull \
                        and bot <= S.p2 and top >= S.p2:
                    short_edge, self._s_from_fvg = S.p2, True

        # 5 — the plain fib fallback (Pine 3518-3522). Never reached at the shipped defaults.
        if not (cfg.bos_use_fvg and cfg.exec_req_fvg):
            if long_edge is None and L.on and L.fibs_ready:
                long_edge = self._fib_entry(L)
            if short_edge is None and S.on and S.fibs_ready:
                short_edge = self._fib_entry(S)

        return long_edge, short_edge

    def _fib_entry(self, leg) -> Optional[float]:
        """Pine `lFibEntry` — the chosen plain-fib entry level for this leg."""
        return {"0.5": leg.p2, "0.702": leg.p4, "0.786": leg.p5,
                "0.886": leg.p6}.get(self._cfg.bos_entry_fib, leg.p3)

    @staticmethod
    def _deep_fib_leg(gb, gt, is_bull, leg) -> Optional[float]:
        """Pine `f_deepFibEdge`, on the BOS leg's own fibs rather than the engine's.

        ONLY the near edge decides it: a real gap is often tall enough to span 0.702/0.786,
        and what the body crosses is irrelevant."""
        if is_bull and gt < leg.p3:
            return leg.p3 if gt >= leg.p4 else (leg.p4 if gt >= leg.p5 else leg.p5)
        if (not is_bull) and gb > leg.p3:
            return leg.p3 if gb <= leg.p4 else (leg.p4 if gb <= leg.p5 else leg.p5)
        return None

    # ── the stop model (spec §6, Pine 3567-3577) ─────────────────────────────────
    def _bos_sl(self, is_long: bool, entry_px: float, leg, sig) -> Optional[float]:
        cfg = self._cfg
        model = cfg.bos_sl_model
        if model == "Broken swing level":
            raw = leg.high if is_long else leg.low
        elif model == "Fib 0.886":
            raw = leg.p6
        elif model == "Last confirmed swing":
            raw = sig.last_conf_low if is_long else sig.last_conf_high
        elif model == "ATR":
            atr = self._bos.atr14
            raw = None if atr is None else (
                entry_px - cfg.bos_sl_atr * atr if is_long else entry_px + cfg.bos_sl_atr * atr)
        elif model == "Break leg origin":
            # NOT in the Pine. The structural continuation stop: the low the break leg started
            # from. Distinct from "Fib 1.0", which with the EXPANSION anchor is the fib engine's
            # own leg origin and can sit somewhere else entirely.
            raw = leg.low if is_long else leg.high
        else:
            raw = leg.p10
        if raw is None:
            return None
        buf = cfg.exec_sl_buf_tk * cfg.mintick
        return raw - buf if is_long else raw + buf

    # ── arm + placement (Pine 3531-3643) ─────────────────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        bos = self._bos
        L, S = bos.long, bos.short

        # F5 — the divergence veto. LIVE, both directions, and deliberately NOT the A+ rule:
        # the A+'s post-SOS exemption treats a divergence during the pullback as the retrace
        # itself. For a CONTINUATION that reasoning inverts — an opposing divergence is
        # weakness in the move we are trying to ride, which is the fakeout signature. So no
        # exemption. Re-checked every bar, so a divergence appearing mid-retrace PULLS the
        # resting limit, and one going stale lets it be re-placed.
        veto_l = cfg.show_div and (sig.bear_div_active or sig.veto_rsi_ob)
        veto_s = cfg.show_div and (sig.bull_div_active or sig.veto_rsi_os)
        dec.long_veto, dec.short_veto = veto_l, veto_s

        late = cfg.exec_no_late_day and 16 <= sig.ny_hour < 18   # F7, 16:00-17:59 NY
        if cfg.bos_no_ny_pm and 12 <= sig.ny_hour < 16:          # F11 (research)
            late = True
        # F10 (research) — the VOLATILITY band the setup is allowed to arm in. Measured as
        # ATR14 / price so it is comparable across a market that ran 1,200 -> 4,100.
        atr = self._bos.atr14
        if cfg.bos_max_atr_rel > 0:
            rel = self._bos.atr_rel
            if rel is None or rel > cfg.bos_max_atr_rel:
                late = True
        if cfg.bos_max_atr_pct > 0 or cfg.bos_min_atr_pct > 0:
            if atr is None:
                late = True
            else:
                pct = atr / sig.close * 100.0
                if cfg.bos_max_atr_pct > 0 and pct > cfg.bos_max_atr_pct:
                    late = True
                if cfg.bos_min_atr_pct > 0 and pct < cfg.bos_min_atr_pct:
                    late = True
        bias_l, bias_s = self._htf_bias_block(sig)               # F8

        long_armed = (cfg.exec_longs and L.on and L.fibs_ready and long_edge is not None
                      and not late and not bias_l
                      and (not veto_l or not cfg.bos_respect_veto)
                      and L.trades < cfg.bos_max_per_regime
                      and (self._traded_sos_l is None or L.bar != self._traded_sos_l))
        short_armed = (cfg.exec_shorts and S.on and S.fibs_ready and short_edge is not None
                       and not late and not bias_s
                       and (not veto_s or not cfg.bos_respect_veto)
                       and S.trades < cfg.bos_max_per_regime
                       and (self._traded_sos_s is None or S.bar != self._traded_sos_s))
        dec.long_armed, dec.short_armed = long_armed, short_armed

        # deliberate deviation (real runs only): no NEW entry inside the flat-by-close window
        if cfg.flat_by_close and self._in_flat_window(sig):
            long_armed = short_armed = False

        # Entry-source filter (research dial, not in the Pine). The two halves of this book
        # behave completely differently — see `mpc_bos_optimization.md` Run 1.
        src = cfg.bos_entry_source
        if src == "Sniper Zone only":
            long_armed = long_armed and self._l_from_sz
            short_armed = short_armed and self._s_from_sz
        elif src == "FVG only":
            long_armed = long_armed and self._l_from_fvg and not self._l_from_sz
            short_armed = short_armed and self._s_from_fvg and not self._s_from_sz

        self._pend_long = None
        self._pend_short = None

        if long_armed:
            sl = self._bos_sl(True, long_edge, L, sig)
            if sl is not None:
                dist = long_edge - sl
                tp1, tp2 = self._targets(True, long_edge, dist, L)
                if self._stop_clears_floor(dist, long_edge):
                    qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                    self._pend_long = _Pending(1, long_edge, qty, sl, tp1, tp2, L.bar)

        if short_armed:
            sl = self._bos_sl(False, short_edge, S, sig)
            if sl is not None:
                dist = sl - short_edge
                tp1, tp2 = self._targets(False, short_edge, dist, S)
                if self._stop_clears_floor(dist, short_edge):
                    qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                    self._pend_short = _Pending(-1, short_edge, qty, sl, tp1, tp2, S.bar)

    def _targets(self, is_long: bool, edge: float, dist: float, leg):
        """TP1 / TP2 for one side.

        "Fib ladder" (the Pine): the rungs are fib levels chosen by how DEEP the entry filled —
        derived, never chosen, so the risk-reward ratio is an output of leg geometry.
        "Fixed R" (research): the rungs sit at a multiple of the stop distance, which is the
        only way "risk 1 to make 2" is expressible at all.
        """
        cfg = self._cfg
        if cfg.bos_exit_mode == "Fixed R":
            k = 1 if is_long else -1
            return edge + k * cfg.bos_rr_tp1 * dist, edge + k * cfg.bos_rr_tp2 * dist

        deep = (edge <= leg.p3) if is_long else (edge >= leg.p3)   # DERIVED — spec §5
        tp1 = leg.p2 if deep else leg.p1        # deep 0.5 / shallow 0.382
        tp2 = leg.p1 if deep else leg.p7        # deep 0.382 / shallow 0.0
        if cfg.bos_tp2_measured and leg.high is not None and leg.low is not None:
            rng = leg.high - leg.low
            m = leg.high + rng if is_long else leg.low - rng
            if (m > tp1) if is_long else (m < tp1):
                tp2 = m
        return tp1, tp2

    # ── F6's counter lives on the tracker; a fill is what increments it ──────────
    def _open_position(self, pend, fill_price, sig, dec, kind: str = "primary") -> bool:
        opened = super()._open_position(pend, fill_price, sig, dec, kind)
        if opened and kind == "primary" and self._tracker is not None:
            self._tracker.on_fill(pend.dir)
        return opened
