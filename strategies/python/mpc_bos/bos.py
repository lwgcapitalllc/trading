"""BosTracker — the MPC BOS setup state machine.

A line-for-line port of `indicators/mpc_bos_strategy.pine` 3234-3412 (Stage 0 regime,
Stage 1 arm + quality filters, the anchor fib, and the death rules).

The idea (spec §1): a shift of structure tells you the trend turned; what follows is a run
of BREAKS of structure in that same direction until the next shift ends it. Each break is a
fresh continuation leg and each leg gives a retracement to buy into. A+ fades the shift,
this rides what the shift started.

Per bar, in Pine file order:
  0. ATR(14) — the yardstick both quality filters are measured in.
  1. STAGE 0 — an SOS opens its own regime and closes the opposite one. Opening is
     gap-guarded, closing is NOT: refusing to believe an SOS printed on a session-gap bar
     cannot make it untrue, and an armed leg left alive into the opposite regime keeps a
     limit resting that has no BOS of its own behind it.
  2. STAGE 1 — a BOS (never an SOS bar: the engine sets `bull_bos` on every `bull_sos` too)
     increments the ordinal, drops any older arm on that side — the NEWEST leg owns the
     setup — and arms only if F1/F2/F3 pass. The counter increments either way, so the
     ordinal a trade reports is its true position in the run.
  3. THE ANCHOR FIB — 0.382/0.5/0.618/0.702/0.786/0.886/0.0/1.0 of either the EXPANSION leg
     (the drawn External fib: origin → running extreme, so the levels move until the
     pullback confirms) or the BREAK leg (frozen at the BOS bar).
  4. DEATH — the cycle completing on the anchor, a close past the anchor's 1.0, F4, or the
     F9 staleness cap. (The other two deaths — the opposite SOS and a newer same-side BOS —
     happen in steps 1 and 2 above.)

It reads `Signals` only and never writes A+ state, exactly like `BLegTracker`. Feed one bar
per `update(sig)`, in order.

`trd_l` / `trd_s` (F6, filled trades this regime) are owned here but INCREMENTED by the
execution layer on a fill, via `on_fill()` — matching the Pine, where `bosTrdL` is bumped in
the fill-detection block below the order block. The execution runs after this tracker within
a bar, so the bump lands for the NEXT bar's arm test, which is where the Pine has it too.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _lvl(ext: Optional[float], org: Optional[float], v: float) -> Optional[float]:
    """Pine `f_lvl(ext, org, v) => ext + (org - ext) * v`, with na propagation.

    `ext` is the leg's 0.0 (the extreme it ran to), `org` its 1.0 (where the leg started).
    Long: ext = high, org = low. Short: the mirror. This is the identical arithmetic the
    engine's own `fiboP*` uses, just anchored per-setup."""
    if ext is None or org is None:
        return None
    return ext + (org - ext) * v


@dataclass(frozen=True)
class BosLeg:
    """One side's armed BOS and the fib ladder priced off it."""

    on: bool                        # a leg is armed and watching
    high: Optional[float]           # the break leg's broken swing (Pine bosL_high / bosS_low mirror)
    low: Optional[float]
    bar: Optional[int]              # the bar it armed on — the one-trade-per-leg key + the F9 clock
    n: int                          # the anchor's BOS ordinal (1 = expansion, 2+ = continuation)
    half: bool                      # the per-anchor 0.5 latch (half of the cycle-complete death)
    regime: bool                    # an SOS has opened this side's regime
    trades: int                     # filled trades since that SOS (F6)
    sos_bar: Optional[int]          # the bar the SOS opened this regime — regime age
    disp_atr: float                 # F2's measure AS A NUMBER, frozen at the arm bar:
    #   how far the breaking bar CLOSED past the broken swing, in ATR14. F2 thresholds it;
    #   this keeps the raw value so it can be studied as a characteristic rather than a gate.
    leg_atr: float                  # F3's measure as a number: break-leg range in ATR14
    fibs_ready: bool
    p1: Optional[float]             # 0.382 — TP2 rung (shallow ladder's TP1)
    p2: Optional[float]             # 0.5   — the entry-band floor / deep ladder's TP1
    p3: Optional[float]             # 0.618 — the deep/shallow boundary
    p4: Optional[float]             # 0.702
    p5: Optional[float]             # 0.786
    p6: Optional[float]             # 0.886 — the entry-band ceiling
    p7: Optional[float]             # 0.0   — the leg extreme
    p10: Optional[float]            # 1.0   — the leg origin, the default stop
    why: str                        # why the last arm died — reporting only


@dataclass(frozen=True)
class BosState:
    long: BosLeg
    short: BosLeg
    atr14: Optional[float]
    atr_rel: Optional[float] = None   # ATR14 / its own ~10-day EMA. 1.0 = normal for this market


class BosTracker:
    """Streaming Signals -> BosState. One instance per backtest run.

    `tf_seconds` is the chart timeframe in seconds (Pine `timeframe.in_seconds()`), used to
    turn `bos_max_days` into the F9 staleness BAR cap so weekends and the daily close don't
    burn the clock. The driver infers it from the frame's bar spacing.
    """

    def __init__(self, config, tf_seconds: int = 900) -> None:
        self._cfg = config
        self._tf_seconds = tf_seconds
        # Pine: int(math.max(1, math.round(bosMaxDays * 86400 / timeframe.in_seconds()))).
        # math.round is round-half-away-from-zero, so floor(x + 0.5), not Python's banker's round.
        self._bos_max = int(max(1, math.floor(config.bos_max_days * 86400 / tf_seconds + 0.5)))

        # ATR(14) — Pine ta.atr(14) = ta.rma(ta.tr(true), 14). Same construction as
        # Execution._update_atr: NA until 14 values, then an SMA seed and Wilder from there.
        self._atr: Optional[float] = None
        self._atr_trs: list = []
        self._atr_prev_close: Optional[float] = None
        # A slow EMA of ATR itself — the market's OWN recent volatility baseline. `atr_rel`
        # (ATR / this) says "fast or slow FOR THIS MARKET RIGHT NOW", which an absolute
        # %-of-price threshold cannot: gold's median 15m ATR ran 0.081% in 2018 and 0.216%
        # in 2026, so a fixed cap silently stops firing as the regime shifts.
        self._atr_base: Optional[float] = None
        self._atr_base_n = 960          # ~10 trading days of 15m bars

        # long side (Pine bosRegL / bosCntL / bosTrdL / bosL_*)
        self._reg_l = False
        self._cnt_l = 0
        self._trd_l = 0
        self._l_on = False
        self._l_high: Optional[float] = None
        self._l_low: Optional[float] = None
        self._l_bar: Optional[int] = None
        self._l_n = 0
        self._l_half = False
        self._l_why = ""
        self._l_sos_bar = None
        self._l_disp = 0.0
        self._l_leg = 0.0
        # short side
        self._reg_s = False
        self._cnt_s = 0
        self._trd_s = 0
        self._s_on = False
        self._s_high: Optional[float] = None
        self._s_low: Optional[float] = None
        self._s_bar: Optional[int] = None
        self._s_n = 0
        self._s_half = False
        self._s_why = ""
        self._s_sos_bar = None
        self._s_disp = 0.0
        self._s_leg = 0.0

    @property
    def bos_max(self) -> int:
        return self._bos_max

    def on_fill(self, direction: int) -> None:
        """F6's counter (Pine `bosTrdL := bosTrdL + 1` in the fill block, 3747/3757)."""
        if direction > 0:
            self._trd_l += 1
        else:
            self._trd_s += 1

    # ── ATR(14), Pine ta.atr(14) ─────────────────────────────────────────────────
    def _update_atr(self, sig) -> None:
        c_prev = self._atr_prev_close
        tr = (sig.high - sig.low) if c_prev is None else max(
            sig.high - sig.low, abs(sig.high - c_prev), abs(sig.low - c_prev))
        self._atr_prev_close = sig.close
        if self._atr is None:
            self._atr_trs.append(tr)
            if len(self._atr_trs) == 14:
                self._atr = sum(self._atr_trs) / 14.0
        else:
            self._atr += (tr - self._atr) / 14.0
        if self._atr is not None:
            if self._atr_base is None:
                self._atr_base = self._atr
            else:
                self._atr_base += (self._atr - self._atr_base) * (2.0 / (self._atr_base_n + 1))

    def update(self, sig) -> BosState:
        cfg = self._cfg
        idx, close, high, low = sig.index, sig.close, sig.high, sig.low

        self._update_atr(sig)
        atr = self._atr

        # ── STAGE 0 — regime (Pine 3280-3291) ────────────────────────────────────
        # CLOSE fires always; OPEN stays gap-guarded. See the module docstring.
        if sig.bear_sos:
            if self._l_on:
                self._l_why = "opposite SOS — the bullish regime is over"
            self._reg_l = False
            self._l_on = False
        if sig.bull_sos:
            if self._s_on:
                self._s_why = "opposite SOS — the bearish regime is over"
            self._reg_s = False
            self._s_on = False
        if sig.bull_sos and not sig.session_gap_bar:
            self._reg_l, self._cnt_l, self._trd_l = True, 0, 0
            self._l_sos_bar = idx
        if sig.bear_sos and not sig.session_gap_bar:
            self._reg_s, self._cnt_s, self._trd_s = True, 0, 0
            self._s_sos_bar = idx

        # ── STAGE 1 — the BOS that arms (Pine 3297-3330) ─────────────────────────
        fire_l = (self._reg_l and sig.bull_bos and not sig.bull_sos and not sig.session_gap_bar
                  and sig.bull_bos_high is not None and sig.bull_bos_low is not None
                  and sig.bull_bos_high > sig.bull_bos_low)
        fire_s = (self._reg_s and sig.bear_bos and not sig.bear_sos and not sig.session_gap_bar
                  and sig.bear_bos_high is not None and sig.bear_bos_low is not None
                  and sig.bear_bos_high > sig.bear_bos_low)

        if fire_l:
            self._cnt_l += 1
            _d, _g = close - sig.bull_bos_high, sig.bull_bos_high - sig.bull_bos_low
            if self._l_on:
                self._l_why = "re-anchored — a newer BOS on this side took the setup"
            self._l_on = False
            if (self._ok_which(self._cnt_l)
                    and self._ok_atr(close - sig.bull_bos_high, cfg.bos_min_disp_atr, atr)
                    and self._ok_atr(sig.bull_bos_high - sig.bull_bos_low, cfg.bos_min_leg_atr, atr)):
                self._l_high = sig.bull_bos_high
                self._l_low = sig.bull_bos_low
                self._l_bar = idx
                self._l_n = self._cnt_l
                self._l_half = False
                self._l_on = True
                self._l_disp = _d / atr if atr else 0.0
                self._l_leg = _g / atr if atr else 0.0

        if fire_s:
            self._cnt_s += 1
            _d, _g = sig.bear_bos_low - close, sig.bear_bos_high - sig.bear_bos_low
            if self._s_on:
                self._s_why = "re-anchored — a newer BOS on this side took the setup"
            self._s_on = False
            if (self._ok_which(self._cnt_s)
                    and self._ok_atr(sig.bear_bos_low - close, cfg.bos_min_disp_atr, atr)
                    and self._ok_atr(sig.bear_bos_high - sig.bear_bos_low, cfg.bos_min_leg_atr, atr)):
                self._s_high = sig.bear_bos_high
                self._s_low = sig.bear_bos_low
                self._s_bar = idx
                self._s_n = self._cnt_s
                self._s_half = False
                self._s_on = True
                self._s_disp = _d / atr if atr else 0.0
                self._s_leg = _g / atr if atr else 0.0

        # ── THE ANCHOR FIB (Pine 3339-3366) ──────────────────────────────────────
        # With the EXPANSION anchor these reproduce the engine's own fiboP* exactly (for a
        # bull leg fiboP7 IS `fibo_ash` and fiboP10 IS `fibo_asl`), computed through the
        # Pine's own `f_lvl` so the float path is identical rather than merely equivalent.
        expansion = cfg.bos_fib_anchor == "Expansion leg"
        if expansion:
            l_ext = sig.fibo_p7 if sig.fibo_dir == 1 else None
            l_org = sig.fibo_p10 if sig.fibo_dir == 1 else None
            s_ext = sig.fibo_p7 if sig.fibo_dir == -1 else None
            s_org = sig.fibo_p10 if sig.fibo_dir == -1 else None
        else:
            l_ext, l_org = self._l_high, self._l_low
            s_ext, s_org = self._s_low, self._s_high

        lp = {v: _lvl(l_ext, l_org, v) for v in (0.382, 0.5, 0.618, 0.702, 0.786, 0.886, 0.0, 1.0)}
        sp = {v: _lvl(s_ext, s_org, v) for v in (0.382, 0.5, 0.618, 0.702, 0.786, 0.886, 0.0, 1.0)}

        l_ready = (None not in (lp[0.382], lp[0.5], lp[0.618], lp[0.886], lp[0.0], lp[1.0])
                   and lp[0.0] > lp[1.0])
        s_ready = (None not in (sp[0.382], sp[0.5], sp[0.618], sp[0.886], sp[0.0], sp[1.0])
                   and sp[1.0] > sp[0.0])

        # ── DEATH (Pine 3383-3412) ───────────────────────────────────────────────
        if self._l_on:
            if l_ready and low <= lp[0.5]:
                self._l_half = True
            why = ""
            if self._l_half and l_ready and high >= lp[0.0]:
                why = "cycle complete — retraced, then came back to the leg extreme"
            elif l_ready and close < lp[1.0]:
                why = "closed past the anchor's fib 1.0 (leg origin) — leg invalidated"
            elif cfg.bos_req_hold and self._l_high is not None and close < self._l_high:
                why = "F4 — closed back through the broken swing"
            elif self._l_bar is not None and idx - self._l_bar > self._bos_max:
                why = "stale — the F9 day cap expired before the retrace arrived"
            if why:
                self._l_on = False
                self._l_why = why

        if self._s_on:
            if s_ready and high >= sp[0.5]:
                self._s_half = True
            why = ""
            if self._s_half and s_ready and low <= sp[0.0]:
                why = "cycle complete — retraced, then came back to the leg extreme"
            elif s_ready and close > sp[1.0]:
                why = "closed past the anchor's fib 1.0 (leg origin) — leg invalidated"
            elif cfg.bos_req_hold and self._s_low is not None and close > self._s_low:
                why = "F4 — closed back through the broken swing"
            elif self._s_bar is not None and idx - self._s_bar > self._bos_max:
                why = "stale — the F9 day cap expired before the retrace arrived"
            if why:
                self._s_on = False
                self._s_why = why

        return BosState(
            long=BosLeg(
                on=self._l_on, high=self._l_high, low=self._l_low, bar=self._l_bar,
                n=self._l_n, half=self._l_half, regime=self._reg_l, trades=self._trd_l,
                fibs_ready=l_ready,
                p1=lp[0.382], p2=lp[0.5], p3=lp[0.618], p4=lp[0.702], p5=lp[0.786],
                p6=lp[0.886], p7=lp[0.0], p10=lp[1.0], why=self._l_why,
                sos_bar=self._l_sos_bar, disp_atr=self._l_disp, leg_atr=self._l_leg,
            ),
            short=BosLeg(
                on=self._s_on, high=self._s_high, low=self._s_low, bar=self._s_bar,
                n=self._s_n, half=self._s_half, regime=self._reg_s, trades=self._trd_s,
                fibs_ready=s_ready,
                p1=sp[0.382], p2=sp[0.5], p3=sp[0.618], p4=sp[0.702], p5=sp[0.786],
                p6=sp[0.886], p7=sp[0.0], p10=sp[1.0], why=self._s_why,
                sos_bar=self._s_sos_bar, disp_atr=self._s_disp, leg_atr=self._s_leg,
            ),
            atr14=atr,
            atr_rel=(atr / self._atr_base if atr is not None and self._atr_base else None),
        )

    # ── quality filters (spec §4) ────────────────────────────────────────────────
    def _ok_which(self, ordinal: int) -> bool:
        """F1 — which break after the SOS is tradeable."""
        w = self._cfg.bos_which
        if w == "All":
            return True
        if w == "1st + 2nd":
            return ordinal <= 2
        return ordinal == 1

    @staticmethod
    def _ok_atr(measured: float, mult: float, atr: Optional[float]) -> bool:
        """F2 / F3 — `mult <= 0 or measured >= mult * atr14`.

        NA reads as false, matching Pine: during the ATR's 13-bar warmup a live floor cannot
        be evaluated, so the leg is refused rather than waved through."""
        if mult <= 0:
            return True
        if atr is None:
            return False
        return measured >= mult * atr
