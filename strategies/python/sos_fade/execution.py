"""Execution — turns the SOS Fade sequence state into orders, and fills them the way
TradingView's broker emulator does.

A port of the STRATEGY EXECUTION block in `strategies/tradingview/sos_fade_strategy.pine` (4112-4735):
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
from execution.intents import IntentKind, OrderIntent
from backtest.portfolio.account import SoloAccount
from backtest.setups import DEAD, FILLED, RESTING, WATCHING, Confluence, SetupSnapshot

# The canonical ratio→price helper, and the only one allowed: `_sl_anchor`'s Custom branch has to
# land on the exact float the fib engine would have produced for that ratio, and re-deriving
# `ash - range*ratio` here would be a second implementation free to drift by a bit.
from engines.fibonacci.geometry import fib_level

from .config import _TP_LEVELS
from .entry_window import in_window as in_entry_window
from .level_memory import SRC as LVL_SRC
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


#: The names a pulled order is reported under in the signals channel (`SetupSnapshot.paused_by`).
#: The first three match the BLOCKED wording in `_setup_context`, so one rule reads the same in
#: both messages.
_PULL_VETO = "Divergence / extreme-RSI veto"
_PULL_LATE = "Final hour (16:00-18:00 New York)"
_PULL_SH_HOURS = "Short-hold hour window"
_PULL_ENTRY_WINDOW = "No-entry window (New York)"
_PULL_HTF = "HTF breakout / bias filter"
_PULL_FLAT = "Flat-by-close window"
_PULL_TIGHT = "Stop too tight for your minimum"
_PULL_QUIET = "Market too quiet to fade"
_PULL_DEEP = "Limit deeper than the short-hold maximum"
_PULL_NO_ROOM = "No room under the account risk cap"


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
    # `strategy.position_size > 0 ? lTP1 : ...` plot gate. The SOS Fade bot reads its rungs off
    # fib levels the export already carries, so `compare_strategy.py` does NOT diff these;
    # the B-LEG derives them from its frozen band, so `compare_bleg.py` does. Reporting
    # only either way — no decision reads them back, so they are parity-safe.
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    #: 🔴 **WHAT THIS BAR ASKED THE MARKET FOR**, in the one vocabulary the backtest and the live
    #: bot both speak (`execution/intents.py`). `fills` says what the emulator DID; this says what
    #: was WANTED, which is the only half a broker can act on — it can refuse, or fill part of it.
    #:
    #: ⚠ **Emitted alongside the existing booking, and nothing consumes it yet.** That is
    #: deliberate: the stream has to be proven to describe the book before anything is allowed to
    #: act on it, and the book may not move while that is established.
    #:
    #: ⚠ **Reporting-only, so it is parity-safe** — no decision reads it back, exactly like
    #: `tp1`/`tp2` above.
    intents: List[OrderIntent] = field(default_factory=list)


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
    # "primary" (the 15m SOS Fade trade) or "secondary" (a fast-feed sniper re-entry). Reporting-only — no
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
    # other way (`b_leg` overrides `_place_entries` and works off band prices, not this ladder)
    # simply carries None, and the chart draws no fib for it rather than an invented one.
    # The fib LEG this trade was priced off, frozen at order placement — see `TradeFib`. Optional
    # for the same reason every other reporting field here is: a fork that prices its entries some
    # other way (`b_leg` overrides `_place_entries` and works off band prices, not this ladder)
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
    # 8 and 9 are the short-hold variant's own refusals — no Pine counterpart, see `_block_codes`.
    8: "Short-hold time block",
    9: "Entry too deep",
    # 10 has no Pine counterpart either, and it is the one that was MISSING rather than merely
    # unported. The dead-market gate rides INSIDE `_stop_clears_floor`, so until 2026-09-03 it
    # refused live entries while booking nothing anywhere — no block record, no miss code, no
    # Telegram message. It was the only shipped rule that could skip a trade and leave no trace.
    10: "Market too quiet",
    # 11 has no Pine counterpart: the New York no-entry window (`entry_window.py`).
    11: "No-entry window",
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
    8: "Short-hold time block — this hour is inside the window the short-hold variant refuses.",
    11: "No-entry window — the order would have been live inside the New York window you set "
        "for no new entries.",
    9: "Entry too deep — the limit would rest deeper into the retrace than the short-hold "
       "variant allows, and a deep entry measured negative on every pool tested.",
    10: "Minimum market volatility — the 15m ATR is under your floor as a share of price, so "
        "there is not enough range for a fade to have anywhere to go. A DIFFERENT question "
        "from the stop floor, which asks whether the leg is long enough to size against.",
}


def _block_codes(dir_off: bool, arm_off: bool, late: bool, veto: bool,
                 htf_brk: bool, htf_bias: bool, tight: bool = False,
                 sh_hours: bool = False, sh_deep: bool = False,
                 quiet: bool = False, entry_window: bool = False) -> List[int]:
    """Every rule refusing this side, in the Pine's `f_blkCode` precedence order.
    Empty = nothing is blocking; `[0]` is what `f_blkCode` itself would have returned.

    `tight` (the minimum-stop floor) is LAST in precedence and defaults False because it is
    the only code that depends on price rather than on a toggle — a caller that has not
    computed the stop distance yet simply omits it.

    ⚠ **8, 9 and 10 have NO Pine counterpart** — the Pine's `f_blkCode` stops at 7. They are
    appended rather than inserted so every existing code keeps its number, and `codes[0]` stays
    exactly what `f_blkCode` would have returned for every combination the Pine can produce.
    `BlockedSetup` is reporting-only (nothing reads a record back) and the parity gate diffs the
    `px_*` decision stream only, which is what makes a new code parity-safe rather than merely
    convenient.

    ⚠ **8 and 9 can only fire with `exec_short_hold` on, so a shipped run never sees them. 10
    IS SHIPPED AND ON** (`exec_min_atr_pct` 0.08 on the live bot), so unlike its two neighbours
    it changes what a real run reports the day it lands."""
    return [c for c, on in enumerate(
        (dir_off, arm_off, late, veto, htf_brk, htf_bias, tight, sh_hours, sh_deep, quiet,
         entry_window),
        start=1) if on]


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
    # 🔴 **8 and 9 were carved OUT of 7, and that is a CORRECTION rather than an addition.**
    # Code 7's sentence claims the limit rested and price never came back. For a setup the two
    # price gates refused, no limit ever rested — so 7 was telling the reader a story about an
    # order that did not exist, on the one message that explains why a setup died.
    # ⚠ **A separate vocabulary from `_BLOCK_LABEL`, so these numbers are unrelated to block 8/9.**
    # That was already true (block 3 and miss 5 are both the final hour) and is why every
    # consumer reads `labels` / `reasons` rather than the integer.
    8: "Stop too tight",
    9: "Market too quiet",
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
    8: "All three met. The stop sat closer than your minimum distance, so no limit was placed.",
    9: "All three met. Volatility was under your floor — no limit was placed in a dead market.",
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
    # ── capture-only, added 2026-09-15. NOTHING reads these back inside the strategy. ──
    # The retrace leg this setup was priced off: 0.0 (the extreme) and 1.0 (the origin).
    # They are captured rather than a handful of finished levels because every ratio a later
    # reader might want — the 0.5 and 0.886 band edges, the 0.886 stop, any entry fib — is
    # `extreme + (origin - extreme) * ratio` off this pair, and a tool that derives them all
    # from one anchor cannot disagree with itself about where the zone was.
    # They come straight off the same signal fields the re-entry's own zone edges use, so a
    # consumer can never be describing a different leg from the one the setup actually had.
    # `None` when the signal published no leg, which is a setup nothing can be priced off.
    leg_extreme: Optional[float] = None   # fib 0.0
    leg_origin: Optional[float] = None    # fib 1.0

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
    # The SOS bar's TIMESTAMP, snapshotted when the watch opens. `sos_bar` is a POSITION in the
    # warm-up window and that position slides every time the engines re-warm — measured shifting
    # by exactly 70 on two bots on 2026-09-15, which renamed a live setup mid-life and started a
    # second Telegram thread for it. Time does not slide, so `_setup_key` reads this.
    sos_ms: Optional[int] = None
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
    blk_t: bool = False               # the stop floor refused it while in the zone
    blk_q: bool = False               # the market was too quiet while in the zone

    def open(self, sos_bar: Optional[int], sos_ms: Optional[int],
             arm_src: str, swp_nm: str) -> None:
        self.watch, self.sos_bar, self.arm_src, self.swp_nm = True, sos_bar, arm_src, swp_nm
        self.sos_ms = sos_ms
        self.zone = self.fvg = self.blk_v = self.blk_l = self.blk_h = False
        self.blk_t = self.blk_q = False
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
    # `exec_rec_entry_mode` = "Market" — this order does not wait for price to come to it. It
    # fills at the NEXT fill-clock bar's open, whatever that is. ⚠ `edge` is then an ESTIMATE (the
    # arming bar's close, the last price known when the order was placed) and is what `qty` was
    # sized off, exactly as a real market order is sized off the price on the screen. The trade's
    # own R is measured off the FILL, never off this.
    market: bool = False
    #: Which HALF of the strategy built this order — "primary" or "secondary".
    #:
    #: 🔴 **DERIVING THIS FROM `src` IS WRONG AND THAT IS WHY THE FIELD EXISTS.** `src` is None on
    #: every primary AND on a secondary whose caller did not name a trigger (the arming record is
    #: duck-typed, and several callers build a bare stand-in), so the two are genuinely
    #: indistinguishable by it. The fill path has never had to guess — `_open_position` is TOLD
    #: the kind by its caller — but `planned_full_exit_price` is asked BEFORE the fill and has
    #: only this object to go on. Rule 1: *primary* and *unnamed secondary* must not be one value.
    kind: str = "primary"


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

    # Whether this order layer records MISSED setups. The codes describe how far an **SOS Fade** setup
    # got before it died, so a fork where SOS Fade never places an order must switch this off rather
    # than report near-misses of a trade it was never going to take — the same call the B-LEG
    # fork already makes for the blocked markers, for the same reason.
    _records_misses = True

    # 🔴 **HOW THIS ORDER LAYER OPENS A POSITION, DECLARED FOR `algos/live/`.** It rests a limit and
    # waits for price, so the bridge places that order BEFORE anything fills and both books fill off
    # it independently. **The declaration is what keeps the divergence halt alive here**: emulator
    # holding a position against an empty broker book means a limit filled in one book and not the
    # other — the 2026-08-07 fault — and the bridge must stop rather than open a fresh position at a
    # price nobody endorsed. A strategy that enters AT MARKET produces the identical state one
    # instant after its own fill, where stopping would be wrong, and nothing observable separates
    # the two. See `strategies/python/live_contract.py` → `ENTRY_STYLES`.
    # ⚠ Read by the LIVE path only. No replay, no cost and no decision reads it, so it cannot move
    # a trade and the parity gate is structurally blind to it.
    entry_style = "resting"

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
        # The shared account owns the budget and sizes entries. Default = a SoloAccount, which
        # never contends for RISK (it always grants the full desired size out of the budget); a
        # shared PortfolioAccount contends this leg against the others. See backtest/portfolio/.
        #
        # 🔴 **"No cap" was written here and stopped being true on 2026-09-02.** A SoloAccount
        # still carries the VENUE ceiling — 100 lots of gold, measured on the live account — which
        # is not part of the budget and binds regardless of what the account can afford, because a
        # broker refusing a 742-lot order does not care how much equity is behind it. So a solo
        # replay is byte-identical to its old self only while it never ASKS for more than that;
        # measured, the SOS Fade book first touches the ceiling above ~$927,000 of balance.
        # ⚠ Which means the default $1,000,000 opening balance above is ALREADY past that point:
        # anything constructing this class without an account and without a capital figure is
        # sizing under the ceiling. `tests/test_execution.py` pins both sides of it.
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
        # The give-back guard's partial, decided at a bar's close and filled at the next bar's
        # open — the same one-bar delay every other exit here carries. A QUANTITY rather than a
        # flag so the amount is fixed at the moment the rule fired, not recomputed on a bar the
        # position may already have changed size on.
        self._pending_bank: float = 0.0
        # Whether the guard has already acted on THIS trade. Only the two keep-it-open actions
        # read it: without it, "hand to the trail" would swallow the time stop on every later
        # bar and "bank half" would halve the runner again and again.
        self._gave_back: bool = False
        # The reversal exit's decision, taken at a FAST bar's close and filled at the NEXT fast
        # bar's open. It is a SEPARATE slot from `_pending_close` on purpose: that one is drained
        # by the 15m path, and a fast-frame decision landing in it would wait up to a whole 15m
        # bar to fill — which is exactly the delay reading a faster chart exists to avoid.
        self._pending_rev: Optional[str] = None
        # Whether the reversal exit has already acted on THIS trade. Read by the two actions that
        # leave the trade open, for the same reason `_gave_back` is.
        self._rev_done: bool = False
        # The trade's best price AS THE FAST FRAME HAS SEEN IT, in the trade's favour. `None`
        # until the first fast bar of a trade.
        #
        # 🔴 IT EXISTS BECAUSE `_ext_high` / `_ext_low` ARE REPORTING ONLY AND SAY SO. They are
        # widened inside `_manage_open`, which for a PRIMARY runs on the 15m stream — so read
        # from a fast bar they are stale by up to a whole 15m bar, which is exactly the delay
        # reading a faster chart exists to remove. Reading them here would also turn a field the
        # file documents as "never read by a decision" into one, silently, for every later
        # reader. The give-back guard above CAN read them because it runs on the 15m path, where
        # `_manage_open` has just widened them on this same bar.
        self._rev_best: Optional[float] = None
        # The level trigger's memory for THIS trade: one [price, visits, touched_last_bar] row per
        # major level seen AHEAD of price while it was open. A LIST of lists, not a dict keyed by
        # price, because it goes through the JSON position record and a float key comes back a
        # string. `_rev_level_fired` is this bar's answer only and is never carried.
        self._rev_levels: List[List[float]] = []
        self._rev_level_fired: bool = False
        # The no-entry window's clock: the last bar time seen and the smallest bar spacing, so the
        # window can be tested at the time an order would be LIVE. Not position state.
        self._ew_last_ms: Optional[int] = None
        self._ew_step_ms: Optional[int] = None
        # A close a PERSON asked for, holding the reason to book it under, or None for the
        # only state this has in the lab and in every parity run: nobody has asked. Nothing in
        # `backtest/`, in the Pine, or in `compare_strategy.py` can reach `request_close`, so
        # this stays None there and the strategy behaves exactly as it did — which is the
        # property that keeps the parity gate meaningful rather than merely green.
        self._close_requested: Optional[str] = None
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
        # The pre-rung stop rule has latched for this trade. ONE latch, whichever entry method
        # owns the rule — see `_protect_rule`. `_rec_be_armed` is legacy: written only on a
        # reclaim, read by nothing here, and kept so a rollback to the previous deployment can
        # still restore this version's position record.
        self._rec_be_armed = False
        self._exc_be_armed = False
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
        # Quote-to-account conversion. `None` means NOBODY HAS INSTALLED A RATE, which is not the
        # same as a rate of zero - `_pv()` falls back to the configured constant rather than
        # treat an unasked rate as a measured one. See `_pv` and `set_rate_provider`.
        self._rate_provider = None
        self._pv_now = None
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
        # The stop this strategy last ASKED for. A stop is re-stated every bar, but
        # only a CHANGE is an instruction — re-sending an unchanged stop would have a
        # live bot modifying the same order on every bar for no reason.
        # ⚠ Not persisted: after a restart the first change re-states it, which is the
        # safe direction (one extra instruction, never a missed one).
        self._last_asked_stop = None
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
        # "1m break" scale-in. `_fast_breaks` is a BUFFER, not position state: each fast bar's
        # internal breaks as (fast bar open ms, +1/-1, "sos"/"bos"), consumed by the 15m bar they
        # fell inside. The `_brk_*` fields are the trade's own leg bookkeeping, in the DIRECTION
        # frame: the best price since the second target, whether a bounce against the trade has
        # been seen, how many breaks back since, whether this push has already added, and how
        # many adds had filled when last looked. Each buffered break also carries the fast
        # feed's EXTERNAL trend as of that bar (+1/-1/0). See `_place_break_add`.
        self._fast_breaks: List[Tuple[int, int, str, int]] = []
        self._brk_ext: Optional[float] = None
        self._brk_bounce = False
        self._brk_count = 0
        self._brk_used = False
        self._brk_nadds = 0
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
        # The same two legs identified by TIME rather than by bar number — see `_same_leg`.
        self._traded_sos_l_ms: Optional[int] = None
        self._traded_sos_s_ms: Optional[int] = None
        # bar number -> bar time, for the run this object is living through.
        self._bar_ms: dict = {}
        # Is that map still in ASCENDING key order? One `step` per bar inserts one strictly
        # increasing index, so it is — in every backtest and in every live session, because the
        # map is rebuilt empty on each restart (it is deliberately NOT in `_POSITION_FIELDS`).
        # That is what lets `_remember_bar` prune in O(1) instead of re-sorting. It is tracked
        # rather than assumed: the day something inserts out of order, the flag latches False and
        # the prune falls back to the sort, which is correct at any order.
        self._bar_ms_ordered: bool = True
        self._bar_ms_last: Optional[int] = None
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
        # The LAST price this setup published as its entry edge, kept after the gap itself is
        # gone — the re-entry's `exec_sec_poi_fallback`. Per SETUP and cleared by
        # `_sync_gap_latch`, the same key and the same lifetime as `_gap_seen_*`: a price
        # belonging to a dead setup is how a re-entry rests at a level nothing is watching.
        # ⚠ It is NOT a second reading of the gap rules — it is the number `_entry_edges`
        # already published, remembered. Nothing reads it unless the fallback is switched on.
        self._poi_last_l: Optional[float] = None
        self._poi_last_s: Optional[float] = None
        # The last level a PRIMARY on this side actually TRADED, as (entry price, that
        # trade's own stop distance, the ms it closed at) — the level memory's whole input.
        # 🔴 It is NOT `_poi_last_*` above and the two must not be merged. That one is the
        # price the setup PUBLISHED, rewritten every bar and cleared when the setup dies.
        # This one is a price the bot FILLED at, and its entire point is that it outlives the
        # setup: `_sync_gap_latch` deliberately does not touch it.
        # ⚠ Written unconditionally at finalise — the config is read by the ARM, not here —
        # so switching the feature on mid-run cannot find a half-filled memory, and the OFF
        # path never looks. Last-per-side rather than a list, so nothing accumulates.
        self._lvl_last_l: Optional[Tuple[float, float, int]] = None
        self._lvl_last_s: Optional[Tuple[float, float, int]] = None
        # A primary a PERSON closed before it reached TP1, as (sos bar, that trade's own first
        # target) — see `_finalise_trade`. While the setup lives, price reaching that level
        # opens the re-entry's breakeven door exactly as holding the trade would have. Per
        # SETUP, cleared by `_sync_gap_latch`. ⚠ It is NOT carried across a restart: the bot
        # re-warms from bars, which cannot know a person closed anything, so a restart loses the
        # watch and the door stays shut. That is the safe direction — a missed re-entry, never
        # an extra one.
        self._cmd_watch_l: Optional[Tuple[int, float]] = None
        self._cmd_watch_s: Optional[Tuple[int, float]] = None
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
        #: How many rungs fell back to the Auto fib level because the level the config NAMED was
        #: not beyond that trade's entry. Reporting-only (parity-safe, nothing reads it back), and
        #: it exists so a sweep cannot report a level as measured when most trades ignored it.
        #: Counted per RUNG placed, so one setup can add two.
        self.tp_level_fallbacks = 0
        # Blocked setups (reporting only — see BlockedSetup). `_blk_keys` is the Pine's
        # per-side dedupe latch (`sosBar*10 + code`): one entry per setup per REASON, so a
        # setup blocked for twenty bars is one record — but a reason SET that CHANGES is a
        # genuinely different refusal and gets its own.
        self.blocks: List[BlockedSetup] = []
        self._blk_keys: List[Optional[Tuple[int, Tuple[int, ...]]]] = [None, None]
        # The gate booleans `_armed` computed this bar, stashed for `_record_blocks`. `_armed`
        # stays a pure gate (the B-LEG fork reuses it as its SOS Fade-priority check), and the
        # recording hangs off `_place_entries`, which that fork overrides — which is exactly
        # why the B-LEG bot records no blocks: its codes describe why an SOS Fade setup was refused,
        # and SOS Fade never trades there. See strategies/python/b_leg/CLAUDE.md.
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
        #: Per side, the strategy's own rules that kept this bar's order OFF the book — set only
        #: by `_place_entries` and `_open_position`, from the same booleans that removed it, and
        #: cleared at the top of every `step`. Reporting only: read by `live_setups()` alone.
        self._pull_why: List[Tuple[str, ...]] = [(), ()]
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

    @property
    def entry_src(self) -> Optional[str]:
        """Which trigger armed the OPEN trade — the string frozen on its order, or None.

        🔴 **IT IS NOT DERIVABLE FROM `entry_kind`, AND THAT IS WHY IT IS PUBLIC.** Several
        sources now share the re-entry's order path and all of them book as `secondary`; the
        driver has to know which state machine to retire on a fill, and asking the config
        would answer *which triggers are enabled* rather than *which one produced this trade*.
        """
        return self._entry_src

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
        "_rec_be_armed", "_exc_be_armed",
        "_trail_swing_hi", "_trail_swing_lo", "_ext_high", "_ext_low", "_legs",
        "_pending_close", "_pending_bank", "_gave_back",
        "_pending_rev", "_rev_done", "_rev_best", "_rev_levels",
        # Scale-in lots, and they belong here for the reason the warning above gives: a
        # restored position that dropped them would carry the base's stop while the adds it
        # actually holds went unpriced and unclosed. `_add_stop` is the stop the last add was
        # sized against — without it a restored runner re-adds immediately at the same locked
        # profit, which is exactly the over-spend the ratchet check exists to stop.
        "_adds", "_add_lots", "_add_stop", "_base_qty", "_add_limit", "_add_armed",
        "_add_pending", "_add_pend_stop", "_add_last_px", "_add_tp_level",
        # The "1m break" leg bookkeeping — without it a restored trade re-seeds its best price
        # and can add twice on one push. ⚠ New 2026-09-25: a record saved by an older version
        # lacks these, and `restore_position` refuses it; migrate it at promote.
        "_brk_ext", "_brk_bounce", "_brk_count", "_brk_used", "_brk_nadds",
        # Which re-entry trigger armed the open secondary. It DECIDES the exit ladder — the
        # reclaim half carries its own first target and its own bank percentage — so a restored
        # trade that lost it would manage against the other half's rungs, silently.
        "_entry_src",
        "_entry_after",
        # SETUP-scoped rather than position-scoped, and carried anyway: it is the
        # one-trade-per-15m-leg latch. Without it a restored bot could re-enter the very setup
        # it is already holding, the moment this trade closes.
        "_traded_sos_l", "_traded_sos_s",
        # ...and their TIMES, which is the half that survives a restart. Without these the
        # restored latch is a bar number from the PREVIOUS numbering and matches nothing.
        "_traded_sos_l_ms", "_traded_sos_s_ms",
    )

    def request_close(self, reason: str = "commanded") -> bool:
        """Ask this strategy to close its open position. Returns True if there was one.

        🔴 **THE STRATEGY IS TOLD, NOT THE BROKER, AND THAT IS THE ENTIRE POINT.** Closing a
        position by hand at the terminal leaves the emulator still holding it, and the bridge
        HALTS on the next bar — correctly, because from the outside that is indistinguishable
        from a position vanishing for a reason nobody can name. A partial close by hand is
        worse: nothing notices at all, and every later size the strategy computes is against a
        book it does not have. So the instruction has to arrive HERE, where it changes what the
        strategy believes, and the broker is brought into line afterwards.

        ⚠ **It does not close anything itself.** The exit happens on the next bar through the
        one path every other market exit uses, so the trade is booked, recorded and alerted on
        exactly like a time stop — same one-bar delay, same fill model, same record. A separate
        exit path here would be a second implementation of the thing this file already does,
        and it would be the one nobody's tests cover.

        ⚠ **Asking twice before the next bar is not two closes.** The second call replaces the
        first's reason and there is still one position to close. It is idempotent by being a
        value rather than a queue.

        ⚠ **`reason` is for the CALLER's record, not this trade's.** The trade is booked under
        `L-CMD` / `S-CMD`, because that is the tag, and a tag is all `_close_at` keeps. Free
        text about who asked and why belongs in the decision ledger, which can hold a sentence;
        writing it here would look stored and would not be.

        ⚠ **It refuses when flat rather than latching**, and the False is the useful half: a
        request that quietly waited would fire on whatever the strategy opened next, which is a
        trade the person asking had no opinion about. The caller reports "nothing to close".
        """
        if self._pos_dir == 0:
            return False
        self._close_requested = reason or "commanded"
        return True

    def snapshot_setup_watch(self) -> Optional[dict]:
        """What this bot is still watching WHILE FLAT, so a restart does not forget it.

        Today that is one thing: a setup whose primary a PERSON closed before it reached its
        first target (`_check_cmd_watch`). `None` when there is nothing to remember, which the
        caller writes as "no file" rather than as an empty record.

        🔴 **IT IS A SEPARATE RECORD FROM `position.json` BECAUSE IT LIVES IN THE OPPOSITE
        STATE.** That file describes an OPEN position and is deleted the moment the bot goes
        flat — which is exactly when this begins to matter. Folding one into the other would
        mean either keeping a position record for a position that does not exist, or losing
        this every time a trade closes.

        ⚠ **Each side carries the leg's TIME beside its bar number**, and the time is the half
        that survives: bar numbering is local to one run. See `_same_leg`.
        """
        def _one(watch):
            if watch is None:
                return None
            return {"sos_bar": watch[0], "sos_ms": watch[1], "tp1": watch[2]}

        if self._cmd_watch_l is None and self._cmd_watch_s is None:
            return None
        return {"version": 1, "long": _one(self._cmd_watch_l), "short": _one(self._cmd_watch_s)}

    def restore_setup_watch(self, record: Optional[dict]) -> bool:
        """Take a record from `snapshot_setup_watch` back. Call AFTER the warm-up.

        Returns True if anything was restored. **Call it after the replay**, for the same reason
        `restore_position` is applied there: the warm-up drives this same object through
        thousands of bars and would clear the watch on the first new break it replays.

        🔴 **A SIDE WITHOUT A LEG TIME IS DROPPED RATHER THAN RESTORED ON ITS BAR NUMBER.** The
        numbering is rebuilt by the warm-up, so the old number now names a different bar — it
        would open a re-entry door on a setup nobody was watching. Dropping it costs a possible
        re-entry, which is the safe direction and the same one the missing watch had before this
        existed. ⚠ An unreadable record is treated the same way and never raises: this is a
        convenience, and it must not be able to stop a bot from starting.
        """
        if not isinstance(record, dict):
            return False
        took = False
        for side, attr in (("long", "_cmd_watch_l"), ("short", "_cmd_watch_s")):
            one = record.get(side)
            if not isinstance(one, dict):
                continue
            sos_ms, tp1 = one.get("sos_ms"), one.get("tp1")
            if sos_ms is None or tp1 is None:
                continue
            try:
                setattr(self, attr, (one.get("sos_bar"), int(sos_ms), float(tp1)))
            except (TypeError, ValueError):
                continue
            took = True
        return took

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
    @property
    def last_primary_level_l(self) -> Optional[Tuple[float, float, int]]:
        """(entry, that trade's stop distance, close ms) of the last LONG primary, or None."""
        return self._lvl_last_l

    @property
    def last_primary_level_s(self) -> Optional[Tuple[float, float, int]]:
        """(entry, that trade's stop distance, close ms) of the last SHORT primary, or None."""
        return self._lvl_last_s

    @property
    def primary_resting_long(self) -> bool:
        """Is a PRIMARY buy limit resting right now?

        Read by the level memory's quiet gate. It is the operational reading of *the bot had
        something armed* — an order on the book is what makes a second order a second claim on
        the one position slot, which a setup merely watching is not.
        """
        return self._pend_long is not None

    @property
    def primary_resting_short(self) -> bool:
        """Is a PRIMARY sell limit resting right now? See `primary_resting_long`."""
        return self._pend_short is not None

    def level_memory_overdue(self, now_ms: int) -> bool:
        """Has an open LEVEL-MEMORY trade been held past `exec_lvl_max_hold_hrs`?

        ⚠ **It answers the question and closes nothing.** `step_secondary` turns a True into
        the same `_pending_close` slot the 15m side uses, so the exit is decided at a bar's
        close and filled at the next bar's OPEN — one exit path, one fill model, one record.

        🔴 **THE ORDINARY TIME STOP CANNOT REACH THIS TRADE, WHICH IS WHY THIS EXISTS.**
        `_time_stop_due` is read in the 15m `step`, inside the branch that skips a secondary
        position outright (`_entry_kind != "secondary"`). Reusing the mode would have looked
        right in the config and done nothing at all.
        """
        if self._pos_dir == 0 or self._entry_src != LVL_SRC:
            return False
        hrs = float(getattr(self._cfg, "exec_lvl_max_hold_hrs", 72.0))
        if hrs <= 0:
            return False
        return (int(now_ms) - self._entry_ms) >= hrs * 3_600_000

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
        # The re-entry runs on its OWN faster clock, and it places orders too, so it stamps the
        # account the same way `step` does — otherwise a clamp on a re-entry carries the 15m
        # bar time of whenever the primary last stepped, which is worse than carrying nothing.
        self._stamp_account_clock(sig1m)
        sink = Decision(index=sig1m.index)   # throwaway — trades land in self.trades regardless
        filled_dir: Optional[int] = None

        # ── Phase A: fill / manage against THIS fill-clock bar ──
        # A close decided at the LAST fill-clock bar's close is a market order, so it fills at
        # THIS bar's open — ahead of any stop or target, exactly as the 15m side does it.
        # ⚠ Guarded on the kind: `_pending_close` is a shared slot, and the 15m `step` only
        # ever writes it for a position IT manages. Draining someone else's would close a
        # primary on the wrong clock.
        if (self._pending_close is not None and self._pos_dir != 0
                and self._entry_kind == "secondary"):
            _reason, _tag = self._pending_close
            self._pending_close = None
            self._close_at(sig1m, sig1m.open, _reason, sink, tag=_tag)
        if self._pos_dir == 0 and self._pend_sec is not None:
            pend = self._pend_sec
            adj = self._ask_adj(pend.dir, entry=True)   # the sniper is a resting limit too
            # `exec_rec_entry_mode` = "Market" — no price test at all: the order was placed at the
            # last bar's close and takes THIS bar's open. It still cannot fill on its own placement
            # bar, because the one-bar delay every fill on this engine is built on comes from the
            # place-at-close / fill-next-bar cycle rather than from a check here.
            if pend.dir > 0 and (pend.market or sig1m.low + adj <= pend.edge):
                o = sig1m.open + adj
                fill = o if pend.market else (pend.edge if o > pend.edge else o)
                if self._open_position(pend, fill, sig1m, sink, kind="secondary"):
                    filled_dir = 1
            elif pend.dir < 0 and (pend.market or sig1m.high >= pend.edge):
                o = sig1m.open
                fill = o if pend.market else (pend.edge if o < pend.edge else o)
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
            # LEVEL MEMORY's maximum hold. Decided here, at the bar's close, and filled at the
            # next bar's open by Phase A above. Off for every other trade on this path.
            if self._pending_close is None and self.level_memory_overdue(sig1m.time_ms):
                self._pending_close = ("level-memory max hold", "TIME")

        return filled_dir

    def _market_entry(self, src) -> bool:
        """`exec_rec_entry_mode` — does THIS re-entry take the next open instead of waiting for
        price to come back to it? Reclaims only, and off unless asked for.

        The reclaim's shipped path is a RETEST: price sweeps the primary's stop, trades back
        through that level (which arms it), and a limit then rests AT the level waiting for price
        to return. MEASURED 2026-08-23: 29 of 90 re-entry orders waited over 30 minutes for that
        return and 8 waited over 12 hours, and Aaron's 2025-08-19 reclaim is one of the 8. A market
        entry buys a worse price and a wider stop in exchange for never missing the move."""
        if (src == LVL_SRC
                and getattr(self._cfg, "exec_lvl_confluence", "None") == "Shift confirms"):
            # The level memory's confirmed entry is a MARKET order by design: the shift is the
            # signal, and a limit resting back at the level would wait for a second tap the
            # confirmation never asked for. Its `edge` is the confirming bar's close — the last
            # price known when the order was placed — exactly as the reclaim's market mode.
            return True
        return (src == "reclaim"
                and getattr(self._cfg, "exec_rec_entry_mode", "Retest") == "Market")

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
                qty = self._qty_for_risk(risk_pct, dist)
                qty = self._fit_to_budget(qty, arm.l_edge, arm.l_sl)
                # ⚠ An unaffordable long falls THROUGH to the short check rather than returning
                # nothing. Only one side can be taken, and refusing the pair because the first
                # one asked for too much would drop a re-entry the budget could have carried.
                # `getattr`, because `arm` is a duck-typed record here and several tests build a
                # bare stand-in for it. A missing field means "no trigger named itself", which the
                # ladder reads as the shared settings — the behaviour every caller had before the
                # reclaim half existed.
                if qty > 0:
                    return _Pending(1, arm.l_edge, qty, arm.l_sl, arm.l_tp1, arm.l_tp2, arm.l_leg,
                                    src=getattr(arm, "l_src", None),
                                    after=getattr(arm, "l_after", None),
                                    market=self._market_entry(getattr(arm, "l_src", None)),
                                    kind="secondary")
        if arm.s_armed and arm.s_edge is not None and arm.s_sl is not None:
            dist = arm.s_sl - arm.s_edge
            if self._stop_clears_floor(dist, arm.s_edge):
                qty = self._qty_for_risk(risk_pct, dist)
                qty = self._fit_to_budget(qty, arm.s_edge, arm.s_sl)
                if qty > 0:
                    return _Pending(-1, arm.s_edge, qty, arm.s_sl, arm.s_tp1, arm.s_tp2,
                                    arm.s_leg,
                                    src=getattr(arm, "s_src", None),
                                    after=getattr(arm, "s_after", None),
                                    market=self._market_entry(getattr(arm, "s_src", None)),
                                    kind="secondary")
        return None

    # ── main step ───────────────────────────────────────────────────────────────
    def step(self, sig, seq) -> Decision:
        dec = Decision(index=sig.index)

        # The conversion rate for THIS bar, asked once so a bar cannot price two of its own
        # fills differently. Inert with no provider installed - see `_pv`.
        if self._rate_provider is not None:
            self._pv_now = self._rate_provider(sig.time_ms)

        # Before anything reads a bar number. See `_same_leg` for why a number is not enough.
        self._remember_bar(sig)
        self._pull_why = [(), ()]

        # Tell the account WHEN it is, unless a shared stack's simulator already owns the clock.
        # Without this a standalone run stamps every budget and venue-ceiling record with a null
        # time — and the venue-ceiling record is the only trace a resized entry leaves anywhere.
        self._stamp_account_clock(sig)

        # Runs before anything can branch — see `_update_atr`.
        self._update_atr(sig)

        # Decision context the Pine computes EVERY bar (not just when flat), so the
        # decision streams line up bar-for-bar: the entry edges, the SOS Fade stage, the veto.
        # Before the edges, so a new break of structure re-opens the block leg on the same bar it
        # arms rather than one bar late.
        self._sync_gap_latch(seq)
        self._check_cmd_watch(sig, seq)
        long_edge, short_edge = self._entry_edges(sig, seq)
        dec.long_edge, dec.short_edge = long_edge, short_edge
        # Latched for the SECONDARY's gap half (any `exec_sec_trigger` naming the gap), which
        # re-uses the PRIMARY's own point-of-interest price rather than computing a second one —
        # Aaron's rule is *"follow the rules of fair value gap entry that we would take on a
        # primary trade"*, and a second implementation of those rules is how the two silently
        # diverge. Reporting-free: nothing reads these unless the gap trigger is on, so the
        # shipped book cannot move. Cleared with the setup by `_sync_gap_latch`'s own caller.
        self._poi_edge_l, self._poi_edge_s = long_edge, short_edge
        # Remember the last price this setup published, for the re-entry's gap-gone fallback.
        # ⚠ Written unconditionally — the config is read at the ARM, not here — so switching the
        # fallback on mid-run cannot find a half-filled memory, and the OFF path never looks.
        if long_edge is not None:
            self._poi_last_l = long_edge
        if short_edge is not None:
            self._poi_last_s = short_edge
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
            self._fill_pending_add(sig, dec)
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
        # The give-back guard's partial fills in the same slot and for the same reason: it is a
        # market order the broker already has, so it goes before any stop or target this bar.
        if self._pending_bank > 0 and self._pos_dir != 0 and not opened:
            self._exit_portion("GIVE", sig.open, self._pending_bank, sig, dec)
        self._pending_bank = 0.0
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
            # ⚠ ON CHANGE ONLY — see `_last_asked_stop`. `dec.stop` is the STATE of the stop and
            # is stated every bar; an intent is an INSTRUCTION and there is only one when it moves.
            if dec.stop is not None and dec.stop != self._last_asked_stop:
                dec.intents.append(OrderIntent(
                    kind=IntentKind.MOVE_STOP, direction=self._pos_dir,
                    stop=dec.stop, reason="stop",
                ))
                self._last_asked_stop = dec.stop
            # Re-rest the adds' target for the NEXT bar, in the same slot the stop is
            # staged in and for exactly the same reason: an exit order placed at THIS
            # close is what the next bar trades against (TradingView's one-bar delay).
            self._add_tp_level = self._add_tp_target(sig)
            dec.tp1, dec.tp2 = self._tp1, self._tp2
            # tell the account this leg's live stop + remaining size, so its reservation is
            # current for any other leg sizing on the next tick (drops to 0 once stop = BE).
            self._account.update_stop(self._leg, dec.stop, self._qty - self._filled_qty)
            # A CLOSE ASKED FOR BY A PERSON, and it outranks every rule below it. It is
            # checked first because an operator instruction is not a competing strategy
            # opinion — if somebody has said get me out, a time stop firing on the same bar
            # must not relabel that exit as the clock's doing. The trade still leaves through
            # the ONE exit path everything else uses, so it is booked, recorded and reported
            # exactly like any other market close (one-bar delay included).
            #
            # ⚠ **Deliberately NOT persisted in `_POSITION_FIELDS`.** The request's home is the
            # file the runner watches, and a restart re-reads it — so there is one source of
            # truth rather than two that can disagree. Persisting it would also make every
            # existing position record incomplete, which the promote gap-check reads as a
            # migration. **And a latched close that survives a restart is the `stop.request`
            # hazard exactly**: a stale instruction outliving the moment somebody meant it, then
            # flattening a position an hour later with nobody expecting it. Losing the request
            # on a restart is visible and cheap — the position is still open and you ask again.
            if self._close_requested is not None:
                # ⚠ **"CMD", not "CLOSE", and the distinction is load-bearing.** Only the TAG
                # reaches the trade record — `_close_at` discards its reason argument and stores
                # the order id built from this — and the opposite-break close above already uses
                # "CLOSE". Sharing it would make *a person asked for this* and *structure broke
                # against us* the same value in the record, which is this repo's oldest defect
                # shape and would quietly corrupt any study of why trades ended.
                self._pending_close = (self._close_requested, "CMD")
                self._close_requested = None
            # optional force-close on an opposite SOS (Pine execCloseOppSOS)
            elif self._cfg.exec_close_opp_sos and (
                (self._pos_dir > 0 and sig.bear_sos) or (self._pos_dir < 0 and sig.bull_sos)
            ):
                self._pending_close = ("opp-SOS", "CLOSE")
            # deliberate deviation: force-flat before the daily close (real runs only)
            elif self._flat_closes_now(sig):
                # The ONE force-close that fills at this bar's CLOSE rather than the next open,
                # and it is not an inconsistency: it has no `strategy.close()` behind it (there is
                # no such input in any Pine file) and its whole purpose is to be FLAT before the
                # daily close. Deferring it to the next bar's open would carry the position
                # overnight — the exact thing it exists to prevent — and would charge the swap it
                # was switched on to avoid.
                self._close_at(sig, sig.close, "flat-by-close", dec)
            # optional give-back guard — how much of its BEST this trade has handed back.
            # It sits ahead of the clock because it is a price rule and the clock is not: a bar
            # that trips both is a trade that gave its profit back, which is the more specific
            # reason to name on the exit. It closes at the NEXT bar's open like every other
            # force-close here, never at the close of the bar that tripped it.
            elif self._giveback_due(sig.close) and self._giveback_has_work():
                self._apply_giveback()
            # optional time stop (Pine execTimeStopMode) — the clock, not the price
            elif self._time_stop_due(sig):
                self._pending_close = ("time-stop", "TIME")
        elif self._pos_dir == 0:
            self._place_entries(sig, seq, dec, dec.long_edge, dec.short_edge)
        # else: a secondary is open — managed on the fill-clock stream (step_secondary), not here.

        return dec

    # ── SOS Fade arm gate (Pine longArmed/shortArmed, 4358-4359) ───────────────────────
    def _armed(self, sig, seq, dec, long_edge, short_edge) -> Tuple[bool, bool]:
        """The full SOS Fade arm decision: arm-source filter + late-day + HTF blocks + veto +
        the one-trade-per-leg latch. Sets `dec.long_armed`/`dec.short_armed` and RETURNS
        the pair, WITHOUT placing anything. Extracted verbatim from `_place_entries` so the
        B-LEG fork can reuse it as its 'SOS Fade has priority' gate — parity-preserving (this is
        exactly what `_place_entries` used to compute inline)."""
        cfg = self._cfg
        late, htf_block_l, htf_block_s, bias_block_l, bias_block_s = self._bar_gates(sig)
        sh_hours = self._sh_hour_block(sig)
        # The variant's window refuses an ENTRY exactly the way the final hour does, so it is
        # ANDed in beside it rather than given its own branch — one place decides what "the clock
        # refuses this bar" means, and the marker below reads the same booleans.
        late_any = late or sh_hours or self._entry_window_block(sig)

        # arm-source filter (Pine 4349-4355)
        use_swp_l = cfg.exec_arm_sweep and seq.sos_l_swp
        use_div_l = cfg.exec_arm_div and seq.sos_l_div
        use_swp_s = cfg.exec_arm_sweep and seq.sos_s_swp
        use_div_s = cfg.exec_arm_div and seq.sos_s_div
        arm_ok_l = use_swp_l or use_div_l
        arm_ok_s = use_swp_s or use_div_s

        long_armed = (cfg.exec_aplus and cfg.exec_longs and arm_ok_l and not late_any and not htf_block_l
                      and not bias_block_l and seq.l_sos_bar is not None and sig.fibo_dir == 1
                      and long_edge is not None
                      and (not dec.long_veto or not cfg.exec_respect_veto)
                      and not self._same_leg(self._traded_sos_l, self._traded_sos_l_ms, seq.l_sos_bar))
        short_armed = (cfg.exec_aplus and cfg.exec_shorts and arm_ok_s and not late_any and not htf_block_s
                       and not bias_block_s and seq.s_sos_bar is not None and sig.fibo_dir == -1
                       and short_edge is not None
                       and (not dec.short_veto or not cfg.exec_respect_veto)
                       and not self._same_leg(self._traded_sos_s, self._traded_sos_s_ms, seq.s_sos_bar))
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

    def _entry_window_block(self, sig) -> bool:
        """Is this bar's order inside the New York no-entry window? Reporting AND refusing.

        The time tested is when the order would be LIVE — this bar's CLOSE, i.e. its open plus
        the bar spacing — because an order decided here can only fill from the next bar on. The
        spacing is the SMALLEST gap seen between bars, the same reading the parity gate uses for
        the chart's timeframe, so a weekend gap cannot inflate it. Before a second bar has been
        seen the spacing is unknown and the open is used, which can only refuse LESS.

        A separate method rather than a widened `late`, for the reason `_sh_hour_block` gives:
        `late` is what the marker renders as the 16:00 final-hour rule.
        """
        cfg = self._cfg
        if not cfg.exec_entry_block_from:
            return False
        t = int(sig.time_ms)
        last = self._ew_last_ms
        if last is not None and t > last:
            gap = t - last
            self._ew_step_ms = gap if self._ew_step_ms is None else min(self._ew_step_ms, gap)
        if last is None or t > last:
            self._ew_last_ms = t
        return in_entry_window(cfg.exec_entry_block_from, cfg.exec_entry_block_to,
                               t + (self._ew_step_ms or 0))

    def _sh_hour_block(self, sig) -> bool:
        """The short-hold variant's own New York hour window, half-open [from, to).

        🔴 **A SEPARATE gate rather than more hours folded into `late`, and that is the whole
        reason it is its own method.** `late` is what the block marker and the missed-setup
        callout both render as *"Final-hour rule — no new entries 16:00-18:00 New York"*. Widening
        it to cover a 10:00 window would leave both of them saying 16:00 about a setup refused at
        10:00 — a label describing a rule the code no longer has, which is this repo's most
        expensive shape of defect. It gets its own code (8) so the marker can say what happened.

        🔴 **AND IT IS A SEPARATE METHOD RATHER THAN A SIXTH RETURN VALUE FROM `_bar_gates`,
        WHICH IS A DIFFERENT REASON AGAIN.** `bos` reuses this class and unpacks that tuple
        into five names, so widening it raised `ValueError: too many values to unpack` in ANOTHER
        strategy — caught by that strategy's own parity test, not by anything here. **A shared
        base class makes its return SHAPE part of a contract two packages away**, and the cheap
        way to add something to it is not to add it to the tuple.

        Off unless both hours are set, and inert entirely with the variant off."""
        cfg = self._cfg
        if not cfg.exec_short_hold:
            return False
        lo, hi = cfg.exec_sh_block_from, cfg.exec_sh_block_to
        if lo < 0 or hi < 0:
            return False
        # A window may WRAP midnight (22:00 -> 02:00). Handled rather than refused, because New
        # York hours are what a trader states a session in and Asia genuinely straddles the day.
        return (lo <= sig.ny_hour < hi) if lo < hi else (sig.ny_hour >= lo or sig.ny_hour < hi)

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
        # The miss watch asks only "did a clock rule refuse this bar", so the two windows fold
        # together HERE rather than in `_bar_gates` — see `_sh_hour_block` for why that method
        # exists at all.
        late = late or self._sh_hour_block(sig) or self._entry_window_block(sig)

        # Which arm sources COUNT — the live flags already filtered through the enable-toggles,
        # exactly as `_armed` reads them, so "armed" means the same thing in both places.
        sides = (
            (0, True, seq.l_stage, seq.l_sos_bar, self._traded_sos_l, self._traded_sos_l_ms,
             self._pos_dir <= 0,
             seq.l_half or seq.l_618, long_edge, dec.long_veto and cfg.exec_respect_veto,
             htf_l or bias_l, cfg.exec_arm_sweep and seq.sos_l_swp,
             cfg.exec_arm_div and seq.sos_l_div, seq.l_arm_src, sig.recent_ssl),
            (1, False, seq.s_stage, seq.s_sos_bar, self._traded_sos_s, self._traded_sos_s_ms,
             self._pos_dir >= 0,
             seq.s_half or seq.s_618, short_edge, dec.short_veto and cfg.exec_respect_veto,
             htf_s or bias_s, cfg.exec_arm_sweep and seq.sos_s_swp,
             cfg.exec_arm_div and seq.sos_s_div, seq.s_arm_src, sig.recent_bsl),
        )
        for (slot, is_long, stage, sos_bar, traded_sos, traded_sos_ms, flat, zone_hit, edge,
             veto,
             htf_any, arm_swp, arm_div, arm_src, swp_nm) in sides:
            m = self._mw[slot]
            # Open the watch on the RISING edge into stage 2 OR HIGHER — a fast leg can print the
            # SOS and tag the 0.5 on the same bar, jumping 1 → 3, and an `== 2` test would never
            # open the watch for it. The arm source and swept level are snapshotted here because
            # the sequence clears them the instant the setup dies.
            if stage >= 2 and self._prev_stage[slot] < 2:
                m.open(sos_bar, self._bar_ms.get(sos_bar) if sos_bar is not None else None,
                       arm_src, swp_nm)
            self._prev_stage[slot] = stage

            if not m.watch:
                self._setup_ctx[slot] = None
                continue
            traded = self._same_leg(traded_sos, traded_sos_ms, m.sos_bar)
            if sos_bar is not None and not traded:
                # still alive — accumulate what it achieved
                m.fib = sig.fibo_p3
                if m.edge is None and edge is not None:
                    m.edge = edge
                # The two PRICE refusals, off this bar's own edge. Read here and not from
                # `_record_blocks` because that runs later in the bar, inside `_place_entries` —
                # and `b_leg` overrides that method, so a miss watch reading its output would
                # go quiet on a fork rather than fail.
                tight, quiet = self._price_blocks(sig, edge, is_long)
                if zone_hit:
                    m.visit(sig, is_long)
                    m.zone = True
                    m.fvg = m.fvg or edge is not None
                    m.blk_v = m.blk_v or veto
                    m.blk_l = m.blk_l or late
                    m.blk_h = m.blk_h or htf_any
                    m.blk_t = m.blk_t or tight
                    m.blk_q = m.blk_q or quiet
                # Reporting only, and captured AFTER the accumulate above — the block that sets
                # `m.zone` on the bar price first tags the band. Capturing before it reported a
                # setup as still waiting on a retrace on the very bar it got one, so the alert
                # said "2 of 3" beside a resting order that needed 3. It also has to be here
                # rather than in `live_setups()`, because this is the one place the per-side
                # gates are already resolved through the enable-toggles exactly as `_armed`
                # reads them — so "armed" means the same thing in an alert as in a decision.
                self._setup_ctx[slot] = self._setup_context(
                    sig, m, is_long, arm_swp, arm_div, veto, late, htf_any, tight, quiet)
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
                # Precedence matches `_block_codes` — toggles first, then the stop floor, then
                # the dead-market gate, and only then "the limit rested and nothing came".
                code = (4 if m.blk_v else 5 if m.blk_l else 6 if m.blk_h
                        else 8 if m.blk_t else 9 if m.blk_q else 7)
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
                leg_extreme=sig.fibo_p7, leg_origin=sig.fibo_p10,
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
        setup context.** `b_leg` and `bos` subclass this and both set it False, so they
        inherit a `live_setups()` that returns `[]` on every bar forever — a method-presence check
        would call them supported and the runner would announce "Setup alerts: ON" for a channel
        that can never send anything. **An empty registry answering confidently, arriving by
        inheritance rather than by a literal `{}`.**

        ⚠ **It is derived rather than a flag each fork must remember to set**, so a new subclass
        cannot acquire a silent, empty signals channel by forgetting one line.

        ⚠ **True here is NOT a claim that a fork's confluences are right.** A fork that turns the
        watch back on would report SOS Fade's three confluences, which describe a setup it does not
        trade. It needs its own `_setup_context` before its alerts go on.
        """
        return bool(self._records_misses)

    # A bar's NUMBER is local to one run; its TIME is not.
    #
    # 🔴 **2026-08-26, live.** The one-trade-per-leg latch stored the shift bar's NUMBER. A live
    # bot renumbers every bar each time it re-warms its history on restart, so a restored latch
    # holding 5059 was compared against the SAME leg now numbered 4953, saw no match, and let the
    # trade through. The bot re-entered a setup it had been scratched out of **three seconds
    # earlier** — same stop, same targets, same leg — at 0.53 lots.
    #
    # ⚠ **This repo already had the lesson written down, about a different tool.** `shadow_diff`
    # joins on bar TIMESTAMP and its docstring says why: *"the live index counts on from wherever
    # warm-up stopped and survives restarts."* The live path itself was still comparing numbers.
    # **A lesson recorded against one consumer is not a lesson applied to the others.**
    #
    # ⚠ **It is a NO-OP in any single continuous run** — one backtest, one Pine chart, one
    # uninterrupted live session — because within a run a number maps to exactly one time. The
    # two answers can only differ across a RESTART, which exists nowhere but live. That is why
    # the parity gate is unaffected, and it was RUN rather than reasoned about.
    _BAR_MS_KEEP = 20_000

    def _remember_bar(self, sig) -> None:
        """Record this bar's time against its number, so a leg can be identified by TIME."""
        ms = getattr(sig, "time_ms", None)
        if ms is None:
            return
        idx = sig.index
        if self._bar_ms_last is not None and idx <= self._bar_ms_last:
            # Out of order, so dict order no longer answers "which key is smallest". Latch it and
            # let the sort below carry the map for the rest of this object's life.
            self._bar_ms_ordered = False
        self._bar_ms_last = idx
        self._bar_ms[idx] = int(ms)
        if len(self._bar_ms) > self._BAR_MS_KEEP:
            # Keep the recent tail. A setup's shift bar is always inside the warm-up window, and
            # an unbounded dict on a bot that runs for weeks is a leak with no upside.
            #
            # 🔴 **PRUNE IN O(1) — RE-SORTING HERE COST ~5 MINUTES OF A FULL-HISTORY RUN.** The
            # first version sorted the whole 20,000-key map to delete ONE entry, and once the cap
            # is reached that happens on EVERY bar: MEASURED under cProfile on a 23,539-bar year,
            # 3,539 sorts were **8.0s of a 52.6s replay — 15%**, and the 6.6-year window pays it
            # 135,807 times. A dict preserves INSERTION order, one `step` inserts one strictly
            # increasing index, and the map is rebuilt empty on every restart — so the
            # earliest-inserted key IS the smallest key and `next(iter(...))` is the same answer
            # the sort was computing from scratch each bar.
            #
            # ⚠ **The equivalence is a fact about the ORDER keys arrive in, so it is CHECKED
            # rather than trusted** — `_bar_ms_ordered` latches False on any out-of-order insert
            # and the old sort takes over, which is correct whatever the order.
            #
            # ⚠ **Same keys survive, so no decision can move**, and that was proven on real bars
            # rather than argued: see `backtest/tools/replay_fingerprint.py`.
            if self._bar_ms_ordered:
                while len(self._bar_ms) > self._BAR_MS_KEEP:
                    del self._bar_ms[next(iter(self._bar_ms))]
            else:
                for k in sorted(self._bar_ms)[: len(self._bar_ms) - self._BAR_MS_KEEP]:
                    del self._bar_ms[k]

    def _same_leg(self, traded_bar, traded_ms, current_bar) -> bool:
        """Is `current_bar` the leg we have already traded?

        TIME decides whenever both sides have one; the bar NUMBER is the fallback for a leg whose
        time we never saw (a record written before this field existed, or a shift bar that fell
        off the tail above). ⚠ **The fallback is the OLD behaviour and is wrong across a restart**
        — it is kept because refusing to answer would silently disable the latch entirely, which
        is the same failure with fewer clues.
        """
        if current_bar is None:
            return False
        if traded_ms is not None:
            current_ms = self._bar_ms.get(current_bar)
            if current_ms is not None:
                return current_ms == traded_ms
        return traded_bar is not None and current_bar == traded_bar

    #: How `_setup_key` spells a key — read by the live alert layer, which cannot compare keys
    #: across a promote that changed the spelling. 🔴 **Change this string whenever the key format
    #: changes**; a promote from bar-number keys to these closed a live short's thread as lost on
    #: 2026-09-16 (`algos/live/setup_alerts.py::_key_scheme`).
    setup_key_scheme = "time-v1"

    def _setup_key(self, is_long: bool, sos_bar: Optional[int],
                   sos_ms: Optional[int]) -> str:
        """The thread id, stable for this setup's whole life AND across a restart.

        Keyed on the SOS bar rather than on anything that moves: the arm, the zone state and the
        entry price all change while a setup is alive, and a key built from any of them would
        start a new Telegram thread on the bar it changed. `_MissWatch` already treats
        `(side, sos_bar)` as this setup's identity — reusing it is what keeps the alert's notion
        of "the same setup" identical to the strategy's.

        🔴 **By TIME, with the bar number only as a fallback — the number is not stable and the
        old docstring claimed it was.** `sos_bar` is an offset into the warm-up window, so every
        restart and every mid-session re-warm renumbers it: measured on 2026-09-15, one live
        setup's number slid from 4958 to 4888 on `sos_fade_1` and from 5050 to 4980 on
        `sos_fade_2`, both by exactly 70 bars, which is the window sliding rather than new
        structure. Each slide renamed a setup that was still alive, so the alert layer saw a new
        setup, posted a second `SETUP FORMING` root, and permanently orphaned the first — four
        identical alerts for one setup inside 24 hours, none of which could ever be closed.
        This is the same defect `_same_leg` directly above already carries a time fallback for.

        ⚠ **The two forms are PREFIXED (`t` / `b`) so they cannot collide.** A timestamp and a
        bar index are both bare integers, and an unprefixed key could in principle name one
        setup by time and a different one by number and call them the same thread.

        ⚠ **The fallback still moves across a restart, and that is accepted rather than hidden.**
        It is only reached when the SOS bar fell off the tail of `_bar_ms` (20,000 bars), which
        is far older than any live setup; refusing to key it at all would silence the setup
        entirely, which is the same failure with fewer clues.
        """
        side = 'L' if is_long else 'S'
        anchor = f"t{sos_ms}" if sos_ms is not None else f"b{sos_bar}"
        return f"{self.strategy_name}:{side}:{anchor}"

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
                       veto: bool, late: bool, htf_any: bool, tight: bool,
                       quiet: bool) -> dict:
        """Freeze what this side's live setup looks like on this bar.

        ⚠ **`tight` / `quiet` carry NO DEFAULT, and that is deliberate.** A default of False
        would make a caller that forgot them indistinguishable from a setup nothing is refusing —
        a declared field standing in for a measured one, which is the failure this repo keeps
        paying for. There is exactly one caller; a second that forgets now fails loudly at the
        call rather than going quiet on a live rule.

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
            # 🔴 **The two PRICE refusals, added 2026-09-03 — until then they were the only
            # shipped rules that could skip a ready setup and send NOTHING.** Both are live on
            # `sos_fade_demo` (`exec_min_stop_mode` "% of price" 0.08, `exec_min_atr_pct`
            # 0.08), so this is not a hypothetical branch — it is the gap the reader was
            # actually experiencing as silence.
            if tight:
                blocked.append("Stop too tight for your minimum")
            if quiet:
                blocked.append("Market too quiet to fade")

        announce = self._announce_ready(sig, m.sos_bar, is_long)


        return {
            "key": self._setup_key(is_long, m.sos_bar, m.sos_ms),
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
        this PROCESS never built a snapshot for it.

        ⚠ **"This process was never told" stopped meaning "the reader was never told" on
        2026-09-16.** The alert layer now keeps its open threads on disk, so a setup announced
        before a restart still has a live Telegram thread when its death lands here with no ctx.
        That case is closed by `SetupAlerts.reconcile` at the end of the next warm-up instead —
        with a message that says the outcome was not recorded, because here there is genuinely
        nothing to report. Do not "fix" it by inventing a snapshot: a composed reason is a second
        explanation for one death, which is what this class is written to avoid.
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
                paused_by=() if resting else self._pull_why[slot],
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
        sh_hours = self._sh_hour_block(sig)

        # "Ready" omits every toggle gate — those ARE the blockers being reported. It asserts
        # only what price and the engine decide: the SOS is in, the fib agrees, an edge exists
        # to rest on, we're flat, and this leg has not already been traded.
        ready = (
            (seq.l_sos_bar is not None and sig.fibo_dir == 1 and long_edge is not None
             and self._pos_dir == 0
             and not self._same_leg(self._traded_sos_l, self._traded_sos_l_ms, seq.l_sos_bar)),
            (seq.s_sos_bar is not None and sig.fibo_dir == -1 and short_edge is not None
             and self._pos_dir == 0
             and not self._same_leg(self._traded_sos_s, self._traded_sos_s_ms, seq.s_sos_bar)),
        )
        # Both PRICE refusals happen at order placement; they are recomputed here so a setup
        # refused on price gets a record like every other refusal (Pine 4167-4172).
        # Per SIDE, not once: with `exec_sl_deep` on, the anchor depends on that side's own
        # entry edge (Pine 4264-4265 calls f_slAnchor twice for the same reason).
        tight_l, quiet_l = self._price_blocks(sig, long_edge, True)
        tight_s, quiet_s = self._price_blocks(sig, short_edge, False)

        codes = (
            _block_codes(not cfg.exec_longs, not arm_ok_l, late,
                         dec.long_veto and cfg.exec_respect_veto, htf_l, bias_l, tight_l,
                         sh_hours, self._too_deep(sig, long_edge, True), quiet_l,
                         self._entry_window_block(sig)),
            _block_codes(not cfg.exec_shorts, not arm_ok_s, late,
                         dec.short_veto and cfg.exec_respect_veto, htf_s, bias_s, tight_s,
                         sh_hours, self._too_deep(sig, short_edge, False), quiet_s,
                         self._entry_window_block(sig)),
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

    def _stamp_account_clock(self, sig) -> None:
        """Tell the account the current bar time — unless something else owns the clock.

        🔴 A shared stack's simulator sets `clock_external` and stamps ONE tick time across every
        leg, which is the only way a shared contention log can be read: two legs on different
        timeframes reporting their own bar opens would make the log disagree with itself about
        when a clash happened. This method must never overwrite that.

        ⚠ Everywhere else NOBODY was stamping it, so a standalone run — including every run the
        lab's own Run button makes — recorded each venue-ceiling clamp with a null time. That log
        is the only evidence a resized entry leaves: the trade list and the equity curve are
        identical either way, because R is profit over risk and both scale with quantity.
        """
        if getattr(self._account, "clock_external", False):
            return
        ms = getattr(sig, "time_ms", None)
        if ms is not None:
            self._account.now = int(ms)

    def _pv(self) -> float:
        """The quote-to-account conversion for the bar being processed RIGHT NOW.

        🔴 **WHY THIS IS A METHOD AND NOT `cfg.point_value`.** For a USD-quoted instrument the
        factor is 1.0 forever and a constant is correct. For anything else it is an EXCHANGE RATE,
        and a rate is not a constant: USDJPY ran roughly 100 to 160 across a window this strategy
        would replay, so pricing six years of trades at one reading is wrong by up to 60% at the
        ends - in sizing, which divides by it, and in every cost, which multiplies by it.

        Each call site reads it at ITS OWN moment, which is what makes the model right rather
        than merely variable: sizing converts at the entry, a fill converts when it fills, swap
        converts at the rollover it is charged for. That is what a broker actually does.

        ⚠ **With no provider installed this returns `cfg.point_value` and the class is
        byte-identical** - which is how this landed without moving a single stored result. The
        provider is opt-in per run, never a default, because a run that silently started
        converting would re-price every historical comparison.

        ⚠ **A provider must never return 0 or a negative.** Sizing divides by it, so a zero rate
        is an infinite position. This returns the configured constant rather than pass a bad rate
        on, and `_qty_for_risk` refuses a non-positive denominator behind it.
        """
        pv = self._pv_now
        if pv is None or pv <= 0:
            return self._cfg.point_value
        return pv

    def set_rate_provider(self, fn) -> None:
        """Install a `time_ms -> rate` callable, or None to go back to the constant.

        Opt-in per run - see `_pv`. Asked once per BAR rather than once per read, so a single bar
        cannot price two of its own fills at two different rates.
        """
        self._rate_provider = fn

    def _qty_for_risk(self, risk_pct: float, dist: float) -> float:
        """Units to put `risk_pct` of equity behind a stop `dist` away, in PRICE terms.

        🔴 **`point_value` IS THE CONVERSION AND LEAVING IT OUT COSTS REAL MONEY.** `dist` is a
        price distance, so it is in the SYMBOL'S quote currency; `equity` is in the ACCOUNT'S.
        Dividing one by the other only lands on a tradeable size when the two currencies are the
        same AND one unit moves one currency unit per 1.0 of price — which is exactly gold, at
        `point_value = 1.0`.

        The four sizing sites used to divide by `dist` alone. Risk is then booked as
        `qty * dist * point_value` (`_finalise_trade`), so the dollars actually at stake were the
        intended risk MULTIPLIED by `point_value`. At 1.0 the two agree, which is why six years
        of gold runs never showed it. On any instrument whose `point_value` is not 1.0 every
        trade is mis-sized by that factor.

        ⚠ **R never noticed, which is how this survived.** P&L is
        `(exit-entry) * dir * qty * point_value` and risk is `qty * dist * point_value`, so both
        terms cancel in the ratio and R is algebraically immune. Every R figure in this repo
        stays good; dollars, lots, dollar drawdown and per-lot costs did not.

        ⚠ **`algos/shared/order_sizing.py` has always done this correctly** — it sizes off the
        broker's own tick value, which is already in the account's currency. The live bot and the
        lab therefore disagreed on any non-USD-quoted symbol, in the one number that decides how
        much money is at risk. This closes that gap from the lab's side.

        Returns 0.0 rather than raising when the denominator is not positive: a zero size places
        nothing, and every caller already treats 0 as "no room".
        """
        denom = dist * self._pv()
        if denom <= 0:
            return 0.0
        return (self.equity * risk_pct / 100.0) / denom

    def _fit_to_budget(self, qty: float, entry: float, stop: float) -> float:
        """Shrink a size to what the ACCOUNT can still afford. 0.0 = place nothing.

        🔴 **At PLACEMENT, which is the entire point.** The account has always had a budget gate,
        but it ran at the FILL — right for a shared backtest, wrong for a live bot, where the
        order is already resting at the broker by then and shrinking the emulator's copy leaves
        the two holding different books. Sizing here means the order that reaches the broker is
        already the size the strategy believes it holds, so both sides book the same quantity.
        This is the same reasoning the venue lot ceiling is applied under: clamp at the DECISION,
        never at the order.

        ⚠ **Inert unless something states a budget.** A solo run's account has infinite room, so
        this returns the desired size untouched and no stored result — or parity gate — moves.
        """
        return self._account.affordable_qty(
            self._leg, entry, stop, self._pv(), qty)

    # ── entry placement (Pine 4264-4507) ─────────────────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        long_armed, short_armed = self._armed(sig, seq, dec, long_edge, short_edge)
        self._record_blocks(sig, seq, dec, long_edge, short_edge)

        # deliberate deviation: no NEW entry inside the flat-by-close window (real runs)
        flat_window = self._flat_due(sig)
        if flat_window:
            long_armed = short_armed = False
        # Reporting only: which named rule kept each side off the book. Read off the gates
        # `_armed` just decided with, so it cannot describe a rule that did not act.
        self._pull_why = [
            self._gate_reasons(sig, dec, True, long_armed, flat_window),
            self._gate_reasons(sig, dec, False, short_armed, flat_window),
        ]

        # One snapshot for both sides — they read the same live fib, and taking it once is what
        # guarantees a long and a short placed on this bar report the identical leg.
        fib = _freeze_fib(sig) if (long_armed or short_armed) else None

        if long_armed:
            sl = self._sl_anchor(sig, long_edge, True) - cfg.exec_sl_buf_tk * cfg.mintick
            dist = long_edge - sl
            deep = long_edge <= sig.fibo_p3       # at/below 0.618
            tp1, tp2 = self._ladder_levels(sig, deep, long_edge, 1)
            if self._stop_clears_floor(dist, long_edge) \
                    and not self._too_deep(sig, long_edge, True):
                qty = self._qty_for_risk(cfg.exec_risk_pct, dist)
                qty = self._fit_to_budget(qty, long_edge, sl)
                if qty <= 0:
                    self._pull_why[0] = (_PULL_NO_ROOM,)
                self._pend_long = _Pending(
                    1, long_edge, qty, sl, tp1, tp2, seq.l_sos_bar, fib) if qty > 0 else None
            else:
                self._pend_long = None
                self._pull_why[0] = self._price_reasons(sig, long_edge, True)
        else:
            self._pend_long = None

        if short_armed:
            sl = self._sl_anchor(sig, short_edge, False) + cfg.exec_sl_buf_tk * cfg.mintick
            dist = sl - short_edge
            deep = short_edge >= sig.fibo_p3
            tp1, tp2 = self._ladder_levels(sig, deep, short_edge, -1)
            if self._stop_clears_floor(dist, short_edge) \
                    and not self._too_deep(sig, short_edge, False):
                qty = self._qty_for_risk(cfg.exec_risk_pct, dist)
                qty = self._fit_to_budget(qty, short_edge, sl)
                if qty <= 0:
                    self._pull_why[1] = (_PULL_NO_ROOM,)
                self._pend_short = _Pending(
                    -1, short_edge, qty, sl, tp1, tp2, seq.s_sos_bar, fib) if qty > 0 else None
            else:
                self._pend_short = None
                self._pull_why[1] = self._price_reasons(sig, short_edge, False)
        else:
            self._pend_short = None


    def _gate_reasons(self, sig, dec, is_long: bool, armed: bool,
                      flat_window: bool) -> Tuple[str, ...]:
        """The named rules that kept one side UNARMED this bar — reporting only.

        ⚠ **Only rules a reader can act on or wait out.** A setup with no edge (nothing to rest a
        limit on), an arm source switched off, a wrong-way fib or an already-traded leg is not a
        pause, so it names nothing and the thread stays silent — the setup is either not ready
        or already over.
        """
        if armed or self._blk_gates is None:
            return ()
        cfg = self._cfg
        late, arm_ok_l, arm_ok_s, htf_l, htf_s, bias_l, bias_s = self._blk_gates
        if not (arm_ok_l if is_long else arm_ok_s):
            return ()
        veto = (dec.long_veto if is_long else dec.short_veto) and cfg.exec_respect_veto
        out = []
        if veto:
            out.append(_PULL_VETO)
        if late:
            out.append(_PULL_LATE)
        if self._sh_hour_block(sig):
            out.append(_PULL_SH_HOURS)
        if self._entry_window_block(sig):
            out.append(_PULL_ENTRY_WINDOW)
        if (htf_l or bias_l) if is_long else (htf_s or bias_s):
            out.append(_PULL_HTF)
        if flat_window:
            out.append(_PULL_FLAT)
        return tuple(out)

    def _price_reasons(self, sig, edge, is_long: bool) -> Tuple[str, ...]:
        """Why an ARMED side still placed nothing — the same helpers placement just asked."""
        tight, quiet = self._price_blocks(sig, edge, is_long)
        out = []
        if tight:
            out.append(_PULL_TIGHT)
        if quiet:
            out.append(_PULL_QUIET)
        if self._too_deep(sig, edge, is_long):
            out.append(_PULL_DEEP)
        return tuple(out)

    def _too_deep(self, sig, edge: Optional[float], is_long: bool) -> bool:
        """Would this limit rest deeper into the retrace than the short-hold variant allows?

        REFUSES rather than re-pricing, and that is deliberate. Moving the limit shallower would
        keep the setup and change the trade: the stop stays pinned at its fib, so a shallower
        entry is a WIDER stop, a different 1R and a different position size — a different trade
        wearing this one's name. The entry model already has three settings for moving a limit
        (they cascade in `_fib_snap`); this one is about not taking the trade.

        The cap is read as a fib RATIO through the canonical geometry, against the same leg
        anchors the stop is priced off, so "deeper than 0.702" means the same thing on a $3 leg
        and a $30 one. Unknown geometry reads as NOT too deep — an unpriced fib must not become a
        silent refusal, which is the shape that makes a filter look like a broken engine.
        """
        cfg = self._cfg
        if not cfg.exec_short_hold or edge is None:
            return False
        if sig.fibo_ash is None or sig.fibo_asl is None or not sig.fibo_dir:
            return False
        cap = fib_level(sig.fibo_ash, sig.fibo_asl, sig.fibo_dir, cfg.exec_sh_max_depth)
        return edge < cap if is_long else edge > cap

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
        """Pine `f_fibEntry` (2026-08-02; named `_fib_snap` here because `bos` already
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
            self._poi_last_l = None
            self._cmd_watch_l = None
        if seq.s_sos_bar != self._gap_seen_sos_s:
            self._gap_seen_sos_s, self._gap_seen_s = seq.s_sos_bar, False
            self._poi_last_s = None
            self._cmd_watch_s = None

    def _check_cmd_watch(self, sig, seq) -> None:
        """Price reached the first target of a trade a PERSON closed early — open the re-entry's
        breakeven door, exactly as holding that trade would have.

        Runs every bar, before the entry edges, so the door is open on the same bar a re-entry
        could first rest on it. Reads the bar's HIGH for a long and its LOW for a short: the same
        touch test the trade's own TP1 uses, so the watch cannot open a door the trade itself
        would not have.

        ⚠ Keyed on the SOS bar the watch was set for, and compared against the CURRENT setup —
        a stale watch can never stamp a leg that has since broken again. `_sync_gap_latch` has
        already cleared it in that case; this test is the second lock, because the cost of
        getting it wrong is a re-entry on a setup nobody is watching.
        """
        watch = self._cmd_watch_l
        if (watch is not None and self._same_leg(watch[0], watch[1], seq.l_sos_bar)
                and sig.high >= watch[2]):
            self._be_sos_l = seq.l_sos_bar
            self._cmd_watch_l = None
        watch = self._cmd_watch_s
        if (watch is not None and self._same_leg(watch[0], watch[1], seq.s_sos_bar)
                and sig.low <= watch[2]):
            self._be_sos_s = seq.s_sos_bar
            self._cmd_watch_s = None

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

    def _market_has_range(self, edge: float) -> bool:
        """`exec_min_atr_pct` — is the market moving enough for a fade to have anywhere to go?

        A DIFFERENT question from the minimum-stop floor, which asks whether the leg is long
        enough to size against. A dead market produces wide stops as happily as tight ones, so
        that floor does not catch this and never could.

        ⚠ Pine's `f_marketHasRange`, and the port is deliberately line-for-line: off returns True
        for every bar, an unseeded ATR returns False, and the comparison is `>=`. Both sides
        default OFF, so `compare_strategy.py` sees exactly the decisions it always did.
        ⚠ Pine gates the 15m setup path ONLY, because that is the only entry path Pine has. The
        re-entry below is Python-only and is gated here with nothing to compare it against.
        ⚠ Reads `self._atr`, the FIFTEEN-minute ATR(14), on both entry paths — the setup is a 15m
        setup whichever timeframe fills it.
        ⚠ An unseeded ATR REFUSES rather than passes. The first 14 bars of a run cannot answer
        "is the market quiet", and a gate that waves through what it could not measure is the
        defect this repo keeps re-learning — never let "no" and "cannot ask" be the same value.
        """
        pct = getattr(self._cfg, "exec_min_atr_pct", 0.0)
        if pct <= 0:
            return True                        # off - the gate does not exist
        if self._atr is None or edge <= 0:
            return False                       # cannot ask -> refuse, never pass
        return (self._atr / edge) * 100.0 >= pct

    def _stop_clears_floor(self, dist: float, edge: float) -> bool:
        """Pine's `slDist > 0 and slDist >= f_minStopFloor(edge)`, with NA reading as false.

        ⚠ The dead-market gate rides HERE rather than at the call sites, because there are two
        of them — the 15m setup path and the re-entry's own fill clock — and a filter that guards
        one entry path is how a setup the strategy means to refuse gets in through the other door.
        ⚠ The re-entry fill clock is `exec_sec_fill_tf_min`, a MEASUREMENT knob that defaults to
        5 minutes; do not name a timeframe here, because the gate must hold whatever it is set to."""
        if dist <= 0:
            return False
        if not self._market_has_range(edge):
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

    def _price_blocks(self, sig, edge: Optional[float], is_long: bool) -> Tuple[bool, bool]:
        """The two refusals that depend on PRICE rather than on a toggle: `(tight, quiet)`.

        REPORTING ONLY — nothing here places, prices or cancels anything. It asks the SAME two
        helpers the placement path asks, with the same edge, so a message can never describe a
        refusal the strategy did not make. One implementation, three readers (the blocked-setup
        record, the miss record and the Telegram setup snapshot); a second copy of either rule is
        exactly how two claims about one setup end up disagreeing.

        ⚠ **No edge means NEITHER rule has been reached, so both answer False and the caller
        reports nothing.** That is *not applicable*, not *passed* — with nothing to rest a limit
        on, the setup is stopped a step earlier and by something else.

        ⚠ **An unseeded ATR refuses the entry WITHOUT being reportable as a quiet market**, which
        is the convention `_stop_is_tight` already follows for a missing floor. "Cannot measure
        the range yet" and "the range is too small" are different sentences, and only the second
        one is true in those words. Unreachable for a setup that has reached all three
        confluences — that takes far more than the 14 bars the ATR needs — and written this way
        so it stays honest if that ever stops being true.
        """
        if edge is None:
            return False, False
        quiet = self._atr is not None and not self._market_has_range(edge)
        anchor = self._sl_anchor(sig, edge, is_long)
        if anchor is None:
            # A missing fib leaves the anchor unknown, which reads as "not tight" — the same way
            # na propagates through the Pine's comparison.
            return False, quiet
        buf = self._cfg.exec_sl_buf_tk * self._cfg.mintick
        dist = (edge - (anchor - buf)) if is_long else ((anchor + buf) - edge)
        return self._stop_is_tight(dist, edge), quiet

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
            self._leg, pend.dir, fill_price, pend.sl, pend.qty, self._pv())
        if granted <= 0.0:
            # refused (no room / below floor): don't open, drop this order, let the strategy
            # re-arm next bar if the setup still holds. No traded-SOS latch is set (see below).
            if kind == "secondary":
                self._pend_sec = None
            elif pend.dir > 0:
                self._pend_long = None
                self._pull_why[0] = (_PULL_NO_ROOM,)
            else:
                self._pend_short = None
                self._pull_why[1] = (_PULL_NO_ROOM,)
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
        # 🔴 **THE FIRST RUNG'S PRICE IS COMPUTED BY `_first_rung`, WHICH IS ALSO WHAT THE LIVE
        # BRIDGE ASKS BEFORE THE ORDER IS SENT.** It used to be written out here and nowhere
        # else; the bridge now needs the same answer for an order that has NOT filled yet, and a
        # second copy of this arithmetic in the live layer is the exact shape this repo keeps
        # paying for. One function, two callers, one rule.
        self._tp1 = self._first_rung(
            dir_=pend.dir, entry=fill_price, stop=pend.sl, kind=kind,
            src=pend.src, fib_tp1=pend.tp1,
        )
        self._tp2 = pend.tp2
        # ⚠ **`src` and not just `kind`.** The two overrides below are the RE-ENTRY's, named
        # `exec_sec_*`, and a level-memory trade only carries `kind="secondary"` because it
        # borrows that order path. Letting them reach it would re-price a rung Run 42 graded,
        # off settings that describe a different trade.
        if kind == "secondary" and pend.src != LVL_SRC:
            # `exec_sec_tp2_x` — REPLACE the second rung with a multiple of the FIRST one's
            # distance, so a re-entry's two targets are in order by construction. Off by default.
            # ⚠ Unlike the floor below, this overrides the fib in BOTH directions: it pulls IN a
            # rung that extended as well as pushing out one that landed inside. That is the whole
            # difference between the two, and the reason both exist.
            # ⚠ Measured off `self._tp1` AFTER the block above, not off `tp_r`, so it holds for the
            # -1 case too, where the first rung is the fib and the multiple is of that distance.
            tp2_x = getattr(self._cfg, "exec_sec_tp2_x", -1.0)
            if tp2_x > 0:
                dx = 1 if pend.dir > 0 else -1
                t1_dist_x = (self._tp1 - fill_price) * dx
                if t1_dist_x > 0:
                    self._tp2 = fill_price + dx * tp2_x * t1_dist_x
            # `exec_sec_tp2_min_x` — the second rung may not sit NEARER than a multiple of the
            # first one's distance. The two are priced by different rulers (risk vs the frozen 15m
            # fib), so nothing otherwise keeps them in order: 36 of 93 re-entries on run
            # `cab44579d74b` came out with the second rung inside the first. Off by default.
            #
            # ⚠ It can only ever push a rung AWAY from the entry — the fib wins whenever it is
            # already further out, because a structure level that has extended carries information
            # a multiple of risk does not.
            # ⚠ Measured off `self._tp1` AFTER the block above, not off `tp_r`, so it holds for the
            # -1 case too, where the first rung is the fib and the multiple is of that distance.
            min_x = getattr(self._cfg, "exec_sec_tp2_min_x", -1.0)
            if min_x > 0:
                d2 = 1 if pend.dir > 0 else -1
                t1_dist = (self._tp1 - fill_price) * d2
                if t1_dist > 0:
                    floor_px = fill_price + d2 * min_x * t1_dist
                    if (self._tp2 - floor_px) * d2 < 0:
                        self._tp2 = floor_px
        # The ladder those three came off, carried through to the closed Trade (reporting only).
        # Taken from the ORDER, not from `sig`: the fib is a live thing that keeps extending, so
        # reading it again at the fill would report a leg the resting limit was never priced on.
        self._fib = pend.fib
        self._stage = 0
        self._gave_back = False
        self._pending_bank = 0.0
        self._rev_done = False
        self._pending_rev = None
        self._rev_best = None
        self._rev_levels = []
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
        self._brk_ext = None
        self._brk_bounce = False
        self._brk_count = 0
        self._brk_used = False
        self._brk_nadds = 0
        self._sos_bar_open = pend.sos_bar
        self._risk_usd = abs(granted) * abs(fill_price - pend.sl) * self._pv()
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
        self._rec_be_armed = False
        self._exc_be_armed = False
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
        # a shift leg, not the 15m SOS Fade leg — so only a primary sets it.
        if kind == "primary":
            # The leg's TIME is recorded beside its number. The number is what a single run
            # compares on; the time is what survives the re-warm a restart performs. See
            # `_same_leg` for the incident that made the difference matter.
            sos_ms = self._bar_ms.get(pend.sos_bar) if pend.sos_bar is not None else None
            if pend.dir > 0:
                self._traded_sos_l, self._traded_sos_l_ms = pend.sos_bar, sos_ms
            else:
                self._traded_sos_s, self._traded_sos_s_ms = pend.sos_bar, sos_ms
        self._pend_long = self._pend_short = self._pend_sec = None
        side = "Long" if pend.dir > 0 else "Short"
        dec.fills.append(Fill("entry", side, fill_price, granted, pend.dir))
        # ⚠ The QUANTITY is `granted`, never `pend.qty`: the account has already sized this and
        # may have shrunk it, and the instruction that reaches a venue must be the size actually
        # taken. Asking for the desired size here would put a number on the wire that the
        # account already refused.
        dec.intents.append(OrderIntent(
            kind=IntentKind.OPEN, direction=pend.dir, qty=granted,
            price=fill_price, stop=pend.sl, reason=side,
        ))
        return True

    # ── open-trade management (Phase A exits + Phase B staging) ───────────────────
    def _manage_open(self, sig, dec) -> None:
        # Excursion (reporting only): widen the hold's high/low before this bar's exits resolve,
        # so the closing bar's extreme counts too. Never read by a decision. Shifted onto the ASK
        # for a short, so the reported best and worst prices are ones its exits could have got.
        adj = self._exit_adj()
        self._ext_high, self._ext_low = self._widen_hold(sig, adj)
        self._widen_add_excursions(sig, adj)
        if self._resolver is not None:
            return self._manage_open_ticks(sig, dec)
        return self._manage_open_bar(sig, dec)

    def _widen_hold(self, sig, adj) -> Tuple[float, float]:
        """This bar's contribution to the hold's high/low, CLAMPED on the adverse side.

        🔴 THE ADVERSE EXTREME CANNOT BE WORSE THAN THE PRICE THE STOP WOULD HAVE CLOSED AT. The
        widen runs before this bar's exits resolve, so it used to take the bar's whole range — and
        on the bar that stops the trade out, the far end of that range is price AFTER the position
        is flat. It is not an intrabar-ordering guess: the stop is triggered BY the adverse move,
        so anything past it necessarily happened at or after the fill.

        MEASURED on run `976aff9ec279` (206 trades) before this: **77 of 77 trades that exited at
        their stop recorded a deepest adverse price beyond it** — median 0.18R past, worst 4.41R.
        One short lost exactly 1.0R and reported 2.22R of adverse excursion, and the chart drew its
        drawdown marker above its own stop line, which is what made somebody ask.

        ⚠ The bound is the stop, EXCEPT on a bar that opens already past it — there the stop fills
        at the open (`_fill_price`), worse than the stop, and that fill is real. `min`/`max` against
        the open covers both without asking which happened.

        ⚠ The FAVOURABLE side is deliberately untouched. A target is partial here: TP1 banks a
        portion and the runner stays open, so price beyond a target is still the trade's move. Only
        the stop closes everything, which is what makes this side determinate and that one not.

        ⚠ Reporting only, like everything it feeds — no decision reads `_ext_high`/`_ext_low`, so
        the decision stream cannot move. Proven rather than argued: `compare_strategy.py` exit 0.
        """
        stop = self._current_stop()
        hi, lo = sig.high + adj, sig.low + adj
        if self._pos_dir > 0:
            lo = max(lo, min(stop, sig.open + adj))
        else:
            hi = min(hi, max(stop, sig.open + adj))
        return max(self._ext_high, hi), min(self._ext_low, lo)

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
        d, pv = self._pos_dir, self._pv()
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
        dec.intents.append(OrderIntent(
            kind=IntentKind.CLOSE_PORTION, direction=d, qty=closed, price=price, reason=oid,
        ))
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
        pnl = (price - self._entry) * d * qty * self._pv()
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
                lot_pnl = (price - lot[0]) * d * closing * self._pv()
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
        dec.intents.append(OrderIntent(
            kind=IntentKind.CLOSE_PORTION, direction=d, qty=qty, price=price, reason=oid,
        ))
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
        d, pv = self._pos_dir, self._pv()
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
        # ⚠ **A LEVEL-MEMORY TRADE IS NOT ON A 15m LEG, SO IT MAY NOT KILL ONE.** It carries
        # `kind="secondary"` because it uses the re-entry's order path, and without this
        # guard its stop-out would retire a re-entry leg it has nothing to do with — the two
        # features are only ever on together by choice, and that is when it would bite.
        if (self._entry_kind == "secondary" and self._stage == 0
                and self._entry_src != LVL_SRC):
            self._sec_stop_dir = self._pos_dir
        # The PRIMARY's own record on this leg, for the looser `exec_sec_require` gates. `_stage`
        # is still the trade's final stage here (it is reset a few lines below), so stage 0 means
        # "closed without ever touching TP1" — a stop-out or a time stop, which is exactly the
        # state the breakeven gate refuses.
        # 🔴 A CLOSE A PERSON ASKED FOR IS NOT A STOP-OUT, AND CALLING IT ONE ARMS THE WRONG
        # RE-ENTRY. `-CMD` is the tag every commanded exit carries, including the hand close the
        # bridge adopts (`algos/live/bridge.py`, `closed_by_you`). Before 2026-09-22 such a close
        # at stage 0 stamped `_prim_lost_sos_*`, so the RECLAIM half — built and measured for
        # primaries the market stopped at the deep edge — would arm on a trade the owner simply
        # ended, at a price nothing was stopped at. The setup is still recorded as CLOSED, which
        # is true and is what the looser "Any close" door reads.
        by_request = str(self._exit_reason or "").endswith("-CMD")
        if self._entry_kind == "primary":
            # The level memory's input: what this trade entered at, what it risked, and when
            # it ended. Recorded for EVERY primary whatever it did — Run 42 graded the
            # returns by outcome and winners, scratches and stop-outs all came back positive,
            # so filtering on the outcome here would be a filter nothing measured.
            _lvl_dist = abs(self._entry - self._init_stop)
            if _lvl_dist > 0:
                _lvl_rec = (float(self._entry), float(_lvl_dist), int(self._exit_ms))
                if d > 0:
                    self._lvl_last_l = _lvl_rec
                else:
                    self._lvl_last_s = _lvl_rec
            if d > 0:
                self._prim_closed_sos_l = self._sos_bar_open
                if self._stage == 0 and not by_request:
                    self._prim_lost_sos_l = self._sos_bar_open
            else:
                self._prim_closed_sos_s = self._sos_bar_open
                if self._stage == 0 and not by_request:
                    self._prim_lost_sos_s = self._sos_bar_open
            # 🔴 KEEP WATCHING THE SETUP THE PERSON STEPPED OUT OF. Aaron, 2026-09-22: *"if I
            # manually close a trade and price comes back to entry"* — the re-entry's door is
            # opened by the primary REACHING ITS FIRST TARGET, and a hand close stops the bot
            # following the trade, so a target price reached an hour later was never seen and the
            # door never opened. The watch asks the question the trade would have asked if it had
            # been left alone: did price reach THIS trade's own first target while the setup
            # lived? Nothing else about the re-entry changes — the same preconditions, the same
            # entry price, the same stop.
            # ⚠ Only from stage 0. A trade that had already reached TP1 stamped the door open
            # before the person closed it, so there is nothing left to watch.
            # ⚠ It opens a door price actually reached; it never invents one. If price never gets
            # there the watch simply expires with the setup.
            # ⚠ The leg is identified by TIME as well as by bar number, and the time is the half
            # that survives a restart — a bar number belongs to one run's numbering. Same pair,
            # same reason, as `_traded_sos_l_ms`; `_same_leg` is the one reader of both.
            if by_request and self._stage == 0 and self._tp1:
                sos_ms = (self._bar_ms.get(self._sos_bar_open)
                          if self._sos_bar_open is not None else None)
                if d > 0:
                    self._cmd_watch_l = (self._sos_bar_open, sos_ms, float(self._tp1))
                else:
                    self._cmd_watch_s = (self._sos_bar_open, sos_ms, float(self._tp1))
        self._account.close_position(self._leg)   # P&L already booked; free the reservation
        self._pos_dir = 0
        self._qty = 0.0
        self._filled_qty = 0.0
        self._last_asked_stop = None   # a new trade's first stop is a real instruction
        self._stage = 0
        self._gave_back = False
        self._pending_bank = 0.0
        self._rev_done = False
        self._pending_rev = None
        self._rev_best = None
        self._rev_levels = []
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
        self._brk_ext = None
        self._brk_bounce = False
        self._brk_count = 0
        self._brk_used = False
        self._brk_nadds = 0
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
        self._charge(-(s / 2.0) * abs(qty) * self._pv())

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
        self._charge(-(ticks * cfg.mintick * abs(qty) * self._pv()))

    def _charge_swap(self, sig) -> None:
        """Charge financing for every rollover this bar crosses while a position is open.

        Fires at most once per rollover (`_last_roll_ms` latches it), so a bar that spans the
        boundary cannot double-book — the same edge-vs-level distinction that caused the sweep
        double-count bug in signals.py. Swap is why holding matters: it hits longs and shorts in
        OPPOSITE directions, so omitting it flatters every long and understates every short.

        🔴 **SCALE-IN LOTS ARE FINANCED TOO, and they were free until 2026-09-07.** A broker
        finances the POSITION, not the order that opened it, so a lot bought on the way up costs
        exactly what the base costs to carry through the same night. This billed
        `_qty - _filled_qty` — the base alone — so every add rode overnight for nothing, and a
        scaled trade held for days was under-charged in every stored run. It was invisible for as
        long as it existed because scale-in shipped OFF; the default moved on 2026-09-06.

        ⚠ **`_adds` is the live ledger and a spent lot is ZEROED IN PLACE** (`_bank_adds`), so
        summing `lot[1]` is the quantity still open and a banked lot contributes nothing. Reading
        `_add_lots` instead would finance lots that had already been sold.

        ⚠ **The base's own timing is inherited rather than re-decided.** This runs before this
        bar's fills and before its exits, so a lot bought THIS bar pays nothing for the night it
        was not yet held, and a lot sold this bar pays for the night it was — which is the same
        rule `_qty - _filled_qty` already applies to the base.
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
        remaining = self._qty - self._filled_qty + sum(lot[1] for lot in self._adds)
        # `point_value` converts the broker's quote-currency swap into the account's. It is
        # 1.0 for gold, so this is inert there; see AccountProfile.swap_charge.
        self._charge(self._profile.swap_charge(
            self._pos_dir, remaining, roll_date, self._pv()))

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
        # THE PRE-RUNG STOP RULE, and there is exactly one of it per trade — `_protect_rule()`
        # hands back the pair belonging to the entry method that opened this position. It used to
        # be two independent latches racing to answer the same question, which is what let a
        # reclaim's stop RETREAT; the resolver's docstring carries the measurement.
        #
        # 🔴 IT EXISTS BECAUSE THE STOP HAS ONE TRIGGER AND IT IS A TARGET TOUCH. A trade can run a
        # full R in profit and, as far as the stop is concerned, nothing has happened. MEASURED on
        # the re-entry short of 2020-11-04 (run `ed21fca08a91`): best price 1.016R in profit,
        # nearest rung at 1.25R, the stop never left its entry level, full loss. Off on every
        # method by default.
        # ⚠ Measured against `_sl`, the FROZEN entry stop, so "1R" keeps meaning the risk the trade
        # was SIZED against. Reading the managed stop would shrink the trigger as the stop ratchets.
        # 🔴 LATCHED IN A FLAG rather than recomputed from `_max_fav` on each read. `_max_fav` is
        # monotonic while a trade runs, but it is also RESTORED state, and this file already warns
        # that a blank one un-ratchets the trail. A stop that can un-ratchet is a trade that can
        # lose after it was protected — so the fact is stored once and `_POSITION_FIELDS` carries it.
        arm_r, _ = self._protect_rule()
        if not self._exc_be_armed and arm_r > 0:
            risk = abs(self._entry - self._sl)
            if risk > 0 and (self._max_fav - self._entry) * d >= arm_r * risk:
                self._exc_be_armed = True
                # ⚠ `_rec_be_armed` is no longer READ by anything — the single latch above is the
                # decision. It is still written, and only for a reclaim, so that a live bot rolled
                # BACK onto the previous deployment restores a record that version understands and
                # computes the same stop from. `_POSITION_FIELDS` refuses a record with a missing
                # field, so dropping it here would make this version's snapshots unrestorable by
                # the one before it — and `promote.py` refuses exactly that.
                if self._entry_src == "reclaim":
                    self._rec_be_armed = True
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

    def _locked_at_stop(self, stop: float) -> float:
        """The profit the shared stop already guarantees on the WHOLE position, in currency.

        🔴 **THIS IS THE WHOLE POSITION, AND THAT IS THE FIX.** It used to read the BASE lot
        alone (`(stop - entry) * base_qty`), which makes the affordability rule below exact for
        the FIRST add and wrong for every one after it: each new add pledged the base's locked
        profit again, while the lots already bought — the ones furthest from the stop, because
        scale-ins only fill as price runs — were invisible to the arithmetic meant to protect
        them. The promise on the tin ("an add can shrink a winner, it cannot manufacture a
        loser") therefore held at one add and was spent twice at two.

        MEASURED on the trade that found it, `sos_fade_1` 2026-09-22, short 0.37L @ 4369.93:
        add 1 (0.17L @ 4320.58) and add 2 (0.10L @ 4300.90) both sized against the base's ~$486,
        both stopped at 4356.86. Base +$483, adds −$617 and −$560, **net −$690 on a trade that
        was +$2,890 open**. When add 2 was sized, add 1 was already $634 under the shared stop
        and nothing looked at it.

        ⚠ **Signed, deliberately.** A lot already in profit at the stop ADDS to the guarantee and
        may fund a larger add; a lot underwater SUBTRACTS and shrinks or refuses the next one.
        Both directions are the same statement — worst case at the stop is flat.

        🔴 **THE BASE TERM IS DELIBERATELY UNCHANGED, AT THE SIZE THE TRADE OPENED WITH.** A
        rung that banks part of the base banks it AT THAT RUNG'S PRICE, and the stage-2 stop floor
        IS that rung's price on the shipped ladder — so `(stop - entry) * base_qty` is still the
        base's guaranteed profit whether it banked early or not. Reading the REMAINING base
        instead was tried and REVERTED the same hour: it made a trade that banks half at the first
        target buy a smaller add than an identical trade that banks nothing, which breaks the
        invariant `test_a_tp_rung_does_not_slice_the_adds` exists to hold — banking at a price and
        stopping at that same price are the same thing. Only the ADDS were ever unaccounted for,
        and only the adds are added here.

        ⚠ **`exec_scale_cap_x` multiplies `_base_qty` and is not part of this sum** — the cap is a
        statement about the size the trade opened with.

        ⚠ Mirrors `sos_fade_strategy.pine`, which sums the same two things: `lBaseQty` off the
        entry, then every OPEN trade whose id names it an add. The two must move together or the
        parity gate is measuring a strategy neither side runs.
        """
        d, pv = self._pos_dir, self._pv()
        locked = (stop - self._entry) * d * self._base_qty * pv
        for px, qty in self._adds:
            if qty > 1e-12:
                locked += (stop - px) * d * qty * pv
        return locked

    def observe_fast_breaks(self, ts_ms: int, breaks, direction: int = 0) -> None:
        """Buffer one fast bar's INTERNAL breaks for the "1m break" scale-in. Called by the dual
        clock on EVERY fast bar; a no-op unless that mode is on and a position is open."""
        cfg = self._cfg
        if (not breaks or self._pos_dir == 0 or not getattr(cfg, "exec_scale_in", False)
                or getattr(cfg, "exec_scale_mode", "Trail") != "1m break"):
            return
        for d, kind in breaks:
            self._fast_breaks.append((int(ts_ms), int(d), kind, int(direction or 0)))

    def _place_break_add(self, sig) -> None:
        """PLACE a "1m break" add: after a bounce against the trade, the SECOND 1-minute internal
        break back in its direction. Market, sized at this 15m close, filled at the next open.

        The rule, in the direction frame (a short's prices negated), from the second target on:

        * the best price since the second target is tracked; a NEW best starts a new push and
          re-arms — one add per push;
        * a 1m internal break AGAINST the trade marks a bounce and resets the count;
        * after a bounce, the second 1m internal break (either kind) BACK in the trade's
          direction adds — but only once the 1m EXTERNAL trend points the trade's way too.

        🔴 **EVERY LOT SHARES THE TRADE'S ONE TRAILING STOP.** Aaron, 2026-09-24: per-add stops
        behind the bounce are "bad because price could come back and hit those easily" — and
        the measurement agreed (3 in 4 stopped).

        Sized like every add — worst case at the shared stop is flat — and **NET OF COSTS**: what
        the trade has paid, the exit side still owed on every open lot, and this add's own round
        trip. Without that, "flat at the stop" was flat before costs (5 trades since 2020 closed
        just under zero on exactly their costs under the shipped rule).

        MEASURED 2026-09-24 before it was built (scratch replay, 2020-01-01 → 2026-09-24, PU
        Prime ECN costs, 3 adds x 0.5x, adds decided at the 15m close): against the shipped
        "Trail", 14 trades made worse instead of 42, NO winner turned into a scratch instead of
        5, worst drop 6.45R instead of 7.27R — for +24.1R over no adds instead of +43.3R. The
        goal it was chosen for is protecting winners, not the most R.

        ⚠ **PYTHON ONLY.** The Pine has no 1-minute feed, so the parity gate can never see it.
        ⚠ **It needs the dual clock's fast feed at ONE minute** — config refuses otherwise.
        """
        cfg, d = self._cfg, self._pos_dir
        # The breaks of the fast bars INSIDE this 15m bar. The dual clock steps a 15m bar only
        # once a fast bar opening at or after its CLOSE arrives, and before that fast bar is fed
        # to the structure engine — so everything buffered at or after this bar's open fell
        # inside it. Earlier ones belong to a bar this method was not called on (flat, or the
        # fill bar) and are dropped, never carried forward.
        # ⚠ Not keyed on `self.bar_ms`: that defaults to five minutes and only the lab sets it.
        events = [(dd, fdir) for (ms, dd, _k, fdir) in self._fast_breaks if ms >= sig.time_ms]
        self._fast_breaks = []
        if self._stage < 2:
            return
        hi = sig.high if d > 0 else -sig.low
        if len(self._adds) > self._brk_nadds:        # an add filled since the last bar
            self._brk_nadds = len(self._adds)
            self._brk_used = True
        if self._brk_ext is None or hi > self._brk_ext:
            self._brk_ext = hi
            self._brk_bounce, self._brk_count, self._brk_used = False, 0, False
        if len(self._adds) >= cfg.exec_scale_max_adds or self._brk_used:
            return
        fire = False
        for dd, fdir in events:
            if dd == -d:
                self._brk_bounce, self._brk_count = True, 0
            elif self._brk_bounce:
                self._brk_count += 1
                # 🔴 AND THE 1-MINUTE TREND MUST ALREADY POINT THE TRADE'S WAY. Two small breaks
                # back can print while the bounce is still the bigger 1m move — MEASURED: 23 of 42
                # adds fired that way before this line (Aaron, 2026-09-25: "it should only add if
                # price is going in the direction of the trade"). Not yet → keep waiting; a later
                # break back re-checks. With it, adding never deepened the worst drawdown
                # (5.98R, the same as no adds) — Run 46.
                if self._brk_count >= 2 and fdir == d:
                    fire = True
                    break
        if not fire:
            return
        self._brk_used = True                       # this push is spent, placed or refused
        pv, stop, level = self._pv(), self._current_stop(), sig.close
        if (level - stop) * d <= 0:
            return
        reserve, cost_unit = 0.0, 0.0
        if self._profile is not None:
            sp = 0.0 if getattr(self._profile, "bid_ask_fills", False) else self._spread()
            open_qty = (self._qty - self._filled_qty) + sum(lot[1] for lot in self._adds)
            reserve = (-self._costs_usd + self._profile.commission(open_qty)
                       + sp / 2.0 * open_qty * pv)
            # Commission is linear in size on every measured profile (a flat rate per unit).
            cost_unit = 2.0 * self._profile.commission(1.0) + sp * pv
        budget = self._locked_at_stop(stop) - reserve
        per_unit = (level - stop) * d * pv + cost_unit
        if budget <= 0 or per_unit <= 0:
            return
        add_qty = min(budget / per_unit, self._base_qty * cfg.exec_scale_cap_x)
        if add_qty <= 1e-9:
            return
        self._add_limit = level
        self._add_pending = add_qty
        self._add_pend_stop = stop
        self._add_armed = True

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
        if getattr(cfg, "exec_scale_mode", "Trail") == "1m break":
            return self._place_break_add(sig)
        # A RESTING order does NOT consume a slot: Pine's `lAddN` increments when the order
        # FILLS, and re-placing while one rests re-uses the same entry id, which replaces it.
        if self._stage < 2 or len(self._adds) >= cfg.exec_scale_max_adds:
            return
        d, pv = self._pos_dir, self._pv()
        stop = self._current_stop()

        # Only add again once the trail has moved PAST the stop the last add was sized against.
        # Checked BEFORE the mode branch because it is a property of the SIZE rule, not of where
        # the add happens: without it a stalling runner re-adds every bar on one guarantee.
        if self._add_stop is not None and (stop - self._add_stop) * d <= 0:
            return
        # 🔴 AND, on "Past the last add", the stop must have ratcheted past the PRICE the last add
        # was bought at — not merely past the stop it was sized against. The weaker test above is
        # what let 2026-09-22 buy a second lot on a 1.17-point stop improvement while the first lot
        # sat 36 points underwater. See `_locked_at_stop` for the other half of that fix.
        if (getattr(cfg, "exec_scale_gate", "Stop improved") == "Past the last add"
                and self._add_last_px is not None
                and (stop - self._add_last_px) * d <= 0):
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
        locked = self._locked_at_stop(stop)
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

    def _fill_pending_add(self, sig, dec) -> None:
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
        if getattr(cfg, "exec_scale_mode", "Trail") in ("Trail", "1m break"):
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
        limit_fill = getattr(cfg, "exec_scale_mode", "Trail") not in ("Trail", "1m break")
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
        # 🔴 **THE ONE ORDER SHAPE WITH NO `Fill` RECORD, WHICH IS WHY THE VOCABULARY HAD AN
        # `ADD` KIND THAT NOTHING PRODUCED.** An add is separate LOTS, so it never entered
        # `dec.fills` and a reader counting fills would conclude the strategy never scales in.
        #
        # ⚠ **NO STOP TRAVELS WITH IT, AND THAT IS A DECISION.** This lot shares the position's
        # one ratcheting stop; it does not get its own. Attaching a stop here would put a second
        # source of truth for the stop on the wire, which is the exact thing this seam removes.
        #
        # 🔴 **BUT THE STOP'S VOLUME MUST STILL GROW TO COVER THIS LOT, AND NOTHING ABOVE SAYS
        # SO.** The stop is emitted on CHANGE only, and an add that fills while the stop price
        # is unmoved emits no `MOVE_STOP` at all — so an executor that reconciles the stop's
        # PRICE alone would leave the added size unprotected and never report a disagreement.
        # Whoever consumes this must reconcile the stop's VOLUME on an `ADD`.
        #
        # ⚠ **`dec` IS REQUIRED, NOT DEFAULTED.** An optional one would let a future caller drop
        # the add from the stream in silence, which is the same failure this emission exists to
        # prevent, one level up.
        dec.intents.append(OrderIntent(
            kind=IntentKind.ADD, direction=d, qty=qty, price=price, reason="add",
        ))

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
        `exec_sec_tp_r`, which is a Python-only override that exists nowhere in `sos_fade_strategy.pine`
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

    def _ladder_levels(self, sig, deep: bool, entry: float, dir_: int):
        """The two fib prices this setup's rungs sit on — (tp1, tp2).

        🔴 **ONE FUNCTION BECAUSE IT WAS TWO COPIES.** The long and short blocks each carried the
        same hardcoded deep/shallow pair, which is how a lever gets added to one side only. Both
        call this now, so a change lands on both or neither.

        "Auto" is the shipped rule and reproduces every stored figure: a DEEP entry (at or below
        0.618) targets 0.5 then 0.382, a SHALLOW one targets 0.382 then 0.0. A named ratio pins
        that rung for every trade — see `exec_tp1_level`.

        ⚠ **A LEVEL BEHIND THE ENTRY CANNOT BE A TARGET, and which levels those are is a property
        of the FILL, not of the config** — a 0.5 rung is a target for an entry at 0.786 and is
        behind one that filled at 0.382. So it cannot be refused at construction. Such a rung
        falls back to the Auto level for that trade and is COUNTED: a run where the setting was
        mostly ignored must not report as a measurement of the setting. `tp_level_fallbacks` is
        reporting-only — nothing reads it back, so it is parity-safe.
        """
        auto1 = sig.fibo_p2 if deep else sig.fibo_p1
        auto2 = sig.fibo_p1 if deep else sig.fibo_p7
        out = []
        for chosen, auto in ((self._cfg.exec_tp1_level, auto1),
                             (self._cfg.exec_tp2_level, auto2)):
            attr = _TP_LEVELS.get(chosen)
            if attr is None:
                out.append(auto)
                continue
            price = getattr(sig, attr, None)
            # `is None` and not falsy: a price of 0.0 is a price. Rule 1.
            if price is None or (price - entry) * dir_ <= 0:
                self.tp_level_fallbacks += 1
                out.append(auto)
            else:
                out.append(price)
        return out[0], out[1]

    def _first_rung(self, *, dir_: int, entry: float, stop: float, kind: str,
                    src: Optional[str], fib_tp1: float) -> float:
        """Where this trade's FIRST rung sits, for a trade of this KIND entered at `entry`.

        🔴 **TWO CALLERS AND THAT IS WHY IT IS A FUNCTION.** `_open_position` calls it at the FILL,
        with the price the trade actually got. `planned_full_exit_price` calls it BEFORE the fill,
        with the price the resting order will get, so the live bridge can hand the target to the
        broker in the same message as the entry. The arithmetic was written out inline in the
        first of those and nowhere else; copying it into `algos/live/` would have put a second
        implementation of a pricing rule in a layer that holds no trading logic.

        ⚠ **Priced off the INITIAL stop, never a trailed one.** 1R must mean the risk the trade
        was sized against, or the target creeps outward every time the stop ratchets.

        ⚠ **The fib rung is the DEFAULT and every branch below REPLACES it.** A configuration with
        no R-multiple set gets the frozen 15-minute level the resting order was priced on, which
        is what every shipped figure reproduces.

        ⚠ **`kind` is passed rather than read off `self`**, because at placement time there is no
        open trade to read it from — that is the whole reason this is parameterised.
        """
        tp = fib_tp1
        d = 1 if dir_ > 0 else -1
        dist = abs(entry - stop)
        if kind == "primary" and getattr(self._cfg, "exec_tp1_r", -1.0) > 0 and dist > 0:
            # PRIMARY, R-PRICED: the first rung sits a multiple of the trade's own frozen risk
            # from the entry, replacing the fib level. The fib rung is a PRICE and price says
            # nothing about distance — measured on run `ea46142df097`, the primary's first rung
            # sat anywhere from 0.31R to 5.57R, so banking "at the first target" banked at a
            # different risk multiple on every trade. See `exec_tp1_r` in config.py.
            # ⚠ The SECOND rung is left where the fib put it, deliberately — same as short-hold
            # below. It still stages the stop, so erasing it would change the stop ladder as
            # well as the bank, which is a second decision.
            # ⚠ Ordered BEFORE short-hold so that fork keeps winning when both are set: its whole
            # point is that the entire position comes off at its own target, and a rung this
            # one moved underneath it would be a ladder neither setting describes.
            tp = entry + d * self._cfg.exec_tp1_r * dist
        if kind == "primary" and self._cfg.exec_short_hold and self._cfg.exec_sh_tp_r > 0:
            # SHORT-HOLD: the whole position comes off at a multiple of its own risk, replacing
            # the fib ladder for this trade. Priced the same way the re-entry below prices its
            # rung — one convention for "a target in R" rather than two.
            # ⚠ The SECOND rung is deliberately LEFT where the fib put it, by the caller. With
            # this one banking 100% (`exec_sh_tp1_pct`) nothing survives to reach it, and blanking
            # it would erase the ladder the chart draws — the record of what the trade AIMED at,
            # which no decision reads and a reader does.
            if dist > 0:
                tp = entry + d * self._cfg.exec_sh_tp_r * dist
        if kind == "secondary":
            # The RECLAIM half reads its own rung (`exec_rec_tp_r`), because under the combined
            # trigger the two halves are different trades: the reclaim enters at the deep edge with
            # a stop a median 0.43R away, so a rung that suits the gap entry is the wrong distance
            # here. MEASURED 2026-08-21: all-out at 3x made 6,740x over 7.9 years where the shipped
            # bank-half-at-1.25x ladder made 3,111x — worse than taking no re-entry at all.
            if src == "reclaim":
                # ⚠ The fallback MIRRORS the config default and must move with it. It is
                # unreachable through a real config (the field always exists), but a duck-typed
                # stand-in that fell back to a stale number would price the rung differently from
                # every shipped run while looking correct.
                tp_r = getattr(self._cfg, "exec_rec_tp_r", 3.25)
            elif src == LVL_SRC:
                # LEVEL MEMORY reads its own rung for the same reason the reclaim does, and a
                # harder one: the setup this level came from is GONE, so there is no frozen
                # 15m fib behind the trade to fall back to. A target in R is the only rung it
                # has, which is why its config refuses anything but a positive multiple.
                tp_r = getattr(self._cfg, "exec_lvl_tp_r", -1.0)
            else:
                tp_r = getattr(self._cfg, "exec_sec_tp_r", -1.0)
            if tp_r > 0 and dist > 0:
                tp = entry + d * tp_r * dist
        return tp

    def _tp1_pct_for(self, kind: str, src: Optional[str]) -> float:
        """The TP1 rung's percentage for a trade of this KIND and trigger.

        ⚠ **Parameterised for the same reason `_first_rung` is**: the live bridge asks this
        question about an order that has not filled, where there is no open trade to read the
        kind off. `_tp1_pct` below is this function asked about the trade that IS open.

        A SECONDARY may bank its own percentage (`exec_sec_tp1_pct`); -1.0 means inherit the
        shared `exec_tp1_pct`, which is what the shipped ladder does, so the default cannot move
        a stored figure. A primary never reads the override.
        """
        if kind == "secondary":
            # The RECLAIM half banks its own percentage — see the note on the first-target rung in
            # `_open_position`. Its default is 100 (the whole position off at its target, no
            # runner), which is the configuration that measured 6,740x.
            if src == "reclaim":
                own = getattr(self._cfg, "exec_rec_tp1_pct", 100.0)
            elif src == LVL_SRC:
                # 100 by default — the whole position off at its R target with no runner
                # behind it, which is the ladder Run 42 graded.
                own = getattr(self._cfg, "exec_lvl_tp1_pct", 100.0)
            else:
                own = getattr(self._cfg, "exec_sec_tp1_pct", -1.0)
            if own != -1.0:
                return own
        elif self._cfg.exec_short_hold:
            # SHORT-HOLD banks its own percentage — 100 by default, i.e. the whole position off
            # at the R target with no runner behind it, which is the point of the variant. Read
            # only for a PRIMARY: a re-entry keeps its own ladder above.
            return self._cfg.exec_sh_tp1_pct
        return self._cfg.exec_tp1_pct

    def _tp1_pct(self) -> float:
        """The TP1 rung's percentage for the trade that is actually open."""
        return self._tp1_pct_for(self._entry_kind, self._entry_src)

    def full_exit_price(self) -> Optional[float]:
        """The price this trade takes the WHOLE position off at, or `None` if it does not.

        Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`), and
        the bridge hands the answer to the broker so the exit fills AT this price instead of at
        market on the next bar close. **Public surface among private neighbours on purpose** — it
        belongs beside `_tp1_pct`, which is the rule it reads, and a reader of one wants the other.

        🔴 **THE RULE LIVES HERE RATHER THAN IN `algos/live/`, AND THAT IS THE POINT.** Which
        percentage a trade's first rung takes depends on what KIND of trade it is — a re-entry
        after a stop-out and a re-entry into a gap read different settings, and on the live bot
        those are 100 and 0. The live layer holds no trading logic, so it cannot answer that; a
        copy of this branch over there would be a second implementation free to drift from the one
        that actually books the fills.

        ⚠ **`None` for a rung that leaves a RUNNER, and that is not caution.** A venue take-profit
        closes the ENTIRE position, so handing it a rung that banks half would delete size this
        strategy is still managing. The bridge reconciles those at market and says so on every
        record it writes.

        ⚠ **`None` while FLAT**, because there is no trade to have a target. Answering the last
        trade's price would put a target on whatever opened next.

        ⚠ **Off `_tp1`, never `_stage_rungs()`.** That method orders the two rungs by DISTANCE for
        the stop ladder and explicitly does not move where profit banks — `_remaining_brackets`
        rests the first rung at `_tp1` whatever the ordering says, so reading the reordered pair
        here would name a price this strategy does not bank at.
        """
        if self._pos_dir == 0:
            return None
        if float(self._tp1_pct()) < 100.0:
            return None
        tp = self._tp1
        if tp is None:
            return None
        tp = float(tp)
        return tp if math.isfinite(tp) and tp > 0 else None

    def planned_full_exit_price(self, pend) -> Optional[float]:
        """The whole-position target a RESTING order would carry if it filled at its own price.

        Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The
        bridge sends this in the SAME message as the entry, the way the stop already travels, so a
        trade is never open at the broker without its target. `full_exit_price` above answers the
        same question about a trade that is already OPEN; this one answers it about an order that
        has not filled.

        🔴 **THE SAFETY PROPERTY IS THAT A LIMIT NEVER FILLS WORSE THAN ITS PRICE, AND IT IS WHAT
        MAKES ANSWERING AT ALL SAFE.** The rung is priced off the FILL, which is not known yet — so
        this is an estimate. But a buy limit fills at its price or LOWER and a sell limit at its
        price or HIGHER, and either way a better fill means a SMALLER risk, which puts the rung
        NEARER the entry. **So this estimate is always at or BEYOND the price the strategy will
        actually bank at, never nearer — the broker's target cannot fire before the strategy's own
        trigger.** Worked both ways, not reasoned: long edge 100 stop 98 at 3.25R gives 106.5, and
        a gap fill at 99 gives 102.25 (nearer); short edge 100 stop 102 gives 93.5, and a gap fill
        at 101 gives 97.75 (nearer, because for a short nearer means higher).
        ⚠ **The bridge's once-a-bar reconciliation trues it up within one fill-clock bar**, so an
        estimate that came out beyond the truth is corrected rather than left standing.

        🔴 **`None` FOR A MARKET ENTRY, and that is the case the property above does NOT cover.**
        `exec_rec_entry_mode = "Market"` fills at the NEXT bar's open, which can be either side of
        the arming price — so a better-or-equal fill is not guaranteed and the estimate could land
        NEARER than the truth, closing the trade early at a price this strategy never chose.
        **The live bot's re-entry is set to rest a limit, so this refusal costs it nothing today.**

        ⚠ **`None` for a rung that leaves a RUNNER**, for the same reason `full_exit_price` gives:
        a venue take-profit closes the ENTIRE position.

        ⚠ **The KIND comes off the order, never off `self`.** Nothing is open when this is asked,
        and deriving it from the trigger name would read an unnamed re-entry as a primary — see
        the note on that field in `_Pending`.
        """
        if pend is None:
            return None
        if getattr(pend, "market", False):
            return None
        kind = getattr(pend, "kind", "primary")
        src = getattr(pend, "src", None)
        if float(self._tp1_pct_for(kind, src)) < 100.0:
            return None
        edge, stop = getattr(pend, "edge", None), getattr(pend, "sl", None)
        if edge is None or stop is None:
            return None
        edge, stop = float(edge), float(stop)
        if not (math.isfinite(edge) and math.isfinite(stop)):
            return None
        tp = float(self._first_rung(
            dir_=pend.dir, entry=edge, stop=stop, kind=kind, src=src,
            fib_tp1=getattr(pend, "tp1", None),
        ))
        if not (math.isfinite(tp) and tp > 0):
            return None
        # ⚠ A target that is not BEYOND the entry is not a target — it is a price already passed,
        # and a venue would either refuse it or fill it on the spot. Refusing here keeps that out
        # of the order rather than letting the broker decide what we meant.
        return tp if (tp - edge) * (1 if pend.dir > 0 else -1) > 0 else None

    def _accrued_cost_price(self) -> float:
        """This trade's costs SO FAR plus the exit side it has not paid yet, as a price distance.

        The staged stop is a PRICE, and costs are DOLLARS, so one of them has to be converted or
        the comparison is meaningless. Dollars → price on the size still open: profit from closing
        the remaining position `x` of price above entry is `x * remaining * point_value`, so the
        price offset that exactly covers a dollar figure is that figure divided by the same two.

        Three things this counts, and one it deliberately does not:

        * **Already charged** — `_costs_usd`, which `_charge` books NEGATIVE. Commission and half
          the spread on the entry, plus every rollover crossed so far. ⚠ It can be POSITIVE overall
          on a short, because gold's swap is a real credit to the short side; that is a genuine
          negative cost and is passed through rather than floored at zero.
        * **Not yet charged** — the exit side's commission and its half of the spread on whatever
          is still open. Without this the floor covers half a round trip and calls it a round trip.
        * **NOT the spread under modelled bid/ask fills.** `_charge_spread` returns early there for
          the reason given in its own docstring — the cost lives in the fill prices rather than in
          the ledger — so charging it here would bill it a second time in a different currency.

        ⚠ **Converted on the REMAINING size, not the original.** The buffer only earns on what is
        still open, so a position that has already banked a rung needs a proportionally WIDER
        offset to cover costs charged against the full size. That is arithmetic, not a policy: with
        the shipped ladder (both rungs bank 0%) nothing exits before the stop and the two are the
        same number.
        """
        cfg = self._cfg
        remaining = self._qty - self._filled_qty
        if self._profile is None or remaining <= 0 or self._pv() <= 0:
            return 0.0
        spent_usd = -self._costs_usd
        exit_usd = self._profile.commission(remaining)
        s = self._spread()
        if s > 0 and not getattr(self._profile, "bid_ask_fills", False):
            exit_usd += (s / 2.0) * remaining * self._pv()
        return (spent_usd + exit_usd) / (remaining * self._pv())

    def _be_buffer(self, *, hold_ok: bool = True) -> Optional[float]:
        """How far past the ENTRY the staged (breakeven) stop sits, as a positive price offset.

        `exec_be_buf_mode` picks which of three questions this answers, and the default is the
        shipped one so nothing moves until somebody changes it:

        * **"Ticks"** — `exec_be_buf_tk * mintick`. One fixed distance on every trade.
        * **"Fraction of stop"** — `exec_be_buf_r` × the FROZEN entry risk, so the cushion is the
          same size *relative to what the trade risked* rather than the same number of ticks.
        * **"Fraction of stop + cost"** — the above, floored at what this trade has actually cost
          (`_accrued_cost_price`) plus `exec_be_cost_margin_r` of risk. This is the only mode that
          can promise the staged exit is not a loss, and the margin is what makes it a small win.

        Both non-tick modes are then CAPPED at `exec_be_cap_pct` of the entry → nearer-rung
        distance. ⚠ The cap is not a safety belt, it is the point: a buffer that reaches the rung
        that staged it closes the trade at the target instead of protecting a runner, and that is
        measured — 24 of 243 trades at a 300-tick buffer, 70 of 243 at 600.

        ⚠ **Off `_stage_rungs()[0]`, never `_tp1`**, for the reason that method exists: a flipped
        re-entry ladder would otherwise cap against a rung price has not reached.

        ⚠ **Risk is measured off `_sl`, the FROZEN entry stop**, so "a fifth of the stop" keeps
        meaning the risk the trade was SIZED against. Reading the live stop would let the buffer
        shrink as the stop ratchets, i.e. the cushion would evaporate exactly as the trade started
        working.

        Returns **None** only in the one case the two rules genuinely disagree — the cost floor
        alone sits above the cap — and only when `hold_ok` and `exec_be_cost_conflict` is
        "Hold stop". The caller then leaves its previous stop alone: no price both covers cost and
        stays below the target, so there is nothing honest to move to. `hold_ok=False` forces the
        clamp for callers that have no previous stop to fall back to.
        """
        cfg = self._cfg
        mode = getattr(cfg, "exec_be_buf_mode", "Ticks")
        ticks = cfg.exec_be_buf_tk * cfg.mintick
        if mode == "Ticks":
            return ticks
        risk = abs(self._entry - self._sl)
        if risk <= 0:
            # No frozen risk to take a fraction OF. Every entry here is priced off a stop, so this
            # is a can't-happen rather than a case — falling back to the tick buffer keeps it a
            # can't-happen instead of a division that silently returns zero cushion.
            return ticks
        buf = getattr(cfg, "exec_be_buf_r", 0.20) * risk
        cost = None
        if mode == "Fraction of stop + cost":
            cost = self._accrued_cost_price() + getattr(cfg, "exec_be_cost_margin_r", 0.05) * risk
            buf = max(buf, cost)
        span = abs(self._stage_rungs()[0] - self._entry)
        if span > 0:
            cap = getattr(cfg, "exec_be_cap_pct", 75.0) / 100.0 * span
            if buf > cap:
                conflict = getattr(cfg, "exec_be_cost_conflict", "Hold stop")
                if cost is not None and cost > cap and hold_ok and conflict == "Hold stop":
                    return None
                buf = cap
        return buf

    # Which config pair holds each entry method's pre-rung stop rule. The KEY is `_entry_src`,
    # the value `secondary.py` stamped on the arm, and it is the only thing that decides.
    _PROTECT_RULES = {
        "reclaim": ("exec_rec_be_r", "exec_rec_be_keep_r"),
        "gap": ("exec_gap_be_r", "exec_gap_be_keep_r"),
        "Structure shift": ("exec_shift_be_r", "exec_shift_be_keep_r"),
        LVL_SRC: ("exec_lvl_be_r", "exec_lvl_be_keep_r"),
    }

    def _protect_rule(self) -> Tuple[float, float]:
        """The pre-rung stop rule OWNED by the entry method that opened this trade.

        Returns `(arm_r, keep_r)`: how far in front the trade must go before the stop moves, and
        how much of its frozen entry risk is left in the market when it does. `arm_r = -1` means
        this method's rule is *never move the stop* — it is a VALUE of the rule, not the rule
        being absent. An entry method cannot have its exit rules detached; switching the method
        on brings them with it.

        🔴 IT REPLACES A LIST WITH A PRECEDENCE ORDER, AND THAT LIST HAD A DEFECT. `_current_stop`
        used to walk its branches and take the first match. The reclaim's pair sat ABOVE the
        general one, so on a reclaim that had already been tightened by the general rule the
        reclaim's rule would fire later and hand back a LOOSER stop. MEASURED with `stopwalk.py`
        on 2026-08-26 — entry 100.00, stop 98.00, general rule arming at 1R keeping half: at
        2.25R in front the stop was 99.00, and at 2.50R it went back to 98.50. A protective stop
        that retreats on a winning trade. Exactly one rule is consulted now, so there is nothing
        left to override anything.

        ⚠ **An UNNAMED secondary gets no stop movement, and that is a decision rather than a
        fallthrough.** Before this, a re-entry whose trigger never named itself read the primary's
        pair — the shared fallback this whole change exists to remove. Reinstating it here for the
        one case the map does not cover would put the precedence question straight back. It can
        only ever leave the frozen entry stop in place, never move one that has already moved.
        ⚠ In production every armed re-entry carries a source (`secondary.py::_src_for`); the
        unnamed case is duck-typed test stand-ins and the combined trigger's neither-gate branch.
        """
        cfg = self._cfg
        if self._entry_kind != "secondary":
            return (getattr(cfg, "exec_be_arm_r", -1.0), getattr(cfg, "exec_be_keep_r", 0.0))
        names = self._PROTECT_RULES.get(self._entry_src)
        if names is None:
            return (-1.0, 0.0)
        return (getattr(cfg, names[0], -1.0), getattr(cfg, names[1], 0.0))

    def _armed_stop(self) -> Optional[float]:
        """Where this trade's own protection rule puts the stop, or None if it has not armed.

        ⚠ Always strictly between the entry and the FROZEN entry stop: `keep` is clamped below 1.0
        by config validation, so this can only ever be TIGHTER than `_sl`. That is what lets the
        callers below treat it as a floor rather than as another candidate to rank.
        """
        if not self._exc_be_armed:
            return None
        _, keep = self._protect_rule()
        d = self._pos_dir
        if keep > 0:
            return self._entry - keep * abs(self._entry - self._sl) * d
        buf = self._be_buffer()
        if buf is None:
            # Cost-covering mode, and this trade's financing alone is further out than the cap
            # allows. Hold the frozen stop — the same answer the rung ladder gives in that state.
            return self._sl
        return self._entry + buf if d > 0 else self._entry - buf

    def _current_stop(self) -> float:
        cfg = self._cfg
        d = self._pos_dir
        # ⚠ The buffer is resolved LAZILY, per branch, and is no longer a plain tick offset —
        # `_be_buffer` reads the trade's own risk and accrued costs, and may answer None ("no stop
        # here both covers cost and stays under the target"). Hoisting it back to the top would
        # compute it on every stage-0 bar and force each branch to handle a None it never asked
        # for.
        # A SECONDARY may hold its INITIAL stop until TP2 instead of ratcheting to breakeven at
        # TP1 (`exec_sec_be_at`). Three of the seven shipped re-entries exited at exactly the
        # 30-tick buffer after touching TP1 — ticked out of their own trade. Secondaries only:
        # the primary's ladder is what the Pine parity gate checks.
        # ⚠ FLOORED AT THIS METHOD'S OWN PROTECTION STOP, which is the second retreat this rewrite
        # closes. Handing back `_sl` unconditionally would WIDEN the stop back to the entry stop on
        # a trade whose protection rule had already moved it — the same defect as the reclaim's,
        # one branch up. `_armed_stop()` is always tighter than `_sl`, so taking it is a floor
        # rather than a ranking, and the two rules involved belong to the SAME entry method.
        if (self._entry_kind == "secondary" and self._stage == 1
                and getattr(cfg, "exec_sec_be_at", "TP1") == "TP2"):
            armed = self._armed_stop()
            return self._sl if armed is None else armed
        if self._stage >= 2:
            floor = self._stage2_floor()
            trail = self._trail()
            if d > 0:
                return floor if trail is None else max(floor, trail)
            return floor if trail is None else min(floor, trail)
        if self._stage >= 1:
            buf = self._be_buffer()
            if buf is None:
                # Cost-covering mode, and this trade's accrued financing alone is further from
                # entry than the cap allows. Hold the frozen entry stop rather than stage: every
                # available price is either a guaranteed loss or the target itself.
                return self._sl
            return self._entry + buf if d > 0 else self._entry - buf
        # No rung has fired, so the only thing that can have moved the stop is the pre-rung rule
        # OWNED BY THIS TRADE'S ENTRY METHOD. There is exactly one, `_protect_rule()` picks it, and
        # nothing else is consulted — which is what makes a retreat unreachable rather than merely
        # unobserved. The two branches that used to sit here, and the stop that walked backwards
        # between them, are written up in `_protect_rule`'s docstring.
        armed = self._armed_stop()
        if armed is not None:
            return armed
        return self._sl

    def _stage2_floor(self) -> float:
        """The stop FLOOR the moment TP2 fills, before the runner trail takes over
        (Pine lStage2Floor / sStage2Floor, `exec_tp2_stop_mode`). The trail can only
        tighten past this — never loosen it."""
        cfg = self._cfg
        d = self._pos_dir
        # ⚠ `hold_ok=False`, so this can never come back None. Stage 2 has no previous stop worth
        # falling back to — the trade is past BOTH rungs, and refusing to floor it there would
        # loosen the stop back toward the entry on a trade that is winning. The clamp is right
        # here for the same reason holding is right at stage 1.
        be_buf = self._be_buffer(hold_ok=False)
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
    #: How many bars late this class's flat exit FILLS. 0 here: `_flat_closes_now` books it at
    #: the bar's own close. A fork that arms a market order instead raises it to 1, and the
    #: shared rule then refuses a window too narrow to get out before the break.
    _flat_exit_delay_bars = 0

    def _flat_closes_now(self, sig) -> bool:
        """Does the flat switch close the position on THIS bar's close?

        True here, and that is the one exit in this class that does not wait for the next bar's
        open. It has no `strategy.close()` behind it (no Pine file has this input) and its whole
        purpose is to be FLAT before the close — deferring it by a bar would carry the position
        through the break it exists to prevent, and would pay the swap it was switched on to
        avoid.

        🔴 **It is a separate question from `_flat_due` because a FORK MAY ANSWER IT DIFFERENTLY,
        and one already does.** Realign enters at market and exits at the next bar's open all the
        way through; it overrides this to False and arms its own request instead. Folding the two
        questions together is what previously produced two whole flat-before-the-close rules —
        the timing difference is real, so it gets its own seam rather than its own rule.
        """
        return self._flat_due(sig)

    def _flat_due(self, sig) -> bool:
        """Is this bar inside the flatten window the switch asked for?

        🔴 **THE CLOCK MOVED OUT TO `strategies/python/time_flat.py` AND THIS IS NOW ONE LINE OF
        DELEGATION.** The rule that used to live here answered a DAILY question only, and Realign
        had grown a second, Friday-shaped answer of its own beside it with different fill timing —
        so this repo held two opinions about when the market closes, and the extreme leg held
        none. The shared module is the single one, and it also knows about the early and holiday
        closes neither of the originals had ever heard of.

        ⚠ **The window is rebuilt when the BAR SIZE changes**, not cached once. A 15m replay and a
        1m secondary stream both reach this object, and a window sized for one is the wrong window
        for the other — the shared rule refuses a window that could never fire, which is a refusal
        that must be asked on the frame actually being stepped.
        """
        cfg = self._cfg
        if cfg.flat_mode == "Off":
            return False
        bar_min = max(1, int(self.bar_ms // 60_000))
        if getattr(self, "_flat_rule_bar_min", None) != bar_min:
            from time_flat import TimeFlatConfig, TimeFlatRule
            self._flat_rule = TimeFlatRule(
                TimeFlatConfig(
                    mode=cfg.flat_mode,
                    minutes_before=cfg.flat_by_close_min,
                    close_hour_ny=cfg.daily_close_hour_ny,
                    holidays=cfg.flat_holidays,
                ),
                bar_minutes=bar_min,
                # 0 — this family's daily flat closes at THIS bar's own close (see
                # `_flat_closes_now`), so no lead bar is needed. Realign overrides that and
                # passes its own timing below.
                exit_delay_bars=self._flat_exit_delay_bars,
            )
            self._flat_rule_bar_min = bar_min
        return self._flat_rule.due(sig.time_ms)

    def step_reversal(self, sig_fast, m1, levels=()) -> None:
        """Advance the REVERSAL EXIT on one fast bar. Primary positions only.

        Two phases, the same shape every other exit on this engine has:
          A. fill what was decided at the LAST fast bar's close, at THIS bar's open.
          B. decide, at THIS bar's close, whether the next bar opens with an order resting.

        🔴 IT IS THE ONE PLACE A PRIMARY IS TOUCHED OFF A FAST BAR, and that is deliberate. The
        15m stream owns the primary's ladder (`step` → `_manage_open`) and the fast stream owns
        the re-entry's; this cuts across that split because the signal it reads only exists on
        the fast frame and waiting for the 15m close is the delay it is built to avoid. It
        touches ONLY the exit, never a stop, a target or a size, so the two streams cannot
        disagree about where the trade's ladder is — `_stage` is the single piece of shared
        state it writes, and it writes the value the ladder itself uses for "the trail governs
        this stop".

        ⚠ CALLED ON EVERY FAST BAR, INDEPENDENTLY OF THE RE-ENTRY. `DualClock.step_fast` runs it
        before its own `exec_secondary` early return, because the fast STRUCTURE feed is stepped
        unconditionally and this rule reads that feed rather than the re-entry's arm state.

        ⚠ `m1` is the fast frame's `M1State`. `new_bull_sos` / `new_bear_sos` are THIS bar's
        events, not latches — a latched flag would re-fire the rule on every later bar of the
        trade, which is a different rule silently answered.
        """
        if self._cfg.exec_rev_exit == "Off":
            return
        sink = Decision(index=sig_fast.index)
        self._stamp_account_clock(sig_fast)

        # ── Phase A: the order decided last bar is a MARKET order the broker already has ──
        act, self._pending_rev = self._pending_rev, None
        if act is not None and self._pos_dir != 0 and self._entry_kind == "primary":
            if act == "Close":
                self._close_at(sig_fast, sig_fast.open, "reversal", sink, tag="REV")
            else:
                if act == "Bank half":
                    # Half of what is still OPEN, for the reason the give-back guard's own
                    # comment gives: a trade that already banked a rung holds less than it was
                    # sold. Fixed at the moment the rule fired, not recomputed here.
                    half = max(self._qty - self._filled_qty, 0.0) * 0.5
                    if half > 0:
                        self._exit_portion("REV", sig_fast.open, half, sig_fast, sink)
                # Hand what is left to the runner trail rather than cutting it. MEASURED
                # 2026-09-22 on the give-back guard, which has the same three actions: at one
                # arming level all three cut the worst drawdown identically and differ only in
                # what they hand back, and closing gave up 11.2R that tightening kept.
                if self._pos_dir != 0:
                    self._stage = 2
                self._rev_done = True

        # ── Phase B: decide at this bar's close ──
        # The high-water mark is carried on THIS frame, from this bar's own extreme, so a trade
        # that spikes and turns inside one 15m bar is armed by the move that actually happened.
        if self._pos_dir != 0 and self._entry_kind == "primary":
            d = self._pos_dir
            here = sig_fast.high if d > 0 else sig_fast.low
            if self._rev_best is None:
                self._rev_best = self._entry
            self._rev_best = max(self._rev_best, here) if d > 0 else min(self._rev_best, here)
            if self._cfg.exec_rev_trigger == "Level rejected":
                self._rev_track_levels(sig_fast, levels)
        if self._reversal_due(m1):
            self._pending_rev = self._cfg.exec_rev_exit

    def _rev_track_levels(self, bar, levels) -> None:
        """Count failed visits to each major level AHEAD of price; set this bar's answer.

        A long's level is overhead, a short's is underneath. That needs no separate filter: a
        level price already sits beyond is dropped as TAKEN on the bar it is first seen, and the
        rejection test is directional, so support holding under a long can never count — it is
        the trade working. (A separate "ahead of price" filter was written first and removed: a
        mutation showed no test could tell it was there.) The touch band is a quarter of the
        bar's own range, the value the re-walk declared before any result.

          reached   the bar's extreme came within the band of the level
          rejected  reached, and the close stayed more than a band short of it
          taken     the close went more than a band THROUGH it -> the row is dropped, because a
                    level price has closed through is no longer one it cannot get past

        Consecutive rejecting bars are ONE visit: two fast bars in a row pressed against the same
        price is one push, not "over and over". A visit starts again once a bar does not touch.
        """
        d = self._pos_dir
        rng = bar.high - bar.low
        band = rng * 0.25
        for lv in levels:
            if lv is None:
                continue
            lv = float(lv)
            if not any(abs(r[0] - lv) < 1e-9 for r in self._rev_levels):
                self._rev_levels.append([lv, 0, False])
        fired = False
        keep = []
        need = self._cfg.exec_rev_level_touches
        ext = bar.high if d > 0 else bar.low
        for lv, n, was in self._rev_levels:
            if (bar.close - (lv + band * d)) * d > 0:
                continue                      # taken — closed through it
            reached = (ext - (lv - band * d)) * d >= 0
            rejected = band > 0 and reached and ((lv - band * d) - bar.close) * d > 0
            if rejected and not was:
                n += 1
                if n >= need:
                    fired = True
            keep.append([lv, n, rejected])
        self._rev_levels = keep
        self._rev_level_fired = fired

    def _reversal_due(self, m1) -> bool:
        """Has the fast frame just shifted structure AGAINST an armed primary?

        R is priced off the FROZEN entry risk (`_entry` - `_init_stop`), the same denominator
        every other R in this file uses, so a trade whose stop has since ratcheted is still
        measured against what it originally risked.
        """
        cfg = self._cfg
        if cfg.exec_rev_exit == "Off" or self._pos_dir == 0:
            return False
        if self._entry_kind != "primary":
            return False
        if self._pending_rev is not None:
            return False        # an order is already resting for the next bar
        if cfg.exec_rev_exit != "Close" and self._rev_done:
            return False        # spent: the two keep-it-open actions fire once per trade
        d = self._pos_dir
        if cfg.exec_rev_trigger == "Level rejected":
            against = self._rev_level_fired
        else:
            against = bool(m1.new_bear_sos) if d > 0 else bool(m1.new_bull_sos)
        if not against:
            return False
        dist = abs(self._entry - self._init_stop)
        if dist <= 0:
            return False
        if self._rev_best is None:
            return False
        return (self._rev_best - self._entry) * d / dist >= cfg.exec_rev_arm_r

    def _apply_giveback(self) -> None:
        """Do what the guard is set to do. Called only when it is both due and unspent.

        It records an INTENT and never a fill — every action here lands at the next bar's open,
        the one-bar delay this whole file is built on.
        """
        act = self._cfg.exec_giveback_action
        if act == "Close":
            self._pending_close = ("give-back", "GIVE")
            return
        if act == "Bank half":
            # Half of what is still OPEN, not half of the original size: a trade that already
            # banked a target rung holds less than it was sold.
            self._pending_bank = max(self._qty - self._filled_qty, 0.0) * 0.5
        # Hand the rest to the runner trail instead of cutting it. `_stage` is the existing
        # state that means "the trail governs this stop" — setting it is how every other path
        # says the same thing, rather than a second flag that could disagree with it.
        self._stage = 2
        self._gave_back = True

    def _giveback_has_work(self) -> bool:
        """Whether the guard can still change anything on this trade.

        🔴 IT GUARDS THE ELIF CHAIN, NOT JUST THE ACTION. A branch that is TAKEN and then does
        nothing still consumes the bar — the time stop below it would never be reached again on
        a trade whose peak stays above the arming level, which is most of them. So a spent guard
        must not take the branch at all.
        """
        if self._cfg.exec_giveback_action == "Close":
            return True   # closing is its own end state; there is no second time
        return not self._gave_back

    def _giveback_due(self, price: float) -> bool:
        """Has this trade handed back more of its best than the guard allows?

        The guard measures against the trade's OWN high-water mark (`_ext_high`/`_ext_low`,
        the same pair that resolves `mfe_price`), never against a target: a trade that runs
        3R and comes back is the case this exists for, and no rung of the ladder knows that
        happened. R is priced off the FROZEN entry risk (`_entry` - `_init_stop`), the same
        denominator every other R in this file uses, so a trade whose stop has since ratcheted
        is still measured against what it originally risked.

        ⚠ OFF IS -1 AND THAT IS NOT THE SAME AS 0. Zero would arm on every trade at its fill.
        The config refuses 0 rather than letting it read as off.
        """
        cfg = self._cfg
        arm = getattr(cfg, "exec_giveback_arm_r", -1.0)
        if arm == -1.0 or self._pos_dir == 0:
            return False
        dist = abs(self._entry - self._init_stop)
        if dist <= 0:
            return False
        d = self._pos_dir
        best = self._ext_high if d > 0 else self._ext_low
        peak_r = (best - self._entry) * d / dist
        if peak_r < arm:
            return False
        held_r = (price - self._entry) * d / dist
        return held_r <= peak_r * (1.0 - cfg.exec_giveback_pct / 100.0)

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
