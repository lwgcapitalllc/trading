"""FftStrategy — the first touch of the 5m first leg's 61.8, with the 15m behind it and the 1m against.

    1m bars ──(the lab's / live runner's stack)──> 1m trend and breaks
            ──ClockFrame(5)──> EngineStack ──> the 5m trend, its BOS count, the FFT fib, liquidity
            ──ClockFrame(15)─> StructureEngine ──> the 15m trend
                                     │
                     rules 1-10 of docs/FFT_SPEC.md, at every 1m close
                                     │
                            FftExecution — one resting limit, one position

🔴 **EVERY DECISION IS MADE AT A 1-MINUTE CLOSE, FOR THE NEXT MINUTE, AND THE ORDER IT PRODUCES IS
THE ONE A BROKER WOULD HOLD.** The limit decided at 10:03's close is the order that meets 10:04's
prices. Nothing is decided inside a minute and then filled inside that same minute — the study's
own rule ("gates on the minute BEFORE the fill") read as an order that a live bot can place.

⚠ **The engines are the canonical ones, imported and never copied.** The 5m stack is built with the
exact switches the study used, so the Structure fib adopts internal swings (MPC Jarvis's default)
exactly as it did there. `docs/FFT_SPEC.md` → *How it is proven* says why there is no Pine twin.

⚠ **A touch spends the leg whether or not the bot could trade it.** That is the study's definition
of "first touch" (a first touch the gates refused is still the first touch) and it is what makes
the second one the SECOND. Every spent leg is recorded in `touches`, traded or not, with the gate
that stopped it — that list is what `tools/compare_study.py` matches against the study.
"""

from __future__ import annotations

import sys
import time as _time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))
_ROOT = Path(__file__).resolve().parents[3]
for _p in (_ROOT, _ROOT / "engines", _ROOT / "engines" / "market_structure"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402
from live_contract import PassThroughSequence, PassThroughSignals  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from time_flat import NY, HolidayCalendar  # noqa: E402

from .config import LEVEL_KEY, FftConfig  # noqa: E402
from .execution import FftExecution, Setup  # noqa: E402
from .frames import Candle, ClockFrame  # noqa: E402

# A gap between two 1-minute bars longer than this is the market being SHUT — a weekend or a
# holiday — never a quiet minute. The study's own threshold, so the two agree on what a closure is.
CLOSURE_MS = 12 * 3_600_000
# How many closed 5m candles are remembered for looking up where a leg's extreme printed. The 5m
# stack's own history is bounded at 2,000 bars (the Pine's max_bars_back), so a leg older than this
# cannot be drawn by the engine either.
KEEP_5M = 2_500

# Why a touched leg was not traded. One code per rule of docs/FFT_SPEC.md, in the order they are
# checked, so the first failing rule is the one recorded.
WHY = {
    "side_off": "that side is switched off",
    "trend5": "rule 1 — the 5m trend is not the fib's direction",
    "bos": "rule 2 — not the 5m first leg",
    "trend15": "rule 3 — the 15m trend is not with the trade",
    "dir1": "rule 4 — the 1m trend is not against the trade",
    "brk1": "rule 5 — the 1m broke in the trade's direction since the extreme",
    "closure": "rule 9 — the market shut inside the leg",
    "calendar": "rule 9 — the next minute is after a weekend or holiday close",
    "ext_unknown": "the leg's extreme is older than the 5m history kept",
    "busy": "rule 10 — an FFT trade is already open",
    "second_off": "second touch — switched off",
    "unsized": "no size — the stop distance is zero",
}


@dataclass
class Row5:
    """The 5m picture at the close of one 5m candle — what a trader sees on the chart."""

    index: int
    close: float
    dir: int  # the fib's direction
    sdir: int  # the 5m structure trend
    levels: Dict[str, float]
    e1_done: bool
    origin: int  # the fib's 1.0 anchor bar (5m index) — with `dir`, the leg's identity
    ext_loc: int  # the fib's 0.0 anchor bar (5m index)
    nbos: int  # continuation BOS in `dir` since its shift
    active_lo: Tuple[float, ...] = ()
    active_hi: Tuple[float, ...] = ()


@dataclass
class _Leg:
    """What is known about one leg's touches."""

    first_bar: Optional[int] = None  # chart bar of the first touch
    tp1_bar: Optional[int] = None  # chart bar that first reached TP1 after it, if it did first
    dead: bool = False  # the 1.0 printed before TP1: no second touch
    second_done: bool = False
    levels: Dict[str, float] = field(default_factory=dict)  # the ladder at the first touch


class FftStrategy:
    def __init__(
        self,
        config: Optional[FftConfig] = None,
        initial_capital: float = 10_000.0,
        cost_profile=None,
        *,
        account=None,
        leg: str = "strat",
        record_bars: bool = False,
    ) -> None:
        self.config = config or FftConfig()
        self.execution = FftExecution(
            self.config,
            initial_capital=initial_capital,
            profile=cost_profile,
            account=account,
            leg=leg,
        )
        # ── the LIVE contract ── one decision per bar, so the first two stages are honest empty
        # seams. See strategies/python/live_contract.py.
        self.signals = PassThroughSignals()
        self.sequence = PassThroughSequence()
        self.execution._strategy = self

        from backtest.replay import EngineConfig, EngineStack

        # The study's exact 5m switches (`five_minute_run`): the fib, sniper, gaps, liquidity and
        # sessions on; macro, internal FIB and RSI off. ⚠ `internal=False` switches off the
        # Internal FIB only — internal STRUCTURE still runs and the Structure fib still adopts its
        # swings, which is what MPC Jarvis draws by default.
        self._stack5 = EngineStack(EngineConfig(macro=False, internal=False, rsi=False))
        self._eng15 = StructureEngine()
        self._f5 = ClockFrame(5)
        self._f15 = ClockFrame(15)
        self._cal = HolidayCalendar(17)

        self.row5: Optional[Row5] = None
        self.dir15 = 0
        self.dir1 = 0
        self._nb = {1: 0, -1: 0}
        self._candles5: Dict[int, Candle] = {}
        self._order5: deque = deque()
        self._swept: Dict[int, Tuple[Tuple[float, ...], Tuple[float, ...]]] = {}
        self._last_break = {1: -1, -1: -1}
        self._last_closure = -1
        self._prev_ms: Optional[int] = None
        self._dropped = False  # a new 0.0 extreme printed in the 5m window being built
        self._legs: Dict[Tuple[int, int], _Leg] = {}
        self._decision: Optional[dict] = None  # what the last close decided for this minute
        # A buy limit the BID reached and the ASK did not — only possible with bid/ask fills on.
        # A real limit stays at the broker, so it keeps resting until it fills or TP1 prints (the
        # setup left without us): the study's costed run (`through_fill`) priced it exactly so.
        self._carry: Optional[dict] = None
        self._carry_setup: Optional[Setup] = None

        self.touches: List[Setup] = []
        self.record_bars = record_bars
        self.bars: List[tuple] = []

    # ── what the platform must build ─────────────────────────────────────────
    @staticmethod
    def engine_config():
        """The stack the platform runs on the 1-MINUTE bars: structure only, pivot length 15.

        The 5m and 15m engines run inside this strategy on candles it builds itself, so the chart
        frame's stack has nothing else to do — every other engine off, not asked.
        """
        from backtest.replay import EngineConfig

        return EngineConfig(
            major_length=15,
            fib=False,
            sniper=False,
            macro=False,
            internal=False,
            fvg=False,
            rsi=False,
            liquidity=False,
            sessions=False,
        )

    def set_timeframe_minutes(self, minutes: int) -> None:
        if int(minutes) != 1:
            raise ValueError(
                f"FFT runs on 1-minute bars and builds its 5m and 15m from them; it was handed a "
                f"{minutes}-minute feed. On any other frame the 1m rules cannot be read at all."
            )

    # ── the frames ───────────────────────────────────────────────────────────
    def _on_5m(self, c: Candle) -> None:
        from backtest.replay.loop import ReplayBar

        s = self._stack5.step(
            ReplayBar(
                index=c.index,
                timestamp_ms=c.start_ms,
                time=pd.Timestamp(c.start_ms, unit="ms"),
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
            )
        )
        ext = s.structure.external
        if ext.bull_bos:
            self._nb[1] = 0 if ext.bull_sos else self._nb[1] + 1
        if ext.bear_bos:
            self._nb[-1] = 0 if ext.bear_sos else self._nb[-1] + 1
        self._candles5[c.index] = c
        self._order5.append(c.index)
        lq = s.liquidity
        sw_lo = tuple(x.price for x in lq.mitigated if x.rule == "sweep_low") if lq else ()
        sw_hi = tuple(x.price for x in lq.mitigated if x.rule == "sweep_high") if lq else ()
        if sw_lo or sw_hi:
            self._swept[c.index] = (sw_lo, sw_hi)
        while len(self._order5) > KEEP_5M:
            old = self._order5.popleft()
            self._candles5.pop(old, None)
            self._swept.pop(old, None)
        self._dropped = False
        f = s.fib
        if f is None or not f.active or f.direction == 0:
            self.row5 = None
            return
        d = f.direction
        self.row5 = Row5(
            index=c.index,
            close=c.close,
            dir=d,
            sdir=self._stack5.structure.dir,
            levels={k: f.levels[k] for k in ("E1", "E2", "E4", "1.0", "TP1", "TP2", "TP3")},
            e1_done="E1" in f.touched_so_far,
            origin=f.asl_loc if d == 1 else f.ash_loc,
            ext_loc=f.ash_loc if d == 1 else f.asl_loc,
            nbos=self._nb[d],
            active_lo=tuple(
                sorted((x.price for x in lq.active if x.rule == "sweep_low"), reverse=True)[:3]
            )
            if lq
            else (),
            active_hi=tuple(sorted(x.price for x in lq.active if x.rule == "sweep_high")[:3])
            if lq
            else (),
        )

    def _on_15m(self, c: Candle) -> None:
        self._eng15.update(Bar(index=c.index, open=c.open, high=c.high, low=c.low, close=c.close))
        self.dir15 = self._eng15.dir

    def _close_candles(self, cs5, cs15) -> None:
        for c in cs5:
            self._on_5m(c)
        for c in cs15:
            self._on_15m(c)

    # ── one minute ───────────────────────────────────────────────────────────
    def step(self, bar_state):
        cfg = self.config
        bar = bar_state.bar
        i, ts = bar.index, bar.timestamp_ms
        if self._prev_ms is not None and ts - self._prev_ms > CLOSURE_MS:
            self._last_closure = i
        self._prev_ms = ts

        # 1. A candle a LATER window's bar proves complete is handed out before this bar is used —
        #    every price in it is older than this bar.
        a5 = self._f5.close_by_arrival(ts)
        a15 = self._f15.close_by_arrival(ts)
        self._close_candles([a5] if a5 else [], [a15] if a15 else [])

        # 2. The order decided at the last close meets this bar's prices.
        decided = self._decision
        self._decision = None
        fill = self.execution.resolve(i, ts, bar.open, bar.high, bar.low)
        if self._carry is not None:
            if fill is not None and fill.key == self._carry["key"]:
                if self._carry_setup is not None:
                    self._carry_setup.traded, self._carry_setup.why = True, None
                    self._carry_setup.fill_price = fill.price
                self._carry = self._carry_setup = None
            elif self._carry_tp1_printed(bar.high, bar.low):
                self._carry = self._carry_setup = None

        # 3. Touch bookkeeping against the 5m picture this minute was traded on.
        self._touch(i, ts, bar.high, bar.low, decided, fill)

        # 4. The 1m structure, already stepped on this bar by the platform's stack.
        self.dir1 = bar_state.snapshot.direction
        ext1 = bar_state.structure.external
        if ext1.bull_bos or ext1.bull_sos:
            self._last_break[1] = i
        if ext1.bear_bos or ext1.bear_sos:
            self._last_break[-1] = i

        # 5. This bar joins its 5m and 15m windows; a window it ENDS closes now.
        c5 = self._f5.add(i, ts, bar.open, bar.high, bar.low, bar.close)
        c15 = self._f15.add(i, ts, bar.open, bar.high, bar.low, bar.close)
        self._close_candles([c5] if c5 else [], [c15] if c15 else [])

        # 6. The order for the next minute.
        self._decision = self._decide(i, ts)
        self.execution.set_pending(self._decision.get("order") if self._decision else None)

        if self.record_bars:
            r = self.row5
            self.bars.append(
                (
                    i,
                    ts,
                    self.dir1,
                    self.dir15,
                    r.sdir if r else 0,
                    r.dir if r else 0,
                    r.nbos if r else -1,
                    bool(self._decision and self._decision.get("order")),
                )
            )
        return self._decision

    # ── the touch ────────────────────────────────────────────────────────────
    def _armed(self, r: Row5) -> bool:
        """The study's scan preconditions for a 5m window (`run()`): the trend agrees with the fib
        and the last 5m close sits beyond the 61.8. Not a gate — a leg failing this is not being
        pulled back into at all."""
        return r.sdir == r.dir and (r.close - r.levels["E1"]) * r.dir > 0

    def _touch(self, i: int, ts: int, high: float, low: float, decided, fill) -> None:
        r = self.row5
        # TP1 / 1.0 watch for every leg whose first touch has printed — the second touch needs it.
        for key, leg in self._legs.items():
            if leg.first_bar is None or leg.tp1_bar is not None or leg.dead or leg.first_bar >= i:
                continue
            lv = leg.levels
            d = key[0]
            if (low <= lv["1.0"]) if d == 1 else (high >= lv["1.0"]):
                leg.dead = True
            elif (high >= lv["TP1"]) if d == 1 else (low <= lv["TP1"]):
                leg.tp1_bar = i
        if r is None or not self._armed(r) or self._dropped:
            return
        d, lv = r.dir, r.levels
        key = (d, r.origin)
        leg = self._legs.get(key)
        if leg is None or leg.first_bar is None:
            if r.e1_done:
                return
            kind = "first"
        elif (
            leg.tp1_bar is not None
            and not leg.second_done
            and self._window_start(i, ts) > leg.tp1_bar
        ):
            kind = "second"
        else:
            return
        if (high > lv["TP3"]) if d == 1 else (low < lv["TP3"]):
            # A new 0.0 extreme redraws the fib at the next 5m close; nothing more this window.
            self._dropped = True
            return
        if not ((low <= lv["E1"]) if d == 1 else (high >= lv["E1"])):
            return
        if leg is None:
            leg = self._legs[key] = _Leg(levels=dict(lv))
        if kind == "first":
            leg.first_bar = i
        else:
            leg.second_done = True
        traded = fill is not None and fill.key == key
        why = None
        if not traded:
            why = (decided or {}).get("why") if (decided or {}).get("key") == key else None
            why = why or ("unfilled" if (decided or {}).get("key") == key else "not_decided")
        setup = Setup(
            kind=kind,
            bar=i,
            ts_ms=ts,
            dir=d,
            key=key,
            levels=dict(lv),
            nbos=r.nbos,
            traded=traded,
            why=why,
            fill_price=fill.price if traded else None,
            swept=self._swept_since(r, ts, d, high, low),
        )
        self.touches.append(setup)
        order = (decided or {}).get("order")
        if (
            not traded
            and order is not None
            and (decided or {}).get("key") == key
            and self.execution._bid_ask()
        ):
            self._carry, self._carry_setup = order, setup
            setup.why = "unfilled — the ask has not reached the limit yet"
        if kind == "first" and ((low <= lv["1.0"]) if d == 1 else (high >= lv["1.0"])):
            leg.dead = True  # the touch minute itself reached the 1.0 — no TP1 first, no second
        # Setups-only housekeeping: forget legs nobody can touch again.
        if len(self._legs) > 500:
            for k in [k for k, v in self._legs.items() if v.dead or v.second_done][:250]:
                self._legs.pop(k, None)

    def _window_start(self, i: int, ts: int) -> int:
        """Chart index of the first bar of the 5m window bar `i` (at `ts`) belongs to, asked
        BEFORE bar `i` joins it. The study only looks for a second touch in a 5m window that
        STARTS after the first touch reached TP1."""
        f = self._f5
        if f._key is None or f._emitted or f.window_of(ts) != f._key:
            return i
        return f._first

    # ── the A+ label ─────────────────────────────────────────────────────────
    def _swept_since(self, r: Row5, ts: int, d: int, high: float, low: float) -> bool:
        """Did the pullback take a day / session / H4 level on its own side between the leg's
        extreme and bar `i`? The study's `sweep()`: levels swept on the closed 5m candles after the
        extreme, plus the live window's own low (high) so far against the levels active at its
        open. Reporting only."""
        for j in range(r.ext_loc + 1, r.index + 1):
            got = self._swept.get(j)
            if got and (got[0] if d == 1 else got[1]):
                return True
        # The window this bar belongs to, so far, INCLUDING this bar (it has not joined yet).
        f = self._f5
        if f._key is not None and not f._emitted and f.window_of(ts) == f._key:
            low, high = min(low, f.building_low), max(high, f.building_high)
        if d == 1:
            return any(low < p for p in r.active_lo)
        return any(high > p for p in r.active_hi)

    # ── the decision ─────────────────────────────────────────────────────────
    def _next_minute_shut(self, ts: int) -> bool:
        """Does the NEXT minute start at or after a close that the market stays shut through —
        a weekend or a holiday, anything longer than the daily one-hour break?

        ⚠ The calendar, never the data: a live bot cannot see that the next bar is two days away,
        and a resting order left over a weekend fills at the reopen — the gap the study excluded.

        ⚠ **The session is dated by its New York CLOSE, and a minute after the close belongs to
        nothing.** Sunday 18:00 New York is the reopen: its date has no close hour of its own, so
        it is never refused here. The first version asked "is today a closed day?" and refused
        every Sunday-evening minute — three study trades on holiday weekends went missing.

        ⚠ **Two shapes of break count, and a plain "tomorrow is a holiday" is NOT one of them.**
        The shared calendar marks Thanksgiving Day closed, but PU Prime trades it until about 13:00
        New York (MEASURED 2020-11-26: Wednesday's session ran straight on, then a five-hour gap).
        Refusing every evening before a closed date lost a study trade that night. So: a weekend-
        length break (`is_last_before_long_break`), or an EARLY close followed by a shut day
        (Christmas Eve and New Year's Eve midweek) — the only holiday shape long enough to matter.
        """
        t = datetime.fromtimestamp((ts + 60_000) / 1000.0, tz=timezone.utc).astimezone(NY)
        day = t.date()
        hour = self._cal.close_hour_ny(day)
        if hour is None or t.hour < hour:
            return False
        if self._cal.is_last_before_long_break(day):
            return True
        return self._cal.is_early_close(day) and self._cal.is_closed(day + timedelta(days=1))

    def _carry_tp1_printed(self, high: float, low: float, order: Optional[dict] = None) -> bool:
        o = order or self._carry
        tp1 = o["levels"]["TP1"]
        return (high >= tp1) if o["pend"].dir > 0 else (low <= tp1)

    def _decide(self, i: int, ts: int) -> Optional[dict]:
        cfg = self.config
        if self._carry is not None:
            if not self.execution.is_flat:
                self._carry = self._carry_setup = None
                return None
            return {
                "key": self._carry["key"],
                "kind": self._carry["kind"],
                "why": None,
                "order": self._carry,
            }
        r = self.row5
        if r is None or not self._armed(r) or self._dropped:
            return None
        d, lv = r.dir, r.levels
        key = (d, r.origin)
        leg = self._legs.get(key)
        if leg is None or leg.first_bar is None:
            if r.e1_done:
                return None
            kind = "first"
        elif (
            leg.tp1_bar is not None
            and not leg.second_done
            and (i + 1 if self._f5._emitted else self._f5._first) > leg.tp1_bar
        ):
            kind = "second"
        else:
            return None
        out = {"key": key, "kind": kind, "why": None, "order": None}

        def no(code: str) -> dict:
            out["why"] = code
            return out

        if not (cfg.exec_longs if d == 1 else cfg.exec_shorts):
            return no("side_off")
        if cfg.max_bos >= 0 and r.nbos > cfg.max_bos:
            return no("bos")
        if cfg.req_15m and self.dir15 != d:
            return no("trend15")
        c = self._candles5.get(r.ext_loc)
        if c is None:
            return no("ext_unknown")
        em = c.high_bar if d == 1 else c.low_bar
        if cfg.req_1m_against:
            if self.dir1 != -d:
                return no("dir1")
            if self._last_break[d] > em:
                return no("brk1")
        if cfg.skip_closure_legs:
            if self._last_closure > em:
                return no("closure")
            if self._next_minute_shut(ts):
                return no("calendar")
        if kind == "second" and not cfg.second_touch:
            return no("second_off")
        if not self.execution.is_flat:
            return no("busy")
        entry = lv["E1"]
        stop = lv[LEVEL_KEY[cfg.stop_level]]
        target = lv[LEVEL_KEY[cfg.target]]
        if (entry - stop) * d <= 0 or (target - entry) * d <= 0:
            return no("unsized")
        order = self.execution.build_order(d, entry, stop, target, key=key, kind=kind, levels=lv)
        if order is None:
            return no("unsized")
        out["order"] = order
        return out

    # ── drivers ──────────────────────────────────────────────────────────────
    def run(self, df, engine_config=None, warmup: int = 0) -> "FftStrategy":
        """Replay a 1-minute frame end to end, the way the lab does."""
        from backtest.replay import EngineStack, iter_bars

        if len(df.index) > 1:
            tf = int(df.index.to_series().diff().min().total_seconds() // 60)
            self.set_timeframe_minutes(tf)
            self.execution.bar_ms = tf * 60_000
        stack = EngineStack(engine_config or self.engine_config())
        t0 = _time.time()
        for bar in iter_bars(df):
            self.step(stack.step(bar))
        self.elapsed_s = _time.time() - t0
        return self
