"""BLegTracker — the B-LEG setup state machine.

A line-for-line port of the B LEG SETUP block in `indicators/strategies/mpc_b_leg_strategy.pine`
(~3683-3758). The B LEG is the SOS whose retrace arrived LATE: an A+ SOS fires, price
expands and prints a continuation BOS BEFORE it ever retraces, so the A+ reversal leg
dies at 2/3 (no 0.5/0.618 latch). On a higher timeframe that is ONE clean leg and the
retrace DOES arrive, later — into the Sniper-Zone band (0.382-0.5) frozen at the ORIGINAL
SOS. This tracker freezes that band and waits for price to trade back into it.

It runs fully PARALLEL to the A+ sequence: it only READS structure (`Signals`) and the
`bleg_arm_*` flags the sequence captured (`SeqState`), and never writes A+ state. Feed
one bar per `update(sig, seq)`, in order.

Per bar the block does four things, in this order (matching the Pine):
  1. FREEZE the SZ band on every SOS — the 0.382/0.5 maths of the break leg. Deepest band
     wins: a fresh same-side SOS while a leg is live and UNTAPPED keeps whichever band is
     FARTHER from price (migrating the watch, not resetting it); the target extends.
  2. TRACK the expansion extreme (the TP reference) until the leg arms, then freeze it.
  3. ARM on the REV's death-by-continuation-BOS (the `bleg_arm_*` flag from the sequence).
  4. DEATH: a close past the leg origin (fib 1.0 = `inv`), or the staleness cap (BLEG_MAX
     bars, converted from `bleg_max_days` ÷ the chart timeframe).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


def _leg_start(*stamps: Optional[int]) -> Optional[int]:
    """The earlier of a leg's two anchor times, ignoring ones this run's window cannot date.

    Mirrors `mpc_sos_fade.execution._freeze_fib`'s `min(stamps)` so both bots anchor a drawn fib
    the same way. None when neither anchor is datable — a leg whose swing predates the replay has
    no honest start here, and inventing one puts the drawing on the wrong candle."""
    known = [t for t in stamps if t is not None]
    return min(known) if known else None


@dataclass(frozen=True)
class BLegState:
    """One bar's B-LEG watch, per side — what the execution layer rests a limit off.

    `*_top`/`*_bot` = the frozen SZ band (0.5 / 0.382 of the SOS leg); the entry limit
    rests at the 0.5 edge (`l_top` for longs, `s_bot` for shorts). `*_inv` = the leg
    origin (fib 1.0), the stop anchor and the invalidation level. `*_tgt` = the expansion
    extreme, the TP2 reference. `*_on` = the leg is live and watching; `*_tap` = price has
    tapped the band (a tapped leg no longer arms / can be replaced). `*_bar` = the bar the
    leg armed on (the one-trade-per-leg key + the staleness clock).

    `*_ext` and `*_leg_ms` are REPORTING ONLY — no rule reads them. They complete the fib this
    bot prices off: `*_inv` is its 1.0 and `*_ext` its 0.0, so the two together are the whole
    leg, and `*_leg_ms` is the bar it started on. Frozen and re-frozen with the band, never
    afterwards — `*_tgt` is the one that keeps tracking, and it is a DIFFERENT number (the
    expansion extreme price ran to, which is past the leg once a target is exceeded)."""

    l_top: Optional[float]
    l_bot: Optional[float]
    l_inv: Optional[float]
    l_tgt: Optional[float]
    l_on: bool
    l_tap: bool
    l_bar: Optional[int]
    s_top: Optional[float]
    s_bot: Optional[float]
    s_inv: Optional[float]
    s_tgt: Optional[float]
    s_on: bool
    s_tap: bool
    s_bar: Optional[int]
    # Reporting only, appended so every field above keeps its required-ness.
    l_ext: Optional[float] = None
    l_leg_ms: Optional[int] = None
    s_ext: Optional[float] = None
    s_leg_ms: Optional[int] = None


class BLegTracker:
    """Streaming Signals+SeqState -> BLegState. One instance per backtest run.

    `tf_seconds` is the chart timeframe in seconds (Pine `timeframe.in_seconds()`), used to
    convert `bleg_max_days` into the staleness BAR cap so weekends/the daily close don't
    burn the clock. The driver infers it from the frame's bar spacing.
    """

    def __init__(self, config, tf_seconds: int = 900) -> None:
        self._cfg = config
        self._tf_seconds = tf_seconds
        # Pine: int(math.max(1, math.round(bLegMaxDays * 86400 / timeframe.in_seconds()))).
        # math.round is round-half-away-from-zero, so floor(x + 0.5), not Python's banker's round.
        self._bleg_max = int(max(1, math.floor(config.bleg_max_days * 86400 / tf_seconds + 0.5)))

        # long leg (Pine bLegL_*)
        self._l_top: Optional[float] = None
        self._l_bot: Optional[float] = None
        self._l_inv: Optional[float] = None
        self._l_tgt: Optional[float] = None
        self._l_on = False
        self._l_tap = False
        self._l_bar: Optional[int] = None
        self._l_ext: Optional[float] = None      # fib 0.0 of the frozen leg (reporting only)
        self._l_leg_ms: Optional[int] = None     # the bar the frozen leg started on
        # short leg (Pine bLegS_*)
        self._s_top: Optional[float] = None
        self._s_bot: Optional[float] = None
        self._s_inv: Optional[float] = None
        self._s_tgt: Optional[float] = None
        self._s_on = False
        self._s_tap = False
        self._s_bar: Optional[int] = None
        self._s_ext: Optional[float] = None
        self._s_leg_ms: Optional[int] = None

    @property
    def bleg_max(self) -> int:
        return self._bleg_max

    def update(self, sig, seq) -> BLegState:
        idx, close, high, low = sig.index, sig.close, sig.high, sig.low

        # ── 1. Freeze the SZ band on every SOS (Pine 3697-3724) ──
        if sig.bull_sos and sig.bull_bos_high is not None and sig.bull_bos_low is not None \
                and sig.bull_bos_high > sig.bull_bos_low:
            rng = sig.bull_bos_high - sig.bull_bos_low
            new = sig.bull_bos_low + rng * 0.5
            was = self._l_on and not self._l_tap
            keep = was and self._l_top is not None and abs(new - close) <= abs(self._l_top - close)
            if not keep:
                self._l_bot = sig.bull_bos_low + rng * 0.382
                self._l_top = new
                self._l_inv = sig.bull_bos_low
                self._l_tgt = max(self._l_tgt if self._l_tgt is not None else high, high) if was else high
                self._l_tap = False
                self._l_on = was
                self._l_bar = idx if was else None
                # Reporting only — the leg this band was cut from, taken in the same breath as
                # the band so a migration re-takes both and they can never describe two legs.
                self._l_ext = sig.bull_bos_high
                self._l_leg_ms = _leg_start(sig.bull_bos_low_ms, sig.bull_bos_high_ms)
        if sig.bear_sos and sig.bear_bos_high is not None and sig.bear_bos_low is not None \
                and sig.bear_bos_high > sig.bear_bos_low:
            rng = sig.bear_bos_high - sig.bear_bos_low
            new = sig.bear_bos_high - rng * 0.5
            was = self._s_on and not self._s_tap
            keep = was and self._s_bot is not None and abs(new - close) <= abs(self._s_bot - close)
            if not keep:
                self._s_top = sig.bear_bos_high - rng * 0.382
                self._s_bot = new
                self._s_inv = sig.bear_bos_high
                self._s_tgt = min(self._s_tgt if self._s_tgt is not None else low, low) if was else low
                self._s_tap = False
                self._s_on = was
                self._s_bar = idx if was else None
                self._s_ext = sig.bear_bos_low
                self._s_leg_ms = _leg_start(sig.bear_bos_high_ms, sig.bear_bos_low_ms)

        # ── 2. Track the expansion extreme until the leg arms (Pine 3728-3731) ──
        if self._l_top is not None and not self._l_on:
            self._l_tgt = max(self._l_tgt if self._l_tgt is not None else high, high)
        if self._s_top is not None and not self._s_on:
            self._s_tgt = min(self._s_tgt if self._s_tgt is not None else low, low)

        # ── 3. Arm on the REV's death-by-continuation-BOS (Pine 3734-3737) ──
        if seq.bleg_arm_l and self._l_top is not None:
            self._l_on = True
            self._l_bar = idx
        if seq.bleg_arm_s and self._s_top is not None:
            self._s_on = True
            self._s_bar = idx

        # ── 4. Tap + death (Pine 3749-3758) ──
        if self._l_on:
            if low <= self._l_top:
                self._l_tap = True
            if close < self._l_inv or (self._l_bar is not None and idx - self._l_bar > self._bleg_max):
                self._l_on = False
        if self._s_on:
            if high >= self._s_bot:
                self._s_tap = True
            if close > self._s_inv or (self._s_bar is not None and idx - self._s_bar > self._bleg_max):
                self._s_on = False

        return BLegState(
            l_top=self._l_top, l_bot=self._l_bot, l_inv=self._l_inv, l_tgt=self._l_tgt,
            l_on=self._l_on, l_tap=self._l_tap, l_bar=self._l_bar,
            s_top=self._s_top, s_bot=self._s_bot, s_inv=self._s_inv, s_tgt=self._s_tgt,
            s_on=self._s_on, s_tap=self._s_tap, s_bar=self._s_bar,
            l_ext=self._l_ext, l_leg_ms=self._l_leg_ms,
            s_ext=self._s_ext, s_leg_ms=self._s_leg_ms,
        )
