"""RealignTracker — the setup state machine.

One armed setup per side. The sequence, written long (the short is the exact mirror):

  1. 15m external trend is BULLISH  — a bullish external SOS or BOS
  2. 15m prints a bearish external SOS, and it is the FIRST bearish break since (1).
     That "first" is what makes it a deviation rather than a trend already down.
     The setup ARMS. The external high that stood is latched — it is the target.
  3. 5m structure goes bearish inside the deviation
  4. 5m prints a bullish shift — the realignment. TRIGGER.

The setup dies `realign_window_hrs` after (2) if (4) has not fired.

⚠ Both sides read the chart frame's SWING stream by default; `realign_long_source` /
`realign_short_source` can point either at the engine's INTERNAL stream instead, and replay
measured that worse. See `config.RealignConfig.realign_long_source`.

THE CHART-FRAME ARM (`realign_arm_frame == "Chart frame"`, 2026-09-11) reads all four steps on
the chart's own swing stream, with no second frame:

  1. the chart trends BULLISH — its SOS, then at least `realign_min_trend_breaks` BOS
  2. it prints a bearish SOS — the counter shift. ARMS (no price target is latched: the
     execution sets it in multiples of the trade's own risk — see `execution.realign_target`)
  3. at most `realign_max_counter_breaks` further bearish BOS
  4. a bullish SOS puts the trend back. TRIGGER (or, on "Next break", the first bullish break
     after it)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

# The ordered internal sequence each pattern requires, as (kind, direction-relative-to-trade).
# "any" matches a break of either kind; +1 is with-trend, -1 is counter-trend.
_PATTERNS = {
    "strict":   (("bos", +1), ("sos", -1), ("sos", +1)),
    "opposing": (("sos", -1), ("sos", +1)),
    "any":      (("any", -1), ("sos", +1)),
}


@dataclass
class Armed:
    """One live setup, waiting for its internal realignment."""
    dir: int                      # +1 long, -1 short
    armed_ms: int
    target: float                 # the external extreme that stood before the deviation
    step: int = 0                 # how far through the internal pattern we are
    counter_bar: Optional[int] = None   # newest counter-direction internal break
    counter_ext: Optional[float] = None  # running extreme since that break — the stop
    counter_bos: int = 0                # chart-frame arm: further counter BOS since the arm


@dataclass
class RealignState:
    """Per-bar tracker output. REPORTING plus the one trigger the execution reads."""
    trigger_dir: int = 0          # 0 = nothing fired this bar
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
        # The CHART-frame arm's own trend read, plus how many with-trend BOS the current trend has
        # printed since the break that started it.
        self._c_trend = 0
        self._c_trend_bos = 0

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
        self._armed = [a for a in self._armed
                       if not ((a.dir > 0 and bear and not ev.bear_sos)
                               or (a.dir < 0 and bull and not ev.bull_sos))]

    # ── the 5m side ──────────────────────────────────────────────────────────────
    def update(self, time_ms: int, high: float, low: float,
               ext, internal) -> RealignState:
        """Fold one chart bar in and report any trigger."""
        cfg = self._cfg
        if cfg.realign_arm_frame == "Chart frame":
            return self._update_chart(time_ms, high, low, ext)
        out = RealignState()
        if not self._armed:
            return out

        window_ms = int(cfg.realign_window_hrs * 3_600_000)
        alive: List[Armed] = []
        for a in self._armed:
            if time_ms - a.armed_ms > window_ms:
                continue    # died waiting — the deviation is accepted as a real trend

            src = cfg.realign_long_source if a.dir > 0 else cfg.realign_short_source
            stream = internal if src == "internal" else ext
            steps = _steps(cfg)

            # Track the extreme since the newest counter-direction break — the stop.
            if a.counter_bar is not None:
                a.counter_ext = (min(a.counter_ext, low) if a.dir > 0
                                 else max(a.counter_ext, high))

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
                continue    # consumed — a setup fires once
            alive.append(a)

        self._armed = alive
        out.long_armed = any(a.dir > 0 for a in self._armed)
        out.short_armed = any(a.dir < 0 for a in self._armed)
        return out

    # ── the chart-frame arm ──────────────────────────────────────────────────────
    def _update_chart(self, time_ms: int, high: float, low: float, ev) -> RealignState:
        """The whole sequence on the chart frame's swing stream.

        Setups already armed are walked over this bar FIRST, and only then is the bar folded
        into the arm state — the order the rule reads in.

        ⚠ On the engine's own stream that order is NOT observable. MEASURED over 467,352 5m bars
        (5,265 breaks): no bar ever carries a bullish and a bearish break together, because a
        break confirms on a close and one close cannot cross both swings. So this bar's events
        can never touch a setup armed on this bar. What really stops the arming SOS counting as
        its own counter break is `ctr_bos` excluding SOS bars below.
        """
        cfg = self._cfg
        out = RealignState()
        window_ms = int(cfg.realign_window_hrs * 3_600_000)
        alive: List[Armed] = []
        for a in self._armed:
            if time_ms - a.armed_ms > window_ms:
                continue    # died waiting
            if a.dir > 0:
                with_sos, ctr_sos = ev.bull_sos, ev.bear_sos
                with_bos = ev.bull_bos and not ev.bull_sos
                ctr_bos = ev.bear_bos and not ev.bear_sos
                a.counter_ext = min(a.counter_ext, low)
            else:
                with_sos, ctr_sos = ev.bear_sos, ev.bull_sos
                with_bos = ev.bear_bos and not ev.bear_sos
                ctr_bos = ev.bull_bos and not ev.bull_sos
                a.counter_ext = max(a.counter_ext, high)

            fired = False
            if a.step == 0:
                if ctr_bos:
                    a.counter_bos += 1
                    cap = cfg.realign_max_counter_breaks
                    if cap is not None and a.counter_bos > cap:
                        continue    # the pullback kept breaking — it became a trend
                if with_sos:
                    if cfg.realign_entry_on == "Next break":
                        a.step = 1
                    else:
                        fired = True
            else:
                if ctr_sos:
                    continue    # the realignment failed before its confirming break
                if with_bos:
                    fired = True

            if fired:
                out.trigger_dir = a.dir
                out.trigger_stop = a.counter_ext
                out.trigger_target = a.target
                continue    # consumed — a setup fires once
            alive.append(a)

        self._armed = alive
        self._fold_chart(ev, time_ms, high, low)
        out.long_armed = any(a.dir > 0 for a in self._armed)
        out.short_armed = any(a.dir < 0 for a in self._armed)
        return out

    def _fold_chart(self, ev, time_ms: int, high: float, low: float) -> None:
        """Arm on a counter SOS that ends a trend with enough BOS behind it, then update the
        chart-frame trend read — AFTER arming, for the reason `on_htf` gives.

        ⚠ No structural target is latched and `target` stays 0.0: on this arm the execution
        prices the target in multiples of the trade's own risk, so an arm must not wait on a
        swing level nothing reads (`execution.realign_target` says why).
        """
        cfg = self._cfg
        k = cfg.realign_min_trend_breaks
        if ev.bear_sos and self._c_trend > 0 and self._c_trend_bos >= k and cfg.realign_longs:
            self._armed.append(Armed(dir=+1, armed_ms=time_ms, target=0.0,
                                     counter_bar=1, counter_ext=low))
        if ev.bull_sos and self._c_trend < 0 and self._c_trend_bos >= k and cfg.realign_shorts:
            self._armed.append(Armed(dir=-1, armed_ms=time_ms, target=0.0,
                                     counter_bar=1, counter_ext=high))

        # A CHoCH bar raises its BOS flag too, so the SOS test must come first: a trend's own
        # SOS starts its BOS count at zero, it is not the first BOS of that trend.
        # ⚠ Arming on `*_sos` rather than any counter break is a guard for an input the engine
        # cannot produce once a run has printed its first break: every counter break is flagged SOS
        # (MEASURED 0 exceptions in 5,265, at swing length 15 and 10). No test can reach it.
        # The `bos and trend <= 0` flip IS reachable, once per run: the first break can be a plain
        # BOS (at swing length 10 the 2020-2026 run's is), and it must set the trend.
        if ev.bull_sos or (ev.bull_bos and self._c_trend <= 0):
            self._c_trend, self._c_trend_bos = +1, 0
        elif ev.bull_bos:
            self._c_trend_bos += 1
        if ev.bear_sos or (ev.bear_bos and self._c_trend >= 0):
            self._c_trend, self._c_trend_bos = -1, 0
        elif ev.bear_bos:
            self._c_trend_bos += 1


def _steps(cfg) -> Tuple[Tuple[str, int], ...]:
    """The pattern the realignment must complete, plus one with-trend break on "Next break"."""
    base = _PATTERNS[cfg.realign_pattern]
    if cfg.realign_entry_on == "Next break":
        return base + (("any", +1),)
    return base


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
