"""Execution — turns the A+ sequence state into orders, and fills them the way
TradingView's broker emulator does.

A port of the STRATEGY EXECUTION block in `indicators/mpc_strategy.pine` (4112-4735):
entry edge → resting limit → TP1/TP2/runner ladder → staged stop → %-risk sizing →
graded R. It runs on top of a small broker emulator (`_Broker`) that reproduces the
two TradingView fill assumptions logic-parity depends on:

  1. **Calc-on-close, one-bar delay.** An order placed while processing bar N's close
     becomes active on bar N+1 — a resting limit never fills on the bar it was placed.
  2. **Intrabar path.** When a bar's range covers both a take-profit and the stop, the
     one that fills first is decided by the open's proximity to the extremes: open
     nearer the high ⇒ price is assumed to travel open→high→low→close (targets first);
     open nearer the low ⇒ open→low→high→close (stop first). This is the single most
     parity-sensitive assumption — `compare_strategy.py` is what confirms it.

Sizing is the Pine's fixed %-risk (`qty = equity·risk% / stopDistance`); R — the unit
the decision stream is graded in — is invariant to account size, so the initial
capital only scales the equity curve, never the parity check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Fill:
    """One order fill this bar — an entry or a (partial) exit."""

    kind: str          # "entry" | "exit"
    order_id: str      # "Long" | "Short" | "L-TP1" | "L-TP2" | "L-RUN" | (short mirror)
    price: float
    qty: float
    dir: int           # +1 long, -1 short (of the position it belongs to)


@dataclass
class Decision:
    """Per-bar decision stream — the columns compare_strategy.py diffs against the
    Pine export. Everything a trade decision hinges on, plus the fills it produced."""

    index: int
    long_armed: bool = False
    short_armed: bool = False
    long_edge: Optional[float] = None
    short_edge: Optional[float] = None
    l_stage: int = 0
    s_stage: int = 0
    long_veto: bool = False
    short_veto: bool = False
    stop: Optional[float] = None          # the active stop of the open trade (if any)
    fills: List[Fill] = field(default_factory=list)
    closed_r: Optional[float] = None      # R booked on the bar a trade closed


@dataclass
class Trade:
    """A completed trade — entry to full close, with the R it made.

    The reporting fields (`*_ms`, `exit_price`, `stop_distance`, `exit_reason`) carry
    no decision weight — they exist so `backtest.output` can build the lab's
    equity_curve / engine_trades without re-deriving them. `exit_price` is the
    qty-weighted mean of the ladder's partial exits, so
    `(exit_price - entry_price) * dir * qty * point_value` reproduces `pnl_usd`.
    `stop_distance` is entry→the stop frozen at PLACEMENT, i.e. the 1R the trade was
    sized against — not the trailed stop it may have exited on.
    """

    dir: int
    entry_index: int
    entry_price: float
    exit_index: int
    qty: float
    risk_usd: float
    pnl_usd: float
    r: float
    entry_ms: int = 0
    exit_ms: int = 0
    exit_price: float = 0.0
    stop_distance: float = 0.0
    exit_reason: str = ""


# ── the resting-order + position model ──────────────────────────────────────────
@dataclass
class _Pending:
    """A resting entry limit, with the stop/target levels frozen at placement."""

    dir: int
    edge: float
    qty: float
    sl: float
    tp1: float
    tp2: float
    sos_bar: Optional[int]


def _intrabar_targets_first(o: float, h: float, l: float) -> bool:
    """TradingView path assumption: True ⇒ price is assumed to reach the HIGH before
    the LOW this bar (open nearer the high), so a long's targets fill before its stop.
    Ties (equal distance) resolve to targets-first, matching the emulator."""
    return abs(o - h) <= abs(o - l)


class Execution:
    def __init__(self, config, initial_capital: float = 1_000_000.0) -> None:
        self._cfg = config
        self._equity_realized = initial_capital  # equity = initial + closed pnl

        # position state
        self._pos_dir = 0                  # 0 flat, +1 long, -1 short
        self._qty = 0.0
        self._entry = 0.0
        self._entry_index = 0
        self._sl = 0.0                     # frozen entry stop (1R yardstick)
        # reporting-only accumulators (see Trade) — never read by a decision
        self._entry_ms = 0
        self._exit_ms = 0
        self._init_stop = 0.0
        self._exit_notional = 0.0
        self._exit_qty = 0.0
        self._exit_reason = ""
        self._tp1 = 0.0
        self._tp2 = 0.0
        self._stage = 0                    # 0 full-stop, 1 BE, 2 stop->TP1 + runner ratchet
        self._max_fav = 0.0
        self._risk_usd = 0.0
        self._filled_qty = 0.0             # how much of the position has exited
        self._sos_bar_open: Optional[int] = None
        self._entry_equity: Optional[float] = None   # equity snapshot at open, for R

        # resting entry orders (one per side; at most one position at a time)
        self._pend_long: Optional[_Pending] = None
        self._pend_short: Optional[_Pending] = None

        # one-trade-per-leg latches (Pine tradedSosL / tradedSosS)
        self._traded_sos_l: Optional[int] = None
        self._traded_sos_s: Optional[int] = None

        self.trades: List[Trade] = []

    # ── public equity read ──
    @property
    def equity(self) -> float:
        return self._equity_realized

    # ── main step ───────────────────────────────────────────────────────────────
    def step(self, sig, seq) -> Decision:
        dec = Decision(index=sig.index)

        # Decision context the Pine computes EVERY bar (not just when flat), so the
        # decision streams line up bar-for-bar: the entry edges, the A+ stage, the veto.
        long_edge, short_edge = self._entry_edges(sig)
        dec.long_edge, dec.short_edge = long_edge, short_edge
        dec.l_stage, dec.s_stage = seq.l_stage, seq.s_stage
        dec.long_veto, dec.short_veto = sig.long_veto, sig.short_veto

        # ── Phase A: fill resting orders against THIS bar (placed last bar) ──
        opened = False
        if self._pos_dir == 0:
            opened = self._try_entry_fill(sig, dec)
        # Exit orders are placed at a bar's close and active the NEXT bar, so a trade
        # never fills an exit on the bar it opened (TradingView one-bar delay).
        if self._pos_dir != 0 and not opened:
            self._manage_open(sig, dec)

        # ── Phase B: at close, (re)place orders for the next bar ──
        if self._pos_dir != 0:
            self._advance_stage(sig)
            dec.stop = self._current_stop()
            # optional force-close on an opposite SOS (Pine execCloseOppSOS)
            if self._cfg.exec_close_opp_sos and (
                (self._pos_dir > 0 and sig.bear_sos) or (self._pos_dir < 0 and sig.bull_sos)
            ):
                self._close_at(sig, sig.close, "opp-SOS", dec)
            # deliberate deviation: force-flat before the daily close (real runs only)
            elif self._cfg.flat_by_close and self._in_flat_window(sig):
                self._close_at(sig, sig.close, "flat-by-close", dec)
        else:
            self._place_entries(sig, seq, dec, dec.long_edge, dec.short_edge)

        return dec

    # ── entry placement (Pine 4264-4507) ─────────────────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        late = cfg.exec_no_late_day and 16 <= sig.ny_hour < 18   # 16:00-17:59 NY block
        w_state, d_state = sig.w_est_state, sig.d_est_state

        # arm-source filter (Pine 4349-4355)
        use_swp_l = cfg.exec_arm_sweep and seq.sos_l_swp
        use_div_l = cfg.exec_arm_div and seq.sos_l_div
        use_swp_s = cfg.exec_arm_sweep and seq.sos_s_swp
        use_div_s = cfg.exec_arm_div and seq.sos_s_div
        arm_ok_l = use_swp_l or use_div_l
        arm_ok_s = use_swp_s or use_div_s

        htf_block_l, htf_block_s = self._htf_exhaustion_block(sig)
        bias_block_l, bias_block_s = self._htf_bias_block(sig)

        long_armed = (cfg.exec_longs and arm_ok_l and not late and not htf_block_l
                      and not bias_block_l and seq.l_sos_bar is not None and sig.fibo_dir == 1
                      and long_edge is not None
                      and (not sig.long_veto or not cfg.exec_respect_veto)
                      and (self._traded_sos_l is None or seq.l_sos_bar != self._traded_sos_l))
        short_armed = (cfg.exec_shorts and arm_ok_s and not late and not htf_block_s
                       and not bias_block_s and seq.s_sos_bar is not None and sig.fibo_dir == -1
                       and short_edge is not None
                       and (not sig.short_veto or not cfg.exec_respect_veto)
                       and (self._traded_sos_s is None or seq.s_sos_bar != self._traded_sos_s))
        dec.long_armed, dec.short_armed = long_armed, short_armed

        # deliberate deviation: no NEW entry inside the flat-by-close window (real runs)
        if cfg.flat_by_close and self._in_flat_window(sig):
            long_armed = short_armed = False

        if long_armed:
            sl = self._sl_anchor(sig) - cfg.exec_sl_buf_tk * cfg.mintick
            dist = long_edge - sl
            deep = long_edge <= sig.fibo_p3       # at/below 0.618
            tp1 = sig.fibo_p2 if deep else sig.fibo_p1   # deep 0.5 / shallow 0.382
            tp2 = sig.fibo_p1 if deep else sig.fibo_p7   # deep 0.382 / shallow 0.0
            if dist > 0:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                self._pend_long = _Pending(1, long_edge, qty, sl, tp1, tp2, seq.l_sos_bar)
            else:
                self._pend_long = None
        else:
            self._pend_long = None

        if short_armed:
            sl = self._sl_anchor(sig) + cfg.exec_sl_buf_tk * cfg.mintick
            dist = sl - short_edge
            deep = short_edge >= sig.fibo_p3
            tp1 = sig.fibo_p2 if deep else sig.fibo_p1
            tp2 = sig.fibo_p1 if deep else sig.fibo_p7
            if dist > 0:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                self._pend_short = _Pending(-1, short_edge, qty, sl, tp1, tp2, seq.s_sos_bar)
            else:
                self._pend_short = None
        else:
            self._pend_short = None

    def _entry_edges(self, sig) -> Tuple[Optional[float], Optional[float]]:
        """The resting-limit price on each side (Pine 4264-4293): the near edge of an
        FVG overlapping the 0.5-0.886 band, clamped into the band; the first one price
        reaches (highest for longs). With Require-FVG off it falls back to 0.618."""
        cfg = self._cfg
        p2, p3, p6 = sig.fibo_p2, sig.fibo_p3, sig.fibo_p6
        fibs_ready = None not in (sig.fibo_p1, p2, p3, p6, sig.fibo_p7, sig.fibo_p10)
        long_edge = short_edge = None
        if fibs_ready:
            for top, bot, is_bull in sig.fvgs:
                l_deep_ok = not cfg.exec_fvg_deep_only or top <= p2
                s_deep_ok = not cfg.exec_fvg_deep_only or bot >= p2
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6 and l_deep_ok:
                    e = min(top, p2)
                    long_edge = e if long_edge is None else max(long_edge, e)
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6 and s_deep_ok:
                    e = max(bot, p2)
                    short_edge = e if short_edge is None else min(short_edge, e)
            if not cfg.exec_req_fvg:
                if long_edge is None and sig.fibo_dir == 1:
                    long_edge = p3
                if short_edge is None and sig.fibo_dir == -1:
                    short_edge = p3
        return long_edge, short_edge

    def _sl_anchor(self, sig) -> float:
        return {
            "0.618": sig.fibo_p3, "0.702": sig.fibo_p4, "0.786": sig.fibo_p5,
            "0.886": sig.fibo_p6,
        }.get(self._cfg.exec_sl_level, sig.fibo_p10)

    # ── entry fill (Phase A) ─────────────────────────────────────────────────────
    def _try_entry_fill(self, sig, dec) -> bool:
        # A long and short limit can't both rest into a fill in the same bar in
        # practice (opposite directions), but resolve deterministically: whichever the
        # bar's path reaches first. We check the one the path favors first.
        targets_first = _intrabar_targets_first(sig.open, sig.high, sig.low)
        order = [self._pend_long, self._pend_short] if targets_first \
            else [self._pend_short, self._pend_long]
        for pend in order:
            if pend is None:
                continue
            if pend.dir > 0 and sig.low <= pend.edge:
                fill = pend.edge if sig.open > pend.edge else sig.open  # gap = better fill
                self._open_position(pend, fill, sig, dec)
                return True
            if pend.dir < 0 and sig.high >= pend.edge:
                fill = pend.edge if sig.open < pend.edge else sig.open
                self._open_position(pend, fill, sig, dec)
                return True
        return False

    def _open_position(self, pend, fill_price, sig, dec) -> None:
        self._pos_dir = pend.dir
        self._qty = pend.qty
        self._entry = fill_price
        self._entry_index = sig.index
        self._entry_ms = sig.time_ms
        self._init_stop = pend.sl
        self._exit_notional = 0.0       # Σ price×qty of this trade's partial exits
        self._exit_qty = 0.0
        self._exit_ms = sig.time_ms
        self._exit_reason = ""
        self._sl = pend.sl
        self._tp1 = pend.tp1
        self._tp2 = pend.tp2
        self._stage = 0
        self._filled_qty = 0.0
        self._sos_bar_open = pend.sos_bar
        self._risk_usd = abs(pend.qty) * abs(fill_price - pend.sl) * self._cfg.point_value
        self._entry_equity = self._equity_realized      # R yardstick baseline
        self._max_fav = None                            # _advance_stage seeds it
        if pend.dir > 0:
            self._traded_sos_l = pend.sos_bar
        else:
            self._traded_sos_s = pend.sos_bar
        self._pend_long = self._pend_short = None
        dec.fills.append(Fill("entry", "Long" if pend.dir > 0 else "Short",
                              fill_price, pend.qty, pend.dir))

    # ── open-trade management (Phase A exits + Phase B staging) ───────────────────
    def _manage_open(self, sig, dec) -> None:
        """Fill the TP1/TP2/runner brackets against this bar using the frozen stop
        (from last bar's close) and the intrabar path."""
        stop = self._current_stop()
        d = self._pos_dir
        targets_first = _intrabar_targets_first(sig.open, sig.high, sig.low)

        # Build the remaining brackets (id, target-price-or-None, portion-qty).
        brackets = self._remaining_brackets()
        if not brackets:
            return

        for oid, target, qty in brackets:
            hit_target = target is not None and (
                (d > 0 and sig.high >= target) or (d < 0 and sig.low <= target))
            hit_stop = (d > 0 and sig.low <= stop) or (d < 0 and sig.high >= stop)
            if not hit_target and not hit_stop:
                continue
            if hit_target and hit_stop:
                take_target = targets_first  # path order decides
            else:
                take_target = hit_target
            level = target if take_target else stop
            price = self._fill_price(level, sig.open, take_target)
            self._exit_portion(oid, price, qty, sig, dec)
            if self._pos_dir == 0:
                return

    def _remaining_brackets(self) -> List[Tuple[str, Optional[float], float]]:
        """The still-open exit brackets in TP1→TP2→runner order, with each portion's
        qty. Percentages are of the ORIGINAL position (Pine qty_percent)."""
        d = self._pos_dir
        prefix = "L" if d > 0 else "S"
        p1 = self._qty * self._cfg.exec_tp1_pct / 100.0
        p2 = self._qty * self._cfg.exec_tp2_pct / 100.0
        out: List[Tuple[str, Optional[float], float]] = []
        remaining = self._qty - self._filled_qty
        # TP1
        if self._filled_qty < p1 - 1e-12:
            out.append((f"{prefix}-TP1", self._tp1, min(p1, remaining)))
            remaining -= min(p1, remaining)
        # TP2
        done = p1
        if self._filled_qty < (p1 + p2) - 1e-12 and remaining > 1e-12:
            already = max(0.0, self._filled_qty - done)
            q = min(p2 - already, remaining)
            if q > 1e-12:
                out.append((f"{prefix}-TP2", self._tp2, q))
                remaining -= q
        # runner (stop-only)
        if remaining > 1e-12:
            out.append((f"{prefix}-RUN", None, remaining))
        return out

    def _fill_price(self, level, open_, is_target) -> float:
        """TradingView broker fill: a limit/stop that the bar OPENS past fills at the
        open, not at its own price (a limit gaps to a better fill, a stop to a worse
        one). Same rule the entry limit already uses (_try_entry_fill)."""
        d = self._pos_dir
        if is_target:                       # limit exit
            gapped = open_ >= level if d > 0 else open_ <= level
        else:                               # stop exit
            gapped = open_ <= level if d > 0 else open_ >= level
        return open_ if gapped else level

    def _exit_portion(self, oid, price, qty, sig, dec) -> None:
        d = self._pos_dir
        pnl = (price - self._entry) * d * qty * self._cfg.point_value
        self._equity_realized += pnl
        self._filled_qty += qty
        self._exit_notional += price * qty
        self._exit_qty += qty
        self._exit_ms = sig.time_ms
        self._exit_reason = oid
        dec.fills.append(Fill("exit", oid, price, qty, d))
        if self._filled_qty >= self._qty - 1e-9:
            self._finalise_trade(sig, dec)

    def _close_at(self, sig, price, _reason, dec) -> None:
        remaining = self._qty - self._filled_qty
        if remaining <= 1e-12:
            return
        prefix = "L" if self._pos_dir > 0 else "S"
        self._exit_portion(f"{prefix}-CLOSE", price, remaining, sig, dec)

    def _finalise_trade(self, sig, dec) -> None:
        # net pnl of the whole trade = equity moved since entry; R against 1R risk
        pnl = self._equity_at_entry_delta()
        r = pnl / self._risk_usd if self._risk_usd > 0 else 0.0
        avg_exit = (self._exit_notional / self._exit_qty) if self._exit_qty > 1e-12 else self._entry
        self.trades.append(Trade(
            dir=self._pos_dir, entry_index=self._entry_index, entry_price=self._entry,
            exit_index=sig.index, qty=self._qty, risk_usd=self._risk_usd, pnl_usd=pnl, r=r,
            entry_ms=self._entry_ms, exit_ms=self._exit_ms, exit_price=avg_exit,
            stop_distance=abs(self._entry - self._init_stop), exit_reason=self._exit_reason))
        dec.closed_r = r
        self._pos_dir = 0
        self._qty = 0.0
        self._filled_qty = 0.0
        self._stage = 0
        self._entry_equity = None

    def _equity_at_entry_delta(self) -> float:
        # this trade's net = equity moved since its entry snapshot.
        return self._equity_realized - (self._entry_equity or self._equity_realized)

    # ── stop staging + trail (Pine 4674-4719) ────────────────────────────────────
    def _advance_stage(self, sig) -> None:
        d = self._pos_dir
        if self._max_fav is None:
            self._max_fav = sig.high if d > 0 else sig.low
        if d > 0:
            self._max_fav = max(self._max_fav, sig.high)
            if self._stage < 1 and sig.high >= self._tp1:
                self._stage = 1
            if self._stage < 2 and sig.high >= self._tp2:
                self._stage = 2
        else:
            self._max_fav = min(self._max_fav, sig.low)
            if self._stage < 1 and sig.low <= self._tp1:
                self._stage = 1
            if self._stage < 2 and sig.low <= self._tp2:
                self._stage = 2

    def _current_stop(self) -> float:
        cfg = self._cfg
        d = self._pos_dir
        be_buf = cfg.exec_be_buf_tk * cfg.mintick
        if self._stage >= 2:
            trail = self._trail()
            if d > 0:
                return self._tp1 if trail is None else max(self._tp1, trail)
            return self._tp1 if trail is None else min(self._tp1, trail)
        if self._stage >= 1:
            return self._entry + be_buf if d > 0 else self._entry - be_buf
        return self._sl

    def _trail(self) -> Optional[float]:
        step = self._cfg.exec_trail_step
        d = self._pos_dir
        if self._max_fav is None:
            return None
        run = (self._max_fav - self._tp2) if d > 0 else (self._tp2 - self._max_fav)
        if run < step:
            return None
        steps = int((run - step) // step)
        return self._tp2 + steps * step if d > 0 else self._tp2 - steps * step

    # ── HTF filters (default off) ────────────────────────────────────────────────
    def _htf_exhaustion_block(self, sig) -> Tuple[bool, bool]:
        cfg = self._cfg
        if not cfg.exec_htf_exhaust_only:
            return (False, False)
        w_up, w_dn = "Close >" in sig.w_est_desc, "Close <" in sig.w_est_desc
        d_up, d_dn = "Close >" in sig.d_est_desc, "Close <" in sig.d_est_desc
        if cfg.exec_htf_source == "Daily":
            up, dn = d_up, d_dn
        elif cfg.exec_htf_source == "Either":
            up, dn = (w_up or d_up), (w_dn or d_dn)
        else:
            up, dn = w_up, w_dn
        return (dn, up)   # long blocked by a fresh breakdown; short by a fresh breakout

    def _htf_bias_block(self, sig) -> Tuple[bool, bool]:
        cfg = self._cfg

        def leg(req, state, is_long):
            agree = (state == "Bullish") if is_long else (state == "Bearish")
            oppose = (state == "Bearish") if is_long else (state == "Bullish")
            if req == "Must agree":
                return not agree
            if req == "Must not oppose":
                return oppose
            if req == "Must oppose (reversal)":
                return not oppose
            return False

        block_l = leg(cfg.exec_htf_weekly, sig.w_est_state, True) or \
            leg(cfg.exec_htf_daily, sig.d_est_state, True)
        block_s = leg(cfg.exec_htf_weekly, sig.w_est_state, False) or \
            leg(cfg.exec_htf_daily, sig.d_est_state, False)
        return (block_l, block_s)

    # ── flat-by-close deviation window ───────────────────────────────────────────
    def _in_flat_window(self, sig) -> bool:
        cfg = self._cfg
        # minutes until the daily close (gold 17:00 NY). Reads NY hour only (bar TF
        # granularity is enough for the 15/60-min windows we use).
        close_h = cfg.daily_close_hour_ny
        if sig.ny_hour >= close_h:
            return False
        mins_left = (close_h - sig.ny_hour) * 60
        return mins_left <= cfg.flat_by_close_min
