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

import math
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
# The canonical ratio→price helper, and the only one allowed: `_sl_anchor`'s Custom branch has to
# land on the exact float the fib engine would have produced for that ratio, and re-deriving
# `ash - range*ratio` here would be a second implementation free to drift by a bit.
from engines.fibonacci.geometry import fib_level

from .signals import sos_aware_veto


def _first(pred, values):
    """The first value satisfying `pred`, skipping None — Pine's `a ? a : b ? b : na` chain.

    A None level is skipped rather than tested because a comparison against Pine's `na` is
    itself `na`, which reads as false and falls through to the next branch. Order is the
    caller's: these chains encode which end of the fib ladder is scanned first.
    """
    for v in values:
        if v is not None and pred(v):
            return v
    return None


def _nearest(shallow, deep, deep_dist, shallow_dist):
    """Pine `na(_D) ? _S : na(_S) ? _D : deep_dist < shallow_dist ? _D : _S`.

    Ties go to the SHALLOWER level, which is the one price reaches first — so an exact tie
    keeps the fill rather than trading it for an identical entry price.
    """
    if deep is None:
        return shallow
    if shallow is None:
        return deep
    return deep if deep_dist < shallow_dist else shallow


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
    # The OPEN trade's frozen TP ladder, or None when flat — mirroring the Pine's
    # `strategy.position_size > 0 ? lTP1 : ...` plot gate. The A+ bot reads its rungs off
    # fib levels the export already carries, so `compare_strategy.py` does NOT diff these;
    # the B-LEG derives them from its frozen band, so `compare_bleg.py` does. Reporting
    # only either way — no decision reads them back, so they are parity-safe.
    tp1: Optional[float] = None
    tp2: Optional[float] = None


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
    # Commission + swap + slippage charged to this trade. `pnl_usd` is already NET of it; this
    # field exists so a run can report what the costs actually were. 0.0 when no cost profile was
    # supplied — an honest zero meaning "nothing was priced", not a claim that trading was free.
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
    # The fib LEG this trade was priced off, frozen at order placement — see `TradeFib`. Optional
    # for the same reason every other reporting field here is: a fork that prices its entries some
    # other way (`mpc_bleg` overrides `_place_entries` and works off band prices, not this ladder)
    # simply carries None, and the chart draws no fib for it rather than an invented one.
    fib: Optional["TradeFib"] = None


# ── blocked setups (Pine 4025-4086, the pink TRADE BLOCKED tag) ─────────────────
# A setup that was READY to rest its entry limit — armed through to the SOS, fib pointing
# the right way, a live entry edge to rest on, flat, this leg not yet traded — and was
# refused by one of the strategy's OWN TOGGLES rather than by price. It places no order, so
# it leaves no trace in any trade list; this is the only place it is countable.
#
# REPORTING ONLY. Nothing reads a recorded block back, so it cannot move a decision — the
# same parity standing as `Trade.mfe_usd`. `compare_strategy.py` diffs the `px_*` decision
# stream, which is untouched.
#
# ONE DELIBERATE DEVIATION FROM THE PINE: we record EVERY rule refusing the setup, not just
# the first. Pine reports one code (`f_blkCode` returns the highest-precedence blocker) because
# a chart tag has room for one line; the lab wants to filter by reason, and "this setup was
# blocked by the veto" must stay true even when the final hour was also blocking it. The Pine's
# PRECEDENCE is kept as the ORDER, so `codes[0]` is exactly what `f_blkCode` would have returned
# — a per-reason count taken off the primary still reconciles with TradingView.
_BLOCK_LABEL = {
    1: "Direction off",
    2: "Arm source off",
    3: "Final hour",
    4: "Divergence / RSI veto",
    5: "HTF breakout",
    6: "HTF bias",
    7: "Stop too tight",
}
# The hover text, word-for-word from Pine `f_blkWhy` so the chart and TradingView agree.
_BLOCK_REASON = {
    1: "'Trade longs' / 'Trade shorts' is OFF for this side.",
    2: "Arm source OFF — this setup was armed by the sweep or divergence trigger you disabled.",
    3: "Final-hour rule — no new entries 16:00-18:00 New York, ahead of the daily close.",
    4: "Divergence / extreme-RSI veto — opposing divergence live at the SOS, or RSI at an extreme.",
    5: "HTF exhaustion filter — the higher timeframe just CLOSED through its prior extreme, so "
       "this is a fresh breakout rather than an exhaustion fade.",
    6: "HTF bias requirement — your Weekly / Daily bias gate is not satisfied.",
    7: "Minimum stop distance — the stop sits closer to the entry than your floor, so this "
       "position would be oversized and noise-sensitive.",
}


def _block_codes(dir_off: bool, arm_off: bool, late: bool, veto: bool,
                 htf_brk: bool, htf_bias: bool, tight: bool = False) -> List[int]:
    """Every rule refusing this side, in the Pine's `f_blkCode` precedence order.
    Empty = nothing is blocking; `[0]` is what `f_blkCode` itself would have returned.

    `tight` (the minimum-stop floor) is LAST in precedence and defaults False because it is
    the only code that depends on price rather than on a toggle — a caller that has not
    computed the stop distance yet simply omits it."""
    return [c for c, on in enumerate(
        (dir_off, arm_off, late, veto, htf_brk, htf_bias, tight), start=1) if on]


@dataclass
class BlockedSetup:
    """One refusal, at the bar it was refused on. `edge` is where the limit would have
    rested — the price the trade never got. `codes` holds EVERY rule that was refusing it,
    in precedence order (see the deviation note above), so `codes[0]` is the primary."""

    dir: int              # +1 long, -1 short
    index: int            # bar index
    time_ms: int
    codes: List[int]      # 1-7, the Pine reason codes, precedence-ordered
    edge: float
    sos_bar: int

    @property
    def code(self) -> int:
        """The PRIMARY reason — what Pine's `f_blkCode` would have reported alone."""
        return self.codes[0] if self.codes else 0

    @property
    def labels(self) -> List[str]:
        return [_BLOCK_LABEL.get(c, "Blocked") for c in self.codes]

    @property
    def reasons(self) -> List[str]:
        return [_BLOCK_REASON.get(c, "") for c in self.codes]


# ── missed setups (Pine 3064-3194 + 4017-4023) — reporting only ─────────────────
# A MISSED setup is the other half of "why didn't this trade", and a different question from a
# BLOCKED one. A block is a setup that was fully READY and a toggle refused it. A miss is a setup
# that got to 2 or 3 of the three confluences and then DIED without ever becoming a trade — most
# often because price never came back, or came back with nothing to enter from.
#
# The three confluences, and what "met" means for each (Pine `f_w23`):
#   1  ARM    a liquidity sweep or an RSI divergence armed Stage 1 — and counts only if the arm
#             source that fired is one you have ENABLED.
#   2  SOS    always met: it is why the watch is open at all.
#   3  ZONE   price tagged the 0.5-0.886 retrace band AND (with Require-FVG on) a gap was live in
#             that band while price was there. Reaching the band is only half of it — having
#             something to rest a limit on is the other half.
#
# Exactly ONE thing is ever missing. At 2 of 3 it is the arm or the zone; at 3 of 3 every
# confluence was there and the entry still never happened, so the miss names the entry-side
# reason instead — in the Pine's own precedence: veto, then the final hour, then HTF, else the
# limit simply rested and price never touched it.
#
# REPORTING ONLY, exactly like `BlockedSetup` below: nothing reads a record back, so it cannot
# move a decision and `compare_strategy.py`'s `px_*` stream is untouched.
_MISS_LABEL = {
    1: "Arm source off",
    2: "No retrace",
    3: "No FVG in zone",
    4: "Divergence / RSI veto",
    5: "Final hour",
    6: "HTF filter",
    7: "Never filled",
}
_MISS_REASON = {
    2: "Price never retraced into the 0.5-0.886 band, so the entry zone was never reached. This "
       "is the ordinary way a setup dies.",
    3: "Price DID reach the 0.5-0.886 band, but no fair-value gap overlapped it while price was "
       "there — there was nothing to rest a limit on.",
    4: "All three confluences met. The divergence / extreme-RSI veto refused the entry.",
    5: "All three confluences met. The final-hour rule (16:00-18:00 New York) refused the entry.",
    6: "All three confluences met. The HTF breakout / bias filter refused the entry.",
    7: "All three confluences met and the limit rested — price never came back to touch it.",
}


@dataclass
class MissedSetup:
    """One setup that reached 2-of-3 or better and died without trading.

    `code` is the ONE thing that was missing (see `_MISS_LABEL`); `met` is 2 or 3. `edge` is
    where the limit would have rested — the entry edge if one ever existed, else the 0.618.
    `near` mirrors the Pine's "near miss" test (`debug23Filter`'s default view): a miss worth
    looking at is one that met all three and still did not fill, or that got price into the zone
    and failed only on the FVG. Everything else is the ordinary outcome of most setups, and is
    what floods a chart — the lab records it anyway and lets the reader filter."""

    dir: int              # +1 long, -1 short
    index: int            # bar index the miss was booked on (the bar the setup died)
    time_ms: int
    met: int              # 2 or 3 (of 3)
    code: int             # 1-7 — the single missing piece
    arm_text: str         # what armed it, in words: "Sweep · Day Low" / "RSI divergence"
    arm_met: bool         # ...and whether that source is one you have enabled
    zone: bool            # price tagged the 0.5-0.886 band
    fvg: bool             # ...and a gap was live while it was there
    edge: float           # where the limit would have rested
    near: bool

    @property
    def labels(self) -> List[str]:
        """A list of one, to match `BlockedSetup`'s shape — the lab reads both the same way."""
        return [_MISS_LABEL.get(self.code, "Missed")]

    @property
    def reasons(self) -> List[str]:
        # Code 1 is the only DYNAMIC sentence: it has to name the source that armed the setup,
        # because "the trigger you switched off" is meaningless without saying which one.
        if self.code == 1:
            return [f"Armed by {self.arm_text} — that arm source is switched OFF. Every other "
                    f"confluence was there."]
        return [_MISS_REASON.get(self.code, "")]

    @property
    def met_lines(self) -> List[str]:
        """The MET breakdown, in the Pine's order — what this setup DID have."""
        out: List[str] = []
        if self.arm_met:
            out.append(f"Arm — {self.arm_text}")
        out.append("SOS — confirmed")
        if self.zone:
            out.append("Zone — 0.5-0.886 tagged" + (", FVG live" if self.fvg else ""))
        return out


@dataclass
class _MissWatch:
    """Per-side state of one live setup (Pine `type MissW`). Opened the moment a setup reaches
    stage 2 and held until it either BECOMES A TRADE or DIES — deliberately NOT closed when price
    reaches the retrace zone, which is the bug that used to make a setup that got all the way to
    the zone and then failed to enter vanish with no explanation."""

    watch: bool = False
    sos_bar: Optional[int] = None
    arm_src: str = ""                 # "SWP" / "DIV" — which source actually armed it
    swp_nm: str = ""                  # the swept level's name, e.g. "Day Low"
    zone: bool = False
    fvg: bool = False
    edge: Optional[float] = None      # first entry edge seen while alive
    fib: Optional[float] = None       # 0.618 fallback, kept fresh
    blk_v: bool = False               # a veto was live while in the zone
    blk_l: bool = False               # the final-hour rule was live while in the zone
    blk_h: bool = False               # an HTF filter was live while in the zone

    def open(self, sos_bar: Optional[int], arm_src: str, swp_nm: str) -> None:
        self.watch, self.sos_bar, self.arm_src, self.swp_nm = True, sos_bar, arm_src, swp_nm
        self.zone = self.fvg = self.blk_v = self.blk_l = self.blk_h = False
        self.edge = self.fib = None


# ── the fib leg a trade was priced off (reporting only) ─────────────────────────
# Every ratio the strategy reads, at the price it read it at, frozen on the bar the order was
# placed. It is a RECORD, not a derivation: `_place_entries` copies the same `fiboP*` values that
# picked the entry edge, the stop anchor and both targets, so a chart drawing this ladder is
# drawing the levels the trade was actually priced against rather than a fib recomputed later
# from anchors and a direction. That distinction is the whole point — a fib rebuilt downstream is
# a second claim about the same leg, and two claims can disagree.
#
# REPORTING ONLY, the same standing as `Trade.mfe_usd` / `tp1` / `tp2`: nothing reads a frozen
# ladder back, so no decision can move and `compare_strategy.py` diffs the same `px_*` stream.
#
# `start_ms` is the bar the LEG began on (the earlier of the two anchors), which is what gives the
# drawing an x-span reaching back through the retracement instead of starting at the entry.
_FIB_RATIOS = ((0.0, "fibo_p7"), (0.382, "fibo_p1"), (0.5, "fibo_p2"), (0.618, "fibo_p3"),
               (0.702, "fibo_p4"), (0.786, "fibo_p5"), (0.886, "fibo_p6"), (1.0, "fibo_p10"))


@dataclass
class TradeFib:
    """The fib leg a trade was priced off. `levels` is (ratio, price), shallow → deep."""

    levels: List[Tuple[float, float]]
    start_ms: Optional[int] = None


def _freeze_fib(sig) -> Optional[TradeFib]:
    """Snapshot the live Structure fib, or None when it is not fully priced.

    All-or-nothing on purpose: a partial ladder would draw some levels and silently omit others,
    which reads as "the trade had no 0.786" rather than "this record is incomplete"."""
    levels: List[Tuple[float, float]] = []
    for ratio, attr in _FIB_RATIOS:
        price = getattr(sig, attr, None)
        if price is None:
            return None
        levels.append((ratio, float(price)))
    stamps = [t for t in (sig.fibo_ash_ms, sig.fibo_asl_ms) if t is not None]
    return TradeFib(levels=levels, start_ms=min(stamps) if stamps else None)


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
    # The whole fib ladder those levels came off, frozen on the same bar (reporting only).
    fib: Optional[TradeFib] = None


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

    # Whether this order layer records MISSED setups. The codes describe how far an **A+** setup
    # got before it died, so a fork where A+ never places an order must switch this off rather
    # than report near-misses of a trade it was never going to take — the same call the B-LEG
    # fork already makes for the blocked markers, for the same reason.
    _records_misses = True

    @property
    def cfg(self):
        """The live config object. READ-ONLY accessor over `_cfg` — no behaviour, no parity
        impact.

        It exists because two consumers outside this package legitimately need to read the
        settings a trade was taken under, and both were reaching for `.cfg` defensively:
        `algos/live/bridge.py` records the risk % on each ledger entry, and
        `algos/live/runner.py` applies a runtime risk change to the running strategy. With
        only the private `_cfg`, `getattr(ex, "cfg", None)` silently returned None and both
        quietly fell back to a default — the ledger recorded no risk at all, and the live
        reload crashed the loop. Neither failed loudly.

        The object is MUTABLE through this handle, and deliberately so: the runner sets
        `exec_risk_pct` on it while the bot is flat. Sizing reads `cfg.exec_risk_pct` at
        trade time (see `_size`), so the next trade picks it up with nothing to rebuild.
        """
        return self._cfg

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
        self._costs_usd = 0.0               # this trade's commission + swap + slippage so far
        self._last_roll_ms: Optional[int] = None   # last rollover already charged

        # position state
        self._pos_dir = 0                  # 0 flat, +1 long, -1 short
        # which layer opened the current position — "primary" (15m) or "secondary" (1m sniper).
        # 15m `step()` only manages a primary; the 1m `step_secondary()` only manages a secondary.
        # They share this one position slot but never the same trade (the secondary arms only when
        # flat), so the tag is all that keeps each stream off the other's position. When flat it is
        # ignored, so with `exec_secondary` OFF (no secondary ever opens) `step()` is unchanged.
        self._entry_kind = "primary"
        # A force-close DECIDED at this bar's close and FILLED at the next bar's open, held as
        # (reason, leg tag) or None. Pine's `strategy.close()` is a MARKET order, and a market
        # order in this fill model is subject to the same one-bar delay every other order is —
        # it cannot execute on the bar that decided it, because that bar has already closed.
        # Measured on a real 4-hour-cutoff export (2026-08-06): Python was closing at bar 696's
        # close 3651.28 while Pine closed at bar 697's open 3651.23, one bar apart on every
        # clock-driven exit. See `### The time stop` in this package's CLAUDE.md.
        self._pending_close: Optional[Tuple[str, str]] = None
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
        self._fib: Optional[TradeFib] = None   # the open trade's frozen fib leg (reporting only)
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
        # Blocked setups (reporting only — see BlockedSetup). `_blk_keys` is the Pine's
        # per-side dedupe latch (`sosBar*10 + code`): one entry per setup per REASON, so a
        # setup blocked for twenty bars is one record — but a reason SET that CHANGES is a
        # genuinely different refusal and gets its own.
        self.blocks: List[BlockedSetup] = []
        self._blk_keys: List[Optional[Tuple[int, Tuple[int, ...]]]] = [None, None]
        # The gate booleans `_armed` computed this bar, stashed for `_record_blocks`. `_armed`
        # stays a pure gate (the B-LEG fork reuses it as its A+-priority check), and the
        # recording hangs off `_place_entries`, which that fork overrides — which is exactly
        # why the B-LEG bot records no blocks: its codes describe why an A+ setup was refused,
        # and A+ never trades there. See strategies/python/mpc_bleg/CLAUDE.md.
        self._blk_gates: Optional[Tuple[bool, ...]] = None
        # Missed setups (reporting only — see MissedSetup). One watch per side, plus last bar's
        # stage so the watch opens on the RISING edge into stage 2 (Pine `stage[1] < 2`).
        self.misses: List[MissedSetup] = []
        self._mw: List[_MissWatch] = [_MissWatch(), _MissWatch()]
        self._prev_stage: List[int] = [0, 0]
        # ATR(14) for the "x ATR(14)" minimum-stop mode. Pine hoists `ta.atr(14)` to the main
        # body so it runs on EVERY bar — a `ta.*` call inside a conditionally-taken branch
        # silently skips bars and returns a different number. Same discipline here: updated at
        # the top of every `step()`, never inside the entry branch, and never on a 1m
        # `step_secondary` bar (the Pine's ATR is on the chart timeframe).
        self._atr: Optional[float] = None
        self._atr_trs: List[float] = []
        self._atr_prev_close: Optional[float] = None

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
            adj = self._ask_adj(pend.dir, entry=True)   # the sniper is a resting limit too
            if pend.dir > 0 and sig1m.low + adj <= pend.edge:
                o = sig1m.open + adj
                fill = pend.edge if o > pend.edge else o
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
        elif self._entry_kind == "secondary" and filled_dir is None:
            # `filled_dir is None` = this 1m bar is not the fill bar. Same rule as the primary
            # (see the fill-bar note in `step`): the sniper also enters on a resting limit, so
            # its fill bar's extreme is the approach to that limit, not the trade's own move.
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

        # Runs before anything can branch — see `_update_atr`.
        self._update_atr(sig)

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
        # A force-close decided last bar is a MARKET order, so it fills at THIS bar's open —
        # before any stop or target, exactly as TradingView executes a `strategy.close()` ahead
        # of the bar's own trading. Doing it after `_manage_open` would let a stop that the
        # market only reached mid-bar pre-empt an exit the broker had already filled.
        if self._pending_close is not None and self._pos_dir != 0 and not opened:
            reason, tag = self._pending_close
            self._close_at(sig, sig.open, reason, dec, tag=tag)
        self._pending_close = None
        # Exit orders are placed at a bar's close and active the NEXT bar, so a trade
        # never fills an exit on the bar it opened (TradingView one-bar delay). A secondary
        # position is managed on the 1m stream, so a 15m bar never touches it.
        if self._pos_dir != 0 and not opened and self._entry_kind != "secondary":
            self._manage_open(sig, dec)

        # The missed-setup watch runs EVERY bar, between the fills and the placement — the same
        # slot the Pine calls `f_w23` from (after the fill state is known, before `strategy.entry`).
        # It cannot live in `_place_entries` like the blocked marker does: a setup keeps
        # accumulating state while a position from the other side is open, and that path never
        # runs then.
        self._record_misses(sig, seq, dec, long_edge, short_edge)

        # ── Phase B: at close, (re)place orders for the next bar ──
        if self._pos_dir != 0 and self._entry_kind != "secondary":
            # The FILL bar cannot stage the stop (Pine: `and strategy.position_size[1] > 0`,
            # i.e. we were ALREADY in the position last bar, so this is not the fill bar). A resting
            # limit is reached by price coming to it from the wrong side — a buy limit fills on
            # the way DOWN, a sell limit on the way UP — so the fill bar's favourable extreme is
            # where the market was BEFORE the trade existed, not profit the trade made. Staging
            # off it lifted the stop to breakeven on a trade that had gone nowhere, and breakeven
            # is then on the WRONG SIDE of the market, so every leg market-closes at the next
            # bar's open at a price that is neither the stop nor any target. The exit orders are
            # not live on this bar either (one-bar delay), so nothing could have banked here.
            if not opened:
                self._advance_stage(sig)
            dec.stop = self._current_stop()
            dec.tp1, dec.tp2 = self._tp1, self._tp2
            # tell the account this leg's live stop + remaining size, so its reservation is
            # current for any other leg sizing on the next tick (drops to 0 once stop = BE).
            self._account.update_stop(self._leg, dec.stop, self._qty - self._filled_qty)
            # optional force-close on an opposite SOS (Pine execCloseOppSOS)
            if self._cfg.exec_close_opp_sos and (
                (self._pos_dir > 0 and sig.bear_sos) or (self._pos_dir < 0 and sig.bull_sos)
            ):
                self._pending_close = ("opp-SOS", "CLOSE")
            # deliberate deviation: force-flat before the daily close (real runs only)
            elif self._cfg.flat_by_close and self._in_flat_window(sig):
                # The ONE force-close that fills at this bar's CLOSE rather than the next open,
                # and it is not an inconsistency: it has no `strategy.close()` behind it (there is
                # no such input in any Pine file) and its whole purpose is to be FLAT before the
                # daily close. Deferring it to the next bar's open would carry the position
                # overnight — the exact thing it exists to prevent — and would charge the swap it
                # was switched on to avoid.
                self._close_at(sig, sig.close, "flat-by-close", dec)
            # optional time stop (Pine execTimeStopMode) — the clock, not the price
            elif self._time_stop_due(sig):
                self._pending_close = ("time-stop", "TIME")
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
        late, htf_block_l, htf_block_s, bias_block_l, bias_block_s = self._bar_gates(sig)

        # arm-source filter (Pine 4349-4355)
        use_swp_l = cfg.exec_arm_sweep and seq.sos_l_swp
        use_div_l = cfg.exec_arm_div and seq.sos_l_div
        use_swp_s = cfg.exec_arm_sweep and seq.sos_s_swp
        use_div_s = cfg.exec_arm_div and seq.sos_s_div
        arm_ok_l = use_swp_l or use_div_l
        arm_ok_s = use_swp_s or use_div_s

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
        # Hand the gate booleans to `_record_blocks` rather than recompute them there — one
        # place decides what "blocked" means, so the marker can never disagree with the arm.
        self._blk_gates = (late, arm_ok_l, arm_ok_s, htf_block_l, htf_block_s,
                           bias_block_l, bias_block_s)
        return long_armed, short_armed

    # ── bar-only gates ───────────────────────────────────────────────────────────
    def _bar_gates(self, sig) -> Tuple[bool, bool, bool, bool, bool]:
        """`(late, htf_block_l, htf_block_s, bias_block_l, bias_block_s)` — the refusal gates
        that depend on the BAR alone, not on the sequence or on being flat.

        Extracted from `_armed` because the missed-setup watch needs them on every bar, including
        while a position is open, where `_armed` never runs. Pure and cheap; one place decides
        what "the final hour" and "the HTF filter" mean, so a marker can never disagree with the
        arm about it."""
        cfg = self._cfg
        late = cfg.exec_no_late_day and 16 <= sig.ny_hour < 18   # 16:00-17:59 NY block
        htf_l, htf_s = self._htf_exhaustion_block(sig)
        bias_l, bias_s = self._htf_bias_block(sig)
        return late, htf_l, htf_s, bias_l, bias_s

    # ── missed-setup watch (Pine f_w23Arm / f_w23, 3116-3194 + 4022-4023) ────────
    def _record_misses(self, sig, seq, dec, long_edge, short_edge) -> None:
        """Track each side's live setup and book a MISS when it dies without trading.

        Two DELIBERATE deviations from the Pine, both reporting-side only:

        1. **Every miss is recorded; none is filtered away here.** The Pine has three view
           filters (`debugShow23`, `debug23Filter`, `debugShow23Disarmed`) and a `debugDays`
           recency window, because a TradingView chart has a hard 500-label cap and a wall of
           boxes is unreadable. The lab has neither problem: the reader filters BY REASON in the
           chart panel, which is strictly more expressive than the Pine's three presets — and a
           miss that was filtered out at write time could never be counted later.
        2. **A setup that filled this bar is closed as TRADED immediately.** The Pine assigns
           `tradedSosL` further down its script than it reads it, so on the fill bar it still
           reads the previous value. Both end with no callout; ours just gets there a bar sooner,
           and it is the correct answer on the one bar where they differ (a trade that opened and
           closed within the same bar, which the Pine would have booked as a miss).
        """
        if not self._records_misses:
            return
        cfg = self._cfg
        late, htf_l, htf_s, bias_l, bias_s = self._bar_gates(sig)

        # Which arm sources COUNT — the live flags already filtered through the enable-toggles,
        # exactly as `_armed` reads them, so "armed" means the same thing in both places.
        sides = (
            (0, True, seq.l_stage, seq.l_sos_bar, self._traded_sos_l, self._pos_dir <= 0,
             seq.l_half or seq.l_618, long_edge, dec.long_veto and cfg.exec_respect_veto,
             htf_l or bias_l, cfg.exec_arm_sweep and seq.sos_l_swp,
             cfg.exec_arm_div and seq.sos_l_div, seq.l_arm_src, sig.recent_ssl),
            (1, False, seq.s_stage, seq.s_sos_bar, self._traded_sos_s, self._pos_dir >= 0,
             seq.s_half or seq.s_618, short_edge, dec.short_veto and cfg.exec_respect_veto,
             htf_s or bias_s, cfg.exec_arm_sweep and seq.sos_s_swp,
             cfg.exec_arm_div and seq.sos_s_div, seq.s_arm_src, sig.recent_bsl),
        )
        for (slot, is_long, stage, sos_bar, traded_sos, flat, zone_hit, edge, veto,
             htf_any, arm_swp, arm_div, arm_src, swp_nm) in sides:
            m = self._mw[slot]
            # Open the watch on the RISING edge into stage 2 OR HIGHER — a fast leg can print the
            # SOS and tag the 0.5 on the same bar, jumping 1 → 3, and an `== 2` test would never
            # open the watch for it. The arm source and swept level are snapshotted here because
            # the sequence clears them the instant the setup dies.
            if stage >= 2 and self._prev_stage[slot] < 2:
                m.open(sos_bar, arm_src, swp_nm)
            self._prev_stage[slot] = stage

            if not m.watch:
                continue
            traded = traded_sos is not None and m.sos_bar is not None and traded_sos == m.sos_bar
            if sos_bar is not None and not traded:
                # still alive — accumulate what it achieved
                m.fib = sig.fibo_p3
                if m.edge is None and edge is not None:
                    m.edge = edge
                if zone_hit:
                    m.zone = True
                    m.fvg = m.fvg or edge is not None
                    m.blk_v = m.blk_v or veto
                    m.blk_l = m.blk_l or late
                    m.blk_h = m.blk_h or htf_any
                continue

            # it died (or traded) — book the miss, then close the watch either way
            m.watch = False
            if traded or not flat:
                continue
            arm_met = arm_swp or arm_div
            zone_met = m.zone and (m.fvg or not cfg.exec_req_fvg)
            met_n = (1 if arm_met else 0) + 1 + (1 if zone_met else 0)
            if met_n < 2:
                continue
            price = m.edge if m.edge is not None else m.fib
            if price is None:
                continue    # nothing to anchor a marker to — a record with no price can't be drawn
            if not arm_met:
                code = 1
            elif not m.zone:
                code = 2
            elif not zone_met:
                code = 3
            else:
                code = 4 if m.blk_v else 5 if m.blk_l else 6 if m.blk_h else 7
            if arm_met:
                arm_text = ("Sweep + RSI div" if (arm_swp and arm_div)
                            else "Sweep" if arm_swp else "RSI divergence")
                if arm_swp and m.swp_nm:
                    arm_text += f" · {m.swp_nm}"
            else:
                arm_text = "RSI divergence" if m.arm_src == "DIV" else "a liquidity sweep"
            self.misses.append(MissedSetup(
                dir=1 if is_long else -1, index=sig.index, time_ms=sig.time_ms,
                met=met_n, code=code, arm_text=arm_text, arm_met=arm_met,
                zone=m.zone, fvg=m.fvg, edge=float(price),
                near=met_n == 3 or (m.zone and not zone_met),
            ))

    # ── blocked-setup marker (Pine 4065-4086) — reporting only ───────────────────
    def _record_blocks(self, sig, seq, dec, long_edge, short_edge) -> None:
        """Record a setup that price and the engine had ready and one of the strategy's own
        toggles refused. Deliberately runs AFTER `_armed`, off the gates it computed."""
        if self._blk_gates is None:
            return
        cfg = self._cfg
        late, arm_ok_l, arm_ok_s, htf_l, htf_s, bias_l, bias_s = self._blk_gates

        # "Ready" omits every toggle gate — those ARE the blockers being reported. It asserts
        # only what price and the engine decide: the SOS is in, the fib agrees, an edge exists
        # to rest on, we're flat, and this leg has not already been traded.
        ready = (
            (seq.l_sos_bar is not None and sig.fibo_dir == 1 and long_edge is not None
             and self._pos_dir == 0
             and (self._traded_sos_l is None or seq.l_sos_bar != self._traded_sos_l)),
            (seq.s_sos_bar is not None and sig.fibo_dir == -1 and short_edge is not None
             and self._pos_dir == 0
             and (self._traded_sos_s is None or seq.s_sos_bar != self._traded_sos_s)),
        )
        # The min-stop refusal itself happens at order placement; it is recomputed here so a
        # setup refused on PRICE gets a record like every other refusal (Pine 4167-4172). A
        # missing fib leaves the anchor unknown, which reads as "not tight" — the same way na
        # propagates through the Pine's comparison.
        # Per SIDE, not once: with `exec_sl_deep` on, the anchor depends on that side's own
        # entry edge (Pine 4264-4265 calls f_slAnchor twice for the same reason).
        buf = cfg.exec_sl_buf_tk * cfg.mintick
        tight_l = tight_s = False
        if long_edge is not None:
            anchor_l = self._sl_anchor(sig, long_edge, True)
            if anchor_l is not None:
                tight_l = self._stop_is_tight(long_edge - (anchor_l - buf), long_edge)
        if short_edge is not None:
            anchor_s = self._sl_anchor(sig, short_edge, False)
            if anchor_s is not None:
                tight_s = self._stop_is_tight((anchor_s + buf) - short_edge, short_edge)

        codes = (
            _block_codes(not cfg.exec_longs, not arm_ok_l, late,
                         dec.long_veto and cfg.exec_respect_veto, htf_l, bias_l, tight_l),
            _block_codes(not cfg.exec_shorts, not arm_ok_s, late,
                         dec.short_veto and cfg.exec_respect_veto, htf_s, bias_s, tight_s),
        )
        for slot, (is_long, ok, cs, edge, sos_bar) in enumerate((
            (True, ready[0], codes[0], long_edge, seq.l_sos_bar),
            (False, ready[1], codes[1], short_edge, seq.s_sos_bar),
        )):
            if not ok or not cs or sos_bar is None or edge is None:
                continue
            # Pine's dedupe (`sosBar*10 + code`), generalised to the full reason SET: one
            # record per setup per distinct COMBINATION, so a setup blocked for twenty bars
            # is one record, but a setup that picks up (or sheds) a second blocker is a
            # genuinely different refusal and gets its own.
            key = (int(sos_bar), tuple(cs))
            if key == self._blk_keys[slot]:
                continue
            self._blk_keys[slot] = key
            self.blocks.append(BlockedSetup(
                dir=1 if is_long else -1, index=sig.index, time_ms=sig.time_ms,
                codes=list(cs), edge=float(edge), sos_bar=int(sos_bar)))

    # ── entry placement (Pine 4264-4507) ─────────────────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        long_armed, short_armed = self._armed(sig, seq, dec, long_edge, short_edge)
        self._record_blocks(sig, seq, dec, long_edge, short_edge)

        # deliberate deviation: no NEW entry inside the flat-by-close window (real runs)
        if cfg.flat_by_close and self._in_flat_window(sig):
            long_armed = short_armed = False

        # One snapshot for both sides — they read the same live fib, and taking it once is what
        # guarantees a long and a short placed on this bar report the identical leg.
        fib = _freeze_fib(sig) if (long_armed or short_armed) else None

        if long_armed:
            sl = self._sl_anchor(sig, long_edge, True) - cfg.exec_sl_buf_tk * cfg.mintick
            dist = long_edge - sl
            deep = long_edge <= sig.fibo_p3       # at/below 0.618
            tp1 = sig.fibo_p2 if deep else sig.fibo_p1   # deep 0.5 / shallow 0.382
            tp2 = sig.fibo_p1 if deep else sig.fibo_p7   # deep 0.382 / shallow 0.0
            if self._stop_clears_floor(dist, long_edge):
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                self._pend_long = _Pending(1, long_edge, qty, sl, tp1, tp2, seq.l_sos_bar, fib)
            else:
                self._pend_long = None
        else:
            self._pend_long = None

        if short_armed:
            sl = self._sl_anchor(sig, short_edge, False) + cfg.exec_sl_buf_tk * cfg.mintick
            dist = sl - short_edge
            deep = short_edge >= sig.fibo_p3
            tp1 = sig.fibo_p2 if deep else sig.fibo_p1
            tp2 = sig.fibo_p1 if deep else sig.fibo_p7
            if self._stop_clears_floor(dist, short_edge):
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                self._pend_short = _Pending(-1, short_edge, qty, sl, tp1, tp2, seq.s_sos_bar, fib)
            else:
                self._pend_short = None
        else:
            self._pend_short = None

    def _gap_pre_zone(self, born: int, sig) -> bool:
        """Pine `f_gapPreZone` — did this gap exist BEFORE price entered the zone?

        A gap is only confluence if it was already sitting in the band when price arrived. One
        printed by the reversal candle AFTER price is inside the 0.5-0.886 band is the retrace
        confirming itself, and it re-prices the resting limit to a level the setup never
        justified. `fibo_half_bar is None` = price has not reached the zone yet, so every gap
        trivially pre-dates it and the gate is inert. STRICTLY earlier: a gap born ON the
        zone-entry bar was still forming as price arrived, so it was not "present".

        Read by BOTH gap consumers — the confluence flag in `sequence.py` and the entry-edge
        loop below. Add the call to any future consumer of `sig.fvgs`, or that path becomes a
        way around this gate.
        """
        return (not self._cfg.exec_fvg_pre_zone
                or sig.fibo_half_bar is None
                or born < sig.fibo_half_bar)

    def _fib_snap(self, gb, gt, is_bull, sig) -> Optional[float]:
        """Pine `f_fibEntry` (2026-08-02; named `_fib_snap` here because `mpc_bos` already
        has an unrelated `_fib_entry`) — the FIB-SNAP entry price for a qualifying gap, or
        None for "leave the limit at the gap's own clamped edge". One function for the whole
        entry model, because its rules are decided off the same two numbers.

        The gap is first CLAMPED into the 0.5-0.886 band: `near` = the shallowest tradeable
        price (long = gap top, short = gap bottom), `far` = the deepest. A gap running past
        either end is therefore judged on the part of it that can actually be entered.

        Three levels are read off the ladder, all with 0.886 EXCLUDED (see the ⚠ below):
          `_l` = the SHALLOWEST level at or deeper than `near`. Because the ladder is ordered,
                 if that one is not ALSO at or shallower than `far` then no level is inside the
                 gap at all — so one comparison decides "does the body hold a level".
          `_s` = the nearest level SHALLOWER than the gap (price reaches it first).
          `_d` = the nearest level DEEPER than the gap (reached last, and only after trading
                 through the whole imbalance).

        Rule 1 (`exec_fib_overlap`) is independent. Rules 2 / 3 / Method 3 answer the SAME
        question — where does a FLOATING gap rest? — so they cascade, each overriding the next:
        `exec_fib_deep_edge` -> the gap's own deep edge · `exec_fib_nearest` -> whichever of
        `_s`/`_d` is closer (ties to `_s`) · `exec_deep_fib` -> `_s`, always (Method 3 exactly).
        A gap shallower than 0.618 that holds no level is untouched by all three.

        ⚠ `far` FALLS BACK TO `_s` WHEN THE GAP REACHES THE BAND FLOOR. A gap floating between
        0.786 and 0.886 clamps its deep edge onto fiboP6 — which is the STOP — so the guard
        sends it to 0.786 instead. Without it that gap is a zero stop distance and no order.

        ⚠ 0.886 IS DELIBERATELY NOT A SNAP TARGET in any rule. The stop is a fixed fib
        (`exec_sl_level`, default 0.886), so an entry resting AT 0.886 has a stop distance of
        zero: `dist > 0` fails, the order is cancelled, and the setup vanishes with no trade and
        no block tag. Stopping every scan at 0.786 hands those gaps what Method 3 already gave
        them, so no rule here can ever REMOVE a trade.

        p4/p5 may be None on a bar p2/p3/p6 are priced (`fibs_ready` does not check them, and
        neither does Pine's `fibsReady`); `_first` skips them, which is what Pine's `na`
        propagation through the ternary chain does.
        """
        cfg = self._cfg
        p2, p3, p4, p5, p6 = (sig.fibo_p2, sig.fibo_p3, sig.fibo_p4, sig.fibo_p5, sig.fibo_p6)
        if is_bull:
            near, far = min(gt, p2), max(gb, p6)
            _l = _first(lambda v: v <= near, (p2, p3, p4, p5))
            _s = _first(lambda v: v > near, (p6, p5, p4, p3, p2))
            _d = _first(lambda v: v < far, (p2, p3, p4, p5))
            _n = _nearest(_s, _d, far - _d if _d is not None else None,
                          _s - near if _s is not None else None)
            if cfg.exec_fib_overlap and _l is not None and _l >= far:
                return _l
            if near > p3:                       # gap shallower than 0.618 — plain edge
                return None
            if cfg.exec_fib_deep_edge:
                return far if far > p6 else _s
        else:
            near, far = max(gb, p2), min(gt, p6)
            _l = _first(lambda v: v >= near, (p2, p3, p4, p5))
            _s = _first(lambda v: v < near, (p6, p5, p4, p3, p2))
            _d = _first(lambda v: v > far, (p2, p3, p4, p5))
            _n = _nearest(_s, _d, _d - far if _d is not None else None,
                          near - _s if _s is not None else None)
            if cfg.exec_fib_overlap and _l is not None and _l <= far:
                return _l
            if near < p3:
                return None
            if cfg.exec_fib_deep_edge:
                return far if far < p6 else _s
        if cfg.exec_fib_nearest:
            return _n
        if cfg.exec_deep_fib:
            return _s
        return None

    def _entry_edges(self, sig) -> Tuple[Optional[float], Optional[float]]:
        """The resting-limit price on each side (Pine 3937-3959): the near edge of an
        FVG overlapping the 0.5-0.886 band, clamped into the band; the first one price
        reaches (highest for longs). With Require-FVG off it falls back to 0.618. The entry
        model (`_fib_snap`) may re-price a qualifying gap onto a fib instead of its own edge."""
        cfg = self._cfg
        p2, p3, p6 = sig.fibo_p2, sig.fibo_p3, sig.fibo_p6
        fibs_ready = None not in (sig.fibo_p1, p2, p3, p6, sig.fibo_p7, sig.fibo_p10)
        long_edge = short_edge = None
        if fibs_ready:
            for top, bot, is_bull, born in sig.fvgs:
                l_deep_ok = not cfg.exec_fvg_deep_only or top <= p2
                s_deep_ok = not cfg.exec_fvg_deep_only or bot >= p2
                # ANDed onto both sides rather than skipping the loop iteration, so with the
                # toggle off the condition is the original one exactly.
                pre_ok = self._gap_pre_zone(born, sig)
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6 and l_deep_ok and pre_ok:
                    df = self._fib_snap(bot, top, True, sig)
                    e = min(top, p2) if df is None else df   # snap override, else shallowest touch
                    long_edge = e if long_edge is None else max(long_edge, e)
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6 and s_deep_ok and pre_ok:
                    df = self._fib_snap(bot, top, False, sig)
                    e = max(bot, p2) if df is None else df
                    short_edge = e if short_edge is None else min(short_edge, e)
            if not cfg.exec_req_fvg:
                if long_edge is None and sig.fibo_dir == 1:
                    long_edge = p3
                if short_edge is None and sig.fibo_dir == -1:
                    short_edge = p3
        return long_edge, short_edge

    def _sl_anchor(self, sig, edge: Optional[float] = None, is_bull: bool = True) -> Optional[float]:
        """The fib price the stop sits at, before `exec_sl_buf_tk` (Pine `f_slAnchor`).

        The five named levels read a fiboP* the fib engine already priced. "Custom" (2026-08-02)
        prices an arbitrary ratio off the SAME leg anchors those fiboP* were built from, through
        the canonical `fib_level()` — so "0.886" and Custom 0.886 are the same float, not merely
        the same number, and switching between them moves nothing.

        `exec_sl_deep` (2026-08-02) makes the anchor depend on WHERE THE LIMIT RESTS, which is
        why this takes the entry edge. AT OR PAST the 0.786 line -> fib 1.0, the leg origin, the
        only level beyond the whole 0.5-0.886 entry band; 0.702 and shallower keeps the chosen
        level. A missing edge is treated as SHALLOW, so an unknown edge can never silently widen
        a stop. The test is inclusive (<= / >=) because 0.786 is a snap target — `_fib_entry`
        assigns fiboP5 to the edge directly, with no arithmetic in between, so it is exact.

        None only when the fib is inactive, which is the same bar every fiboP* is None. Callers
        that place an order are already past `fibs_ready` (an entry edge cannot exist without it),
        so the None is reachable only from `_record_blocks`, which checks for it.
        """
        cfg = self._cfg
        if cfg.exec_sl_deep and edge is not None and sig.fibo_p5 is not None and (
                edge <= sig.fibo_p5 if is_bull else edge >= sig.fibo_p5):
            return sig.fibo_p10
        if cfg.exec_sl_level == "Custom":
            if sig.fibo_ash is None or sig.fibo_asl is None or sig.fibo_dir == 0:
                return None
            return fib_level(sig.fibo_ash, sig.fibo_asl, sig.fibo_dir, cfg.exec_sl_custom)
        return {
            "0.618": sig.fibo_p3, "0.702": sig.fibo_p4, "0.786": sig.fibo_p5,
            "0.886": sig.fibo_p6,
        }.get(cfg.exec_sl_level, sig.fibo_p10)

    # ── minimum stop distance (Pine 3801-3807, execMinStopMode / execMinStopVal) ──
    def _update_atr(self, sig) -> None:
        """Pine `ta.atr(14)` = `ta.rma(ta.tr(true), 14)`, reproduced exactly.

        `ta.tr(true)` uses high-low on the first bar (no prior close to reference); `ta.rma`
        is NA until it has `length` values, then seeds with their SMA and runs Wilder from
        there. The NA phase matters: with the "x ATR(14)" mode selected, an unknown floor
        makes Pine's `slDist >= floor` comparison NA, which reads as false — so the first 13
        bars refuse every entry rather than pass them. `_min_stop_floor` returns None for
        exactly that case so the caller can reproduce it."""
        c_prev = self._atr_prev_close
        tr = (sig.high - sig.low) if c_prev is None else max(
            sig.high - sig.low, abs(sig.high - c_prev), abs(sig.low - c_prev))
        self._atr_prev_close = sig.close
        if self._atr is None:
            self._atr_trs.append(tr)
            if len(self._atr_trs) == 14:
                self._atr = sum(self._atr_trs) / 14.0     # the SMA seed
        else:
            self._atr += (tr - self._atr) / 14.0          # Wilder: alpha = 1/length

    def _min_stop_floor(self, px: float) -> Optional[float]:
        """The floor in PRICE for the selected mode, or None when it cannot be known yet
        (ATR mode before the ATR has 14 bars). `0.0` — the "Off" answer — is a real floor
        that every positive stop distance clears, so the default stays inert."""
        cfg = self._cfg
        mode = cfg.exec_min_stop_mode
        if mode == "% of price":
            return px * cfg.exec_min_stop_val / 100.0
        if mode == "Fixed $":
            return cfg.exec_min_stop_val
        if mode == "x ATR(14)":
            return None if self._atr is None else cfg.exec_min_stop_val * self._atr
        return 0.0

    def _stop_clears_floor(self, dist: float, edge: float) -> bool:
        """Pine's `slDist > 0 and slDist >= f_minStopFloor(edge)`, with NA reading as false."""
        if dist <= 0:
            return False
        floor = self._min_stop_floor(edge)
        return floor is not None and dist >= floor

    def _stop_is_tight(self, dist: float, edge: float) -> bool:
        """Pine's `lBlkTight` — a POSITIVE stop distance that fails the floor, which is what
        distinguishes a floor refusal from an inverted stop (that has its own cancel path).
        NA reads as false here too, so the ATR warmup refuses entries WITHOUT tagging them —
        matching the Pine, whose `<` against NA is equally falsy."""
        if dist <= 0:
            return False
        floor = self._min_stop_floor(edge)
        return floor is not None and dist < floor

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
        # Path order is read off the BID bar, and correctly so: `_ask_adj` shifts open, high and
        # low by the same constant, which leaves every distance between them unchanged.
        targets_first = _intrabar_targets_first(sig.open, sig.high, sig.low)
        order = [self._pend_long, self._pend_short] if targets_first \
            else [self._pend_short, self._pend_long]
        for pend in order:
            if pend is None:
                continue
            adj = self._ask_adj(pend.dir, entry=True)   # long buys the ask; short sells the bid
            if pend.dir > 0 and sig.low + adj <= pend.edge:
                o = sig.open + adj
                fill = pend.edge if o > pend.edge else o     # gap = better fill
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
        # The ladder those three came off, carried through to the closed Trade (reporting only).
        # Taken from the ORDER, not from `sig`: the fib is a live thing that keeps extending, so
        # reading it again at the fill would report a leg the resting limit was never priced on.
        self._fib = pend.fib
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
        self._charge_spread(pend.qty)       # half the round turn; the exits pay the other half
        # Seeded from the ENTRY PRICE, not the entry bar's extreme (Pine `lMaxFav := lEntry`).
        # The bar's FAVOURABLE extreme is where price was on its way INTO the resting limit,
        # i.e. before the trade existed — see the fill-bar note in `step`.
        self._max_fav = fill_price
        self._trail_swing_hi = None                     # structure-trail anchors — same
        self._trail_swing_lo = None
        # Excursion (reporting only) is seeded ASYMMETRICALLY on the entry bar, and the asymmetry
        # is the whole point: a buy limit is filled on the way DOWN, so the bar's LOW is reached
        # AFTER the fill and is a real adverse excursion, while its HIGH is the approach and is
        # not the trade's move at all. Mirrored for a short. Seeding both from the bar (the old
        # behaviour) is what made this bug's own report conclude "favorable excursion = 0, so the
        # stop was never staged" — a reading of the approach, not of the trade.
        if pend.dir > 0:
            self._ext_high, self._ext_low = fill_price, sig.low
        else:
            self._ext_high, self._ext_low = sig.high, fill_price
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
        # so the closing bar's extreme counts too. Never read by a decision. Shifted onto the ASK
        # for a short, so the reported best and worst prices are ones its exits could have got.
        adj = self._exit_adj()
        self._ext_high = max(self._ext_high, sig.high + adj)
        self._ext_low = min(self._ext_low, sig.low + adj)
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
            self._exit_portion(oid, fill.price, qty, sig, dec, market=False)
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
        adj = self._exit_adj()      # a short exits by BUYING — test it against the ask

        # Build the remaining brackets (id, target-price-or-None, portion-qty).
        brackets = self._remaining_brackets()
        if not brackets:
            return

        for oid, target, qty in brackets:
            hit_target = target is not None and (
                (d > 0 and sig.high >= target) or (d < 0 and sig.low + adj <= target))
            hit_stop = (d > 0 and sig.low <= stop) or (d < 0 and sig.high + adj >= stop)
            if not hit_target and not hit_stop:
                continue
            if hit_target and hit_stop:
                take_target = targets_first  # path order decides
            else:
                take_target = hit_target
            level = target if take_target else stop
            price = self._fill_price(level, sig.open + adj, take_target)
            self._exit_portion(oid, price, qty, sig, dec, market=not take_target)
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

    def _exit_portion(self, oid, price, qty, sig, dec, *, market: bool = True) -> None:
        # `market` says whether this fill was a MARKET order (a stop, or a force-close) rather
        # than a resting limit (a TP rung). Only the market ones can slip — see _charge_slippage.
        # It defaults True because every caller that does not pass it is a force-close.
        d = self._pos_dir
        pnl = (price - self._entry) * d * qty * self._cfg.point_value
        self._equity_realized += pnl
        self._account.book_pnl(self._leg, pnl)   # realize onto the shared balance as it happens
        self._charge_commission(qty)        # commission is per SIDE — each ladder leg pays
        self._charge_spread(qty)            # ...and so does each leg's half of the spread
        if market:
            self._charge_slippage(qty)
        self._filled_qty += qty
        self._exit_notional += price * qty
        self._exit_qty += qty
        self._exit_ms = sig.time_ms
        self._exit_reason = oid
        self._legs.append({"reason": oid, "price": price, "ms": sig.time_ms, "qty": qty})
        dec.fills.append(Fill("exit", oid, price, qty, d))
        if self._filled_qty >= self._qty - 1e-9:
            self._finalise_trade(sig, dec)

    def _close_at(self, sig, price, _reason, dec, *, tag: str = "CLOSE") -> None:
        # `tag` names the exit leg (L-CLOSE / L-TIME / ...). It defaults to CLOSE so the
        # opposite-SOS and flat-by-close paths keep the leg name every stored run already
        # carries — a force-close is a force-close, and renaming those retroactively would
        # make an old run's exit list stop matching its own chart.
        remaining = self._qty - self._filled_qty
        if remaining <= 1e-12:
            return
        prefix = "L" if self._pos_dir > 0 else "S"
        self._exit_portion(f"{prefix}-{tag}", price, remaining, sig, dec)

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
            tp1=round(self._tp1, 5), tp2=round(self._tp2, 5), fib=self._fib))
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

    def _spread(self) -> float:
        """The stated bar-mode spread, or 0.0 when there is nothing to price.

        Tick mode returns 0.0 for the same reason `_charge_slippage` does: the resolver transacts
        on the real side of the book, so the spread is already IN the fill price and charging a
        stated one on top books it twice.

        ⚠ **An UNMEASURED spread raises rather than reading as 0.0** — `AccountProfile` carries a
        sentinel for an account nobody has measured (a raw PU Prime tier), and 0.0 means "charge
        nothing" on purpose. Collapsing the two would run a raw-tier backtest that silently
        charged commission and no spread, which is not a cost model any real account offers. The
        sentinel is also NEGATIVE, so passing it through would pay the trader half a spread per
        fill. The refusal is the profile's own, so it names the tool that fixes it."""
        if self._profile is None or self._resolver is not None:
            return 0.0
        refuse = getattr(self._profile, "spread_or_refuse", None)
        if refuse is not None:
            return refuse()
        return getattr(self._profile, "spread", 0.0)

    def _charge_spread(self, qty: float) -> None:
        """Charge HALF the spread on one side of a round turn.

        Half, not the whole thing, and it is the only split that survives a partial exit. The
        quoted mid sits between bid and ask, so each side of a round turn gives up `spread / 2`
        against it: a long lifts the ask to get in and hits the bid to get out. Charging half at
        the entry and half on each exit portion totals exactly one spread across the position
        however many rungs the ladder fills — charging a whole spread per fill would bill a
        three-leg exit three times.

        ⚠ **This is the ALTERNATIVE to `bid_ask_fills`, never its companion**, and the two are
        answering the same question two different ways:

        * **Here** — bill a flat spread per round turn and leave every fill where it was. Moves
          money, moves no trades, and stays directly comparable to a run with no costs at all.
        * **`bid_ask_fills`** — put every order on the side of the book it really transacts on,
          and let the cost fall wherever the order structure puts it.

        Running both bills the spread twice, so this returns early when the fills are modelled.

        ⚠ **They do NOT converge, and the reason matters more than the arithmetic.** A flat charge
        is the MARKET-ORDER intuition — buy the ask, sell the bid, lose the spread — and this
        strategy places neither side as a market order. Every order here names a PRICE, and a
        named price is reached when the relevant side of the book gets to it, so the spread
        changes WHEN you fill rather than what you are filled at. Worked through on a long: the
        buy limit fills at its own price (the ask got there) and the stop sells at its own price
        (the bid got there), so the cash result is identical and the whole effect is that the
        limit is harder to reach. A SHORT is where it really bites — it sells the bid to get in
        and BUYS THE ASK to get out, so its stop arrives a spread early and its targets a spread
        late, every time.

        So the flat charge is a deliberately CONSERVATIVE approximation for this strategy, not a
        cheaper version of the same answer: measured over 2020-2026 it takes 5.7R off the book
        while the fill model does not. Treat it as an upper bound on what the spread can cost,
        and `bid_ask_fills` as the question of what it actually does."""
        s = self._spread()
        if s <= 0 or getattr(self._profile, "bid_ask_fills", False):
            return
        self._charge(-(s / 2.0) * abs(qty) * self._cfg.point_value)

    # ── the ask side of the book (AccountProfile.bid_ask_fills) ───────────────────
    def _ask_adj(self, direction: int, *, entry: bool) -> float:
        """How much to ADD to this bar's bid prices before testing a level, in price units.

        Broker bars are the BID. A buy transacts at the ask, which is `spread` higher — so a
        level a buy is waiting on is reached when `bid + spread` gets there, not when the bid
        does. Which of the four order sides is a buy follows entirely from the position:

        * a LONG **enters** by buying (its limit is one spread harder to reach) and **exits** by
          selling (unchanged — the bar already is the bid);
        * a SHORT **enters** by selling (unchanged) and **exits** by buying — so its stop, its TP
          rungs and its excursion all live on the ask.

        So the whole rule is: a long's entry, and everything a short does after entry. Returns 0.0
        with the toggle off, which is what makes that path byte-identical to the old one."""
        s = self._spread()
        if s <= 0 or not getattr(self._profile, "bid_ask_fills", False):
            return 0.0
        return s if (direction > 0 if entry else direction < 0) else 0.0

    def _exit_adj(self) -> float:
        """`_ask_adj` for the OPEN position's own exits — nonzero only for a short."""
        return self._ask_adj(self._pos_dir, entry=False)

    def _charge_slippage(self, qty: float) -> None:
        """Charge the profile's per-fill slippage ESTIMATE on a market exit.

        Three gates, each of which is the honest answer to a different question:

        * **No profile ⇒ nothing.** Bar mode with no stated costs, which is what
          `compare_strategy.py` runs and what every historical result was measured at.
        * **Tick mode ⇒ nothing.** `TickPathResolver` fills at the next price that actually
          existed, so the slippage is already IN the fill price. Charging an estimate on top
          would book it twice.
        * **Market exits only.** The caller says whether this fill was a market order. A resting
          limit — the entry, and every TP rung — fills at its price or better or not at all, so
          it does not slip against us (`backtest/fills.py`, module docstring). Only a stop, and
          the force-closes that behave like one, pay.
        """
        if self._profile is None or self._resolver is not None:
            return
        ticks = getattr(self._profile, "slippage_ticks", 0)
        if not ticks:
            return
        cfg = self._cfg
        self._charge(-(ticks * cfg.mintick * abs(qty) * cfg.point_value))

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
        # A short's favourable extreme and its TP touches are read on the ASK, the same price its
        # rungs fill at (`_manage_open_bar`). They have to agree: staging the stop off a level the
        # rung could not fill at would move the stop for a take-profit that never happened.
        adj = self._exit_adj()
        if self._max_fav is None:
            self._max_fav = sig.high if d > 0 else sig.low + adj
        if d > 0:
            self._max_fav = max(self._max_fav, sig.high)
            if self._stage < 1 and sig.high >= self._tp1:
                self._stage = 1
            if self._stage < 2 and sig.high >= self._tp2:
                self._stage = 2
        else:
            self._max_fav = min(self._max_fav, sig.low + adj)
            if self._stage < 1 and sig.low + adj <= self._tp1:
                self._stage = 1
            if self._stage < 2 and sig.low + adj <= self._tp2:
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
        if cfg.exec_runner_trail == "Structure + % ratchet":
            # Pine f_swingRatchet. Same anchor as the plain structure trail, but the stop
            # then climbs one %-of-price step per step of favourable move, so it does not
            # sit at a lagging swing while price runs away. Falls back to the bare anchor
            # until the move is one full step past it — never LOOSER than Structure.
            swing = self._trail_swing_lo if d > 0 else self._trail_swing_hi
            if swing is None:
                return None
            buf = cfg.exec_struct_trail_buf_tk * cfg.mintick
            anchor = swing - buf if d > 0 else swing + buf
            if self._max_fav is None:
                return anchor
            step = self._max_fav * cfg.exec_trail_pct / 100.0
            run = (self._max_fav - anchor) * d
            if step <= 0 or run < step:
                return anchor
            steps = math.floor((run - step) / step)
            return anchor + steps * step * d
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

    def _time_stop_due(self, sig) -> bool:
        """Has this position been open longer than `exec_time_stop_hrs`, and does the mode
        still care about it?  (Pine `execTimeStopMode` / `execTimeStopHrs`.)

        The clock is CALENDAR hours since the fill, weekends included — the same basis the
        swap is charged on, and the one a reader can check against a chart without knowing
        which hours the market was open.

        `_stage == 0` is the "before TP1" test, and it is the existing state rather than a new
        flag on purpose: stage 1 IS "price touched TP1", the moment the stop staged to
        breakeven. Deriving it a second way would be a second claim about one event.
        """
        cfg = self._cfg
        if cfg.exec_time_stop_mode == "Off" or self._pos_dir == 0:
            return False
        if cfg.exec_time_stop_mode == "Before TP1 only" and self._stage != 0:
            return False
        # `>=` so a threshold landing exactly on a bar's close fires on that bar rather than a
        # bar later — the same convention `_min_stop_floor` uses for its floor.
        return (sig.time_ms - self._entry_ms) >= cfg.exec_time_stop_hrs * 3_600_000
