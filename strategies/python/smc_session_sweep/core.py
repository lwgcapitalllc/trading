"""The session-sweep decision core — a bar-for-bar transcription of
`strategies/tradingview/smc_session_sweep_strategy.pine`.

**What this file is gated on.** `tools/compare_smc_session_sweep.py` replays a real TradingView
export through this class and diffs every `px_*` column. What it therefore PROVES is everything
downstream of the two structure streams — sessions, the pool, the sweep, the gap scan, the block
ladder, the geometry, sizing, the order lifecycle and the exit ladder.

🔴 **What it does NOT prove, stated here so nobody reads a green gate as more than it is.** The
15-minute direction stream and the 1-minute confirmation stream are FED IN from the export's own
`px_dir` / `px_conf_*` columns. They cannot be derived from a 5-minute chart at all — a minute
bar is not recoverable from a five-minute one — so the gate is silent about them. They come from
`engines/market_structure/`, which carries its own parity gate; that is the file that proves
them, and this one never will.

**The broker.** Pine's emulator is reproduced, not approximated, and the two rules that decide
most fills are:

1. **One bar of order delay.** The script runs at a bar's close; an order it places is live from
   the NEXT bar. So the fill bar carries no stop, and a stop moved to breakeven at a bar's close
   protects from the following bar. This is the same one-bar delay every fill model in this repo
   is built on — see the *Never Do* entry about the wrong-side stop.
2. **Both levels in one bar resolves to the WORSE one.** When a bar's range covers the stop and
   a target, neither Pine nor this file knows the path, so the stop is taken. It makes the result
   slightly worse than reality, which is the safe direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from .config import SessionSweepConfig

__all__ = ["SessionSweepCore", "BarInput", "BarOutput"]

_TZ_ASIA = ZoneInfo("Asia/Tokyo")
_TZ_LDN = ZoneInfo("Europe/London")
_TZ_NY = ZoneInfo("America/New_York")

#: The six session strings are HARDCODED in every Pine file in this repo, not inputs. They decide
#: trades — the sweep pool is read off them — and they are frozen because a divergence between
#: files would be a bug rather than a setting. A change belongs in every file that carries them.
_SESS_ASIA = "0900-1800"
_SESS_LDN = "0800-1700"
_SESS_NY = "0800-1700"

NAN = float("nan")


def _isna(x: Optional[float]) -> bool:
    return x is None or x != x


def _nz(x: Optional[float], alt: float = 0.0) -> float:
    return alt if _isna(x) else float(x)


def _in_session(ms: int, spec: str, tz: ZoneInfo) -> bool:
    """Pine's `time(_, session, tz)` as a boolean, read off the bar's OPEN time.

    ⚠ No day filter, matching a session string with no day spec on a 24/5 symbol. The export
    twin exports what this DECIDED (`inAsia`, `inLdn`, `inNy`), so a timezone error shows up in
    the gate as a disagreeing bit instead of hiding behind two strings that match.
    """
    local = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(tz)
    hm = local.hour * 100 + local.minute
    start, end = (int(p) for p in spec.split("-"))
    if start <= end:
        return start <= hm < end
    return hm >= start or hm < end


@dataclass
class BarInput:
    """One chart bar, plus the streams this core is not allowed to compute for itself."""

    time_ms: int
    open: float
    high: float
    low: float
    close: float
    dir_dir: int            # px_dir       — the direction timeframe's structure direction
    dir_shifts: int         # px_dir_shifts
    conf_dir: int           # px_conf_dir
    conf_shifts: int        # px_conf_shifts — a COUNTER, never a flag; see the note below
    pdh: float              # previous day's high  (request.security "D", lookahead on)
    pdl: float
    pwh: float              # previous week's high
    pwl: float


@dataclass
class BarOutput:
    """Every value the export twin plots, so the comparator can diff them by name."""

    px_sess: int = 0
    px_pool_hi: float = NAN
    px_pool_lo: float = NAN
    px_swp_hi: float = NAN
    px_swp_lo: float = NAN
    px_state: int = 0
    px_poi_bull_t: float = NAN
    px_poi_bull_b: float = NAN
    px_poi_bear_t: float = NAN
    px_poi_bear_b: float = NAN
    px_poi_bits: int = 0
    px_arm_top: float = NAN
    px_arm_bot: float = NAN
    px_ent_l: float = NAN
    px_stp_l: float = NAN
    px_dist_l: float = NAN
    px_t1_l: float = NAN
    px_t2_l: float = NAN
    px_ent_s: float = NAN
    px_stp_s: float = NAN
    px_dist_s: float = NAN
    px_t1_s: float = NAN
    px_t2_s: float = NAN
    px_blk_l: int = 0
    px_blk_s: int = 0
    px_min_stop: float = NAN
    px_pend_dir: int = 0
    px_pos_dir: int = 0
    px_fill: float = NAN
    px_stop_live: float = NAN
    px_sl: float = NAN
    px_tp1: float = NAN
    px_tp2: float = NAN
    px_qty: float = NAN
    px_exec: int = 0
    px_closed_r: float = NAN
    px_atr14: float = NAN


@dataclass
class _Zone:
    top: float
    bot: float
    bull: bool
    tapped: bool
    born: int


@dataclass
class _Order:
    """A resting entry order. `limit is None` means a market order on the next bar."""

    direction: int
    qty: float
    limit: Optional[float]
    placed_bar: int


class SessionSweepCore:
    """Replays the Pine strategy one bar at a time. `step()` returns that bar's plot row."""

    def __init__(self, cfg: SessionSweepConfig):
        self.cfg = cfg
        self.tick = cfg.tick_size

        # ── bar history, for the gap scan's `high[2]` / `low[2]` and ATR
        self._i = -1
        self._highs: List[float] = []
        self._lows: List[float] = []
        self._closes: List[float] = []

        # ── ATR(14) = Wilder's RMA of true range
        self._tr: List[float] = []
        self._atr: Optional[float] = None

        # ── sessions and the pool
        self._in_asia_prev = False
        self._in_ldn_prev = False
        self._raw_sess_prev = 0
        self.asia_hi = NAN
        self.asia_lo = NAN
        self.ldn_hi = NAN
        self.ldn_lo = NAN
        self.pool_hi = NAN
        self.pool_lo = NAN
        self.leg_id = 0

        # ── per-leg state
        self.swept_hi = False
        self.swept_lo = False
        self.swp_hi = NAN
        self.swp_lo = NAN
        self.conf_short = False
        self.conf_long = False
        self.took_leg = False
        self.arm_z_top = NAN
        self.arm_z_bot = NAN
        self.arm_dir = 0
        self.arm_touched = False

        # ── the gap scan's live zone list (the Pine's five parallel arrays)
        self._zones: List[_Zone] = []

        # ── orders, position, book
        self.pend: Optional[_Order] = None
        self.pend_entry = NAN
        self.pend_stop = NAN
        self.pend_t1 = NAN
        self.pend_t2 = NAN
        self.pend_z_top = NAN
        self.pend_z_bot = NAN

        self.pos_dir = 0        # `posDir` — STICKY. Set at the fill, never cleared; the twin
                                # plots it unconditionally, so it outlives the position.
        self.pos_size = 0.0
        self._pending_close = False
        self.pos_entry = NAN
        self.pos_stop = NAN
        self.pos_t1 = NAN
        self.pos_t2 = NAN
        self.pos_z_top = NAN
        self.pos_z_bot = NAN
        self.pos_dist = NAN
        self.pos_qty = NAN
        self.pos_time: Optional[int] = None
        self.pos_stop0 = NAN
        self.t1_done = False
        self.be_shift_done = False
        self.pnl_at_fill = 0.0
        self.net_profit = 0.0

        #: The stop and targets the BROKER is working, i.e. what last bar's script issued. The
        #: live `pos_stop` moves at a bar's close and only protects from the next bar — rule 1
        #: in this module's docstring, and the difference the phantom-exit bug lived in.
        self._broker_stop = NAN
        self._broker_t1 = NAN
        self._broker_run = NAN
        self._broker_two_legs = False
        self._broker_t1_done = False

        self._conf_shifts_prev: Optional[int] = None
        self._pos_size_prev = 0.0

    # ── indicators ────────────────────────────────────────────────────────────────────

    def _push_bar(self, b: BarInput) -> None:
        self._highs.append(b.high)
        self._lows.append(b.low)
        self._closes.append(b.close)

        if self._i == 0:
            tr = b.high - b.low
        else:
            pc = self._closes[-2]
            tr = max(b.high - b.low, abs(b.high - pc), abs(b.low - pc))
        self._tr.append(tr)
        n = 14
        if len(self._tr) < n:
            self._atr = None
        elif len(self._tr) == n:
            self._atr = sum(self._tr) / n          # ta.rma seeds on the SMA of its first n
        else:
            self._atr = (self._atr * (n - 1) + tr) / n

    # ── step 4, the gap scan ──────────────────────────────────────────────────────────

    def _poi_scan(self) -> tuple:
        """`f_poiScan` — three-candle imbalances, their mitigation, and the nearest live one.

        ⚠ This is a SECOND implementation of nothing: `engines/fair_value_gaps/` is canonical and
        the LAB strategy uses it. What lives here is the Pine's own arithmetic, transcribed, so
        the gate compares like with like. The two are reconciled in `strategy.py`.
        """
        cfg = self.cfg
        untouched_only = cfg.pb_poi_untouched
        i = self._i
        # `thr` is zero below the 15-minute; the scan's timeframe is `pbPoiTf`, not the chart's.
        thr = 0.0 if int(cfg.pb_poi_tf if cfg.pb_poi_tf != "Off" else 5) * 60 < 900 else 0.04

        if i >= 2:
            h2 = self._highs[-3]
            l2 = self._lows[-3]
            hi = self._highs[-1]
            lo = self._lows[-1]
            if lo > h2 and (lo - h2) / h2 * 100 > thr:
                self._zones.append(_Zone(top=lo, bot=h2, bull=True, tapped=False, born=i))
            if hi < l2 and (l2 - hi) / l2 * 100 > thr:
                self._zones.append(_Zone(top=l2, bot=hi, bull=False, tapped=False, born=i))
            while len(self._zones) > 30:
                self._zones.pop(0)

            close = self._closes[-1]
            for k in range(len(self._zones) - 1, -1, -1):
                z = self._zones[k]
                aged = i > z.born
                if aged and (close <= z.bot if z.bull else close >= z.top):
                    self._zones.pop(k)
                elif aged and self._highs[-1] >= z.bot and self._lows[-1] <= z.top:
                    z.tapped = True

        bull_t = bull_b = bear_t = bear_b = NAN
        bull_tap = bear_tap = False
        close = self._closes[-1]
        for z in self._zones:
            if untouched_only and z.tapped:
                continue
            if z.bull and z.top < close:
                if _isna(bull_t) or z.top > bull_t:
                    bull_t, bull_b, bull_tap = z.top, z.bot, z.tapped
            if (not z.bull) and z.bot > close:
                if _isna(bear_b) or z.bot < bear_b:
                    bear_t, bear_b, bear_tap = z.top, z.bot, z.tapped
        return bull_t, bull_b, bear_t, bear_b, bull_tap, bear_tap

    # ── step 5, targets ───────────────────────────────────────────────────────────────

    def _targets(self, direction: int, entry: float, dist: float, b: BarInput) -> tuple:
        cfg = self.cfg
        a = (b.pdh if direction == 1 else b.pdl) if cfg.exec_use_tp1 else NAN
        c = (b.pwh if direction == 1 else b.pwl) if cfg.exec_use_tp2 else NAN
        min_dist = cfg.exec_min_rr * dist
        a_ok = not _isna(a) and ((a - entry >= min_dist) if direction == 1 else (entry - a >= min_dist))
        c_ok = not _isna(c) and ((c - entry >= min_dist) if direction == 1 else (entry - c >= min_dist))

        t1 = NAN
        t2 = NAN
        if cfg.exec_tp1_mode == "Fixed R":
            t1 = entry + cfg.exec_tp1_r * dist * direction
            far = NAN
            if a_ok and ((a > t1) if direction == 1 else (a < t1)):
                far = a
            if c_ok and ((c > t1) if direction == 1 else (c < t1)):
                far = c if _isna(far) else (max(far, c) if direction == 1 else min(far, c))
            t2 = far
        elif a_ok and c_ok:
            da = abs(a - entry)
            dc = abs(c - entry)
            t1 = a if da <= dc else c
            t2 = c if da <= dc else a
            if abs(t2 - t1) < dist * 0.25:
                t2 = NAN
        elif a_ok:
            t1 = a
        elif c_ok:
            t1 = c

        if _isna(t1) and cfg.exec_tp_fallback_r > 0:
            t1 = entry + cfg.exec_tp_fallback_r * dist * direction
        return t1, t2

    # ── the broker ────────────────────────────────────────────────────────────────────

    def _broker(self, b: BarInput) -> None:
        """Fill whatever last bar's script left working, against THIS bar's range."""
        if self.pos_size != 0:
            self._broker_exits(b)
        elif self.pend is not None and self.pend.placed_bar < self._i:
            self._broker_entry(b)

    def _broker_entry(self, b: BarInput) -> None:
        o = self.pend
        if o.limit is None:
            fill = b.open
        elif o.direction == 1:
            if b.low > o.limit:
                return
            fill = min(o.limit, b.open)     # a gap through the limit fills at the open, not worse
        else:
            if b.high < o.limit:
                return
            fill = max(o.limit, b.open)
        self.pos_size = o.qty * o.direction
        self.pos_entry = fill
        self.pend = None

    def _broker_exits(self, b: BarInput) -> None:
        if self._pending_close:
            # `strategy.close()` is a MARKET order: it fills at the next bar's open, never at the
            # close that asked for it. One bar of delay, same as every other order here.
            self._pending_close = False
            self._close_all(b.open)
            return
        d = 1 if self.pos_size > 0 else -1
        stop = self._broker_stop
        if _isna(stop):
            return
        hit_stop = (b.low <= stop) if d == 1 else (b.high >= stop)
        if hit_stop:
            # Both levels inside one bar resolves to the stop — see this module's docstring.
            px = min(stop, b.open) if d == 1 else max(stop, b.open)
            self._close_all(px)
            return

        if self._broker_two_legs and not self._broker_t1_done and not _isna(self._broker_t1):
            t1 = self._broker_t1
            if (b.high >= t1) if d == 1 else (b.low <= t1):
                px = max(t1, b.open) if d == 1 else min(t1, b.open)
                self._close_part(px, self.cfg.exec_tp1_pct / 100.0)

        run = self._broker_run
        if self.pos_size != 0 and not _isna(run):
            if (b.high >= run) if d == 1 else (b.low <= run):
                px = max(run, b.open) if d == 1 else min(run, b.open)
                self._close_all(px)

    def _close_part(self, px: float, frac: float) -> None:
        qty = abs(self.pos_size) * frac
        self.net_profit += (px - self.pos_entry) * qty * self.pos_dir
        self.pos_size -= qty * self.pos_dir

    def _close_all(self, px: float) -> None:
        qty = abs(self.pos_size)
        self.net_profit += (px - self.pos_entry) * qty * self.pos_dir
        self.pos_size = 0.0

    # ── one bar ───────────────────────────────────────────────────────────────────────

    def step(self, b: BarInput) -> BarOutput:
        cfg = self.cfg
        tick = self.tick
        self._pos_size_prev = self.pos_size

        # ⚠ The bar index advances BEFORE the broker runs, because `placed_bar < self._i` is what
        # encodes the one-bar order delay. Advancing it afterwards made every order one bar late
        # and cost the first fill of the export — caught by the gate, not by a unit test.
        self._i += 1
        self._broker(b)
        live_dir = 1 if self.pos_size > 0 else (-1 if self.pos_size < 0 else 0)
        self._push_bar(b)
        atr14 = self._atr

        just_filled = self.pos_size != 0 and self._pos_size_prev == 0
        just_closed = self.pos_size == 0 and self._pos_size_prev != 0

        # ── sessions, the pool, the sweep ─────────────────────────────────────────────
        in_asia = _in_session(b.time_ms, _SESS_ASIA, _TZ_ASIA)
        in_ldn = _in_session(b.time_ms, _SESS_LDN, _TZ_LDN)
        in_ny = _in_session(b.time_ms, _SESS_NY, _TZ_NY)

        if in_asia:
            self.asia_hi = b.high if (not self._in_asia_prev or _isna(self.asia_hi)) else max(self.asia_hi, b.high)
            self.asia_lo = b.low if (not self._in_asia_prev or _isna(self.asia_lo)) else min(self.asia_lo, b.low)
        if in_ldn:
            self.ldn_hi = b.high if (not self._in_ldn_prev or _isna(self.ldn_hi)) else max(self.ldn_hi, b.high)
            self.ldn_lo = b.low if (not self._in_ldn_prev or _isna(self.ldn_lo)) else min(self.ldn_lo, b.low)

        raw_sess = 2 if in_ny else (1 if in_ldn else 0)
        sess_tradable = cfg.pb_trade_ny if raw_sess == 2 else (cfg.pb_trade_ldn if raw_sess == 1 else False)
        new_leg = raw_sess != self._raw_sess_prev

        if new_leg:
            self.leg_id += 1
            if raw_sess == 1:
                self.pool_hi, self.pool_lo = self.asia_hi, self.asia_lo
            elif raw_sess == 2:
                self.pool_hi, self.pool_lo = self.ldn_hi, self.ldn_lo
            else:
                self.pool_hi = self.pool_lo = NAN
            self.swept_hi = self.swept_lo = False
            self.swp_hi = self.swp_lo = NAN
            self.conf_short = self.conf_long = False
            self.took_leg = False
            self.arm_z_top = self.arm_z_bot = NAN
            self.arm_dir = 0
            self.arm_touched = False

        if raw_sess != 0:
            if not _isna(self.pool_hi) and b.high > self.pool_hi:
                self.swept_hi = True
                self.swp_hi = b.high if _isna(self.swp_hi) else max(self.swp_hi, b.high)
            if not _isna(self.pool_lo) and b.low < self.pool_lo:
                self.swept_lo = True
                self.swp_lo = b.low if _isna(self.swp_lo) else min(self.swp_lo, b.low)

        # ⚠ A COUNTER, not a flag. A boolean read back through `request.security` stays true, so
        # "it JUST shifted" is only recoverable by comparing the count with its own previous bar.
        new_conf_shift = (
            self._conf_shifts_prev is not None
            and b.conf_shifts is not None
            and b.conf_shifts > self._conf_shifts_prev
        )

        in_win_ldn = _in_session(b.time_ms, cfg.exec_win_ldn, _TZ_NY)
        in_win_ny = _in_session(b.time_ms, cfg.exec_win_ny, _TZ_NY)
        in_exec_win = (not cfg.exec_use_windows) or in_win_ldn or in_win_ny

        poi_bull_t, poi_bull_b, poi_bear_t, poi_bear_b, poi_bull_tap, poi_bear_tap = self._poi_scan()

        conf_at_zone = cfg.pb_require_conf and cfg.pb_conf_when == "At the zone (enter at market)"
        poi_off = cfg.pb_poi_tf == "Off" and cfg.pb_require_conf

        if conf_at_zone and raw_sess != 0:
            if self.arm_dir == 0:
                if b.dir_dir == -1 and self.swept_hi and not _isna(poi_bear_t):
                    self.arm_z_top, self.arm_z_bot, self.arm_dir = poi_bear_t, poi_bear_b, -1
                elif b.dir_dir == 1 and self.swept_lo and not _isna(poi_bull_t):
                    self.arm_z_top, self.arm_z_bot, self.arm_dir = poi_bull_t, poi_bull_b, 1
            if not _isna(self.arm_z_top) and b.high >= self.arm_z_bot and b.low <= self.arm_z_top:
                self.arm_touched = True

        if raw_sess != 0 and new_conf_shift:
            place_ok = (not conf_at_zone) or self.arm_touched
            if self.swept_hi and b.conf_dir == -1 and place_ok:
                self.conf_short = True
            if self.swept_lo and b.conf_dir == 1 and place_ok:
                self.conf_long = True

        conf_ok_short = self.conf_short if cfg.pb_require_conf else self.swept_hi
        conf_ok_long = self.conf_long if cfg.pb_require_conf else self.swept_lo

        # ── the minimum-stop floor ────────────────────────────────────────────────────
        mode = cfg.exec_min_stop_mode
        if mode == "% of price":
            min_stop_dist = b.close * cfg.exec_min_stop_val / 100
        elif mode == "Fixed $":
            min_stop_dist = cfg.exec_min_stop_val
        elif mode == "x ATR(14)":
            min_stop_dist = 0.0 if atr14 is None else atr14 * cfg.exec_min_stop_val
        else:
            min_stop_dist = 0.0

        # ── cancel a resting order ────────────────────────────────────────────────────
        just_cancelled = False
        if self.pend is not None and self.pos_size == 0:
            pd = self.pend.direction
            c_ttl = cfg.exec_cancel_bars > 0 and (self._i - self.pend.placed_bar) > cfg.exec_cancel_bars
            c_flip = cfg.exec_cancel_flip and (b.dir_dir != pd)
            c_opp = cfg.exec_cancel_flip and new_conf_shift and b.conf_dir == -pd
            if c_ttl or new_leg or c_flip or c_opp or (not in_exec_win):
                self.pend = None
                just_cancelled = True

        flat = self.pos_size == 0
        busy = (not flat) or self.pend is not None or self.took_leg

        # ── geometry, both sides, armed or refused ────────────────────────────────────
        def zone_entry(direction: int, z_top: float, z_bot: float) -> float:
            prox = z_top if direction == 1 else z_bot
            dist = z_bot if direction == 1 else z_top
            if cfg.exec_zone_entry == "Proximal edge":
                return prox
            if cfg.exec_zone_entry == "Distal edge":
                return dist
            return (z_top + z_bot) / 2

        # short
        if poi_off:
            s_z_top = s_z_bot = NAN
        elif conf_at_zone:
            s_z_top = self.arm_z_top if self.arm_dir == -1 else NAN
            s_z_bot = self.arm_z_bot if self.arm_dir == -1 else NAN
        else:
            s_z_top, s_z_bot = poi_bear_t, poi_bear_b

        if poi_off:
            s_entry = b.close
        elif _isna(s_z_top):
            s_entry = NAN
        else:
            s_entry = b.close if conf_at_zone else zone_entry(-1, s_z_top, s_z_bot)

        if poi_off:
            s_stop = NAN if _isna(self.swp_hi) else self.swp_hi + cfg.exec_sl_buf_tk * tick
        elif _isna(s_z_top):
            s_stop = NAN
        else:
            base = max(s_z_top, self.swp_hi) if (cfg.exec_stop_from == "The sweep extreme" and not _isna(self.swp_hi)) else s_z_top
            s_stop = base + cfg.exec_sl_buf_tk * tick
        s_dist = NAN if (_isna(s_entry) or _isna(s_stop)) else s_stop - s_entry
        s_t1, s_t2 = self._targets(-1, _nz(s_entry, b.close), _nz(s_dist, b.close * 0.001), b)

        # long
        if poi_off:
            l_z_top = l_z_bot = NAN
        elif conf_at_zone:
            l_z_top = self.arm_z_top if self.arm_dir == 1 else NAN
            l_z_bot = self.arm_z_bot if self.arm_dir == 1 else NAN
        else:
            l_z_top, l_z_bot = poi_bull_t, poi_bull_b

        if poi_off:
            l_entry = b.close
        elif _isna(l_z_top):
            l_entry = NAN
        else:
            l_entry = b.close if conf_at_zone else zone_entry(1, l_z_top, l_z_bot)

        if poi_off:
            l_stop = NAN if _isna(self.swp_lo) else self.swp_lo - cfg.exec_sl_buf_tk * tick
        elif _isna(l_z_bot):
            l_stop = NAN
        else:
            base = min(l_z_bot, self.swp_lo) if (cfg.exec_stop_from == "The sweep extreme" and not _isna(self.swp_lo)) else l_z_bot
            l_stop = base - cfg.exec_sl_buf_tk * tick
        l_dist = NAN if (_isna(l_entry) or _isna(l_stop)) else l_entry - l_stop
        l_t1, l_t2 = self._targets(1, _nz(l_entry, b.close), _nz(l_dist, b.close * 0.001), b)

        # ── the block ladder. The ORDER is the message: the first rule to say no owns the tag.
        def block(direction: int) -> int:
            if direction == -1:
                on, entry, stop, dist, t1 = cfg.pb_trade_shorts, s_entry, s_stop, s_dist, s_t1
                conf_ok, wrong_side = conf_ok_short, (not _isna(s_entry) and s_entry <= b.close)
                too_far = (not _isna(s_entry)) and atr14 is not None and s_entry - b.close > cfg.pb_poi_max_atr * (atr14 or 0)
            else:
                on, entry, stop, dist, t1 = cfg.pb_trade_longs, l_entry, l_stop, l_dist, l_t1
                conf_ok, wrong_side = conf_ok_long, (not _isna(l_entry) and l_entry >= b.close)
                too_far = (not _isna(l_entry)) and atr14 is not None and b.close - l_entry > cfg.pb_poi_max_atr * (atr14 or 0)
            swept = self.swept_hi if direction == -1 else self.swept_lo

            if not on:
                return 1
            if b.dir_dir != direction:
                return 2
            if raw_sess == 0 or not sess_tradable:
                return 3
            if not in_exec_win:
                return 11
            if not swept:
                return 4
            if not conf_ok:
                return 5
            if _isna(entry) or _isna(stop) or ((not poi_off) and (not conf_at_zone) and wrong_side):
                return 6
            if (not conf_at_zone) and cfg.pb_poi_max_atr > 0 and atr14 is not None and too_far:
                return 7
            if _isna(dist) or dist <= 0 or dist < min_stop_dist:
                return 8
            if _isna(t1):
                return 9
            if busy:
                return 10
            return 0

        s_blk = block(-1)
        l_blk = block(1)
        arm_short = s_blk == 0
        arm_long = l_blk == 0

        # ── arm ───────────────────────────────────────────────────────────────────────
        equity = cfg.initial_capital + self.net_profit
        if self.pos_size != 0 and not _isna(self.pos_entry):
            equity += (b.close - self.pos_entry) * self.pos_size

        def qty_for(dist: float) -> float:
            if cfg.exec_size_mode == "Fixed contracts":
                return cfg.exec_fixed_qty
            raw = (equity * cfg.exec_risk_pct / 100) / dist if dist > 0 else 0.0
            step = cfg.qty_step
            # TRUNCATED to the venue's quantity step, never rounded — see the note on `qty_step`.
            return math.floor(raw / step + 1e-9) * step if step > 0 else raw

        market_entry = conf_at_zone or poi_off
        if arm_short:
            q = qty_for(s_dist)
            if q > 0:
                self.pend = _Order(-1, q, None if market_entry else s_entry, self._i)
                self.pend_entry, self.pend_stop = s_entry, s_stop
                self.pend_t1, self.pend_t2 = s_t1, s_t2
                self.pend_z_top, self.pend_z_bot = s_z_top, s_z_bot

        if arm_long and self.pend is None:
            q = qty_for(l_dist)
            if q > 0:
                self.pend = _Order(1, q, None if market_entry else l_entry, self._i)
                self.pend_entry, self.pend_stop = l_entry, l_stop
                self.pend_t1, self.pend_t2 = l_t1, l_t2
                self.pend_z_top, self.pend_z_bot = l_z_top, l_z_bot

        # ── the fill, and what the position inherits from the order ───────────────────
        if just_filled:
            self.pos_dir = live_dir
            self.pos_stop = self.pend_stop
            self.pos_t1, self.pos_t2 = self.pend_t1, self.pend_t2
            self.pos_z_top, self.pos_z_bot = self.pend_z_top, self.pend_z_bot
            self.pos_qty = abs(self.pos_size)
            self.pos_dist = abs(self.pos_stop - self.pos_entry)
            self.pos_time = b.time_ms
            self.pnl_at_fill = self.net_profit
            self.t1_done = False
            self.be_shift_done = False
            self.took_leg = True
            self.pos_stop0 = self.pend_stop

        # ── management, at the bar's CLOSE. It protects from the NEXT bar, never this one.
        open_since_prev = self.pos_size != 0 and self._pos_size_prev != 0
        if open_since_prev and not self.t1_done and not _isna(self.pos_t1):
            reached = (b.high >= self.pos_t1) if live_dir == 1 else (b.low <= self.pos_t1)
            if reached:
                self.t1_done = True
                if cfg.exec_be_at_tp1:
                    be = self.pos_entry + cfg.exec_be_buf_tk * tick * live_dir
                    self.pos_stop = max(self.pos_stop, be) if live_dir == 1 else min(self.pos_stop, be)

        if cfg.exec_be_on_shift and open_since_prev and not self.be_shift_done:
            if new_conf_shift and b.conf_dir == -live_dir:
                self.be_shift_done = True
                be = self.pos_entry + cfg.exec_be_buf_tk * tick * live_dir
                self.pos_stop = max(self.pos_stop, be) if live_dir == 1 else min(self.pos_stop, be)

        two_legs = (not _isna(self.pos_t2)) and 0 < cfg.exec_tp1_pct < 100
        run_tgt = self.pos_t2 if two_legs else self.pos_t1
        time_up = (
            cfg.exec_time_stop_hrs > 0
            and not self.t1_done
            and self.pos_time is not None
            and b.time_ms - self.pos_time >= cfg.exec_time_stop_hrs * 3_600_000
        )
        if time_up and self.pos_size != 0:
            self._pending_close = True

        # hand the broker what this bar's script issued, for the NEXT bar
        if self.pos_size != 0:
            self._broker_stop = self.pos_stop
            self._broker_t1 = self.pos_t1
            self._broker_run = run_tgt
            self._broker_two_legs = two_legs
            self._broker_t1_done = self.t1_done
        else:
            self._broker_stop = self._broker_t1 = self._broker_run = NAN
            self._broker_two_legs = False

        closed_r = NAN
        if just_closed:
            pnl = self.net_profit - self.pnl_at_fill
            risk_usd = self.pos_dist * self.pos_qty
            closed_r = pnl / risk_usd if risk_usd > 0 else NAN

        # ── the plot row ──────────────────────────────────────────────────────────────
        out = BarOutput(
            px_sess=raw_sess,
            px_pool_hi=self.pool_hi,
            px_pool_lo=self.pool_lo,
            px_swp_hi=self.swp_hi,
            px_swp_lo=self.swp_lo,
            px_state=(
                (1 if in_asia else 0) + (2 if in_ldn else 0) + (4 if in_ny else 0)
                + (8 if sess_tradable else 0) + (16 if new_leg else 0)
                + (32 if self.swept_hi else 0) + (64 if self.swept_lo else 0)
                + (128 if self.conf_short else 0) + (256 if self.conf_long else 0)
                + (512 if self.took_leg else 0) + (1024 if in_win_ldn else 0)
                + (2048 if in_win_ny else 0) + (4096 if in_exec_win else 0)
                + (8192 if new_conf_shift else 0) + (16384 if conf_at_zone else 0)
                + (32768 if poi_off else 0) + (65536 if self.arm_touched else 0)
                + (131072 if busy else 0) + (262144 if just_cancelled else 0)
            ),
            px_poi_bull_t=poi_bull_t, px_poi_bull_b=poi_bull_b,
            px_poi_bear_t=poi_bear_t, px_poi_bear_b=poi_bear_b,
            px_poi_bits=(1 if poi_bull_tap else 0) + (2 if poi_bear_tap else 0)
                        + (4 if self.arm_dir == 1 else 0) + (8 if self.arm_dir == -1 else 0),
            px_arm_top=self.arm_z_top, px_arm_bot=self.arm_z_bot,
            px_ent_l=l_entry, px_stp_l=l_stop, px_dist_l=l_dist, px_t1_l=l_t1, px_t2_l=l_t2,
            px_ent_s=s_entry, px_stp_s=s_stop, px_dist_s=s_dist, px_t1_s=s_t1, px_t2_s=s_t2,
            px_blk_l=l_blk, px_blk_s=s_blk,
            px_min_stop=min_stop_dist,
            px_pend_dir=0 if self.pend is None else self.pend.direction,
            px_pos_dir=self.pos_dir,
            px_atr14=NAN if atr14 is None else atr14,
            px_exec=(
                (1 if just_filled else 0) + (2 if just_closed else 0)
                + (4 if self.t1_done else 0) + (8 if self.be_shift_done else 0)
                + (16 if two_legs else 0) + (32 if time_up else 0)
                + (64 if arm_long else 0) + (128 if arm_short else 0)
            ),
            px_closed_r=closed_r,
        )
        if self.pos_size != 0:
            out.px_fill = self.pos_entry
            out.px_stop_live = self.pos_stop
            out.px_sl = self.pos_stop0
            out.px_tp1 = self.pos_t1
            out.px_tp2 = self.pos_t2
            out.px_qty = self.pos_qty

        self._in_asia_prev = in_asia
        self._in_ldn_prev = in_ldn
        self._raw_sess_prev = raw_sess
        self._conf_shifts_prev = b.conf_shifts
        return out
