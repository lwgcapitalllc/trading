"""level_memory.py — the level this bot ALREADY traded, rested again after the setup died.

Aaron, 2026-09-22, watching it happen live: the Monday short filled at the gap edge the setup
published, tagged its first target, moved the stop into profit and closed there for roughly
nothing — and about twenty hours later price came all the way back to that same price and sold
off, with the bot holding nothing. *"We did not have any logic to take that trade. Why?"*

**Why it had nothing, from its own decision record, and it is two independent causes:**

1. The setup DIED at 05:15 UTC when structure re-broke. `Execution._sync_gap_latch` clears the
   published entry price with the setup, which is correct for everything that reads it — a price
   belonging to a dead setup is exactly how a re-entry rests at a level nothing is watching. The
   side effect is that the bot has no memory of a level it traded an hour ago.
2. No shift of structure printed on the short side all evening. The sequence sat at stage 1 — a
   sweep and nothing more — so nothing armed and nothing could be placed. The level is the only
   thing that could have carried the trade, and it was gone.

🔴 **THIS IS NOT `exec_sec_poi_fallback`, AND READING IT AS THAT ONE IS THE MISTAKE TO AVOID.**
That switch rests the re-entry at the primary's own entry price WHILE THE SETUP IS STILL ALIVE
(Run 41). This is the opposite case: the setup is gone, nothing is watching, and the level is
remembered anyway. It is also not Runs 27-36 (setups the primary NEVER traded) and not Run 39
(the return into the zone from the leg extreme). Run 42 measured it because nothing else did.

**The trade, and every number in it is the screen's:**
  LEVEL   the price the PRIMARY itself entered at — not a re-derived gap edge, the number the
          execution already published and filled on.
  ARMED   from the bar that primary CLOSES, for `exec_lvl_days`.
  AWAY    price must first travel `exec_lvl_away_r` x that trade's own 1R away from the level,
          in the trade's own direction. 🔴 Not a knob — see the config note. A profit stop exits
          AT the entry price, so without it "price came back" is true the minute the trade ends.
  ENTRY   a limit at the level, same direction as the original, filled on the fill clock.
  STOP    `exec_lvl_stop_frac` x the ORIGINAL trade's own stop distance. This is the variable
          that matters: at 1.0 the screen makes +11.67R and at 0.5 it makes +16.35R.
  QUIET   by default it rests only while nothing else is armed on that side — the 44 returns
          where a setup WAS live are worth -0.02R, and there is one position slot.

**What this module is NOT allowed to do**, and the reason the class is this small: it holds no
structure engine, reads no fib, and decides no gap. Every price it hands out came from a trade
the execution already booked. A second reading of the entry rules is how two halves of one
strategy silently disagree, which this package has paid for twice.

⚠ **It emits `SecArm`, the re-entry's own record, rather than a second contract.** Everything
downstream — sizing, the minimum-stop floor, the budget fit, the fill, the ladder — is the
re-entry's existing path, reached through `Execution._secondary_pending`. The only thing that
tells the two apart at the far end is `src`, which is what `_PROTECT_RULES` and the rung
functions key on.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .secondary import SecArm

#: What `src` a level-memory order carries. One string, named once, because three modules read it
#: (`Execution._first_rung`, `_tp1_pct_for`, `_PROTECT_RULES`) and a typo in any of them would
#: silently price the trade as an unnamed re-entry rather than raise.
SRC = "level memory"

_MS_DAY = 86_400_000.0


@dataclass
class _Remembered:
    """One side's remembered level. Mutable on purpose — `away` is a latch that fills in."""

    level: float
    stop_dist: float     # the ORIGINAL trade's own 1R, in price
    closed_ms: int       # when that primary closed; the memory's clock starts here
    away: bool = False   # price has since travelled far enough away for a return to mean anything
    done: bool = False   # this level has had its one order filled
    # "Gap still open" — the gap this level came from, as the gap engine listed it when the memory
    # was taken: (top, bottom, born). None = no such gap was live, which spends the level under that
    # filter rather than letting it trade unfiltered. Unused by the other filters.
    gap: Optional[Tuple[float, float, int]] = None
    # "Shift confirms" — price has come back to the level, the most extreme price since, and how
    # many fill-clock bars have passed. Unused by the other filters.
    tapped: bool = False
    tap_ext: Optional[float] = None
    since_tap: int = 0


#: The legal values of the level memory's confluence setting, named once so the config's
#: validation and this module cannot disagree about the spelling.
CONFLUENCES = ("None", "Gap still open", "Sweep first", "Shift confirms")


class LevelMemory:
    """Per side, the last level a PRIMARY traded, kept alive after its setup is gone.

    One level per side at a time, and a newer primary REPLACES an older memory. That is a
    deliberate narrowing of the screen, which graded every primary's level independently: with one
    position slot only one of them can ever trade, and keeping a queue would describe a book the
    account cannot hold. ⚠ It does mean this can take FEWER trades than Run 42 graded, never more
    — the safe direction, and the replay is what settles the difference.

    The memory is learned by POLLING the execution rather than by being pushed to, and the
    execution keeps only the last closed primary per side. Nothing accumulates, a run that never
    switches the feature on still costs nothing, and there is no drain that a second driver could
    forget to call.
    """

    def __init__(self, config) -> None:
        self._cfg = config
        self._l: Optional[_Remembered] = None
        self._s: Optional[_Remembered] = None
        # 🔴 **THE CLOSE TIME OF THE LAST RECORD THIS SIDE TOOK, WHETHER OR NOT IT STILL HOLDS IT.
        # WITHOUT IT THE MEMORY RESURRECTS ITSELF AND THE FEATURE BECOMES A CASCADE.** The
        # execution keeps its last-closed-primary record standing for days; this class polls it.
        # So a level that has been SPENT (`mark_traded`) or has EXPIRED drops to None here and is
        # then re-created from the same still-present record on the very next bar, for ever.
        # MEASURED 2026-09-23 on the first replay of this feature: 141 extra trades where Run 42's
        # screen found 39 returns it could take at all, and +227.5R fell to +205.4R.
        # ⚠ *Held it* and *never saw it* must not be the same value — rule 1, from the other end.
        self._l_seen_ms: Optional[int] = None
        self._s_seen_ms: Optional[int] = None

    # ── learning ────────────────────────────────────────────────────────────────────────────
    def observe(self, last_l, last_s, sig=None) -> None:
        """Take the execution's last-closed-primary record per side, if it is a new one.

        `last_*` is `(level, stop_dist, closed_ms)` or None. Compared on `closed_ms`, which is the
        only field that is certainly different between two trades on one side — two primaries CAN
        enter at the same price off the same gap. ⚠ Compared against what this side has EVER
        taken, never against what it still holds; see `_l_seen_ms`.

        `sig` is the last-closed 15m signal record. Read only by the "Gap still open" filter, which
        pins the gap this level came from AT THE MOMENT THE MEMORY IS TAKEN — the one moment the
        gap and the level are known to belong together.
        """
        old_l, old_s = self._l, self._s
        self._l, self._l_seen_ms = self._take(self._l, self._l_seen_ms, last_l)
        self._s, self._s_seen_ms = self._take(self._s, self._s_seen_ms, last_s)
        if self._confluence() == "Gap still open":
            if self._l is not None and self._l is not old_l:
                self._l.gap = self._find_gap(self._l, +1, sig)
            if self._s is not None and self._s is not old_s:
                self._s.gap = self._find_gap(self._s, -1, sig)

    def _confluence(self) -> str:
        return str(getattr(self._cfg, "exec_lvl_confluence", "None"))

    def _find_gap(self, rec: "_Remembered", side: int, sig) -> Optional[Tuple[float, float, int]]:
        """The live gap of the trade's own direction whose band holds the level, or None.

        ⚠ **Read off the gap engine's own live list (`sig.fvgs`), never recomputed.** That list is
        what the primary chose its entry from, so a match here is the same gap by construction.
        The tolerance exists because the entry edge can be snapped or deepened inside the gap
        before it is published; it is a fraction of THIS trade's own 1R so it scales with it.
        ⚠ A long came from a BULLISH gap below price and a short from a BEARISH one above it.
        When two gaps qualify the NEWEST wins — it is the one the setup had just printed.
        """
        if sig is None:
            return None
        tol = float(getattr(self._cfg, "exec_lvl_gap_tol_r", 0.1)) * rec.stop_dist
        want_bull = side > 0
        best = None
        for top, bottom, is_bull, born in getattr(sig, "fvgs", ()) or ():
            if bool(is_bull) != want_bull:
                continue
            if bottom - tol <= rec.level <= top + tol:
                if best is None or born > best[2]:
                    best = (float(top), float(bottom), int(born))
        return best

    @staticmethod
    def _gap_live(rec: "_Remembered", sig) -> bool:
        """Is the pinned gap still on the engine's live list? Matched on all three fields.

        ⚠ **"Not on the list" is two things, and this cannot tell them apart:** price closed
        through the gap (mitigated — the signal wanted) or seven newer gaps pushed it off the end
        (evicted — not a trading signal). So this reads *still open AND still recent*, and Run 45's
        spec says so in advance.
        """
        if rec.gap is None or sig is None:
            return False
        return rec.gap in {(float(t), float(b), int(n))
                           for t, b, _bull, n in (getattr(sig, "fvgs", ()) or ())}

    @staticmethod
    def _take(held: Optional[_Remembered], seen_ms: Optional[int], rec):
        """(what this side now holds, the last close time it has taken)."""
        if rec is None:
            return held, seen_ms
        level, dist, closed_ms = rec
        closed_ms = int(closed_ms)
        if seen_ms is not None and closed_ms == seen_ms:
            # Already taken once. `held` may be None because the level was spent or expired, and
            # that None is the answer, not a gap to fill.
            return held, seen_ms
        if not (dist > 0):
            # A trade whose stop distance is zero or missing cannot price a stop OR an away test.
            # Refusing it is rule 1 again: "no usable record" must not become "a level at no
            # risk". ⚠ It is marked SEEN so the refusal is not re-taken every bar.
            return held, closed_ms
        return _Remembered(float(level), float(dist), closed_ms), closed_ms

    # ── arming ──────────────────────────────────────────────────────────────────────────────
    def update(self, *, now_ms: int, high: float, low: float, flat: bool,
               primary_resting_l: bool, primary_resting_s: bool,
               sig=None, m1=None, close: Optional[float] = None) -> SecArm:
        """One fill-clock bar. Returns what should rest, as a `SecArm`.

        The away latch is fed THIS bar's high and low before the arm is tested, which is the same
        ordering the rest of the package uses: the bar that carries price far enough away is
        allowed to be the bar that arms. It cannot also be the bar that FILLS, because every fill
        on this engine is a resting order placed at the previous bar's close.
        """
        cfg = self._cfg
        if not getattr(cfg, "exec_lvl_memory", False):
            return SecArm()

        arm = SecArm()
        keep_ms = float(getattr(cfg, "exec_lvl_days", 5.0)) * _MS_DAY
        away_r = float(getattr(cfg, "exec_lvl_away_r", 1.0))
        quiet = bool(getattr(cfg, "exec_lvl_require_quiet", True))

        self._l = self._age(self._l, now_ms, keep_ms)
        self._s = self._age(self._s, now_ms, keep_ms)

        if self._l is not None:
            # The original was a LONG at this level: it ran UP and away, so the away test reads
            # this bar's HIGH, and the return comes back DOWN onto a buy limit.
            if not self._l.away and (high - self._l.level) >= away_r * self._l.stop_dist:
                self._l.away = True
            got = self._side(self._l, +1, high, low, close, flat, quiet, primary_resting_l,
                             sig, m1)
            if got is not None:
                edge, sl, tp1, tp2 = got
                arm = replace(arm, l_armed=True, l_edge=edge, l_sl=sl, l_tp1=tp1, l_tp2=tp2,
                              l_leg=None, l_src=SRC, l_after="level memory")

        if self._s is not None:
            if not self._s.away and (self._s.level - low) >= away_r * self._s.stop_dist:
                self._s.away = True
            got = self._side(self._s, -1, high, low, close, flat, quiet, primary_resting_s,
                             sig, m1)
            if got is not None:
                edge, sl, tp1, tp2 = got
                arm = replace(arm, s_armed=True, s_edge=edge, s_sl=sl, s_tp1=tp1, s_tp2=tp2,
                              s_leg=None, s_src=SRC, s_after="level memory")

        return arm

    def _side(self, rec, side, high, low, close, flat, quiet, resting, sig, m1):
        """One side's arm under the configured confluence: (entry, stop, tp1, tp2) or None.

        "None", "Gap still open" and "Sweep first" all REST A LIMIT AT THE LEVEL and differ only in
        whether it may rest this bar — each filter is re-read every fill-clock bar, so the order
        is pulled the moment its reason is gone and nothing is decided on information the bar has
        not published. "Shift confirms" is a different ENTRY, not a filter on this one.
        """
        mode = self._confluence()
        if mode == "Shift confirms":
            return self._shift_entry(rec, side, high, low, close, flat, quiet, resting, m1)
        if not self._armable(rec, flat, quiet, resting):
            return None
        if mode == "Gap still open":
            if rec.gap is None:
                # No gap of this direction held the level when the memory was taken, so there is
                # nothing for the filter to watch — the level is spent, not traded unfiltered.
                rec.done = True
                return None
            if not self._gap_live(rec, sig):
                return None
        elif mode == "Sweep first":
            # The primary's OWN sweep reading, on the trade's side: buy-side liquidity taken for a
            # short (price ran the highs into the level), sell-side for a long. Empty = none live.
            pool = getattr(sig, "recent_bsl" if side < 0 else "recent_ssl", "") if sig else ""
            if not pool:
                return None
        return self._prices(rec, side)

    def _shift_entry(self, rec, side, high, low, close, flat, quiet, resting, m1):
        """ "Shift confirms": price taps the level, then a fast-chart shift of structure in the
        trade's direction must print within `exec_lvl_shift_bars` bars. Market entry at the next
        bar's open, stop at the most extreme price since the tap, target `exec_lvl_tp_r` x THAT.

        ⚠ The tap bar counts as bar 0 and may itself carry the shift — a rejection that breaks
        structure inside one 5-minute bar is still a rejection. ⚠ One attempt per level: a window
        that closes without a shift spends the level. ⚠ Refused when the confirmed risk is wider
        than the ORIGINAL trade's full 1R — Run 42 measured that a wider stop is the losing side.
        """
        if not rec.away:
            return None
        if not rec.tapped:
            touched = (high >= rec.level) if side < 0 else (low <= rec.level)
            if not touched:
                return None
            rec.tapped, rec.since_tap = True, 0
            rec.tap_ext = high if side < 0 else low
        else:
            rec.since_tap += 1
            rec.tap_ext = max(rec.tap_ext, high) if side < 0 else min(rec.tap_ext, low)
        if rec.since_tap > int(getattr(self._cfg, "exec_lvl_shift_bars", 24)):
            rec.done = True
            return None
        if m1 is None or close is None:
            return None
        shifted = bool(m1.new_bear_sos) if side < 0 else bool(m1.new_bull_sos)
        if not shifted or not flat or (quiet and resting):
            return None
        risk = (rec.tap_ext - close) if side < 0 else (close - rec.tap_ext)
        if not (0 < risk <= rec.stop_dist):
            return None
        tp_r = float(getattr(self._cfg, "exec_lvl_tp_r", 2.0))
        tp1 = close - tp_r * risk if side < 0 else close + tp_r * risk
        return float(close), float(rec.tap_ext), tp1, tp1

    @staticmethod
    def _age(rec: Optional[_Remembered], now_ms: int, keep_ms: float) -> Optional[_Remembered]:
        if rec is None:
            return None
        if rec.done:
            return None
        if (int(now_ms) - rec.closed_ms) > keep_ms:
            return None
        return rec

    @staticmethod
    def _armable(rec: _Remembered, flat: bool, quiet: bool, resting: bool) -> bool:
        return rec.away and flat and not (quiet and resting)

    def _prices(self, rec: _Remembered, side: int) -> Tuple[float, float, float, float]:
        """(entry, stop, first rung, second rung) for one side.

        ⚠ The rungs are priced here off the RESTING price and again in `Execution._first_rung` off
        the FILL. Both are the same rule; the second is the one that counts, and it exists because
        a limit can fill better than it rests. Pricing them here as well is what lets the live
        bridge hand a target to the broker in the same message as the entry.
        """
        cfg = self._cfg
        dist = rec.stop_dist * float(getattr(cfg, "exec_lvl_stop_frac", 0.5))
        tp_r = float(getattr(cfg, "exec_lvl_tp_r", 2.0))
        tp2_r = float(getattr(cfg, "exec_lvl_tp2_r", -1.0))
        entry = rec.level
        stop = entry - side * dist
        tp1 = entry + side * tp_r * dist
        tp2 = tp1 if tp2_r <= 0 else entry + side * tp2_r * dist
        return entry, stop, tp1, tp2

    # ── retirement ──────────────────────────────────────────────────────────────────────────
    def mark_traded(self, direction: int) -> None:
        """This side's level has had its order filled — one per remembered level.

        ⚠ Retired on the FILL, not on the exit. A level that has been traded again is not a level
        nothing is watching any more, and a cascade at one price is a different feature with its
        own measurement, which does not exist.
        """
        rec = self._l if direction > 0 else self._s
        if rec is not None:
            rec.done = True

    def forget(self, direction: int) -> None:
        """Drop this side's memory outright — used when a fill-clock feed is rebuilt."""
        if direction > 0:
            self._l = None
        else:
            self._s = None
        # ⚠ The seen marker deliberately STAYS. Forgetting a level is not the same as never
        # having seen it, and clearing the marker would let the next poll hand it straight back.

    def reset(self) -> None:
        self._l = self._s = None
        self._l_seen_ms = self._s_seen_ms = None

    # ── reporting ───────────────────────────────────────────────────────────────────────────
    def watching(self) -> Tuple[Optional[float], Optional[float]]:
        """(long level, short level) currently remembered and not yet spent. Reporting only."""
        return (None if self._l is None else self._l.level,
                None if self._s is None else self._s.level)
