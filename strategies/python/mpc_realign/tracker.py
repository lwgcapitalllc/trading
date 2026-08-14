"""RealignTracker — the setup state machine.

One armed setup per side. The sequence, written long (the short is the exact mirror):

  1. 15m external trend is BULLISH  — a bullish external SOS or BOS
  2. 15m prints a bearish external SOS, and it is the FIRST bearish break since (1).
     That "first" is what makes it a deviation rather than a trend already down.
     The setup ARMS. The external high that stood is latched — it is the target.
  3. 5m structure goes bearish inside the deviation
  4. 5m prints a bullish shift — the realignment. TRIGGER.

The setup dies `realign_window_hrs` after (2) if (4) has not fired.

⚠ EACH SIDE READS A DIFFERENT STREAM, and that is measured rather than stylistic. Shorts
trigger on the engine's INTERNAL structure (iBOS/iSOS); longs trigger on the frame's own
SWING structure, one level coarser. See `config.RealignConfig.realign_long_source`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

# The ordered internal sequence each pattern requires, as (kind, direction-relative-to-trade).
# "any" matches a break of either kind; +1 is with-trend, -1 is counter-trend.
_PATTERNS = {
    "strict": (("bos", +1), ("sos", -1), ("sos", +1)),
    "opposing": (("sos", -1), ("sos", +1)),
    "any": (("any", -1), ("sos", +1)),
}


@dataclass
class Armed:
    """One live setup, waiting for its internal realignment."""

    dir: int  # +1 long, -1 short
    armed_ms: int
    target: float  # the external extreme that stood before the deviation
    step: int = 0  # how far through the internal pattern we are
    counter_bar: Optional[int] = None  # newest counter-direction internal break
    counter_ext: Optional[float] = None  # running extreme since that break — the stop


@dataclass
class RealignState:
    """Per-bar tracker output. REPORTING plus the one trigger the execution reads."""

    trigger_dir: int = 0  # 0 = nothing fired this bar
    trigger_stop: float = 0.0
    trigger_target: float = 0.0
    long_armed: bool = False
    short_armed: bool = False


class RealignTracker:
    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._armed: List[Armed] = []
        # The 15m trend read: +1 after a bullish external break, -1 after a bearish one.
        self._htf_trend = 0

    # ── the 15m side ─────────────────────────────────────────────────────────────
    def on_htf(self, ev, time_ms: int, broken_high, broken_low) -> None:
        """Fold one CLOSED 15m bar's external events in. Called only on an HTF close."""
        cfg = self._cfg
        bull = ev.bull_bos or ev.bull_sos
        bear = ev.bear_bos or ev.bear_sos

        # A LONG setup arms on a bearish SOS that is the first bearish break in an uptrend.
        if ev.bear_sos and self._htf_trend > 0 and cfg.realign_longs:
            tgt = broken_high if broken_high is not None else ev.broken_high_price
            if tgt is not None:
                self._armed.append(Armed(dir=+1, armed_ms=time_ms, target=tgt))
        if ev.bull_sos and self._htf_trend < 0 and cfg.realign_shorts:
            tgt = broken_low if broken_low is not None else ev.broken_low_price
            if tgt is not None:
                self._armed.append(Armed(dir=-1, armed_ms=time_ms, target=tgt))

        # The trend read updates AFTER arming — an SOS both ends the old trend and starts
        # the new one, and the setup is about the trend it ended.
        if bull:
            self._htf_trend = +1
        elif bear:
            self._htf_trend = -1

        # A break against a setup's own direction kills it: the deviation has become a
        # trend, which is exactly the thing this setup bets against.
        self._armed = [
            a
            for a in self._armed
            if not (
                (a.dir > 0 and bear and not ev.bear_sos) or (a.dir < 0 and bull and not ev.bull_sos)
            )
        ]

    # ── the 5m side ──────────────────────────────────────────────────────────────
    def update(self, time_ms: int, high: float, low: float, ext, internal) -> RealignState:
        """Fold one chart bar in and report any trigger."""
        cfg = self._cfg
        out = RealignState()
        if not self._armed:
            return out

        window_ms = int(cfg.realign_window_hrs * 3_600_000)
        alive: List[Armed] = []
        for a in self._armed:
            if time_ms - a.armed_ms > window_ms:
                continue  # died waiting — the deviation is accepted as a real trend

            src = cfg.realign_long_source if a.dir > 0 else cfg.realign_short_source
            stream = internal if src == "internal" else ext
            steps = _PATTERNS[cfg.realign_pattern]

            # Track the extreme since the newest counter-direction break — the stop.
            if a.counter_bar is not None:
                a.counter_ext = min(a.counter_ext, low) if a.dir > 0 else max(a.counter_ext, high)

            fired = False
            for kind, sign in _breaks(stream):
                if sign == -a.dir:
                    a.counter_bar = 1
                    a.counter_ext = low if a.dir > 0 else high
                want_kind, want_sign = steps[a.step]
                if sign == want_sign * a.dir and (want_kind == "any" or want_kind == kind):
                    a.step += 1
                    if a.step == len(steps):
                        fired = True
                        break

            if fired and a.counter_ext is not None:
                out.trigger_dir = a.dir
                out.trigger_stop = a.counter_ext
                out.trigger_target = a.target
                continue  # consumed — a setup fires once
            alive.append(a)

        self._armed = alive
        out.long_armed = any(a.dir > 0 for a in self._armed)
        out.short_armed = any(a.dir < 0 for a in self._armed)
        return out


def _breaks(ev) -> List[Tuple[str, int]]:
    """The (kind, direction) breaks an events object raised this bar, in Pine order.

    ⚠ A CHoCH bar raises BOTH its plain BOS flag and its SOS flag, so it appears twice.
    That is faithful to the engine and is what a consumer must expect — a pattern step
    matching "any" will consume the BOS reading of a bar whose SOS reading it wanted.
    """
    out: List[Tuple[str, int]] = []
    if getattr(ev, "bull_bos", False):
        out.append(("bos", +1))
    if getattr(ev, "bull_sos", False):
        out.append(("sos", +1))
    if getattr(ev, "bear_bos", False):
        out.append(("bos", -1))
    if getattr(ev, "bear_sos", False):
        out.append(("sos", -1))
    return out
