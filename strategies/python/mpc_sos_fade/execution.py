"""Execution — turns the A+ sequence state into orders, and fills them the way
TradingView's broker emulator does.

A port of the STRATEGY EXECUTION block in `indicators/strategies/mpc_strategy.pine` (4112-4735):
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
from backtest.setups import DEAD, FILLED, RESTING, WATCHING, Confluence, SetupSnapshot

# The canonical ratio→price helper, and the only one allowed: `_sl_anchor`'s Custom branch has to
# land on the exact float the fib engine would have produced for that ratio, and re-deriving
# `ash - range*ratio` here would be a second implementation free to drift by a bit.
from engines.fibonacci.geometry import fib_level

from .signals import POI_SOURCE_OB_NO_FVG, poi_rank_is_fvg, pois_for, sos_aware_veto


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
    `(exit_price - entry_price) * dir * qty * point_value` reproduces `pnl_usd`
    ONLY on a trade that filled no scale-in add. 🔴 `qty` is the BASE size and an add
    is a separate lot at its OWN entry price (see `_exit_portion`), so with adds the
    identity needs every lot:

        pnl_usd = (exit_price - entry_price) * dir * qty * point_value
                + Σ over `adds` of (exit_price - add.price) * dir * add.qty * point_value
                + costs_usd

    That is why `adds` is carried rather than folded into `qty`: without it a reader
    of the trade record — the chart included — sees a short exiting BELOW its entry and
    a P&L of zero, with nothing in the record to explain it. Measured on run
    295a6ff29d21: 8 trades booked exactly $0.00 and the add that took the profit back
    appeared in no field. `stop_distance` is entry→the stop frozen at PLACEMENT, i.e.
    the 1R the trade was sized against — not the trailed stop it may have exited on.
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
    # "primary" (the 15m A+ trade) or "secondary" (a fast-feed sniper re-entry). Reporting-only — no
    # decision reads it; it lets the lab/chart tell the two apart. See secondary.py.
    kind: str = "primary"
    # For a SECONDARY only, what the PRIMARY on the same setup DID — "breakeven" | "stopped" |
    # "closed", None when it cannot be told. Reporting-only, and it is the fact the price chart
    # needs to say WHY there is a second trade on this leg: the whole point of the re-entry layer
    # is that a scratch and a stop-out are different situations, and one `secondary` tag cannot
    # tell you which one you are looking at. ⚠ NOT the trigger — see `SecArm.l_after`.
    after: Optional[str] = None
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
    # Reporting-only SCALE-IN ledger — one dict per add lot that actually FILLED, in fill order
    # (a placed-but-unfilled add is not here; it bought nothing). Empty on every trade that never
    # added, which is every trade with `exec_scale_in` off. It is the only record that the position
    # was ever bigger than `qty` — see the P&L identity above.
    #
    # Each lot is a TRADE-SHAPED record, because a lot is a position and gets asked the same
    # questions: `{"price", "ms", "qty", "mfe_price", "mae_price", "exit_price", "exit_ms",
    # "exit_reason", "pnl_usd"}`. `mfe_price`/`mae_price` are the lot's OWN excursion, measured
    # from its own fill and not inherited from the base — an add bought 40 points into a runner
    # has a different best and worst price from the entry that started the trade, and reusing the
    # base's would report the base's move as the lot's.
    #
    # ⚠ Everything past `qty` is OPTIONAL and a consumer must treat it that way. A run stored
    # before 2026-08-19 carries the three original keys and nothing backfills it; `exit_price` is
    # absent (never 0.0) on a lot nothing closed.
    adds: List[dict] = field(default_factory=list)
    # Reporting-only TP TARGET ladder — the fib levels the trade AIMED at, frozen at entry (NOT
    # where each rung actually closed; that's `legs`). Lets the chart draw an UNHIT next target so a
    # runner's near-miss of the following TP is visible. No decision reads them (parity-safe).
    tp1: float = 0.0
    tp2: float = 0.0
    # The same two rungs as `(price, banks_pct)` pairs, in ladder order — how much of the position
    # each one actually TAKES OFF. `tp1`/`tp2` alone say only where a rung sits, and a chart reading
    # them has no way to tell a real profit target from a level that places no order at all and only
    # steps the stop. At the shipped settings BOTH rungs on a primary bank 0% (it runs on the trail
    # and banks nothing), and a chart drawing those two prices as "TP1"/"TP2" is claiming targets
    # the trade never had — which is exactly what it did until 2026-08-21.
    #
    # ⚠ The percentage is resolved for the trade that was actually OPEN, not read off the config:
    # a re-entry may bank its own percentage, and the reclaim half a different one again.
    #
    # REPORTING ONLY, the same standing as `mfe_usd` / `tp1` / `tp2` — no decision reads it back.
    # Empty rather than a guessed pair on any fork that prices its exits some other way, because
    # "this strategy does not report rungs" and "these rungs bank nothing" must not be one value.
    tp_rungs: Tuple[Tuple[float, float], ...] = ()
    # The fib LEG this trade was priced off, frozen at order placement — see `TradeFib`. Optional
    # for the same reason every other reporting field here is: a fork that prices its entries some
    # other way (`mpc_bleg` overrides `_place_entries` and works off band prices, not this ladder)
    # simply carries None, and the chart draws no fib for it rather than an invented one.
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
#: ⚠ **These are read in TWO places and shortening them moved both**: the Telegram `NO TRADE`
#: reply, and the lab's miss report. They are always rendered UNDER their `_MISS_LABEL`
#: ("No retrace", "No FVG in zone", …), so a sentence restating the label is saying it twice —
#: which is what the long forms did. Trimmed 2026-08-13 on Aaron's *"less verbose"*; the FACTS are
#: unchanged and no code branches on this text.
_MISS_REASON = {
    2: "Price never retraced into the 0.5-0.886 band.",
    3: "Price reached the band, but no fair-value gap overlapped it — nothing to rest a limit on.",
    4: "All three met. The divergence / extreme-RSI veto refused the entry.",
    5: "All three met. The final-hour rule (16:00-18:00 New York) refused the entry.",
    6: "All three met. The HTF breakout / bias filter refused the entry.",
    7: "All three met and the limit rested — price never came back to touch it.",
}


@dataclass
class MissedSetup:
    """One setup that reached 2-of-3 or better and died without trading.

    `code` is the ONE thing that was missing (see `_MISS_LABEL`); `met` is 2 or 3. `edge` is
    where the limit would have rested — the entry edge if one ever existed, else the 0.618.
    `near` mirrors the Pine's "near miss" test (`debug23Filter`'s default view): a miss worth
    looking at is one that met all three and still did not fill, or that got price into the zone
    and failed only on the FVG. Everything else is the ordinary outcome of most setups, and is
    what floods a chart — the lab records it anyway and lets the reader filter.

    ⚠ **`time_ms` is the bar the setup DIED, and it is nowhere near where the setup was.** The
    watch accumulates for as long as the leg lives, so on 32 of the 35 three-of-three misses in the
    reference run price sits a median $22 (and up to $205) away from `edge` on that bar. That is
    correct for a marker saying *this setup is now over*, and useless for any consumer asking
    *where was price when this setup was live* — which is why `zone_time_ms` and `zone_turn_ms`
    exist. They bracket the RETRACE: the first bar price tagged the 0.5-0.886 band, and the deepest
    bar it reached while in it. Both are `None` if price never got there (a 2-of-3 miss on the
    zone), and both are recorded rather than derived — searching back from the death bar for a bar
    that traded through `edge` finds one for all 35 of the reference run's three-of-three misses,
    *including the ten where price provably never reached the limit*, because price crosses that
    level at unrelated moments. Reporting only.

    ⚠ **`zone_turn_ms` is deliberately not "the extreme between the zone touch and the death"** —
    the watch outlives the visit by a median 18 and up to 718 bars, and over that range the extreme
    routinely belongs to a different move entirely."""

    dir: int              # +1 long, -1 short
    index: int            # bar index the miss was booked on (the bar the setup died)
    time_ms: int
    met: int              # 2 or 3 (of 3)
    code: int             # 1-7 — the single missing piece
    arm_text: str         # what armed it, in words: "Sweep · Day Low" / "RSI divergence"
    arm_met: bool         # ...and whether that source is one you have enabled
    zone: bool            # price tagged the 0.5-0.886 band
    zone_time_ms: Optional[int]   # WHEN it first did — see below
    zone_turn_ms: Optional[int]   # ...and the deepest bar of that visit
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
    # The DEEPEST visit to the band, and the visit currently in progress. A setup can tag the zone,
    # leave, and come back hundreds of bars later — those are different retraces, and the one worth
    # reporting is the one that came closest to filling.
    zone_ms: Optional[int] = None        # first bar of the deepest visit
    zone_turn_ms: Optional[int] = None   # ...and its most adverse bar
    zone_turn_px: Optional[float] = None
    run_bar: Optional[int] = None        # last bar of the visit in progress (contiguity test)
    run_ms: Optional[int] = None
    run_turn_ms: Optional[int] = None
    run_turn_px: Optional[float] = None
    fvg: bool = False
    edge: Optional[float] = None      # first entry edge seen while alive
    fib: Optional[float] = None       # 0.618 fallback, kept fresh
    blk_v: bool = False               # a veto was live while in the zone
    blk_l: bool = False               # the final-hour rule was live while in the zone
    blk_h: bool = False               # an HTF filter was live while in the zone

    def open(self, sos_bar: Optional[int], arm_src: str, swp_nm: str) -> None:
        self.watch, self.sos_bar, self.arm_src, self.swp_nm = True, sos_bar, arm_src, swp_nm
        self.zone = self.fvg = self.blk_v = self.blk_l = self.blk_h = False
        self.edge = self.fib = self.zone_ms = None
        self.zone_turn_ms = self.zone_turn_px = None
        self.run_bar = self.run_ms = self.run_turn_ms = self.run_turn_px = None

    def visit(self, sig, is_long: bool) -> None:
        """Track the RETRACE — which bars price actually spent in the 0.5-0.886 band, and how deep
        each visit ran. `zone_ms` / `zone_turn_ms` end up bracketing the DEEPEST visit, i.e. the one
        that came closest to filling.

        ⚠ **It must not be driven off the caller's `zone_hit`, which is a LATCH** (`l_half or
        l_618`): once price tags 0.5 that stays true until the leg resets, so every bar to the death
        reads as "in the zone" and the visit measures 717 bars on a real run. This asks the bar
        directly — does its range overlap `[0.5, 0.886]` — which is the question the latch was
        answering once and then remembering.

        A bar with no fib band yet extends the visit in progress rather than opening or closing one:
        the band is momentarily unknown, which is not the same as price having left it.
        """
        p2, p6 = sig.fibo_p2, sig.fibo_p6
        if p2 is None or p6 is None:
            return
        band_lo, band_hi = (p2, p6) if p2 <= p6 else (p6, p2)
        if sig.low > band_hi or sig.high < band_lo:
            return
        px = sig.low if is_long else sig.high
        if self.run_bar is None or sig.index != self.run_bar + 1:
            self.run_ms = self.run_turn_ms = sig.time_ms   # a new visit
            self.run_turn_px = px
        elif (px < self.run_turn_px) if is_long else (px > self.run_turn_px):
            self.run_turn_px, self.run_turn_ms = px, sig.time_ms
        self.run_bar = sig.index
        if self.zone_turn_px is None or (
                (self.run_turn_px < self.zone_turn_px) if is_long else
                (self.run_turn_px > self.zone_turn_px)):
            self.zone_ms, self.zone_turn_ms = self.run_ms, self.run_turn_ms
            self.zone_turn_px = self.run_turn_px


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
    # For a SECONDARY, which trigger armed it ("Structure shift" | "gap" | "reclaim"). NOT reporting-only:
    # the reclaim half carries its own exit ladder, so the open trade has to remember what it came
    # from. None on every primary and on any secondary from a caller that does not set it.
    src: Optional[str] = None
    # For a SECONDARY, what the primary on this setup did — reporting only, straight through to
    # the closed `Trade`. Never read by anything that arms, prices or sizes.
    after: Optional[str] = None


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
        # The OPENING balance, kept because it cannot be recovered afterwards: `equity` is the
        # closing one and subtracting the trades back off it silently assumes nothing else ever
        # touched the ledger. Read by the loss-recovery pass, which sizes off the running
        # balance and therefore has to start from the real one. Reporting-only — no decision
        # reads it, so parity is unaffected.
        self.initial_capital = float(initial_capital)
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
        # which layer opened the current position — "primary" (15m) or "secondary" (fast-feed sniper).
        # 15m `step()` only manages a primary; the fill-clock `step_secondary()` only manages a secondary.
        # They share this one position slot but never the same trade (the secondary arms only when
        # flat), so the tag is all that keeps each stream off the other's position. When flat it is
        # ignored, so with `exec_secondary` OFF (no secondary ever opens) `step()` is unchanged.
        self._entry_kind = "primary"
        # Which re-entry trigger armed the open secondary (see `_open_position`). None on a primary
        # and while flat.
        self._entry_src: Optional[str] = None
        self._entry_after: Optional[str] = None
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
        # Scale-in lots: [entry_price, qty_still_open] per add. Separate LOTS rather than extra
        # `_qty` because `_exit_portion` prices the position off one `_entry` — growing `_qty`
        # would value the added units as if bought at the base entry and invent profit.
        self._adds: List[List[float]] = []
        # The same lots as they were BOUGHT, never consumed by the exit — `_adds` above is a live
        # book and each lot's qty is decremented to zero on the way out, so it cannot answer "what
        # did this trade actually hold?" once the trade is closed. Reporting only.
        self._add_lots: List[dict] = []
        self._add_stop = None              # the stop the last add was sized against
        self._base_qty = 0.0               # size the trade OPENED with; every add sizes off it
        self._add_limit = None             # "BOS retest" mode: the price the next add rests at
        self._add_armed = False            # a break has fired and we are waiting for the retest
        self._add_pending = None           # qty of a PLACED add order not yet filled
        self._add_pend_stop = None         # the stop that order was sized against
        # Fill price of the NEWEST add (Pine lAddLastPx / sAddLastPx). The scale-in target has
        # to sit BEYOND it, so every lot the target closes is closed in profit. It is the newest
        # rather than the worst-priced add because in "Trail" mode adds fill at successively
        # better-for-us prices, making the two identical — and Pine can name the newest fill
        # (`strategy.opentrades.entry_price`) without keeping a running extreme.
        self._add_last_px = None
        # The adds' target as it stood at the LAST bar's CLOSE -- i.e. the limit Pine
        # already has resting. 🔴 NOT recomputed from the live bar, and that is the whole
        # point: a daily or H4 level is swept by a WICK, and the engine steps before the
        # strategy sees the bar, so the level is ALREADY flagged mitigated on the exact bar
        # it would have filled. Reading it live made `Prev day H/L` resolve 1,804 targets
        # and fill ZERO, reproducing `Ride` byte-for-byte -- a mode that answers
        # confidently and does nothing. Weekly hid it: that one needs a CLOSE through, so a
        # bar can spike past it and leave it standing.
        self._add_tp_level = None
        self._sos_bar_open: Optional[int] = None
        self._entry_equity: Optional[float] = None   # equity snapshot at open, for R

        # resting entry orders (one per side; at most one position at a time)
        self._pend_long: Optional[_Pending] = None
        self._pend_short: Optional[_Pending] = None
        # the secondary sniper limit, placed/filled on the fill-clock stream (step_secondary). Its own slot
        # so the 15m `_place_entries` can never clobber it. At most one side arms (fibo_dir is one).
        self._pend_sec: Optional[_Pending] = None

        # one-trade-per-leg latches (Pine tradedSosL / tradedSosS)
        # "Order block (no FVG)" only: has a QUALIFYING gap ever been in the band on this setup?
        # Per SETUP, keyed on the SOS bar and cleared by `_sync_gap_latch` when a new break arms —
        # the same shape as `_traded_sos_*` below, and for the same reason: a setup is the unit a
        # decision like this belongs to, and a bar is not.
        self._gap_seen_l = False
        self._gap_seen_s = False
        self._gap_seen_sos_l: Optional[int] = None
        self._gap_seen_sos_s: Optional[int] = None
        self._traded_sos_l: Optional[int] = None
        self._traded_sos_s: Optional[int] = None
        # secondary eligibility: the 15m leg whose PRIMARY reached at least TP1 (moved to
        # breakeven, _stage >= 1). A secondary arms only when its leg == this — a primary that
        # opened and got stopped at its initial stop (never reached TP1) leaves no re-entry.
        self._be_sos_l: Optional[int] = None
        self._be_sos_s: Optional[int] = None
        # The last-closed 15m bar's PRIMARY entry edge per side — the secondary's gap trigger
        # rests on it. None until the first 15m bar is stepped, and None whenever the setup has
        # no qualifying gap, which is the honest reading: "no gap to enter on", never a price.
        self._poi_edge_l: Optional[float] = None
        self._poi_edge_s: Optional[float] = None
        # The looser secondary gates (`exec_sec_require`). `_prim_closed_sos_*` = a PRIMARY has
        # traded this 15m leg and is now closed, whatever the outcome; `_prim_lost_sos_*` = it
        # closed at stage 0, i.e. never reached TP1 (the swept-stop case). Both are latched at
        # finalise, so they can only ever be read while flat — which is the only state that arms a
        # re-entry. Nothing but `SecondaryArm` reads them, so parity is untouched.
        self._prim_closed_sos_l: Optional[int] = None
        self._prim_closed_sos_s: Optional[int] = None
        self._prim_lost_sos_l: Optional[int] = None
        self._prim_lost_sos_s: Optional[int] = None
        # set for one fill-clock step when a SECONDARY closes at its initial stop (stage 0 = never
        # reached TP1). The driver reads it to kill that 15m leg — a stopped re-entry ends the
        # cascade on that leg. +1/-1/None; reset at the top of every step_secondary.
        self._sec_stop_dir: Optional[int] = None

        # REPORTING ONLY — the "price has retraced far enough to be worth announcing" latch, per
        # side, holding the SOS bar of the leg that has already qualified. Read by
        # `_announce_ready`; nothing that places or prices an order sees it.
        self._announce_latch_l: Optional[int] = None
        self._announce_latch_s: Optional[int] = None

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
        # Pre-trade alerts (reporting only — `backtest/setups.py`). `_setup_ctx` is what each
        # side's watch looked like on THIS bar, captured inside `_record_misses` because that is
        # the one place the per-side gates are already resolved; `_setup_done` holds setups that
        # reached a terminal state this bar. `live_setups()` assembles both. Nothing reads either
        # back, so no decision can move — proven by replay, not by this comment.
        self._setup_ctx: List[Optional[dict]] = [None, None]
        self._setup_done: List[SetupSnapshot] = []
        # What an alert calls this bot. Overwritten by the STRATEGY that owns this object,
        # because three strategies share this execution layer and its own class name would
        # label all of them "Execution". The default is honest rather than blank: an unnamed
        # setup in a Telegram group with two bots in it names neither.
        self.strategy_name: str = type(self).__name__
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

    # ── reads the secondary layer needs (the secondary arm gates on these) ──
    @property
    def is_flat(self) -> bool:
        return self._pos_dir == 0

    @property
    def entry_kind(self) -> str:
        return self._entry_kind

    # ── position snapshot / restore (for the LIVE bot only) ───────────────────────
    #
    # **Why these exist.** `algos/live/` runs this same object against a real broker, and a
    # restart rebuilds it EMPTY from a warm-up replay. Before this, a bot that restarted while a
    # trade was open HALTED and left that trade unmanaged — its broker-side stop stood, but
    # nothing ratcheted it again and the time stop never fired. See
    # `algos/live/position_state.py` for the whole design; this end is only the state itself.
    #
    # **REPORTING-NEUTRAL and DECISION-NEUTRAL in a backtest.** Nothing in `step()`,
    # `step_secondary()` or the parity harness calls either method, so `compare_strategy.py` is
    # structurally unaffected — the same standing the `account` / `leg` seam has. A lab replay
    # never opens a position it did not itself fill.
    #
    # ⚠ **`_POSITION_FIELDS` is the WHOLE open-trade state and a missing entry is silent.** Leave
    # one out and the restored trade manages against a default — a zero `_max_fav` un-ratchets the
    # trail, a zero `_stage` puts a breakeven stop back to the full stop, a missing `_entry_ms`
    # resets the time stop's clock. None of those raise; they just trade differently.
    # `test_position_snapshot_covers_every_field_open_position_assigns` DERIVES the required set
    # by reading `_open_position`'s own source, because a hand-written list would re-freeze
    # exactly the assumption that fails — the same guard `run_dual`'s fill-clock signal needed after it
    # shipped missing two fields that three weeks of green tests never saw.

    _POSITION_FIELDS = (
        "_pos_dir", "_entry_kind", "_qty", "_entry", "_entry_index", "_entry_ms",
        "_init_stop", "_exit_notional", "_exit_qty", "_exit_ms", "_exit_reason",
        "_sl", "_tp1", "_tp2", "_fib", "_stage", "_filled_qty", "_sos_bar_open",
        "_risk_usd", "_entry_equity", "_costs_usd", "_last_roll_ms", "_max_fav",
        "_trail_swing_hi", "_trail_swing_lo", "_ext_high", "_ext_low", "_legs",
        "_pending_close",
        # Scale-in lots, and they belong here for the reason the warning above gives: a
        # restored position that dropped them would carry the base's stop while the adds it
        # actually holds went unpriced and unclosed. `_add_stop` is the stop the last add was
        # sized against — without it a restored runner re-adds immediately at the same locked
        # profit, which is exactly the over-spend the ratchet check exists to stop.
        "_adds", "_add_lots", "_add_stop", "_base_qty", "_add_limit", "_add_armed",
        "_add_pending", "_add_pend_stop", "_add_last_px", "_add_tp_level",
        # Which re-entry trigger armed the open secondary. It DECIDES the exit ladder — the
        # reclaim half carries its own first target and its own bank percentage — so a restored
        # trade that lost it would manage against the other half's rungs, silently.
        "_entry_src",
        "_entry_after",
        # SETUP-scoped rather than position-scoped, and carried anyway: it is the
        # one-trade-per-15m-leg latch. Without it a restored bot could re-enter the very setup
        # it is already holding, the moment this trade closes.
        "_traded_sos_l", "_traded_sos_s",
    )

    def snapshot_position(self) -> dict:
        """Everything needed to carry on managing the open trade, as plain JSON types."""
        if self._pos_dir == 0:
            raise ValueError("snapshot_position() called while flat — there is nothing to record")
        snap: dict = {}
        for name in self._POSITION_FIELDS:
            value = getattr(self, name)
            if name == "_fib":
                value = None if value is None else {
                    "levels": [[float(r), float(p)] for r, p in value.levels],
                    "start_ms": value.start_ms,
                }
            elif name in ("_legs", "_add_lots"):
                # Copied rather than handed over: both are ledgers the open trade keeps appending
                # to, and a snapshot that aliases them would keep growing after it was taken.
                value = [dict(row) for row in value]
            elif name == "_pending_close":
                value = None if value is None else list(value)
            snap[name] = value
        return snap

    def restore_position(self, snap: dict) -> None:
        """Put a recorded position back, exactly. REFUSES an incomplete record.

        ⚠ **It refuses rather than filling a default, and that is the whole safety property.** A
        record missing `_stage` is not "a trade at stage 0" — it is a record we cannot trust, and
        managing a real position against a guess is the failure this is meant to end. The caller
        halts, which is what the bot did in every case before this existed.

        ⚠ **It does NOT touch the structure/fib/gap state** — the warm-up replay rebuilds all of
        that from real bars, which is the correct source and the only one that stays current
        across an outage of unknown length. This restores the EMULATOR's own book and nothing
        else, so it must be called AFTER the warm-up, never before: a warm-up run afterwards
        would overwrite it with whatever the replay imagined.
        """
        missing = [n for n in self._POSITION_FIELDS if n not in snap]
        if missing:
            raise ValueError(
                "refusing to restore an incomplete position record; missing: "
                + ", ".join(sorted(missing)))
        for name in self._POSITION_FIELDS:
            value = snap[name]
            if name == "_fib" and value is not None:
                value = TradeFib(
                    levels=[(float(r), float(p)) for r, p in value["levels"]],
                    start_ms=value.get("start_ms"),
                )
            elif name == "_pending_close" and value is not None:
                value = tuple(value)
            setattr(self, name, value)
        # The resting limits are NOT part of the record and must be cleared: a position is open,
        # so the strategy holds no pending entry, and `algos/live/bridge.py` cancels every stale
        # broker-side order at startup for the same reason.
        self._pend_long = self._pend_short = self._pend_sec = None

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
    def prim_closed_sos_l(self) -> Optional[int]:
        return self._prim_closed_sos_l

    @property
    def prim_closed_sos_s(self) -> Optional[int]:
        return self._prim_closed_sos_s

    @property
    def prim_lost_sos_l(self) -> Optional[int]:
        return self._prim_lost_sos_l

    @property
    def prim_lost_sos_s(self) -> Optional[int]:
        return self._prim_lost_sos_s

    @property
    def sec_stop_dir(self) -> Optional[int]:
        """+1/-1 if a secondary just closed at its initial stop this 1m step (the driver kills
        that 15m leg), else None. Reset at the top of every step_secondary."""
        return self._sec_stop_dir

    # ── secondary (fast-feed sniper) path — driven by the fill-clock stream, never a 15m bar ────────
    def step_secondary(self, sig1m, arm) -> Optional[int]:
        """Advance the SECONDARY on one 1m bar. Same calc-on-close/one-bar-delay + intrabar-path
        rules as the primary, but on 1m bars, and only ever touching a secondary position:

          - flat  → fill the sniper limit placed LAST 1m bar (if touched), then (re)place from
                    this bar's arm. A fill retires its shift leg (returned dir → driver calls
                    `arm.mark_traded`) and stages the trade so its stop is live next bar.
          - holding a secondary → run its TP1/TP2/runner ladder against this bar, then re-stage.
          - holding a PRIMARY  → do nothing (the 15m stream owns it).

        `sig1m` needs `index / time_ms / open / high / low / close` (a `_Bar1mSig`). Returns the
        direction filled this bar (+1/-1) or None. Bar-mode only for now; tick-mode secondary
        fills are a later add (the 1m tick seam isn't wired)."""
        self._sec_stop_dir = None            # cleared each step; _finalise_trade sets it on a stop-out
        sink = Decision(index=sig1m.index)   # throwaway — trades land in self.trades regardless
        filled_dir: Optional[int] = None

        # ── Phase A: fill / manage against THIS fill-clock bar ──
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
            # `filled_dir is None` = this fill-clock bar is not the fill bar. Same rule as the primary
            # (see the fill-bar note in `step`): the sniper also enters on a resting limit, so
            # its fill bar's extreme is the approach to that limit, not the trade's own move.
            self._advance_stage(sig1m)

        return filled_dir

    def _secondary_pending(self, arm) -> Optional["_Pending"]:
        """Turn the armed side of a `SecArm` into a resting `_Pending`, sized off the 1m-leg stop
        distance with the same %-risk as the primary. At most one side arms (fibo_dir is one value).

        The minimum-stop floor applies HERE as well as on the 15m path, and it is the same
        `_stop_clears_floor` rather than a second copy of the rule. The hazard is identical and
        it is worse on this path: `qty = risk / dist`, and a 1-minute leg is a shorter leg, so
        its stop distance is smaller by construction — measured, 90 of 1,956 secondary limits
        rested under the shipped 0.08%-of-price floor. What makes them easy to miss is that a
        limit under the floor costs nothing until price happens to reach it; only ONE of the 90
        ever filled in 7.9 years.

        ⚠ The floor is read off `self._atr`, which is the FIFTEEN-minute ATR(14) — `_update_atr`
        runs in `step`, never in `step_secondary`. That is the right reading (the setup is a 15m
        setup and the risk is budgeted against it) but it only matters under "x ATR(14)"; the
        shipped "% of price" mode is a pure function of the entry price and does not care.
        """
        cfg = self._cfg
        # A re-entry may risk a FRACTION of what the primary risks (`exec_sec_risk_pct`, 100 =
        # the same). Applied to the %-risk, so it scales the LOT and nothing else — the minimum
        # stop floor below still reads the raw stop distance, which is the right question (a leg
        # too short to trade is too short whatever size you put on it).
        risk_pct = cfg.exec_risk_pct * getattr(cfg, "exec_sec_risk_pct", 100.0) / 100.0
        if arm.l_armed and arm.l_edge is not None and arm.l_sl is not None:
            dist = arm.l_edge - arm.l_sl
            if self._stop_clears_floor(dist, arm.l_edge):
                qty = (self.equity * risk_pct / 100.0) / dist
                # `getattr`, because `arm` is a duck-typed record here and several tests build a
                # bare stand-in for it. A missing field means "no trigger named itself", which the
                # ladder reads as the shared settings — the behaviour every caller had before the
                # reclaim half existed.
                return _Pending(1, arm.l_edge, qty, arm.l_sl, arm.l_tp1, arm.l_tp2, arm.l_leg,
                                src=getattr(arm, "l_src", None),
                                after=getattr(arm, "l_after", None))
        if arm.s_armed and arm.s_edge is not None and arm.s_sl is not None:
            dist = arm.s_sl - arm.s_edge
            if self._stop_clears_floor(dist, arm.s_edge):
                qty = (self.equity * risk_pct / 100.0) / dist
                return _Pending(-1, arm.s_edge, qty, arm.s_sl, arm.s_tp1, arm.s_tp2, arm.s_leg,
                                src=getattr(arm, "s_src", None),
                                after=getattr(arm, "s_after", None))
        return None

    # ── main step ───────────────────────────────────────────────────────────────
    def step(self, sig, seq) -> Decision:
        dec = Decision(index=sig.index)

        # Runs before anything can branch — see `_update_atr`.
        self._update_atr(sig)

        # Decision context the Pine computes EVERY bar (not just when flat), so the
        # decision streams line up bar-for-bar: the entry edges, the A+ stage, the veto.
        # Before the edges, so a new break of structure re-opens the block leg on the same bar it
        # arms rather than one bar late.
        self._sync_gap_latch(seq)
        long_edge, short_edge = self._entry_edges(sig, seq)
        dec.long_edge, dec.short_edge = long_edge, short_edge
        # Latched for the SECONDARY's gap half (any `exec_sec_trigger` naming the gap), which
        # re-uses the PRIMARY's own point-of-interest price rather than computing a second one —
        # Aaron's rule is *"follow the rules of fair value gap entry that we would take on a
        # primary trade"*, and a second implementation of those rules is how the two silently
        # diverge. Reporting-free: nothing reads these unless the gap trigger is on, so the
        # shipped book cannot move. Cleared with the setup by `_sync_gap_latch`'s own caller.
        self._poi_edge_l, self._poi_edge_s = long_edge, short_edge
        dec.l_stage, dec.s_stage = seq.l_stage, seq.s_stage
        dec.long_veto, dec.short_veto = sos_aware_veto(sig, seq.l_sos_bar, seq.s_sos_bar)

        # Financing for any rollover crossed while still holding — charged before this bar's
        # exits, since the night was already carried by the time the bar trades. No-op in bar mode.
        self._charge_swap(sig)

        # ── Phase A: fill resting orders against THIS bar (placed last bar) ──
        # An add TRIGGERED last bar is a market order, so it fills at THIS bar's open — ahead of
        # any stop, target or force-close, exactly as TradingView fills a pending
        # `strategy.entry` before the bar trades. It must come first: filling it after
        # `_manage_open` would let a stop the market only reached mid-bar pre-empt a lot the
        # broker had already bought.
        if self._add_armed and self._pos_dir != 0:
            self._fill_pending_add(sig)
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
        # position is managed on the fill-clock stream, so a 15m bar never touches it.
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
            # Re-rest the adds' target for the NEXT bar, in the same slot the stop is
            # staged in and for exactly the same reason: an exit order placed at THIS
            # close is what the next bar trades against (TradingView's one-bar delay).
            self._add_tp_level = self._add_tp_target(sig)
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
        # else: a secondary is open — managed on the fill-clock stream (step_secondary), not here.

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
                self._setup_ctx[slot] = None
                continue
            traded = traded_sos is not None and m.sos_bar is not None and traded_sos == m.sos_bar
            if sos_bar is not None and not traded:
                # still alive — accumulate what it achieved
                m.fib = sig.fibo_p3
                if m.edge is None and edge is not None:
                    m.edge = edge
                if zone_hit:
                    m.visit(sig, is_long)
                    m.zone = True
                    m.fvg = m.fvg or edge is not None
                    m.blk_v = m.blk_v or veto
                    m.blk_l = m.blk_l or late
                    m.blk_h = m.blk_h or htf_any
                # Reporting only, and captured AFTER the accumulate above — the block that sets
                # `m.zone` on the bar price first tags the band. Capturing before it reported a
                # setup as still waiting on a retrace on the very bar it got one, so the alert
                # said "2 of 3" beside a resting order that needed 3. It also has to be here
                # rather than in `live_setups()`, because this is the one place the per-side
                # gates are already resolved through the enable-toggles exactly as `_armed`
                # reads them — so "armed" means the same thing in an alert as in a decision.
                self._setup_ctx[slot] = self._setup_context(
                    sig, m, is_long, arm_swp, arm_div, veto, late, htf_any)
                continue

            # it died (or traded) — book the miss, then close the watch either way
            m.watch = False
            # Reporting only. Every exit below books a terminal snapshot BEFORE its `continue`,
            # because a setup the alert layer announced and never hears about again leaks a
            # Telegram thread and, worse, reads to a human as still live.
            ctx, self._setup_ctx[slot] = self._setup_ctx[slot], None
            if traded:
                self._book_setup_end(ctx, FILLED, "Entered.")
                continue
            if not flat:
                self._book_setup_end(ctx, DEAD,
                                     "The setup ended while another position was open.")
                continue
            arm_met = arm_swp or arm_div
            zone_met = m.zone and (m.fvg or not cfg.exec_req_fvg)
            met_n = (1 if arm_met else 0) + 1 + (1 if zone_met else 0)
            if met_n < 2:
                self._book_setup_end(ctx, DEAD,
                                     "The setup died before reaching two confluences.")
                continue
            price = m.edge if m.edge is not None else m.fib
            if price is None:
                # nothing to anchor a marker to — a record with no price can't be drawn
                self._book_setup_end(ctx, DEAD, "The setup died with no price to report.")
                continue
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
            miss = MissedSetup(
                dir=1 if is_long else -1, index=sig.index, time_ms=sig.time_ms,
                met=met_n, code=code, arm_text=arm_text, arm_met=arm_met,
                zone=m.zone, zone_time_ms=m.zone_ms, zone_turn_ms=m.zone_turn_ms,
                fvg=m.fvg, edge=float(price),
                near=met_n == 3 or (m.zone and not zone_met),
            )
            self.misses.append(miss)
            # The alert reuses the miss's OWN sentence rather than composing a second one. Two
            # explanations for one death can disagree, and the reader has no way to tell which
            # is the strategy's.
            self._book_setup_end(ctx, DEAD, miss.reasons[0] or miss.labels[0],
                                 label=miss.labels[0])

    # ── pre-trade setup snapshots (backtest/setups.py) — reporting only ──────────
    #
    # The contract the Telegram signals channel reads. NOTHING here may reach a decision: no
    # method below is called from `step`, `step_secondary` or `_manage_open`, and every value is
    # COPIED from state the strategy already holds rather than recomputed. An alert naming a
    # level the bot never traded is worse than no alert, because you would act on it.
    #
    # ⚠ Proven reporting-only by REPLAY (a byte-identical trade list over the full history), not
    # by this comment. See `docs/LIVE_SETUP_ALERTS.md` §4.

    @property
    def reports_setups(self) -> bool:
        """Whether this class can actually answer `live_setups()` — read by `implements_contract`.

        🔴 **Tied to `_records_misses`, because that flag gates the ONE method that populates the
        setup context.** `mpc_bleg` and `mpc_bos` subclass this and both set it False, so they
        inherit a `live_setups()` that returns `[]` on every bar forever — a method-presence check
        would call them supported and the runner would announce "Setup alerts: ON" for a channel
        that can never send anything. **An empty registry answering confidently, arriving by
        inheritance rather than by a literal `{}`.**

        ⚠ **It is derived rather than a flag each fork must remember to set**, so a new subclass
        cannot acquire a silent, empty signals channel by forgetting one line.

        ⚠ **True here is NOT a claim that a fork's confluences are right.** A fork that turns the
        watch back on would report A+'s three confluences, which describe a setup it does not
        trade. It needs its own `_setup_context` before its alerts go on.
        """
        return bool(self._records_misses)

    def _setup_key(self, is_long: bool, sos_bar: Optional[int]) -> str:
        """The thread id, stable for this setup's whole life.

        Keyed on the SOS bar rather than on anything that moves: the arm, the zone state and the
        entry price all change while a setup is alive, and a key built from any of them would
        start a new Telegram thread on the bar it changed. `_MissWatch` already treats
        `(side, sos_bar)` as this setup's identity — reusing it is what keeps the alert's notion
        of "the same setup" identical to the strategy's.
        """
        return f"{self.strategy_name}:{'L' if is_long else 'S'}:{sos_bar}"

    def _announce_ready(self, sig, sos_bar: Optional[int], is_long: bool) -> bool:
        """Has price retraced far enough for this setup's RESTING ORDER to be worth announcing?

        REPORTING ONLY — read by `_setup_context` and by nothing that places, prices or cancels
        an order. It cannot move a trade, so it is parity-safe in the same way `Trade.mfe_usd`
        and the whole missed-setup layer are: `compare_strategy.py` diffs the `px_*` decision
        stream, which this never touches.

        **The rule (Aaron, 2026-08-14):** *"I only want to know a limit is pending when price
        gets back to 23.6% of the retracement."* The order is placed the instant the setup arms,
        which on the live bot meant a limit resting 41 points below price for a whole session and
        a Telegram message about it 45 minutes before anything could happen.

        🔴 **The ratio being SHALLOWER than the entry band is what makes this safe, and it is a
        guarantee rather than a measurement.** The band runs 0.5-0.886, so any fill must be at
        0.5 or deeper, and price cannot reach 0.5 without crossing 0.236 first. **A suppressed
        message therefore belongs to a setup that never filled** — this can never silence the
        announcement of a trade that happens. ⚠ That property depends on
        `alert_resting_fib < 0.5`; `__post_init__` refuses anything else rather than trusting the
        reader, because the failure mode is a real trade reaching the trades room having never
        been signalled, with nothing anywhere reporting the missing message.

        ⚠ **LATCHED per leg, keyed on the SOS bar**, so a wick to 0.236 that immediately reverses
        does not un-announce a setup already announced. The alert layer sends the message once
        per setup anyway, but a flapping input would make the two disagree about why.

        ⚠ **Priced through the canonical `fib_level()` off the same leg anchors the fib engine
        used**, never by interpolating between the zone edges. Two ways of deriving one price is
        the failure this file already records for `Trade.fib`.
        """
        if sos_bar is None or sig.fibo_dir == 0:
            return False
        latch = self._announce_latch_l if is_long else self._announce_latch_s
        if latch == sos_bar:
            return True
        if sig.fibo_ash is None or sig.fibo_asl is None:
            return False

        level = fib_level(sig.fibo_ash, sig.fibo_asl, sig.fibo_dir,
                          self._cfg.alert_resting_fib)
        # The BAR's extreme, not its close: price tagging the level intrabar is price having got
        # there, and the close is a different question. Same reading `_MissWatch.visit` takes of
        # the zone itself.
        reached = sig.low <= level if is_long else sig.high >= level
        if reached:
            if is_long:
                self._announce_latch_l = sos_bar
            else:
                self._announce_latch_s = sos_bar
            return True
        return False

    def _setup_context(self, sig, m: _MissWatch, is_long: bool, arm_swp: bool, arm_div: bool,
                       veto: bool, late: bool, htf_any: bool) -> dict:
        """Freeze what this side's live setup looks like on this bar.

        ⚠ **`arm_swp` / `arm_div` are the ENABLE-FILTERED flags** — the same ones `_armed` reads.
        A setup armed by a source the config has switched off can never trade, and announcing it
        as a forming setup would be a label with no code behind it. It is reported with its arm
        confluence UNMET, which is exactly how `MissedSetup` books it (code 1).
        """
        cfg = self._cfg
        arm_met = arm_swp or arm_div
        if arm_met:
            arm_text = ("Sweep + RSI div" if (arm_swp and arm_div)
                        else "Sweep" if arm_swp else "RSI divergence")
            if arm_swp and m.swp_nm:
                arm_text += f" · {m.swp_nm}"
        else:
            # Name the source that DID arm it and say it is off — "your arm source is off" is
            # meaningless without saying which one. Same sentence `MissedSetup.reasons` uses.
            src = "RSI divergence" if m.arm_src == "DIV" else "a liquidity sweep"
            arm_text = f"armed by {src}, but that source is switched OFF"

        if not m.zone:
            zone_text = "not tagged yet"
        elif m.fvg:
            zone_text = "0.5-0.886 tagged, FVG live"
        elif cfg.exec_req_fvg:
            zone_text = "0.5-0.886 tagged, but no FVG in it"
        else:
            zone_text = "0.5-0.886 tagged"
        zone_met = bool(m.zone) and (m.fvg or not cfg.exec_req_fvg)

        # The whole tradeable range, which is knowable as soon as the fib is live and is the
        # thing worth saying BEFORE an order exists. `entry` (the one resting price) is read
        # separately in `live_setups()`, from the order itself.
        shallow, deep = sig.fibo_p2, sig.fibo_p6
        zone = (float(shallow), float(deep)) if (shallow is not None and deep is not None
                                                 and sig.fibo_dir != 0) else None
        # Where the stop WOULD sit for a fill at the deep edge. Routed through `_sl_anchor` so
        # `exec_sl_level` / `exec_sl_custom` / `exec_sl_deep` resolve exactly as they would for a
        # real order — a stop the alert computed its own way is a second claim about one setup.
        anchor = self._sl_anchor(sig, deep, is_long) if zone is not None else None
        proj_stop = None
        if anchor is not None:
            buf = cfg.exec_sl_buf_tk * cfg.mintick
            proj_stop = float(anchor - buf if is_long else anchor + buf)

        # 🔴 **Only a READY setup can be blocked, and getting this wrong made the message lie.**
        # A veto, the final hour or an HTF filter can be live at any moment while a setup is
        # merely forming — reporting that as BLOCKED announced setups that then went on to rest
        # and fill, under a sentence reading "the setup was ready and this rule stopped it".
        # `BlockedSetup` has always required full readiness; this now asks the same question, and
        # asks it of the CURRENT bar rather than of `m.blk_*`, which latch true for the rest of
        # the setup's life and would keep reporting a rule that has since stopped applying.
        blocked = []
        if arm_met and zone_met:
            if veto:
                blocked.append("Divergence / extreme-RSI veto")
            if late:
                blocked.append("Final hour (16:00-18:00 New York)")
            if htf_any:
                blocked.append("HTF breakout / bias filter")

        announce = self._announce_ready(sig, m.sos_bar, is_long)

        return {
            "key": self._setup_key(is_long, m.sos_bar),
            # Can this setup still reach a fill under the config this bot is running? `_armed`
            # requires `arm_ok_*`, which is these same enable-filtered flags — and the arm source
            # is SNAPSHOTTED at the SOS bar (`seq.sos_l_swp` / `.sos_l_div`), so a setup armed by
            # a source you have switched off can never acquire a different one. It dies as miss
            # code 1.
            # ⚠ **MEASURED: it fires on ONE setup in 6.5 years, not the 220 first estimated.**
            # `arm_src` names which source reached stage 1 first and is NOT the same question:
            # `sos_l_swp` asks whether a sweep was live at the SOS, and nearly every
            # divergence-armed setup has one, so it is tradeable. `miss_audit.py` reports **zero**
            # code-1 misses over the same window, which is the independent confirmation.
            # ⚠ This is the ONLY untradeable condition here, deliberately. A veto or the final
            # hour can lift while a setup is still alive, so those stay reportable and are
            # carried as `blocked_by` instead.
            "tradeable": arm_met,
            "announce_resting": announce,
            "side": 1 if is_long else -1,
            "confluences": (
                Confluence("Arm", arm_met, arm_text),
                # ⚠ "SOS confirmed", not "confirmed". The alert layer prints the DETAIL and drops
                # the name, so a detail that only makes sense under its own label reads as a bare
                # "confirmed" in the message. A strategy owns what its confluences are CALLED —
                # `alerts.py` must never learn what an SOS is.
                Confluence("Shift of structure", True, "SOS confirmed"),
                Confluence("Retrace zone", zone_met, zone_text),
            ),
            "zone": zone,
            "stop": proj_stop,
            "blocked_by": tuple(blocked),
        }

    def _book_setup_end(self, ctx: Optional[dict], state: str, reason: str,
                        label: str = "") -> None:
        """Record a setup reaching a terminal state, so the alert layer can close its thread.

        A missing `ctx` is dropped in silence and that is deliberate: it means the watch was
        opened before this bar's context was captured (a warm-up boundary, or a restart), so
        there is no setup the reader was ever told about to close.
        """
        if ctx is None:
            return
        self._setup_done.append(SetupSnapshot(
            key=ctx["key"], strategy=self.strategy_name, symbol=self._cfg.symbol or "",
            side=ctx["side"], state=state, confluences=ctx["confluences"],
            zone=ctx["zone"], entry=None, stop=ctx["stop"], targets=(),
            blocked_by=ctx["blocked_by"], reason=(f"{label} — {reason}" if label else reason),
            tradeable=ctx["tradeable"],
        ))

    def live_setups(self) -> List[SetupSnapshot]:
        """Every setup this strategy is watching right now, plus any that resolved this bar.

        ⚠ **Call it AFTER `step()` has returned.** The resting order is rebuilt during
        `_place_entries`, which runs after `_record_misses` — so reading `_pend_*` any earlier
        reports the PREVIOUS bar's price beside this bar's confluences, which is the "two claims
        about one setup" failure with a one-bar delay hiding it.

        ⚠ **`entry` is read from the ORDER, never recomputed from `sig`.** A fib keeps extending
        while a limit rests; re-deriving the price here would describe a leg the order was never
        placed against, exactly as recorded for `Trade.fib`.
        """
        out = list(self._setup_done)
        for slot, pend in ((0, self._pend_long), (1, self._pend_short)):
            ctx = self._setup_ctx[slot]
            if ctx is None:
                continue
            resting = pend is not None and pend.sos_bar is not None
            out.append(SetupSnapshot(
                key=ctx["key"], strategy=self.strategy_name, symbol=self._cfg.symbol or "",
                side=ctx["side"],
                state=RESTING if resting else WATCHING,
                confluences=ctx["confluences"],
                zone=ctx["zone"],
                entry=float(pend.edge) if resting else None,
                stop=float(pend.sl) if resting else ctx["stop"],
                targets=(float(pend.tp1), float(pend.tp2)) if resting else (),
                blocked_by=ctx["blocked_by"],
                tradeable=ctx["tradeable"],
                announce_resting=ctx["announce_resting"],
            ))
        return out

    def drain_setups(self) -> List[SetupSnapshot]:
        """`live_setups()`, then forget the resolved ones.

        The live runner calls this once per bar. Terminal snapshots MUST be cleared or they are
        re-sent every bar for the life of the process; the live watches are rebuilt from
        `_setup_ctx` each bar and so are not accumulated state. Same contract as `blocks` /
        `misses` and `runner._drain_records`.
        """
        out = self.live_setups()
        self._setup_done.clear()
        return out

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

    def _deepen(self, edge: float, sig, is_bull: bool, p2, p6) -> float:
        """The deepest same-direction order block edge past `edge`, or `edge` unchanged.

        DEEPEST rather than nearest, deliberately: the question this answers is "how much better
        a price was available", and taking the nearest would measure a diluted version of the
        idea and then be read as a verdict on the idea itself. If the deepest is refused by the
        minimum-stop floor the trade simply does not happen, which is a real answer.

        Direction is written against `is_bull` throughout — the fib ladder inverts on a short, so
        deeper means a LOWER price on a long and a HIGHER one on a short, and a `<` written once
        would be silently backwards on half the book.
        """
        lo, hi = min(p2, p6), max(p2, p6)
        best = edge
        for top, bot, ob_bull, _born in sig.obs:
            if ob_bull != is_bull:
                continue
            if min(top, hi) < max(bot, lo):          # not in the tradable band at all
                continue
            near = min(top, hi) if is_bull else max(bot, lo)
            if is_bull and near < best:
                best = near
            elif (not is_bull) and near > best:
                best = near
        # never past the deep edge of the band — that line is the stop
        return max(best, lo) if is_bull else min(best, hi)

    def _sync_gap_latch(self, seq) -> None:
        """Clear the "a gap has been here" latch when a NEW setup arms on that side.

        Per SETUP, never per lifetime: the block leg standing down for ever after one gap would
        retire the side entirely. The key is the SOS bar because that is what identifies a setup
        — stable across replays, since `signals` and `sequence` are driven by the engine stack
        alone and nothing in `execution` can move them. Entry time is not stable and the death
        bar is not either (giving a setup an entry changes the bar it dies on).

        A side with no live SOS keys on `None` and simply stays cleared.
        """
        if seq.l_sos_bar != self._gap_seen_sos_l:
            self._gap_seen_sos_l, self._gap_seen_l = seq.l_sos_bar, False
        if seq.s_sos_bar != self._gap_seen_sos_s:
            self._gap_seen_sos_s, self._gap_seen_s = seq.s_sos_bar, False

    def _entry_edges(self, sig, seq) -> Tuple[Optional[float], Optional[float]]:
        """The resting-limit price on each side (Pine 3937-3959): the near edge of an
        FVG overlapping the 0.5-0.886 band, clamped into the band; the first one price
        reaches (highest for longs). With Require-FVG off it falls back to 0.618. The entry
        model (`_fib_snap`) may re-price a qualifying gap onto a fib instead of its own edge.

        `seq` is REQUIRED rather than optional, and that is the point: `exec_nogap_arm` gates the
        fallback on what armed the SOS, which only `SeqState` knows. A default of None would make
        "the sequence was not passed" and "the confluence was not there" the same value at the one
        place that decides whether a trade happens — this repo's own most-repeated defect. There
        is exactly one caller (`step`), so requiring it costs nothing."""
        cfg = self._cfg
        p2, p3, p6 = sig.fibo_p2, sig.fibo_p3, sig.fibo_p6
        fibs_ready = None not in (sig.fibo_p1, p2, p3, p6, sig.fibo_p7, sig.fibo_p10)
        long_edge = short_edge = None
        # The precedence tier the current best edge came from ("FVG first" only). Every other
        # mode hands back one flat tier, so these never differ and the choice below collapses to
        # the original nearest-first max/min exactly.
        long_rank = short_rank = None
        long_stood_down = short_stood_down = False
        if fibs_ready:
            for top, bot, is_bull, born, rank in pois_for(self._cfg, sig):
                l_deep_ok = not cfg.exec_fvg_deep_only or top <= p2
                s_deep_ok = not cfg.exec_fvg_deep_only or bot >= p2
                # ANDed onto both sides rather than skipping the loop iteration, so with the
                # toggle off the condition is the original one exactly.
                pre_ok = self._gap_pre_zone(born, sig)
                if is_bull and sig.fibo_dir == 1 and bot <= p2 and top >= p6 and l_deep_ok and pre_ok:
                    df = self._fib_snap(bot, top, True, sig)
                    e = min(top, p2) if df is None else df   # snap override, else shallowest touch
                    # A HIGHER tier wins on rank alone, however much further away it rests — that
                    # IS the precedence. Only within one tier does "first price reaches" decide.
                    if long_edge is None or rank > long_rank:
                        long_edge, long_rank = e, rank
                    elif rank == long_rank:
                        long_edge = max(long_edge, e)
                if (not is_bull) and sig.fibo_dir == -1 and top >= p2 and bot <= p6 and s_deep_ok and pre_ok:
                    df = self._fib_snap(bot, top, False, sig)
                    e = max(bot, p2) if df is None else df
                    if short_edge is None or rank > short_rank:
                        short_edge, short_rank = e, rank
                    elif rank == short_rank:
                        short_edge = min(short_edge, e)
            # "Order block (no FVG)" — the second LEG of the pair, not a second strategy. It trades
            # a block ONLY where the FVG leg would not have traded at all, so the two can never
            # take the same setup and never double the risk on one idea.
            #
            # ⚠ The test is on the WINNING TIER, after the loop, and that is the whole correctness
            # argument. A gap only reaches `*_rank` if it overlapped the band AND passed the
            # deep-only gate AND passed the pre-zone gate — i.e. only if the FVG leg would really
            # have rested an entry on it. A gap those gates REFUSED never enters the comparison, so
            # it cannot stand this leg down over a setup the other leg was never going to take;
            # testing `sig.fvgs` directly would do exactly that and leave the setup untraded by
            # both legs. Same ordering `pois_for`'s tier comment already pins for "FVG first".
            if cfg.exec_poi_source == POI_SOURCE_OB_NO_FVG:
                # ⚠ A LATCH, not this bar's answer, and the difference is 60 setups in 6.5 years.
                # "Is there a gap right now" is far weaker than "has this setup ever had one":
                # price runs into the zone, CREATES a gap, and the FVG leg takes a setup this leg
                # entered a bar earlier — or the gap that armed the FVG leg is later mitigated,
                # leaving a block behind and this leg re-trading the same structure hours later.
                # MEASURED before the latch existed: 60 of 181 setups (33%) were traded by BOTH
                # legs, 44 of them with the FVG leg first. `_sync_gap_latch` clears it on a new
                # SOS, so it is per SETUP and a fresh break re-opens the leg.
                if long_rank is not None and poi_rank_is_fvg(long_rank):
                    self._gap_seen_l = True
                if short_rank is not None and poi_rank_is_fvg(short_rank):
                    self._gap_seen_s = True
                if self._gap_seen_l:
                    long_edge, long_stood_down = None, True
                if self._gap_seen_s:
                    short_edge, short_stood_down = None, True
            # `exec_ob_deepen` — re-price an entry we are ALREADY taking onto a deeper order
            # block. It does not create or remove a setup, it moves where the limit rests, so it
            # only ever applies to a side that already has an edge.
            #
            # ⚠ Clamped into the band at `p6`, because 0.886 IS the stop: a limit resting there
            # has a zero stop distance and `qty = risk / dist` is the hazard the minimum-stop
            # guard exists for. That guard (ON by default at 0.08% of price) is what refuses the
            # rest, and it is expected to refuse a lot of these — a 79% tighter stop is 5x the
            # position.
            if cfg.exec_ob_deepen and sig.obs_available:
                if long_edge is not None:
                    long_edge = self._deepen(long_edge, sig, True, p2, p6)
                if short_edge is not None:
                    short_edge = self._deepen(short_edge, sig, False, p2, p6)
            if not cfg.exec_req_fvg:
                # ⚠ A stand-down must not be undone here. `exec_req_fvg` off falls back to 0.618
                # whenever no zone qualified, and "I deliberately declined this setup" reads
                # identically to "I found nothing" from a None edge alone — so the leg would
                # decline the gap and then re-enter the same setup one line later at a different
                # price. The pin (`exec_req_fvg=True` on both legs) makes this unreachable today;
                # the flag makes it wrong-proof if the pin is ever relaxed.
                #
                # `exec_nogap_arm` narrows WHICH of those setups may fall back. "Any" is the
                # original rule exactly — `_nogap_arm_ok` returns True unconditionally — so the
                # default is byte-identical and nothing historical moves.
                if long_edge is None and sig.fibo_dir == 1 and not long_stood_down \
                        and self._nogap_arm_ok(seq, True):
                    long_edge = p3
                if short_edge is None and sig.fibo_dir == -1 and not short_stood_down \
                        and self._nogap_arm_ok(seq, False):
                    short_edge = p3
        return long_edge, short_edge

    def _nogap_arm_ok(self, seq, is_long: bool) -> bool:
        """May a setup with NO qualifying zone rest a fallback limit at the 0.618?

        Reads the RAW arm flags (`sos_*_swp` / `sos_*_div`), which are what the market did at the
        SOS, deliberately NOT the toggle-filtered ones the arm gate uses. The two answer different
        questions: `exec_arm_sweep` / `exec_arm_div` say which triggers the operator will act on,
        and this says how much confluence a setup had before its gap was checked. Reading the
        filtered pair would make this lever silently do nothing whenever `exec_arm_div` is off,
        which is the shipped default — i.e. it would look enabled and refuse everything.

        MEASURED 2026-08-10 over 155,531 M15 bars: of the 173 setups the fallback would take,
        the 78 carrying both sources made +35.47R and the 95 carrying only a sweep made +0.71R —
        an average of +0.007R, which is the whole reason this gate exists."""
        if self._cfg.exec_nogap_arm == "Any":
            return True
        # "Sweep + RSI div"; the config refuses any third value at construction.
        return (seq.sos_l_swp and seq.sos_l_div) if is_long else (seq.sos_s_swp and seq.sos_s_div)

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
        # Which re-entry trigger armed this trade, frozen from the ORDER. Read by the ladder below
        # and by `_tp1_pct`, because the reclaim half carries its own first target and its own bank
        # percentage. ⚠ Taken from the pending order rather than re-derived from the config at exit
        # time: the config answers "which triggers are enabled", and the question here is which one
        # produced THIS trade — two different questions the moment both halves are live.
        self._entry_src = pend.src
        self._entry_after = pend.after
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
        # `exec_sec_tp_r` — a SECONDARY may put its first rung at a multiple of its own risk
        # instead of the 15m 0.5 fib. Applied HERE, after `pend.tp1`, so the resting order still
        # carries the fib rung it was priced on and only the open trade's ladder moves. Off by
        # default (-1.0), so the shipped ladder is untouched and every stored figure reproduces.
        # ⚠ Priced off the INITIAL stop, not the trailed one: 1R must mean the risk the trade was
        # sized against, or the target would creep in as the stop ratchets.
        if kind == "secondary":
            # The RECLAIM half reads its own rung (`exec_rec_tp_r`), because under the combined
            # trigger the two halves are different trades: the reclaim enters at the deep edge with
            # a stop a median 0.43R away, so a rung that suits the gap entry is the wrong distance
            # here. MEASURED 2026-08-21: all-out at 3x made 6,740x over 7.9 years where the shipped
            # bank-half-at-1.25x ladder made 3,111x — worse than taking no re-entry at all.
            if pend.src == "reclaim":
                tp_r = getattr(self._cfg, "exec_rec_tp_r", 3.0)
            else:
                tp_r = getattr(self._cfg, "exec_sec_tp_r", -1.0)
            dist = abs(fill_price - pend.sl)
            if tp_r > 0 and dist > 0:
                self._tp1 = fill_price + (1 if pend.dir > 0 else -1) * tp_r * dist
        # The ladder those three came off, carried through to the closed Trade (reporting only).
        # Taken from the ORDER, not from `sig`: the fib is a live thing that keeps extending, so
        # reading it again at the fill would report a leg the resting limit was never priced on.
        self._fib = pend.fib
        self._stage = 0
        self._filled_qty = 0.0
        # Snapshot the OPENING size and clear the add ledger. Every add sizes off `_base_qty`
        # rather than the live position: sizing off the live one would compound, so add #2
        # would budget against base+add#1 and the "an add can never create a loser" guarantee
        # would be spent several times over on a single trade.
        self._adds = []
        self._add_lots = []
        self._add_stop = None
        self._base_qty = granted
        self._add_limit = None
        self._add_armed = False
        self._add_pending = None
        self._add_pend_stop = None
        self._add_last_px = None
        self._add_tp_level = None
        self._sos_bar_open = pend.sos_bar
        self._risk_usd = abs(granted) * abs(fill_price - pend.sl) * self._cfg.point_value
        self._entry_equity = self._equity_realized      # R yardstick baseline
        # Costs are charged AFTER the R baseline is snapshotted, so they land inside the trade's
        # own P&L (and its R) rather than being quietly excluded from it.
        self._costs_usd = 0.0
        self._last_roll_ms = None
        self._charge_commission(granted)
        self._charge_spread(granted)        # half the round turn; the exits pay the other half
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
        # a shift leg, not the 15m A+ leg — so only a primary sets it.
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
        self._widen_add_excursions(sig, adj)
        if self._resolver is not None:
            return self._manage_open_ticks(sig, dec)
        return self._manage_open_bar(sig, dec)

    def _widen_add_excursions(self, sig, adj) -> None:
        """Widen each OPEN scale-in lot's own high/low with this bar. Reporting only.

        🔴 **`_adds` and `_add_lots` are INDEX-ALIGNED, and that is load-bearing here.** Both are
        appended in one place (`_fill_pending_add`) on the same line of control flow, and neither
        is ever reordered or shortened mid-trade — `_bank_adds` zeroes a spent lot IN PLACE
        precisely so the ladder's cap keeps counting. That alignment is what lets the spent list
        say which lots are still LIVE while the record list says what each one DID. A future edit
        that pops from either list breaks this silently, in reporting only, which is the shape of
        defect nothing here would fail on.

        A lot filled on a LIMIT this bar is skipped whole: its adverse side was already seeded
        from this bar at the fill, and widening the favourable side would hand it the approach
        into the order — price that moved before the lot existed.
        """
        if not self._adds:
            return
        hi, lo = sig.high + adj, sig.low + adj
        for i, lot in enumerate(self._adds):
            if lot[1] <= 1e-12 or i >= len(self._add_lots):
                continue
            rec = self._add_lots[i]
            if rec.get("_limit_fill") and rec.get("_fill_ms") == sig.time_ms:
                continue
            rec["ext_hi"] = max(rec["ext_hi"], hi)
            rec["ext_lo"] = min(rec["ext_lo"], lo)

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

        # ── the scale-in adds bank on their OWN target, ahead of / behind the base ladder ──
        # Same intrabar convention as every bracket below: when a bar touches both the target
        # and the stop, the path decides which came first. The adds are checked separately
        # because they close on a level the BASE position knows nothing about.
        add_tp = self._add_tp_level
        add_hit = add_tp is not None and (
            (d > 0 and sig.high >= add_tp) or (d < 0 and sig.low + adj <= add_tp))
        add_px = self._fill_price(add_tp, sig.open + adj, True) if add_hit else None
        if add_hit and targets_first:
            self._bank_adds(sig, add_px, dec)

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

        # The path put the STOP first on this bar, so the adds bank only if the base position
        # survived it — a stop that closed the trade has already taken them pro-rata.
        if add_hit and not targets_first and self._pos_dir != 0:
            self._bank_adds(sig, add_px, dec)

    def _add_tp_target(self, sig) -> Optional[float]:
        """Where the scale-in lots bank (Pine `lAddTp` / `sAddTp`), or None to ride them.

        Two conditions, and each is doing a job:

        * the level must be one price has NOT already taken — `signals.py` reports only
          UNMITIGATED levels, because a swept level is not somewhere to aim at, it is a price
          we are already past;
        * it must sit BEYOND the newest add, so every lot this closes is closed in profit.
          Banking one lot at a loss to bank another at a gain is not what the input is for.

        "Ride", a trade with no live adds, and a run whose first week has not completed all
        answer None — which is what keeps the shipped behaviour byte-identical with the input
        on "Ride" and with `exec_scale_in` off.

        ⚠ Two of the guards below are REDUNDANT and are kept deliberately, which is worth
        saying so the next reader does not mistake them for the thing doing the work. The
        `mode == "Ride"` clause is also caught by the closing `else`, and `lvl is None` by
        `return lvl` returning None anyway — both were proven no-ops by mutation. They stay
        because each names an intention the fallthrough only implements by accident, and a mode
        added later could easily stop the fallthrough covering them.
        """
        mode = getattr(self._cfg, "exec_scale_tp_mode", "Ride")
        if mode == "Ride" or self._add_last_px is None:
            return None
        if not any(lot[1] > 1e-12 for lot in self._adds):
            return None
        d = self._pos_dir
        if mode == "Prev week H/L":
            lvl = sig.liq_w_high if d > 0 else sig.liq_w_low
        elif mode == "Prev day H/L":
            lvl = sig.liq_d_high if d > 0 else sig.liq_d_low
        elif mode == "H4 H/L":
            lvl = sig.liq_h4_high if d > 0 else sig.liq_h4_low
        else:
            return None
        if lvl is None or (lvl - self._add_last_px) * d <= 0:
            return None
        return lvl

    def _bank_adds(self, sig, price, dec) -> None:
        """Close every open add lot at `price`, leaving the BASE position untouched.

        Each lot is valued against its OWN entry, which is the same arithmetic `_exit_portion`
        does for the pro-rata case and for the same reason: the base position is priced off one
        `_entry`, and an add was bought somewhere else.

        🔴 `_adds` is NOT emptied — the lots are zeroed IN PLACE. `_maybe_scale_in` caps the
        ladder on `len(self._adds)`, and Pine caps it on `lAddN`, which only ever counts up. An
        emptied list would hand the slot back and let the trade add again after banking, which
        is a different strategy from the one that was measured (Run 22) and one nothing here has
        tested. ⚠ `_qty` and `_filled_qty` are untouched for the mirror-image reason: they
        describe the BASE position, which is not one lot closer to finished because an add
        banked.
        """
        d, pv = self._pos_dir, self._cfg.point_value
        oid = ("L" if d > 0 else "S") + "-ATP"   # named before the loop; each lot's record takes it
        pnl, closed = 0.0, 0.0
        for i, lot in enumerate(self._adds):
            q = lot[1]
            if q <= 1e-12:
                continue
            lot_pnl = (price - lot[0]) * d * q * pv
            pnl += lot_pnl
            self._charge_commission(q)   # the add pays its own exit side, as on every other path
            self._charge_spread(q)
            lot[1] = 0.0
            closed += q
            self._close_add_record(i, price, sig.time_ms, oid, lot_pnl)
        if closed <= 1e-12:
            return
        self._add_last_px = None         # nothing live left for a target to clear
        self._equity_realized += pnl
        self._account.book_pnl(self._leg, pnl)
        dec.fills.append(Fill("exit", oid, price, closed, d))
        self._legs.append({"reason": oid, "price": price, "ms": sig.time_ms, "qty": closed})

    def _close_add_record(self, i, price, ms, reason, pnl) -> None:
        """Stamp a scale-in lot's RECORD with where it came off and what it made. Reporting only.

        This is what makes an add answerable the way a trade is. The record already said what was
        bought and at what price; it said nothing about how the lot then behaved, so the chart
        could draw an `Add` line and nothing else.

        `mfe_price`/`mae_price` are resolved from the lot's own running high/low HERE rather than
        at the fill, because which of the two is FAVOURABLE is a fact about the direction — the
        same convention `_finalise_trade` uses for the base position.

        ⚠ A lot is stamped ONCE. `_bank_adds` and `_exit_portion` both close adds and both call
        this, and a lot already zeroed is skipped by each of them — but the re-entry guard is kept
        anyway, because a second stamp would overwrite a real exit with a later price and there is
        nothing in the output to say it happened.
        """
        if i >= len(self._add_lots):
            return
        rec = self._add_lots[i]
        if "exit_price" in rec:
            return
        d = self._pos_dir
        hi, lo = rec.get("ext_hi", price), rec.get("ext_lo", price)
        rec["mfe_price"] = round(hi if d > 0 else lo, 5)
        rec["mae_price"] = round(lo if d > 0 else hi, 5)
        rec["exit_price"] = round(price, 5)
        rec["exit_ms"] = int(ms)
        rec["exit_reason"] = reason
        rec["pnl_usd"] = round(pnl, 2)

    def _add_record(self, lot: dict) -> dict:
        """One scale-in lot as it LEAVES the strategy.

        The running high/low and the fill-bar marks are bookkeeping: `_close_add_record` has
        already resolved them into `mfe_price`/`mae_price`, and a consumer reading `ext_hi` would
        be reading an un-directioned number as though it meant *favourable*.
        """
        drop = ("ext_hi", "ext_lo", "_fill_ms", "_limit_fill")
        out = {k: v for k, v in lot.items() if k not in drop}
        if "mfe_price" not in out:
            # A lot still OPEN at finalise. Nothing should reach here — `_exit_portion` takes every
            # add on the trade's last fill — so resolve the excursion rather than emit a half
            # record, and leave `exit_price` ABSENT, which is the honest statement that nothing
            # closed it. A zero there would read as an exit at price 0.00.
            d = self._pos_dir
            hi, lo = lot.get("ext_hi", lot["price"]), lot.get("ext_lo", lot["price"])
            out["mfe_price"] = round(hi if d > 0 else lo, 5)
            out["mae_price"] = round(lo if d > 0 else hi, 5)
        return out

    def _remaining_brackets(self) -> List[Tuple[str, Optional[float], float]]:
        """The still-open exit brackets in TP1→TP2→runner order, with each portion's
        qty. Percentages are of the ORIGINAL position (Pine qty_percent)."""
        d = self._pos_dir
        prefix = "L" if d > 0 else "S"
        p1 = self._qty * self._tp1_pct() / 100.0
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
        # 🔴 A TP RUNG DOES NOT TOUCH THE ADDS; A STOP OR FORCE-CLOSE TAKES THEM IN FULL. That is
        # what the Pine does and it is the reason this is not pro-rata: `L-TP1`/`L-TP2` are
        # `from_entry = "Long"`, so they can only ever close the BASE entry, while each add
        # carries its own `L-AX1..4` exit at the SAME stop and dies with it.
        #
        # 🔴 IT WAS PRO-RATA UNTIL 2026-08-19 AND THAT SILENTLY BINNED PROFIT. A rung closing
        # half the base closed half of every add, then `_finalise_trade` did `self._adds = []`
        # and the remainder vanished with its P&L never booked. MEASURED over 2018-09→2026-08:
        # 112 add lots dropped per run, up to 42.46R — 32% of the result at `exec_tp1_pct = 50,
        # exec_tp2_pct = 25`. It could not fire at the shipped `0/0` (the runner closes 100% of
        # the base, so the fraction was always 1.0), which is exactly why it survived: the
        # divergence lived only on the settings nobody had run. Rule 14 — a green parity gate
        # says nothing about a branch neither implementation entered.
        #
        # `final` is here rather than trusting `market` alone: if a TP rung is what CLOSES the
        # base (`exec_tp1_pct + exec_tp2_pct == 100`), the adds must still go with it. Nothing
        # may outlive the trade that owns it.
        #
        # Each lot is valued against its OWN entry — the line above prices everything off one
        # `_entry`, so folding an add into `_qty` would value units bought at the add price as
        # if bought at the base entry, i.e. invent profit out of arithmetic.
        final = (self._filled_qty + qty) >= self._qty - 1e-9
        if self._adds and (market or final):
            for i, lot in enumerate(self._adds):
                closing = lot[1]
                if closing <= 1e-12:
                    continue
                lot_pnl = (price - lot[0]) * d * closing * self._cfg.point_value
                pnl += lot_pnl
                lot[1] = 0.0
                self._charge_commission(closing)   # the add pays its own exit side too
                self._charge_spread(closing)
                if market:
                    self._charge_slippage(closing)
                self._close_add_record(i, price, sig.time_ms, oid, lot_pnl)
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
            after=self._entry_after,
            mfe_usd=round(mfe_usd, 2), mae_usd=round(mae_usd, 2),
            mfe_price=round(mfe_price, 5), mae_price=round(mae_price, 5), legs=list(self._legs),
            adds=[self._add_record(lot) for lot in self._add_lots],
            tp1=round(self._tp1, 5), tp2=round(self._tp2, 5),
            tp_rungs=((round(self._tp1, 5), self._tp1_pct()),
                      (round(self._tp2, 5), self._cfg.exec_tp2_pct)),
            fib=self._fib))
        dec.closed_r = r
        # A secondary that closes at stage 0 never reached TP1 — it hit its initial stop ("didn't
        # hold"). Flag its direction so the driver kills that 15m leg (a stopped re-entry ends the
        # cascade). A secondary that reached breakeven-or-better (stage >= 1) does NOT flag.
        if self._entry_kind == "secondary" and self._stage == 0:
            self._sec_stop_dir = self._pos_dir
        # The PRIMARY's own record on this leg, for the looser `exec_sec_require` gates. `_stage`
        # is still the trade's final stage here (it is reset a few lines below), so stage 0 means
        # "closed without ever touching TP1" — a stop-out or a time stop, which is exactly the
        # state the breakeven gate refuses.
        if self._entry_kind == "primary":
            if d > 0:
                self._prim_closed_sos_l = self._sos_bar_open
                if self._stage == 0:
                    self._prim_lost_sos_l = self._sos_bar_open
            else:
                self._prim_closed_sos_s = self._sos_bar_open
                if self._stage == 0:
                    self._prim_lost_sos_s = self._sos_bar_open
        self._account.close_position(self._leg)   # P&L already booked; free the reservation
        self._pos_dir = 0
        self._qty = 0.0
        self._filled_qty = 0.0
        self._stage = 0
        self._adds = []
        self._add_lots = []
        self._add_stop = None
        self._base_qty = 0.0
        self._add_limit = None
        self._add_armed = False
        self._add_pending = None
        self._add_pend_stop = None
        self._add_last_px = None
        self._add_tp_level = None
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
        near, far = self._stage_rungs()
        if d > 0:
            self._max_fav = max(self._max_fav, sig.high)
            if self._stage < 1 and sig.high >= near:
                self._stage = 1
            if self._stage < 2 and sig.high >= far:
                self._stage = 2
        else:
            self._max_fav = min(self._max_fav, sig.low + adj)
            if self._stage < 1 and sig.low + adj <= near:
                self._stage = 1
            if self._stage < 2 and sig.low + adj <= far:
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

        self._maybe_scale_in(sig)

    def _maybe_scale_in(self, sig) -> None:
        """PLACE an add order on a runner the trail is already protecting (Pine `execScaleIn`).

        Placement only — `_fill_pending_add` fills it, and the split is load-bearing rather than
        tidy. The whole rule is a SIZING rule, not a timing one:

            locked   = (stop - entry) * base_qty     profit the stop already guarantees
            per_unit = (level - stop)                what one extra unit risks to that SAME stop
            add_qty  = locked / per_unit             worst case == the locked profit

        Stop out immediately after adding and the two cancel: the base banks `locked`, the add
        gives back at most `locked`, the trade closes at worst flat. An add can shrink a winner;
        it cannot manufacture a loser. That is the property that makes this different from every
        protective rule Run 8 killed.

        🔴 **`level` HAS TO BE THE PRICE THE LOT IS ACTUALLY BOUGHT AT, or the guarantee above is
        arithmetic about a trade nobody took.** It held here only once the add became a RESTING
        LIMIT. See `_fill_pending_add` for what a market order cost it, and note that "Trail" is
        a market order by nature and therefore still carries a small version of that gap.

        🔴 **The trigger is the TRAIL (stage 2), never a target.** At TP2 the stop is only at TP1,
        so `locked` is small while `price - stop` is large and the affordable add is a rounding
        error — measured, and it is why "add at TP2" looks worthless. Once the trail has ratcheted
        up near price the same arithmetic permits a LARGE add. The rule therefore self-regulates:
        a trending runner buys size, a stalling one buys nothing, and no separate "is this trade
        still good?" test is needed.

        ⚠ **The ratchet check is load-bearing.** Without it a stalling runner re-adds on every bar
        against the same `locked`, spending the guarantee several times over.

        ⚠ **Costs are charged on the way IN here** (commission + half the spread), exactly as
        `_open_position` does for the base. The other half is charged per portion in
        `_exit_portion`. An add that paid nothing to open is the flattery this was re-measured to
        remove.

        ⚠ **No account call.** The base went through `_account.grant`; an add's net risk to the
        shared stop is <= 0 by construction, so there is nothing for a risk budget to reserve —
        but MARGIN still sees the full position and the live allocator does not exist. That is a
        reason this must not go live yet, and it is recorded on `exec_scale_in` in config.py.
        """
        cfg = self._cfg
        if not getattr(cfg, "exec_scale_in", False) or self._pos_dir == 0:
            return
        # A RESTING order does NOT consume a slot: Pine's `lAddN` increments when the order
        # FILLS, and re-placing while one rests re-uses the same entry id, which replaces it.
        if self._stage < 2 or len(self._adds) >= cfg.exec_scale_max_adds:
            return
        d, pv = self._pos_dir, cfg.point_value
        stop = self._current_stop()

        # Only add again once the trail has moved PAST the stop the last add was sized against.
        # Checked BEFORE the mode branch because it is a property of the SIZE rule, not of where
        # the add happens: without it a stalling runner re-adds every bar on one guarantee.
        if self._add_stop is not None and (stop - self._add_stop) * d <= 0:
            return

        mode = getattr(cfg, "exec_scale_mode", "Trail")
        if mode == "Trail":
            # Run 19's rule: MARKET, on the bar the trail ratcheted. The worst price of the leg
            # by construction — it buys after the move, where the base entry rests a limit and
            # waits — and it makes the most raw R purely because it fires most often.
            # ⚠ A market order is sized off `close` and filled at the NEXT bar's open, so this
            # mode alone still carries the trigger-to-fill gap the resting limit closed. Measured
            # at ZERO breaches over 182 trades, because close-to-next-open is a small gap — but
            # zero is what was observed, not a guarantee the arithmetic provides.
            level = sig.close
        elif mode == "BOS retest":
            # Wait for the next confirmed break of structure our way, then REST A LIMIT at the
            # level that break cleared and let price come back to it.
            # ⚠ Re-arming on every fresh break is deliberate: a later break supersedes an older
            # limit, because the older level stopped being the edge of structure the moment the
            # newer one printed. Pine gets the same behaviour for free — re-issuing
            # `strategy.entry` with the same id REPLACES the resting order.
            if not (sig.bull_bos if d > 0 else sig.bear_bos):
                return
            hi = sig.bull_bos_high if d > 0 else sig.bear_bos_high
            lo = sig.bull_bos_low if d > 0 else sig.bear_bos_low
            # ⚠ BOTH endpoints are required and the leg must be well-formed, even though only
            # one of them is the limit. It is the condition the measurement ran under, and
            # dropping it arms on legs that run never saw.
            if hi is None or lo is None or hi <= lo:
                return
            level = hi if d > 0 else lo
        else:
            # A typed value that is not a mode must never fall through to a default — that would
            # replay a whole book against a rule nobody chose. Same standing as exec_sl_custom.
            raise ValueError(
                f"exec_scale_mode={mode!r} is not a mode. Use 'Trail' or 'BOS retest'."
            )

        # Refuse once the stop is already past the level — that is not an add, it is a loss.
        if (level - stop) * d <= 0:
            return
        locked = (stop - self._entry) * d * self._base_qty * pv
        per_unit = (level - stop) * d * pv
        if locked <= 0 or per_unit <= 0:
            return
        add_qty = min(locked / per_unit, self._base_qty * cfg.exec_scale_cap_x)
        if add_qty <= 1e-9:
            return
        # PLACE the order; `_fill_pending_add` fills it. Nothing is bought here, so nothing is
        # charged here and `_adds` does not grow — a placed-but-unfilled add must not read as a
        # lot the position holds.
        self._add_limit = level
        self._add_pending = add_qty
        self._add_pend_stop = stop
        self._add_armed = True

    def _fill_pending_add(self, sig) -> None:
        """Fill an add order PLACED on an earlier bar. Called before anything can exit.

        🔴 THE ORDER TYPE IS THE WHOLE POINT, AND GETTING IT WRONG COST THE FEATURE ITS ONE
        GUARANTEE. The affordability rule sizes an add so that its worst case equals the profit
        the stop already locked — arithmetic written against the price the add is bought at. A
        MARKET order is sized at one price and filled at another (the next bar's open), so
        whatever moves against you in between is size the guarantee never covered. Measured: a
        market add turned two winners of +3.41R and +1.34R into losses of -2.50R and -2.15R,
        against an un-scaled worst of -2.06R over the same 182 trades. The rule promised that
        could not happen.

        A RESTING LIMIT closes it. The fill price is known before the order is sent, so the size
        is exact; and price that GAPS through a buy limit fills at the open, which is BELOW the
        limit, i.e. BETTER. Every error term now points the safe way.

        ⚠ The size is frozen at PLACEMENT and deliberately not refreshed while the order rests.
        That is also the safe direction: the stop only ratchets favourably, so by the time the
        order fills `locked` has grown and `per_unit` has shrunk — the resting size is smaller
        than what the arithmetic would now permit, never larger.

        ⚠ Costs are charged HERE. A lot that has not been bought has paid no commission and
        crossed no spread.
        """
        cfg, d = self._cfg, self._pos_dir
        qty = self._add_pending
        if qty is None or qty <= 0 or d == 0:
            self._add_armed = False
            self._add_pending = None
            return
        if getattr(cfg, "exec_scale_mode", "Trail") == "Trail":
            price = sig.open          # market: TradingView fills it at the next bar's open
        else:
            reached = (sig.low <= self._add_limit) if d > 0 else (sig.high >= self._add_limit)
            if not reached:
                return                # still resting — Pine leaves the order live too
            price = self._add_limit
            if (sig.open - price) * d < 0:
                price = sig.open      # gapped through: filled BETTER than the limit
        self._adds.append([price, qty])
        # …and the same lot again for the RECORD. `_adds` is spent by `_exit_portion`; this one is
        # not, so the closed trade can still say what it bought and at what price.
        #
        # The lot also carries its OWN excursion window, seeded here and widened every bar by
        # `_widen_add_excursions`, so an add can be asked what any trade is asked: how far did it
        # run, how far did it go against, where did it come off. Until 2026-08-19 the record was
        # the three fields above and a reader could see only that a lot was BOUGHT.
        #
        # Seeded the same ASYMMETRIC way the base entry is (`_try_entry_fill`) and for the same
        # reason: a resting limit is reached by price coming to it from the WRONG side, so the fill
        # bar's favourable extreme is the approach INTO the order and not the lot's own move. A
        # "Trail" add is a MARKET order at this bar's open, so the whole bar is genuinely the
        # lot's and both sides seed at the fill — `_manage_open` runs later in this same `step`
        # and widens it with the bar. Reporting only; no decision reads any of it.
        limit_fill = getattr(cfg, "exec_scale_mode", "Trail") != "Trail"
        if not limit_fill:
            ext_hi = ext_lo = price
        elif d > 0:
            ext_hi, ext_lo = price, sig.low
        else:
            ext_hi, ext_lo = sig.high, price
        self._add_lots.append({
            "price": price, "ms": sig.time_ms, "qty": qty,
            "ext_hi": ext_hi, "ext_lo": ext_lo,
            "_fill_ms": sig.time_ms, "_limit_fill": limit_fill,
        })
        # The ratchet gate is the stop this lot was SIZED against, not the one live at the fill.
        self._add_stop = self._add_pend_stop
        self._add_armed = False
        self._add_pending = None
        self._add_pend_stop = None
        self._add_limit = None
        self._add_last_px = price   # the scale-in target has to clear this
        self._charge_commission(qty)
        self._charge_spread(qty)    # half the round turn; `_exit_portion` pays the other half

    def _stage_rungs(self) -> Tuple[float, float]:
        """The two rung prices ORDERED BY DISTANCE from the entry — (nearer, further).

        🔴 **The stop ladder has to climb in the order price actually reaches the rungs**, and on a
        re-entry it did not. `_tp1` is priced off RISK (`exec_sec_tp_r`, 1.25R) while `_tp2` stays
        the 15m fib it was armed on, so nothing keeps the first beyond the second — MEASURED on run
        687c8df2a523, **23 of 45 re-entries came out flipped** (all 160 primaries were correctly
        ordered, and so is the Pine's own 0.5→0.382 ladder). On a flipped trade `_advance_stage`
        tested the FURTHER price for stage 1 and the NEARER one for stage 2, so price armed the
        TRAIL without ever arming BREAKEVEN — the trade skipped the step that makes it unloseable
        and went straight to the one that assumes it already had. Trade T198 of that run is the
        picture: stage 0 → 2 in one bar, breakeven never armed.

        ⚠ **SECONDARIES ONLY, and that is a parity decision, not caution.** The flip is created by
        `exec_sec_tp_r`, which is a Python-only override that exists nowhere in `mpc_strategy.pine`
        — the Pine has no re-entry at all. Ordering a PRIMARY's rungs would be an unparity-able
        edit to the ported path for a case that has never occurred, so the primary ladder is passed
        through untouched and `compare_strategy.py` sees the same decisions it always did.

        ⚠ **This orders the STOP LADDER only. It does NOT move where profit banks** —
        `_remaining_brackets` still rests the first rung's order at `_tp1` for `_tp1_pct()` of the
        position, wherever that price sits (Aaron's call, 2026-08-21). The 1.25R rung was chosen by
        measurement; reordering the stop steps is a fix, moving the bank is a different decision.
        """
        if self._entry_kind != "secondary":
            return self._tp1, self._tp2
        d = self._pos_dir
        if (self._tp2 - self._entry) * d < (self._tp1 - self._entry) * d:
            return self._tp2, self._tp1
        return self._tp1, self._tp2

    def _tp1_pct(self) -> float:
        """The TP1 rung's percentage for the trade that is actually open.

        A SECONDARY may bank its own percentage (`exec_sec_tp1_pct`); -1.0 means inherit the
        shared `exec_tp1_pct`, which is what the shipped ladder does, so the default cannot move
        a stored figure. A primary never reads the override."""
        if self._entry_kind == "secondary":
            # The RECLAIM half banks its own percentage — see the note on the first-target rung in
            # `_open_position`. Its default is 100 (the whole position off at its target, no
            # runner), which is the configuration that measured 6,740x.
            if self._entry_src == "reclaim":
                own = getattr(self._cfg, "exec_rec_tp1_pct", 100.0)
            else:
                own = getattr(self._cfg, "exec_sec_tp1_pct", -1.0)
            if own != -1.0:
                return own
        return self._cfg.exec_tp1_pct

    def _current_stop(self) -> float:
        cfg = self._cfg
        d = self._pos_dir
        be_buf = cfg.exec_be_buf_tk * cfg.mintick
        # A SECONDARY may hold its INITIAL stop until TP2 instead of ratcheting to breakeven at
        # TP1 (`exec_sec_be_at`). Three of the seven shipped re-entries exited at exactly the
        # 30-tick buffer after touching TP1 — ticked out of their own trade. Secondaries only:
        # the primary's ladder is what the Pine parity gate checks.
        if (self._entry_kind == "secondary" and self._stage == 1
                and getattr(cfg, "exec_sec_be_at", "TP1") == "TP2"):
            return self._sl
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
        # "TP1 price" (default) — the FIRST rung price, i.e. the nearer one. Reaching the second
        # rung pulls the stop back to the first; naming `_tp1` directly would, on a flipped
        # re-entry, pull it to the price price just reached and close the trade there.
        return self._stage_rungs()[0]

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
        far = self._stage_rungs()[1]              # the rung that ARMED stage 2 — see `_stage_rungs`
        run = (self._max_fav - far) if d > 0 else (far - self._max_fav)
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
