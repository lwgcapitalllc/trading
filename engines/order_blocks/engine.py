"""
order_blocks/engine.py — the order-block state machine (OrderBlockEngine).

One stateful streaming engine, fed one closed bar at a time (index + OHLC), returning that bar's
ORDER-BLOCK EVENTS: zones created, consumed (mitigated), aged out (expired) and dropped past the cap
(evicted), plus the two live zone lists. Ported line-by-line from the ORDER BLOCKS blocks in
indicators/mpc_assistant.pine.

--------------------------------------------------------------------------------------------------
THIS IS A RE-PORT, NOT A RE-SYNC (2026-07-31)
--------------------------------------------------------------------------------------------------
The previous engine implemented a different object. It created a zone on every structure break by
scanning the break leg for the last opposing ENGULFING candle, killed it on a close past the far
edge, and capped 2 per side. Every part of that is gone. What replaced it:

  * STRUCTURE BREAKS NO LONGER CREATE BLOCKS AT ALL. All four Pine creation sites (external
    bull/bear, internal bull/bear) and the helpers f_obMake / f_obCandle are commented out. This
    engine is therefore STANDALONE now — it consumes no other engine, so StructureSnapshot is gone.
  * EVERY BLOCK BELONGS TO A TURN, detected as a short pivot (ta.pivotlow/pivothigh, len 2). Two
    sources read the same turn two ways, and a turn yields at most ONE block:
      - PUSH (the engulf reading): an impulsive candle that closed through the open of the nearest
        opposing candle behind it, with a bigger body than the one it consumed. It must sit at or
        just after a matching-direction pivot. Read `push_wait` bars late.
      - TURN (the no-engulf reading): the last candle of the base, found by walking forward from the
        pivot to the first candle that CLOSES clear of every body in the base so far, and taking the
        bar immediately before it.
    The push source runs first and latches the pivot it used; the turn source refuses that pivot.
  * A CANDIDATE MUST SURVIVE SIX GATES in _add (Pine f_obAdd): the anchor must be `min_back` bars
    behind; price must not have closed clean past the zone since (dead); price must have DISPLACED
    at least `disp_mult` x ATR away (gone); no bar may have tapped-and-rejected the zone after that
    displacement (tapped); the zone must not overlap a live block by `dupe_overlap` of its own
    height (dupe); and it must not be taller than `max_atr` x ATR (huge).
  * MITIGATION IS ENTER-THEN-LEAVE, PLUS A TAP, PLUS A THROUGH. See _extend.

--------------------------------------------------------------------------------------------------
PER-BAR ORDER (ported exactly — do not reorder)
--------------------------------------------------------------------------------------------------
1. Push the bar into the rolling history and update ATR, so `[0]` is the current bar.
2. EXTEND/MITIGATE both lists (Pine extendOBs, called at mpc line 2158 — BEFORE any creation, which
   is what guarantees a block is never mitigation-checked on the bar it is born).
3. Detect this bar's pivots and remember the latest confirmed pivot bar per side.
4. PUSH source (mpc 2710-2715).
5. TURN source (mpc 2878-2881).

Steps 4 and 5 in that order are load-bearing: whichever runs first claims the turn, and the Pine's
own note says swapping them is the entire fix if the wrong reading ever wins.

--------------------------------------------------------------------------------------------------
WHAT IT NEEDS
--------------------------------------------------------------------------------------------------
Closed bars, in order, one at a time, with full OHLC. No timestamp, no volume, no upstream engine.
Warm-up is real but short: ATR(14) is None for 13 bars, the pivot needs 5, and the turn source needs
`turn_len + turn_wait` (12) bars of history, so the earliest a block can form is around bar 14.
Against a Pine export the practical warm-up is far longer — Pine's arrays open holding blocks whose
anchors are off-screen, and those only clear as they mitigate or FIFO out.

Drawing (box.new / box.set_right / colours / the OB_STUB box width / the trend-aligned hide) is out
of scope — this emits events, not visuals.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, NamedTuple, Optional

from .types import OrderBlock, OrderBlockEvents


class _Bar(NamedTuple):
    index: int
    open: float
    high: float
    low: float
    close: float


# How much OHLC / ATR / pivot history the sources can reach back through. The deepest read is the
# push source's `push_wait + push_look` (10 + 5) plus the pivot window, so 64 is comfortable slack.
_HISTORY = 64


class OrderBlockEngine:
    """Streaming order-block detector (turn-anchored).

    Build one per symbol/timeframe and feed it one closed bar at a time, in order. Defaults mirror
    the mpc_assistant.pine constants; pass overrides to match a tweaked Pine.
    """

    def __init__(self,
                 max_active: int = 10,        # Pine maxActiveOB
                 body_only: bool = False,     # Pine obBodyOnly
                 max_age: int = 500,          # Pine OB_MAX_AGE
                 min_back: int = 3,           # Pine OB_MIN_BACK
                 max_atr: float = 2.0,        # Pine OB_MAX_ATR
                 dupe_overlap: float = 0.5,   # Pine OB_DUPE_OVERLAP
                 disp_mult: float = 1.0,      # Pine OB_DISP_MULT
                 turn_len: int = 2,           # Pine OB_TURN_LEN
                 turn_scan: int = 8,          # Pine OB_TURN_SCAN
                 turn_wait: int = 10,         # Pine OB_TURN_WAIT
                 push_look: int = 5,          # Pine OB_PUSH_LOOK
                 push_wait: int = 10,         # Pine OB_PUSH_WAIT
                 push_mult: float = 0.3,      # Pine OB_PUSH_MULT
                 atr_len: int = 14) -> None:  # Pine ta.atr(14)
        self._max_active = max_active
        self._body_only = body_only
        self._max_age = max_age
        self._min_back = min_back
        self._max_atr = max_atr
        self._dupe_overlap = dupe_overlap
        self._disp_mult = disp_mult
        self._turn_len = turn_len
        self._turn_scan = turn_scan
        self._turn_wait = turn_wait
        self._push_look = push_look
        self._push_wait = push_wait
        self._push_mult = push_mult
        self._atr_len = atr_len

        # The two live lists, oldest-first — Pine activeBullOBs / activeBearOBs.
        self._bull: List[OrderBlock] = []
        self._bear: List[OrderBlock] = []

        # Rolling history, NEWEST-FIRST so `self._bars[j]` reads exactly like Pine's `[j]`.
        self._bars: Deque[_Bar] = deque(maxlen=_HISTORY)
        self._atr_hist: Deque[Optional[float]] = deque(maxlen=_HISTORY)

        # The pivot SERIES (Pine obPvLo / obPvHi): the pivot's price on the bar it confirms, else
        # None. Kept as history because the turn source reads it `turn_wait` bars back.
        self._pv_lo_hist: Deque[Optional[float]] = deque(maxlen=_HISTORY)
        self._pv_hi_hist: Deque[Optional[float]] = deque(maxlen=_HISTORY)

        # Latest confirmed pivot bar index per side — Pine obPvLoBar / obPvHiBar (`var`, so they
        # persist until the next pivot of that side confirms).
        self._pv_lo_bar: Optional[int] = None
        self._pv_hi_bar: Optional[int] = None

        # The pivot bar a PUSH block was drawn from, so the turn source refuses it — Pine
        # obTurnUsedL / obTurnUsedS. Latched on the RETURN of _add, not on the push firing, because
        # every gate in _add can still refuse; if the push was refused, no block exists and the turn
        # source must still get its chance at that pivot.
        self._turn_used_l: Optional[int] = None
        self._turn_used_s: Optional[int] = None

        # Wilder ATR state (Pine ta.atr == ta.rma(ta.tr(true), len), seeded with the SMA of the
        # first `len` true ranges — so it is None until bar len-1).
        self._tr_seed: List[float] = []
        self._atr: Optional[float] = None
        self._prev_close: Optional[float] = None

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, index: int, open_: float, high: float, low: float,
               close: float) -> OrderBlockEvents:
        """Feed one closed bar. Returns this bar's OrderBlockEvents."""
        ev = OrderBlockEvents()

        # 1. History + ATR, so `[0]` is this bar (Pine's implicit series semantics).
        self._bars.appendleft(_Bar(index, open_, high, low, close))
        self._push_atr(high, low, close)

        # 2. Extend + mitigate BEFORE any creation — this is what stops a block being
        #    mitigation-checked on the bar it is born (Pine extendOBs, mpc line 2158).
        self._extend(self._bull, index, high, low, close, ev)
        self._extend(self._bear, index, high, low, close, ev)

        # 3. Pivots (Pine obPvLo / obPvHi + the two `var` bar trackers, mpc 2628-2635).
        pv_lo = self._pivot_low()
        pv_hi = self._pivot_high()
        self._pv_lo_hist.appendleft(pv_lo)
        self._pv_hi_hist.appendleft(pv_hi)
        if pv_lo is not None:
            self._pv_lo_bar = index - self._turn_len
        if pv_hi is not None:
            self._pv_hi_bar = index - self._turn_len

        # 4. PUSH source, then 5. TURN source. Order matters — see the module docstring.
        self._push_source(index, ev)
        self._turn_source(index, ev)

        ev.active_bull = list(self._bull)
        ev.active_bear = list(self._bear)
        return ev

    # ------------------------------------------------------------------
    # Live zone lists (read)
    def active_bull(self) -> List[OrderBlock]:
        return list(self._bull)

    def active_bear(self) -> List[OrderBlock]:
        return list(self._bear)

    # ------------------------------------------------------------------
    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _push_atr(self, high: float, low: float, close: float) -> None:
        """Pine ta.atr(len) == ta.rma(ta.tr(true), len). `ta.tr(true)` falls back to high-low on the
        first bar (no previous close); ta.rma is seeded with the SMA of the first `len` values, so
        the result is None (Pine na) until then."""
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        if self._atr is None:
            self._tr_seed.append(tr)
            if len(self._tr_seed) == self._atr_len:
                self._atr = sum(self._tr_seed) / self._atr_len
        else:
            alpha = 1.0 / self._atr_len
            self._atr = alpha * tr + (1.0 - alpha) * self._atr
        self._atr_hist.appendleft(self._atr)
        self._prev_close = close

    def _atr_at(self, back: int) -> Optional[float]:
        """ATR `back` bars ago — Pine `ta.atr(14)[back]`."""
        if back >= len(self._atr_hist):
            return None
        return self._atr_hist[back]

    # ------------------------------------------------------------------
    # Pivots. Pine's ta.pivothigh/pivotlow are NOT symmetric-strict: the centre may EQUAL a bar to
    # its LEFT but must be STRICTLY beyond every bar to its RIGHT (so the last bar of an equal-price
    # run is the pivot). Getting this wrong silently drops the frequent raw-price ties on gold — the
    # exact bug found and fixed in equal_highs_lows/ and rsi_divergence/ on 2026-07-19.
    def _pivot_low(self) -> Optional[float]:
        L = self._turn_len
        need = 2 * L + 1
        if len(self._bars) < need:
            return None
        centre = self._bars[L].low
        for i in range(need):
            if i == L:
                continue
            b = self._bars[i]
            if i < L:                 # NEWER than the centre == to its RIGHT: strict
                if b.low <= centre:
                    return None
            else:                     # OLDER == to its LEFT: an equal low is allowed
                if b.low < centre:
                    return None
        return centre

    def _pivot_high(self) -> Optional[float]:
        L = self._turn_len
        need = 2 * L + 1
        if len(self._bars) < need:
            return None
        centre = self._bars[L].high
        for i in range(need):
            if i == L:
                continue
            b = self._bars[i]
            if i < L:                 # RIGHT: strict
                if b.high >= centre:
                    return None
            else:                     # LEFT: an equal high is allowed
                if b.high > centre:
                    return None
        return centre

    # ------------------------------------------------------------------
    def _extend(self, arr: List[OrderBlock], index: int, high: float, low: float,
                close: float, ev: OrderBlockEvents) -> None:
        """Pine extendOBs, drawing stripped. Walks the list backwards so removal by index is safe.

        MITIGATION — a zone survives exactly ONE thing: price still being inside it at the close.
          * `entered` latches the first time a candle CLOSES inside the zone.
          * A close clean past the FAR edge kills it outright (`through`), entered or not — price
            has been through every order in there. Without this a block price runs cleanly THROUGH
            in one bar (never closing inside) would be immortal, waiting on a condition that can no
            longer happen.
          * Otherwise, if this bar is not closing inside, the block dies when EITHER the bar touched
            the zone (a wick in that closed back out — took what was there and left inside one
            candle) OR it had previously entered (parked inside, now closing outside, either side).

        THE COST OF THE WICK HALF, stated because it is real: this is a tap rule, and a tap rule
        kills the blocks that HELD — a level that rejects price cleanly is wicked and closed out of,
        which is now its death. That is the trade Aaron chose for a chart with no worked-through
        zones left on it.

        AGE is the other way out, and it carries weight under this rule: a block price never returns
        to can never be mitigated, because both halves need price at the zone.
        """
        for i in range(len(arr) - 1, -1, -1):
            ob = arr[i]
            inside = ob.bottom <= close <= ob.top
            touch = low <= ob.top and high >= ob.bottom
            if not ob.entered and inside:
                ob.entered = True
            stale = index - ob.origin_index > self._max_age
            through = close < ob.bottom if ob.is_bullish else close > ob.top
            mitigated = through or ((not inside) and (touch or ob.entered))
            if stale or mitigated:
                arr.pop(i)
                # Pine deletes on `obStale or obMitigated` with no precedence; a block that is both
                # is reported as MITIGATED, since being consumed is the meaningful half.
                (ev.mitigated if mitigated else ev.expired).append(ob)

    # ------------------------------------------------------------------
    def _add(self, arr: List[OrderBlock], off: int, is_bullish: bool, index: int,
             ev: OrderBlockEvents, from_break: bool = False) -> bool:
        """Pine f_obAdd. `off` is the anchor candle's bars-ago offset. Returns whether a block was
        actually drawn — the caller needs that fact, not merely "the source fired", because every
        gate below can refuse.

        The anchor is the NOMINATED candle, full stop: the turn source hands over the last base
        candle, the push source hands over the candle it consumed, and neither is second-guessed
        here. An earlier snap-to-the-nearby-extreme search was measured to drag the anchor OFF the
        turn (the deepest wick in a six-bar window is frequently not the candle price turned on).
        """
        if off >= len(self._bars):
            return False
        anchor = self._bars[off]
        if self._body_only:
            top = max(anchor.open, anchor.close)
            bottom = min(anchor.open, anchor.close)
        else:
            top, bottom = anchor.high, anchor.low

        atr = self._atr
        # HEIGHT CEILING — an order block is the small base BEFORE the impulse; a box the size of
        # the impulse is not a level, it is a redrawing of the move. Oversized zones are also the
        # ones that become immortal, since price can RANGE INSIDE them for hours and never leave.
        # na-guarded so the first bars of a feed, where ATR has not warmed up, do not refuse
        # everything.
        huge = atr is not None and (top - bottom) > atr * self._max_atr

        # THE LOOK-BACK REPLAY. Walks every bar between the anchor and the live bar, stopping at
        # bar 1 — the live bar can never be the close that proves price left, which is what makes
        # this a look-BACK. It does three jobs:
        #   dead   — price already closed clean past the far edge, so extendOBs would delete this
        #            block on the very next bar; refuse it now rather than flicker one onto the
        #            chart and take it straight back.
        #   travel — the furthest CLOSE beyond the edge price departed by. Leaving is not enough, it
        #            has to be a DISPLACEMENT: in chop price closes just past a candle's range
        #            constantly, drifts back, and closes past it again, and every one of those
        #            nothing-turns used to become a level. Measured in ATR so it travels across
        #            instruments and timeframes, and on CLOSES so a single spike out and back cannot
        #            buy a level.
        #   tapped — once price has genuinely displaced, a bar that reaches into the zone and closes
        #            outside it is a real tap-and-reject, so the block is refused at birth rather
        #            than drawn and deleted a bar later.
        # `tapped` deliberately only counts AFTER `left` is set. The candle right after the anchor is
        # the DRIVE, and a drive starts from inside the base it is leaving — it overlaps the zone by
        # construction and closes outside, which is the tap rule exactly. Applied from bar one, every
        # block on the chart would be mitigated by its own departure.
        # NOTE the block is born CLEAN (`entered=False`). Carrying `entered` from this replay was
        # measured to kill correct blocks on arrival: the base candles nearly always contain a close
        # inside the zone, and since `gone` already requires price to be OUTSIDE, extendOBs'
        # `not inside and (touch or entered)` fires on the very next bar. A block cannot be mitigated
        # by the move that CREATED it — the level did not exist yet.
        dead = False
        left = False
        tapped = False
        travel = 0.0
        if off >= self._min_back:
            for j in range(off - 1, 0, -1):
                bar = self._bars[j]
                if (bar.close < bottom) if is_bullish else (bar.close > top):
                    dead = True
                    break
                if left:
                    if (bar.low <= top and bar.high >= bottom
                            and (bar.close > top or bar.close < bottom)):
                        tapped = True
                        break
                away = (bar.close - top) if is_bullish else (bottom - bar.close)
                if away > travel:
                    travel = away
                if not left and atr is not None and travel >= atr * self._disp_mult:
                    left = True
        gone = atr is not None and travel >= atr * self._disp_mult

        # DEDUPE BY OVERLAP, NOT EQUALITY. The push and turn sources fire at the same turn but often
        # land on ADJACENT candles whose highs and lows differ by cents, so an equality test never
        # matched and both boxes printed, describing one zone twice. Deliberately a fraction of the
        # CANDIDATE's own height: a small candidate wholly inside a big live zone is a duplicate,
        # while a big candidate that merely contains a small old one is not. FIRST DRAWN WINS — the
        # push source runs before the turn source, so on a turn that also engulfed, the PUSH block is
        # the one kept.
        dupe = False
        for other in arr:
            overlap = min(top, other.top) - max(bottom, other.bottom)
            if overlap > 0 and overlap >= (top - bottom) * self._dupe_overlap:
                dupe = True
                break

        if not (gone and not dead and not tapped and not dupe and not huge):
            return False

        ob = OrderBlock(top=top, bottom=bottom, is_bullish=is_bullish,
                        origin_index=anchor.index, created_index=index, id=self._take_id(),
                        from_break=from_break, entered=False)
        arr.append(ob)
        ev.created.append(ob)
        # Pine manageOBs: plain oldest-out at the cap. It used to protect structure-born blocks; with
        # the turn sources now the ONLY source, both kinds queue by AGE and nothing else.
        while len(arr) > self._max_active:
            ev.evicted.append(arr.pop(0))
        return True

    # ------------------------------------------------------------------
    def _push_source(self, index: int, ev: OrderBlockEvents) -> None:
        """Pine's PUSH source (mpc 2636-2715) — the engulf reading of a turn.

        A push is TWO things and both must hold:
          ENGULFING — the candle closed through the nearest opposing candle's OPEN, and its body is
            BIGGER than the body it consumed. That consumed candle is the block, and it must itself
            clear the ATR noise floor: if the nearest opposing candle is a doji, the last opposing
            candle genuinely IS a doji and there is no order block there. It REFUSES rather than
            scanning deeper, which would claim a level the push never came off.
          IMPULSIVE — the pushing candle's body beats ATR x push_mult. That is only a NOISE FLOOR
            whose job is to stop two microscopic bars qualifying in dead chop; the real size test is
            beating the consumed body, which is self-scaling with no constant involved.

        Read `push_wait` bars late, so the anchor is already history when it is examined. The WAIT
        IS THE DISPLACEMENT WINDOW: _add's departure loop runs from the anchor's offset down to bar
        1, so how far back the anchor sits IS how many bars price has to displace in. Too short a
        wait and almost nothing clears the ATR of travel — and since each source fires ONCE, a block
        that had not displaced yet was lost for good rather than deferred.
        """
        w = self._push_wait
        atr = self._atr_at(w)
        if atr is None or w >= len(self._bars):
            return
        pb = self._bars[w]
        body = abs(pb.close - pb.open)
        up = pb.close > pb.open
        # Pine also gates on barstate.isconfirmed; this engine only ever sees closed bars.
        if not body > atr * self._push_mult:
            return

        # Nearest OPPOSING candle BEHIND the push bar — the one it consumed. Offsets are absolute
        # (measured from the live bar), so they start one past the push itself. The push's block
        # candle is NOT always the previous bar: real bases are two or three small bars, so
        # demanding bar[1] be the opposing candle rejected almost every real push.
        idx: Optional[int] = None
        for j in range(w + 1, w + self._push_look + 1):
            if j >= len(self._bars):
                break
            b = self._bars[j]
            if (b.close < b.open) if up else (b.close > b.open):
                idx = j
                break
        if idx is None:
            return

        consumed = self._bars[idx]
        prev_body = abs(consumed.close - consumed.open)
        real = prev_body > atr * self._push_mult
        engulfed = real and body > prev_body and (
            pb.close > consumed.open if up else pb.close < consumed.open)
        if not engulfed:
            return

        # AND THE PUSH MUST BE AT A TURN. The anchor has to sit AT OR JUST AFTER a matching-direction
        # pivot — a pivot LOW for a bullish block, a pivot HIGH for a bearish one. "At or just
        # after", not "anywhere near": a block BEFORE the pivot is in the move that was still going
        # the other way, which is the previous leg, not this turn's base. Without this gate the
        # source fired on any impulsive engulfing candle on the chart, mid-trend included, with no
        # turn anywhere near it — a box out in the middle of a fall with no reference zone beside it.
        anchor_bar = index - idx
        pv_bar = self._pv_lo_bar if up else self._pv_hi_bar
        if pv_bar is None or anchor_bar < pv_bar or anchor_bar - pv_bar > self._turn_scan:
            return

        if self._add(self._bull if up else self._bear, idx, up, index, ev):
            if up:
                self._turn_used_l = self._pv_lo_bar
            else:
                self._turn_used_s = self._pv_hi_bar

    # ------------------------------------------------------------------
    def _turn_source(self, index: int, ev: OrderBlockEvents) -> None:
        """Pine's TURN source (mpc 2717-2881) — the no-engulf reading of a turn.

        Every turn is a potential block: an engulfing candle is one SYMPTOM of a turn, not the turn
        itself. Plenty of turns roll over across two or three bars leaving no candle that swallows
        its neighbour, and the engulf rule sees nothing there.

        THE ANCHOR IS DERIVED, NOT COUNTED. "The last candle before the turn" means the last candle
        before price LEAVES, so the walk goes forward from the pivot to the first candle that CLOSES
        CLEAR OF EVERY CANDLE IN THE BASE SO FAR, and takes the bar immediately before it. A fixed
        offset cannot be right — how long price spends in the base differs at every turn. There is
        deliberately no SIZE test on the breakout candle either: the move away often starts modest
        and only gets big a bar or two later, so asking for size walks straight past the real first
        drive candle and anchors late.

        THE BASE'S CEILING IS ITS BODIES, NOT ITS WICKS. A wick is the highest thing in a base by
        definition, so demanding a close above every spike fires a bar LATE and walks the anchor one
        bar forward onto a candle slightly up the turn — measured as a uniform one-candle offset
        against the reference overlay. Both sides of the test are body-based, and COLOUR IS NEVER
        TESTED, on the anchor or the breakout candle.

        Measuring against the base's OWN running extreme, not the pivot candle alone, is what stops
        a slow base ending early: one candle poking above the pivot bar while the base is still
        forming is not a departure; clearing everything printed so far is.

        Falls back to the pivot bar if nothing clears inside `turn_scan` — a base that long has not
        displaced, and _add's displacement gate refuses it anyway.
        """
        base = self._turn_len + self._turn_wait
        if base >= len(self._bars):
            return
        # The pivot SERIES `turn_wait` bars ago — non-None exactly when the pivot bar itself was
        # `base` bars ago (a pivot confirms `turn_len` bars after the bar it marks).
        turn_lo = self._pv_lo_hist[self._turn_wait] if self._turn_wait < len(self._pv_lo_hist) else None
        turn_hi = self._pv_hi_hist[self._turn_wait] if self._turn_wait < len(self._pv_hi_hist) else None
        if turn_lo is None and turn_hi is None:
            return

        pivot = self._bars[base]
        off_l = off_s = base
        found_l = found_s = False
        run_h = max(pivot.open, pivot.close)
        run_l = min(pivot.open, pivot.close)
        # The two directions need their own scans: a bullish base ends on a close above its highs, a
        # bearish one on a close below its lows, and at the same turn those land on different bars.
        for j in range(base - 1, max(3, base - self._turn_scan) - 1, -1):
            b = self._bars[j]
            if not found_l:
                if b.close > run_h:
                    off_l, found_l = j + 1, True
                else:
                    run_h = max(run_h, b.open, b.close)
            if not found_s:
                if b.close < run_l:
                    off_s, found_s = j + 1, True
                else:
                    run_l = min(run_l, b.open, b.close)

        # The pivot bar THIS source is reading — compared against the push latch so a turn the
        # engulf rule already claimed is not boxed a second time.
        pv_bar = index - base
        if turn_lo is not None and pv_bar != self._turn_used_l:
            self._add(self._bull, off_l, True, index, ev)
        if turn_hi is not None and pv_bar != self._turn_used_s:
            self._add(self._bear, off_s, False, index, ev)
