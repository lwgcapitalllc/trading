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

**A2 (fill & cost model).** Both assumptions above describe BAR mode, which stays the
default and stays exactly as written — it is what `compare_strategy.py` diffs against the
Pine. Passing a `resolver` + `profile` switches to TICK mode: real bid/ask fills (spread
and slippage measured off the tape) plus commission and swap. Tick mode is an added branch
at each fill site, never a rewrite of the bar path, so parity cannot be collateral damage.
See `backtest/fills.py` for why both models must exist.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# repo-root on path so `backtest.fills` imports standalone, matching strategy.py's shim.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest import fills as _fills
from backtest.portfolio.account import SoloAccount

from .signals import sos_aware_veto


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
    # Commission + swap charged to this trade. `pnl_usd` is already NET of it; this field
    # exists so a run can report what the costs actually were. Always 0.0 in bar mode, which
    # charges nothing — an honest zero, not a claim that trading was free.
    costs_usd: float = 0.0
    exit_price: float = 0.0
    stop_distance: float = 0.0
    exit_reason: str = ""
    # "primary" (the 15m A+ trade) or "secondary" (a 1m sniper re-entry). Reporting-only — no
    # decision reads it; it lets the lab/chart tell the two apart. See secondary.py.
    kind: str = "primary"
    # Reporting-only excursion (no decision weight): the most this trade was ever showing in
    # profit (`mfe_usd` ≥ 0, favorable) and the deepest it sat against us (`mae_usd` ≤ 0, adverse)
    # before it closed — measured across the full hold on bar high/low, the same intrabar
    # approximation the trail's `_max_fav` uses. Feeds the equity chart's excursion overlay.
    mfe_usd: float = 0.0
    mae_usd: float = 0.0
    # Reporting-only PRICES (same parity-safety as the USD excursion above — no decision reads them):
    # the deepest favorable price the hold ever reached (`mfe_price`) and the deepest adverse price
    # (`mae_price`), plus the per-rung exit ledger (`legs`), each `{"reason", "price", "ms", "qty"}`.
    # These feed the price chart's profit-depth trade view (how far price ran vs where each rung
    # actually banked).
    mfe_price: float = 0.0
    mae_price: float = 0.0
    legs: List[dict] = field(default_factory=list)
    # Reporting-only TP TARGET ladder — the fib levels the trade AIMED at, frozen at entry (NOT
    # where each rung actually closed; that's `legs`). Lets the chart draw an UNHIT next target so a
    # runner's near-miss of the following TP is visible. No decision reads them (parity-safe).
    tp1: float = 0.0
    tp2: float = 0.0


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
    """The order layer + a small broker emulator.

    `resolver`/`profile` are the A2 seam and BOTH default to None, which is bar mode: the Pine's
    own intrabar guess with zero costs, i.e. every code path below behaves exactly as it did before
    A2 existed. That default is load-bearing — `compare_strategy.py`'s exit 0 rests on it, so the
    bar paths are never routed through the resolver. Tick mode is an added branch, never a rewrite.
    """

    def __init__(self, config, initial_capital: float = 1_000_000.0,
                 resolver=None, profile=None, bar_ms: int = 300_000,
                 account=None, leg: str = "strat") -> None:
        self._cfg = config
        self._equity_realized = initial_capital  # LEG-LOCAL ledger — R is measured against this
        # The shared account owns the budget and sizes entries. Default = a SoloAccount (no cap,
        # always grants full size), so a bot run alone is byte-identical to before the seam existed;
        # a shared PortfolioAccount contends this leg against the others. See backtest/portfolio/.
        self._account = account if account is not None else SoloAccount(balance=initial_capital)
        self._leg = leg
        # A2: None ⇒ bar mode (the Pine guess, no costs). See the class docstring.
        self._resolver = resolver
        self._profile = profile
        self.bar_ms = bar_ms                # bar duration; only tick mode reads it
        self._costs_usd = 0.0               # this trade's commission + swap so far
        self._last_roll_ms: Optional[int] = None   # last rollover already charged

        # position state
        self._pos_dir = 0                  # 0 flat, +1 long, -1 short
        # which layer opened the current position — "primary" (15m) or "secondary" (1m sniper).
        # 15m `step()` only manages a primary; the 1m `step_secondary()` only manages a secondary.
        # They share this one position slot but never the same trade (the secondary arms only when
        # flat), so the tag is all that keeps each stream off the other's position. When flat it is
        # ignored, so with `exec_secondary` OFF (no secondary ever opens) `step()` is unchanged.
        self._entry_kind = "primary"
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
        self._stage = 0                    # 0 full-stop, 1 BE, 2 floor + runner trail
        self._max_fav = 0.0
        # Structure-trail anchors, snapshotted at each bar's CLOSE (see _advance_stage). The stop
        # placed at bar N's close is what bar N+1 trades against, so the trail must read bar N's
        # swing — never the live one — exactly like `_max_fav` does for the fixed-step ratchet.
        self._trail_swing_hi: Optional[float] = None
        self._trail_swing_lo: Optional[float] = None
        # excursion extremes across the whole hold (reporting only — see Trade.mfe_usd)
        self._ext_high = 0.0
        self._ext_low = 0.0
        self._legs: List[dict] = []        # per-rung exit ledger of the OPEN trade (reporting only)
        self._risk_usd = 0.0
        self._filled_qty = 0.0             # how much of the position has exited
        self._sos_bar_open: Optional[int] = None
        self._entry_equity: Optional[float] = None   # equity snapshot at open, for R

        # resting entry orders (one per side; at most one position at a time)
        self._pend_long: Optional[_Pending] = None
        self._pend_short: Optional[_Pending] = None
        # the secondary sniper limit, placed/filled on the 1m stream (step_secondary). Its own slot
        # so the 15m `_place_entries` can never clobber it. At most one side arms (fibo_dir is one).
        self._pend_sec: Optional[_Pending] = None

        # one-trade-per-leg latches (Pine tradedSosL / tradedSosS)
        self._traded_sos_l: Optional[int] = None
        self._traded_sos_s: Optional[int] = None
        # secondary eligibility: the 15m leg whose PRIMARY reached at least TP1 (moved to
        # breakeven, _stage >= 1). A secondary arms only when its leg == this — a primary that
        # opened and got stopped at its initial stop (never reached TP1) leaves no re-entry.
        self._be_sos_l: Optional[int] = None
        self._be_sos_s: Optional[int] = None
        # set for one 1m step when a SECONDARY closes at its initial stop (stage 0 = never
        # reached TP1). The driver reads it to kill that 15m leg — a stopped re-entry ends the
        # cascade on that leg. +1/-1/None; reset at the top of every step_secondary.
        self._sec_stop_dir: Optional[int] = None

        self.trades: List[Trade] = []

    # ── public equity read ──
    @property
    def equity(self) -> float:
        # The SHARED balance the leg sizes against. In solo mode this equals the leg-local
        # ledger; in a portfolio it is the account all legs share, so every leg scales together.
        return self._account.balance

    # ── reads the secondary layer needs (the 1m arm gates on these) ──
    @property
    def is_flat(self) -> bool:
        return self._pos_dir == 0

    @property
    def entry_kind(self) -> str:
        return self._entry_kind

    @property
    def traded_sos_l(self) -> Optional[int]:
        return self._traded_sos_l

    @property
    def traded_sos_s(self) -> Optional[int]:
        return self._traded_sos_s

    @property
    def be_sos_l(self) -> Optional[int]:
        return self._be_sos_l

    @property
    def be_sos_s(self) -> Optional[int]:
        return self._be_sos_s

    @property
    def sec_stop_dir(self) -> Optional[int]:
        """+1/-1 if a secondary just closed at its initial stop this 1m step (the driver kills
        that 15m leg), else None. Reset at the top of every step_secondary."""
        return self._sec_stop_dir

    # ── secondary (1m sniper) path — driven by the 1m stream, never a 15m bar ────────
    def step_secondary(self, sig1m, arm) -> Optional[int]:
        """Advance the SECONDARY on one 1m bar. Same calc-on-close/one-bar-delay + intrabar-path
        rules as the primary, but on 1m bars, and only ever touching a secondary position:

          - flat  → fill the sniper limit placed LAST 1m bar (if touched), then (re)place from
                    this bar's arm. A fill retires its 1m leg (returned dir → driver calls
                    `arm.mark_traded`) and stages the trade so its stop is live next bar.
          - holding a secondary → run its TP1/TP2/runner ladder against this bar, then re-stage.
          - holding a PRIMARY  → do nothing (the 15m stream owns it).

        `sig1m` needs `index / time_ms / open / high / low / close` (a `_Bar1mSig`). Returns the
        direction filled this bar (+1/-1) or None. Bar-mode only for now; tick-mode secondary
        fills are a later add (the 1m tick seam isn't wired)."""
        self._sec_stop_dir = None            # cleared each step; _finalise_trade sets it on a stop-out
        sink = Decision(index=sig1m.index)   # throwaway — trades land in self.trades regardless
        filled_dir: Optional[int] = None

        # ── Phase A: fill / manage against THIS 1m bar ──
        if self._pos_dir == 0 and self._pend_sec is not None:
            pend = self._pend_sec
            if pend.dir > 0 and sig1m.low <= pend.edge:
                fill = pend.edge if sig1m.open > pend.edge else sig1m.open
                if self._open_position(pend, fill, sig1m, sink, kind="secondary"):
                    filled_dir = 1
            elif pend.dir < 0 and sig1m.high >= pend.edge:
                fill = pend.edge if sig1m.open < pend.edge else sig1m.open
                if self._open_position(pend, fill, sig1m, sink, kind="secondary"):
                    filled_dir = -1
        elif self._pos_dir != 0 and self._entry_kind == "secondary":
            self._manage_open(sig1m, sink)

        # ── Phase B: at close, (re)place the sniper limit / stage the open trade ──
        if self._pos_dir == 0:
            self._pend_sec = self._secondary_pending(arm)
        elif self._entry_kind == "secondary":
            self._advance_stage(sig1m)

        return filled_dir

    def _secondary_pending(self, arm) -> Optional["_Pending"]:
        """Turn the armed side of a `SecArm` into a resting `_Pending`, sized off the 1m-leg stop
        distance with the same %-risk as the primary. At most one side arms (fibo_dir is one value)."""
        cfg = self._cfg
        if arm.l_armed and arm.l_edge is not None and arm.l_sl is not None:
            dist = arm.l_edge - arm.l_sl
            if dist > 0:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                return _Pending(1, arm.l_edge, qty, arm.l_sl, arm.l_tp1, arm.l_tp2, arm.l_leg)
        if arm.s_armed and arm.s_edge is not None and arm.s_sl is not None:
            dist = arm.s_sl - arm.s_edge
            if dist > 0:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                return _Pending(-1, arm.s_edge, qty, arm.s_sl, arm.s_tp1, arm.s_tp2, arm.s_leg)
        return None

    # ── main step ───────────────────────────────────────────────────────────────
    def step(self, sig, seq) -> Decision:
        dec = Decision(index=sig.index)

        # Decision context the Pine computes EVERY bar (not just when flat), so the
        # decision streams line up bar-for-bar: the entry edges, the A+ stage, the veto.
        long_edge, short_edge = self._entry_edges(sig)
        dec.long_edge, dec.short_edge = long_edge, short_edge
        dec.l_stage, dec.s_stage = seq.l_stage, seq.s_stage
        dec.long_veto, dec.short_veto = sos_aware_veto(sig, seq.l_sos_bar, seq.s_sos_bar)

        # Financing for any rollover crossed while still holding — charged before this bar's
        # exits, since the night was already carried by the time the bar trades. No-op in bar mode.
        self._charge_swap(sig)

        # ── Phase A: fill resting orders against THIS bar (placed last bar) ──
        opened = False
        if self._pos_dir == 0:
            opened = self._try_entry_fill(sig, dec)
        # Exit orders are placed at a bar's close and active the NEXT bar, so a trade
        # never fills an exit on the bar it opened (TradingView one-bar delay). A secondary
        # position is managed on the 1m stream, so a 15m bar never touches it.
        if self._pos_dir != 0 and not opened and self._entry_kind != "secondary":
            self._manage_open(sig, dec)

        # ── Phase B: at close, (re)place orders for the next bar ──
        if self._pos_dir != 0 and self._entry_kind != "secondary":
            self._advance_stage(sig)
            dec.stop = self._current_stop()
            # tell the account this leg's live stop + remaining size, so its reservation is
            # current for any other leg sizing on the next tick (drops to 0 once stop = BE).
            self._account.update_stop(self._leg, dec.stop, self._qty - self._filled_qty)
            # optional force-close on an opposite SOS (Pine execCloseOppSOS)
            if self._cfg.exec_close_opp_sos and (
                (self._pos_dir > 0 and sig.bear_sos) or (self._pos_dir < 0 and sig.bull_sos)
            ):
                self._close_at(sig, sig.close, "opp-SOS", dec)
            # deliberate deviation: force-flat before the daily close (real runs only)
            elif self._cfg.flat_by_close and self._in_flat_window(sig):
                self._close_at(sig, sig.close, "flat-by-close", dec)
        elif self._pos_dir == 0:
            self._place_entries(sig, seq, dec, dec.long_edge, dec.short_edge)
        # else: a secondary is open — managed on the 1m stream (step_secondary), not here.

        return dec

    # ── A+ arm gate (Pine longArmed/shortArmed, 4358-4359) ───────────────────────
    def _armed(self, sig, seq, dec, long_edge, short_edge) -> Tuple[bool, bool]:
        """The full A+ arm decision: arm-source filter + late-day + HTF blocks + veto +
        the one-trade-per-leg latch. Sets `dec.long_armed`/`dec.short_armed` and RETURNS
        the pair, WITHOUT placing anything. Extracted verbatim from `_place_entries` so the
        B-LEG fork can reuse it as its 'A+ has priority' gate — parity-preserving (this is
        exactly what `_place_entries` used to compute inline)."""
        cfg = self._cfg
        late = cfg.exec_no_late_day and 16 <= sig.ny_hour < 18   # 16:00-17:59 NY block

        # arm-source filter (Pine 4349-4355)
        use_swp_l = cfg.exec_arm_sweep and seq.sos_l_swp
        use_div_l = cfg.exec_arm_div and seq.sos_l_div
        use_swp_s = cfg.exec_arm_sweep and seq.sos_s_swp
        use_div_s = cfg.exec_arm_div and seq.sos_s_div
        arm_ok_l = use_swp_l or use_div_l
        arm_ok_s = use_swp_s or use_div_s

        htf_block_l, htf_block_s = self._htf_exhaustion_block(sig)
        bias_block_l, bias_block_s = self._htf_bias_block(sig)

        long_armed = (cfg.exec_aplus and cfg.exec_longs and arm_ok_l and not late and not htf_block_l
                      and not bias_block_l and seq.l_sos_bar is not None and sig.fibo_dir == 1
                      and long_edge is not None
                      and (not dec.long_veto or not cfg.exec_respect_veto)
                      and (self._traded_sos_l is None or seq.l_sos_bar != self._traded_sos_l))
        short_armed = (cfg.exec_aplus and cfg.exec_shorts and arm_ok_s and not late and not htf_block_s
                       and not bias_block_s and seq.s_sos_bar is not None and sig.fibo_dir == -1
                       and short_edge is not None
                       and (not dec.short_veto or not cfg.exec_respect_veto)
                       and (self._traded_sos_s is None or seq.s_sos_bar != self._traded_sos_s))
        dec.long_armed, dec.short_armed = long_armed, short_armed
        return long_armed, short_armed

    # ── entry placement (Pine 4264-4507) ─────────────────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        long_armed, short_armed = self._armed(sig, seq, dec, long_edge, short_edge)

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

    def _deep_fib_edge(self, gb, gt, is_bull, sig) -> Optional[float]:
        """Method 3 (Pine f_deepFibEdge) — the re-priced entry for a DEEP gap whose NEAR edge
        sits below 0.618, or None when the near edge is shallower (those keep the exact-edge
        entry). ONLY the near edge's position decides it — a gap tall enough to span 0.702/0.786
        is fine; what the body crosses is irrelevant. Long near edge = gap top (gt); short = gap
        bottom (gb). The re-priced level is the fib just SHALLOWER than the near edge — the one
        price reaches first (0.618-0.702 -> 0.618, 0.702-0.786 -> 0.702, 0.786-0.886 -> 0.786)."""
        p3, p4, p5 = sig.fibo_p3, sig.fibo_p4, sig.fibo_p5
        if is_bull and gt < p3:            # long: near edge deeper than the 0.618 line
            return p3 if gt >= p4 else (p4 if gt >= p5 else p5)
        if (not is_bull) and gb > p3:      # short: near edge deeper than the 0.618 line
            return p3 if gb <= p4 else (p4 if gb <= p5 else p5)
        return None

    def _entry_edges(self, sig) -> Tuple[Optional[float], Optional[float]]:
        """The resting-limit price on each side (Pine 4264-4293): the near edge of an
        FVG overlapping the 0.5-0.886 band, clamped into the band; the first one price
        reaches (highest for longs). With Require-FVG off it falls back to 0.618. With
        Method 3 (exec_deep_fib) on, a gap whose near edge is deeper than 0.618 is
        re-priced to the nearest shallower fib instead of its own edge."""
        cfg = self._cfg
        p2, p3, p6 = sig.fibo_p2, sig.fibo_p3, sig.fibo_p6
        fibs_ready = None not in (sig.fibo_p1, p2, p3, p6, sig.fibo_p7, sig.fibo_p10)
        long_edge = short_edge = None
        if fibs_ready:
            for top, bot, is_bull in sig.fvgs:
                l_deep_ok = not cfg.exec_fvg_deep_only or top <= p2
                s_deep_ok = not cfg.exec_fvg_deep_only or bot >= p2
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6 and l_deep_ok:
                    df = self._deep_fib_edge(bot, top, True, sig) if cfg.exec_deep_fib else None
                    e = min(top, p2) if df is None else df   # Method 3 override, else shallowest touch
                    long_edge = e if long_edge is None else max(long_edge, e)
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6 and s_deep_ok:
                    df = self._deep_fib_edge(bot, top, False, sig) if cfg.exec_deep_fib else None
                    e = max(bot, p2) if df is None else df
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
        if self._resolver is not None:
            return self._try_entry_fill_ticks(sig, dec)
        return self._try_entry_fill_bar(sig, dec)

    def _try_entry_fill_ticks(self, sig, dec) -> bool:
        """Real-tick entry. An entry limit transacts on the side that actually trades: a long
        BUYS the ask, a short SELLS the bid — so the spread is paid here by construction rather
        than modelled. A limit never slips against you; it fills at its price or better."""
        for pend in (self._pend_long, self._pend_short):
            if pend is None:
                continue
            buying = pend.dir > 0
            # A long's limit sits BELOW price (price must fall to it); a short's sits above.
            level = _fills.Level(pend.edge, falling=buying)
            fill = self._resolver.first_touch(
                self._bar_of(sig), {"entry": level}, buying=buying)
            if fill is not None:
                if self._open_position(pend, fill.price, sig, dec):
                    return True
        return False

    def _try_entry_fill_bar(self, sig, dec) -> bool:
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
                if self._open_position(pend, fill, sig, dec):
                    return True
            if pend.dir < 0 and sig.high >= pend.edge:
                fill = pend.edge if sig.open < pend.edge else sig.open
                if self._open_position(pend, fill, sig, dec):
                    return True
        return False

    def _open_position(self, pend, fill_price, sig, dec, kind: str = "primary") -> bool:
        # The gate runs HERE, at the fill — a resting limit reserves nothing until it fills.
        # The account scales the leg's own desired size (pend.qty) to the room; solo → full size.
        granted = self._account.request_fill(
            self._leg, pend.dir, fill_price, pend.sl, pend.qty, self._cfg.point_value)
        if granted <= 0.0:
            # refused (no room / below floor): don't open, drop this order, let the strategy
            # re-arm next bar if the setup still holds. No traded-SOS latch is set (see below).
            if kind == "secondary":
                self._pend_sec = None
            elif pend.dir > 0:
                self._pend_long = None
            else:
                self._pend_short = None
            return False
        self._pos_dir = pend.dir
        self._entry_kind = kind
        self._qty = granted
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
        self._risk_usd = abs(granted) * abs(fill_price - pend.sl) * self._cfg.point_value
        self._entry_equity = self._equity_realized      # R yardstick baseline
        # Costs are charged AFTER the R baseline is snapshotted, so they land inside the trade's
        # own P&L (and its R) rather than being quietly excluded from it.
        self._costs_usd = 0.0
        self._last_roll_ms = None
        self._charge_commission(pend.qty)
        self._max_fav = None                            # _advance_stage seeds it
        self._trail_swing_hi = None                     # structure-trail anchors — same
        self._trail_swing_lo = None
        self._ext_high = sig.high                       # excursion (reporting) — seed on entry bar
        self._ext_low = sig.low
        self._legs = []                                 # per-rung exit ledger (reporting only)
        # The traded-SOS latch is the PRIMARY's one-trade-per-15m-leg gate (and the secondary's
        # "primary already went" precondition). A secondary fill must NOT move it — its sos_bar is
        # a 1m leg, not the 15m A+ leg — so only a primary sets it.
        if kind == "primary":
            if pend.dir > 0:
                self._traded_sos_l = pend.sos_bar
            else:
                self._traded_sos_s = pend.sos_bar
        self._pend_long = self._pend_short = self._pend_sec = None
        dec.fills.append(Fill("entry", "Long" if pend.dir > 0 else "Short",
                              fill_price, granted, pend.dir))
        return True

    # ── open-trade management (Phase A exits + Phase B staging) ───────────────────
    def _manage_open(self, sig, dec) -> None:
        # Excursion (reporting only): widen the hold's high/low before this bar's exits resolve,
        # so the closing bar's extreme counts too. Never read by a decision.
        self._ext_high = max(self._ext_high, sig.high)
        self._ext_low = min(self._ext_low, sig.low)
        if self._resolver is not None:
            return self._manage_open_ticks(sig, dec)
        return self._manage_open_bar(sig, dec)

    def _manage_open_ticks(self, sig, dec) -> None:
        """Real-tick exits. Exiting transacts on the OPPOSITE side of the book from entering —
        a long exits by SELLING the bid, a short by BUYING the ask — which is why `buying` here
        is `d < 0` and not the position's direction.

        The stop is frozen from last bar's close (same as bar mode), so it is constant across the
        bar and the ladder resolves in TP1→TP2→runner order. That ordering is safe with ticks:
        TP2 lies beyond TP1 in the same direction, so any tick reaching TP2 has already passed
        TP1. Unlike bar mode, a stop fill reports the price that ACTUALLY existed next, so its
        slippage is measured rather than assumed away.
        """
        stop = self._current_stop()
        d = self._pos_dir
        buying = d < 0
        bar = self._bar_of(sig)
        for oid, target, qty in self._remaining_brackets():
            levels = {"stop": _fills.Level(stop, falling=d > 0)}
            if target is not None:
                levels[oid] = _fills.Level(target, falling=d < 0)
            fill = self._resolver.first_touch(bar, levels, buying=buying)
            if fill is None:
                return
            if fill.key == "stop":
                self._close_at(sig, fill.price, "stop", dec)
                return
            self._exit_portion(oid, fill.price, qty, sig, dec)
            if self._pos_dir == 0:
                return

    def _bar_of(self, sig) -> "_fills.Bar":
        return _fills.Bar(time_ms=sig.time_ms, open=sig.open, high=sig.high, low=sig.low,
                          close=sig.close, duration_ms=self.bar_ms)

    def _manage_open_bar(self, sig, dec) -> None:
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
        self._account.book_pnl(self._leg, pnl)   # realize onto the shared balance as it happens
        self._charge_commission(qty)        # commission is per SIDE — each ladder leg pays
        self._filled_qty += qty
        self._exit_notional += price * qty
        self._exit_qty += qty
        self._exit_ms = sig.time_ms
        self._exit_reason = oid
        self._legs.append({"reason": oid, "price": price, "ms": sig.time_ms, "qty": qty})
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
        d, pv = self._pos_dir, self._cfg.point_value
        mfe_price = self._ext_high if d > 0 else self._ext_low
        mae_price = self._ext_low if d > 0 else self._ext_high
        mfe_usd = (mfe_price - self._entry) * d * self._qty * pv
        mae_usd = (mae_price - self._entry) * d * self._qty * pv
        self.trades.append(Trade(
            dir=self._pos_dir, entry_index=self._entry_index, entry_price=self._entry,
            exit_index=sig.index, qty=self._qty, risk_usd=self._risk_usd, pnl_usd=pnl, r=r,
            entry_ms=self._entry_ms, exit_ms=self._exit_ms, exit_price=avg_exit,
            costs_usd=self._costs_usd,
            stop_distance=abs(self._entry - self._init_stop), exit_reason=self._exit_reason,
            kind=self._entry_kind,
            mfe_usd=round(mfe_usd, 2), mae_usd=round(mae_usd, 2),
            mfe_price=round(mfe_price, 5), mae_price=round(mae_price, 5), legs=list(self._legs),
            tp1=round(self._tp1, 5), tp2=round(self._tp2, 5)))
        dec.closed_r = r
        # A secondary that closes at stage 0 never reached TP1 — it hit its initial stop ("didn't
        # hold"). Flag its direction so the driver kills that 15m leg (a stopped re-entry ends the
        # cascade). A secondary that reached breakeven-or-better (stage >= 1) does NOT flag.
        if self._entry_kind == "secondary" and self._stage == 0:
            self._sec_stop_dir = self._pos_dir
        self._account.close_position(self._leg)   # P&L already booked; free the reservation
        self._pos_dir = 0
        self._qty = 0.0
        self._filled_qty = 0.0
        self._stage = 0
        self._entry_equity = None

    def _equity_at_entry_delta(self) -> float:
        # this trade's net = equity moved since its entry snapshot.
        return self._equity_realized - (self._entry_equity or self._equity_realized)

    # ── costs (A2) — no-ops without a profile, which is what bar mode runs ────────
    def _charge(self, amount: float) -> None:
        """Book a cost against equity. `amount` is signed the way the broker books it:
        negative = charged, positive = credited (a short's gold swap is a real credit)."""
        self._equity_realized += amount
        self._account.book_pnl(self._leg, amount)   # costs hit the shared balance too
        self._costs_usd += amount

    def _charge_commission(self, qty: float) -> None:
        if self._profile is None:
            return
        self._charge(-self._profile.commission(qty))

    def _charge_swap(self, sig) -> None:
        """Charge financing for every rollover this bar crosses while a position is open.

        Fires at most once per rollover (`_last_roll_ms` latches it), so a bar that spans the
        boundary cannot double-book — the same edge-vs-level distinction that caused the sweep
        double-count bug in signals.py. Swap is why holding matters: it hits longs and shorts in
        OPPOSITE directions, so omitting it flatters every long and understates every short.
        """
        if self._profile is None or self._profile.swap is None or self._pos_dir == 0:
            return
        roll = self._last_rollover_before(sig.time_ms)
        if roll is None or roll[0] == self._last_roll_ms:
            return
        roll_ms, roll_date = roll
        if roll_ms <= self._entry_ms:      # the rollover predates this position
            self._last_roll_ms = roll_ms
            return
        self._last_roll_ms = roll_ms
        remaining = self._qty - self._filled_qty
        self._charge(self._profile.swap_charge(self._pos_dir, remaining, roll_date))

    def _last_rollover_before(self, time_ms: int):
        """(epoch-ms, date) of the most recent daily rollover at/before `time_ms`, or None.

        The rollover is the broker's day boundary — the same 17:00-NY instant the daily close
        uses. Saturday is skipped: the market is shut, so no night is booked there (the weekend
        is carried by the triple-swap weekday instead).
        """
        from datetime import datetime, time, timedelta, timezone
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        now = datetime.fromtimestamp(time_ms / 1000.0, tz=timezone.utc).astimezone(ny)
        day = now.date() if now.hour >= self._cfg.daily_close_hour_ny else \
            (now - timedelta(days=1)).date()
        for _ in range(4):                 # step back over any shut days
            if day.weekday() != 5:         # Saturday books nothing
                roll = datetime.combine(day, time(self._cfg.daily_close_hour_ny), tzinfo=ny)
                return int(roll.timestamp() * 1000), day
            day -= timedelta(days=1)
        return None

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
        # Latch the 15m leg once its PRIMARY reaches TP1 (stage >= 1 = moved to breakeven) — the
        # secondary's eligibility gate. Idempotent; only a primary sets it (a secondary reaching
        # TP1 calls this too, but must not move the primary latch). No decision reads it → parity-safe.
        if self._entry_kind == "primary" and self._stage >= 1:
            if d > 0:
                self._be_sos_l = self._sos_bar_open
            else:
                self._be_sos_s = self._sos_bar_open

        # Structure-trail anchors for the NEXT bar (Pine reads st.last_conf_* on the same bar it
        # calls strategy.exit, and that exit is active from the following bar).
        self._trail_swing_hi = sig.last_conf_high
        self._trail_swing_lo = sig.last_conf_low

    def _current_stop(self) -> float:
        cfg = self._cfg
        d = self._pos_dir
        be_buf = cfg.exec_be_buf_tk * cfg.mintick
        if self._stage >= 2:
            floor = self._stage2_floor()
            trail = self._trail()
            if d > 0:
                return floor if trail is None else max(floor, trail)
            return floor if trail is None else min(floor, trail)
        if self._stage >= 1:
            return self._entry + be_buf if d > 0 else self._entry - be_buf
        return self._sl

    def _stage2_floor(self) -> float:
        """The stop FLOOR the moment TP2 fills, before the runner trail takes over
        (Pine lStage2Floor / sStage2Floor, `exec_tp2_stop_mode`). The trail can only
        tighten past this — never loosen it."""
        cfg = self._cfg
        d = self._pos_dir
        be_buf = cfg.exec_be_buf_tk * cfg.mintick
        be = self._entry + be_buf if d > 0 else self._entry - be_buf
        mode = cfg.exec_tp2_stop_mode
        if mode == "Breakeven":
            return be
        if mode == "One trail step behind":
            if self._max_fav is None:            # no bar has staged yet — hold breakeven
                return be
            step = cfg.exec_trail_step
            return max(be, self._max_fav - step) if d > 0 else min(be, self._max_fav + step)
        return self._tp1                          # "TP1 price" (default)

    def _trail(self) -> Optional[float]:
        """The runner's trailing stop past TP2, or None when it hasn't engaged yet
        (Pine lTrail / sTrail, `exec_runner_trail`)."""
        cfg = self._cfg
        d = self._pos_dir
        if cfg.exec_runner_trail == "Structure (swing)":
            swing = self._trail_swing_lo if d > 0 else self._trail_swing_hi
            if swing is None:                     # no confirmed swing yet — floor only
                return None
            buf = cfg.exec_struct_trail_buf_tk * cfg.mintick
            return swing - buf if d > 0 else swing + buf
        step = cfg.exec_trail_step
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
        # Minutes until the daily close (gold 17:00 NY). The minute-of-hour is read off the
        # UTC timestamp directly: every NY offset is a whole number of hours, so minutes past
        # the hour are the same in both zones and need no tz conversion.
        close_h = cfg.daily_close_hour_ny
        if sig.ny_hour >= close_h:
            return False
        mins_left = (close_h - sig.ny_hour) * 60 - (sig.time_ms // 60_000) % 60
        return 0 < mins_left <= cfg.flat_by_close_min
