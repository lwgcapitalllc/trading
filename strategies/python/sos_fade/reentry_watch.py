"""reentry_watch.py — a re-entry the bot can still take, reported as one more watched setup.

**REPORTING ONLY.** Nothing here arms, prices, sizes or cancels an order. It reads the re-entry
state machine (`SecondaryArm.outlook`) and the order layer's own resting order, and produces
`backtest.setups.SetupSnapshot`s with `reentry_of` set, so the live signals room can open a thread
for the re-entry the same way it does for a first trade.

🔴 **Why (2026-10-01, `sos_fade_demo`, live): a re-entry filled with no warning at all.** The
setup's thread had closed when its first trade filled, and nothing anywhere said a second chance
was open. The first trade closed at breakeven at 08:15 UTC and the re-entry filled at 08:17.

**The life of one re-entry thread, per side:**

- OPENED when the bot is flat, the setup is still alive, and the re-entry's door is open — the
  first trade reached its first target (the gap half) or was stopped at its original stop (the
  reclaim half) — and the setup has not already used, lost or voided its re-entry.
- RESTING while the re-entry's own order is the one on the book.
- FILLED when that order fills.
- DEAD when the setup ends (a new break, its final target reached, price closing past its start,
  or it simply expired), or when the re-entry is retired for this setup (already used, stopped
  out, timed out, or — the reclaim — price reached the stop level first).

⚠ **One thread per setup.** Every way a watch ends is permanent for that setup, so it cannot
reopen and re-announce. The key is the setup's own key plus `:re`, so it is stable across a
restart exactly as the setup's is.

⚠ **A re-entry fill with no watch open still gets a thread, opened and closed on the same bar.**
That should never happen — `tools/setup_alert_rate.py` counts it — but a silent fill is the very
failure this file exists to end, so the fallback is a late warning rather than none.
"""

from __future__ import annotations

from typing import List, Optional

from backtest.setups import DEAD, FILLED, RESTING, WATCHING, Confluence, SetupSnapshot

#: Appended to the setup's own key. A re-entry is its own thread, never a reply on the first one.
KEY_SUFFIX = ":re"

#: What the first trade did, in the reader's words. Keys are `SecondaryArm._primary_fate`'s.
_FATE = {
    "breakeven": "First trade reached its first target, then closed",
    "stopped": "First trade was stopped at its original stop",
    "closed": "First trade closed",
    None: "Does not need the first trade",
}

#: Why a re-entry the setup was still alive for can no longer happen. Keys are `outlook.retired`.
_RETIRED = {
    "used": "This setup's one re-entry was already used.",
    "dead": "A re-entry on this setup was already stopped out.",
    "timed_out": "The re-entry order waited too long and was cancelled.",
    "void": "Price reached the stop level before it came back.",
}


def _why_setup_ended(sig, side: int) -> str:
    """Why the setup itself ended, read off the 15m bar that ended it.

    ⚠ **The order mirrors `SosFadeSequence`'s own clears**, most decisive first. It only NAMES the
    cause; nothing reads it back. When none of them is visible on the bar the sequence cleared on,
    the honest answer is that the setup expired.
    """
    long_ = side > 0
    own_sos = sig.bull_sos if long_ else sig.bear_sos
    own_bos = sig.bull_bos if long_ else sig.bear_bos
    other_sos = sig.bear_sos if long_ else sig.bull_sos
    flipped = sig.fibo_dir == (-1 if long_ else 1)
    if other_sos or flipped:
        return "Structure broke the other way, which ends the setup."
    if own_sos or own_bos:
        return "A new break of structure ended the setup."
    if sig.fibo7_touched:
        return "Price reached the setup's final target, which ends it."
    origin = sig.fibo_p10
    if origin is not None and ((sig.close < origin) if long_ else (sig.close > origin)):
        return "Price closed past where the move started, which cancels the setup."
    return "The setup expired."


class ReentryWatch:
    """Per side, the setup whose re-entry is possible right now. Owned by the order layer."""

    def __init__(self, execution) -> None:
        self._ex = execution
        #: slot (0 long, 1 short) -> the open watch, or None.
        self._open: List[Optional[dict]] = [None, None]
        #: Terminal snapshots not yet drained.
        self._done: List[SetupSnapshot] = []
        #: The text of the exception that stopped this watch, or None. A reporting failure may
        #: never take a trade down with it (`DualClock` catches it), but it must not be silent:
        #: the live runner logs it, and the measurement tool refuses a run that set it.
        self.failed: Optional[str] = None

    # ── fed by `DualClock` ───────────────────────────────────────────────────────────────────
    def observe(self, arm_sm, sig, seq, filled: Optional[int] = None) -> None:
        """One step. `filled` is +1 / -1 when a RE-ENTRY (not another fast-clock entry) filled on
        this bar, else None."""
        if self.failed is not None or sig is None or seq is None:
            return
        ex = self._ex
        # The same execution fields `DualClock.step_fast` hands the arm, so "possible" reads
        # exactly what the arm will read.
        looks = arm_sm.outlook(
            sig, seq, ex.be_sos_l, ex.be_sos_s, ex.prim_closed_sos_l, ex.prim_closed_sos_s,
            ex.prim_lost_sos_l, ex.prim_lost_sos_s, ex._poi_edge_l, ex._poi_edge_s,
            ex._poi_last_l, ex._poi_last_s,
        )
        for slot, side in ((0, 1), (1, -1)):
            look = looks[slot]
            sos_now = seq.l_sos_bar if side > 0 else seq.s_sos_bar
            w = self._open[slot]
            if w is None:
                if filled == side:
                    # Never silent — see the module docstring. Named from the setup that just
                    # re-entered, which is still `sos_now` on the fill bar.
                    w = self._start(side, sos_now, look)
                    if w is None:
                        continue
                    self._end(slot, w, FILLED, "Re-entered.")
                elif look is not None and not look.retired and ex.is_flat:
                    self._open[slot] = self._start(side, sos_now, look)
                continue
            if filled == side:
                self._end(slot, w, FILLED, "Re-entered.")
            elif sos_now != w["sos"]:
                self._end(slot, w, DEAD, _why_setup_ended(sig, side))
            elif look is None:
                self._end(slot, w, DEAD, "The setup no longer allows a re-entry.")
            elif look.retired:
                self._end(slot, w, DEAD, _RETIRED[look.retired])
            else:
                w["look"] = look

    def fail(self, err: BaseException) -> None:
        """Stop watching for good, keeping the reason. Called by `DualClock` on an exception."""
        self.failed = f"{type(err).__name__}: {err}"
        self._open = [None, None]

    # ── read by the order layer's `live_setups()` / `drain_setups()` ──────────────────────────
    def snapshots(self) -> List[SetupSnapshot]:
        out = list(self._done)
        for slot, side in ((0, 1), (1, -1)):
            w = self._open[slot]
            if w is not None:
                out.append(self._snap(w, side))
        return out

    def clear_done(self) -> None:
        self._done.clear()

    def open_sides(self) -> List[int]:
        return [side for slot, side in ((0, 1), (1, -1)) if self._open[slot] is not None]

    # ── internals ────────────────────────────────────────────────────────────────────────────
    def _start(self, side: int, sos: Optional[int], look) -> Optional[dict]:
        if sos is None:
            return None
        ex = self._ex
        sos_ms = ex._bar_ms.get(sos)
        parent = ex._setup_key(side > 0, sos, sos_ms)
        return {
            "sos": sos, "sos_ms": sos_ms, "parent": parent, "key": parent + KEY_SUFFIX,
            "look": look,
        }

    def _end(self, slot: int, w: dict, state: str, reason: str) -> None:
        self._done.append(self._snap(w, 1 if slot == 0 else -1, state=state, reason=reason))
        self._open[slot] = None

    def _confluences(self, w: dict, side: int):
        look = w["look"]
        fate = Confluence("First trade", True, _FATE.get(look.fate if look else None,
                                                         _FATE[None]))
        if look is not None and look.half == "reclaim":
            way = "above" if side > 0 else "below"
            return (fate,
                    Confluence("Reclaim", look.reclaimed, f"Price back {way} the entry level"),
                    Confluence("Retest", False, "A retest of the entry level"))
        if look is not None and look.half == "gap":
            # 🔴 The arm's real two conditions, never the plan's paraphrase of them. The zone is
            # asked ONCE (a 15m close in it with a gap present); after that the order rests at
            # whatever gap edge is live. Saying "price must pull back" would describe a wait the
            # bot does not do — on 2026-10-01 it re-entered two minutes after the first trade.
            return (fate,
                    Confluence("Zone", look.latched, "A close in the re-entry zone"),
                    Confluence("Gap", look.has_gap, "A gap to rest the order on"))
        return (fate,)

    def _snap(self, w: dict, side: int, state: Optional[str] = None,
              reason: str = "") -> SetupSnapshot:
        ex = self._ex
        look = w["look"]
        pend = ex._pend_sec
        mine = (pend is not None and pend.dir == side and look is not None
                and pend.src == look.half)
        if state is None:
            state = RESTING if mine else WATCHING
        resting = state == RESTING
        return SetupSnapshot(
            key=w["key"], strategy=ex.strategy_name, symbol=ex._cfg.symbol or "",
            side=side, state=state, confluences=self._confluences(w, side),
            zone=look.zone if look else None,
            entry=float(pend.edge) if resting else None,
            stop=float(pend.sl) if resting else (look.stop if look else None),
            reason=reason, reentry_of=w["parent"], origin_ms=w["sos_ms"],
            planned_entry=look.price if look else None,
        )
