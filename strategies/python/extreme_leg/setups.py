"""The extreme-leg bot's side of the pre-trade setup contract (`backtest/setups.py`).

REPORTING ONLY. Nothing here is read back by a decision: `ExtremeLegStrategy.step` hands this the
finished `LegState` AFTER the order has been decided, and every price below is copied from that
state. Proven by replay, not by this sentence — see `notes/setup_alerts.md`.

**What a "setup" is on this bot.** A liquidity sweep ARMS a side for `swept_minutes`; the trade
fires at market on the first 5m shift of structure inside that window that clears the refusal
ladder. So one setup is one ARMED EPISODE on one side:

    sweep arms the side        -> tracked, NOT announced (see the measurement in `_observe_side`)
    a shift fires, refused     -> WATCHING + blocked_by — the root and the BLOCKED reply; it may
                                  still fire again inside the window
    a shift fires, taken       -> FILLED
    the window closes          -> DEAD, with the last refusal if there was one

⚠ **The key is the time of the sweep that OPENED the episode**, never a bar number (a re-warm
renumbers bars — the 2026-09-15 duplicate-thread defect in `sos_fade`). A fresh sweep while the side
is still armed EXTENDS the episode under the same key; a new key needs the side to have disarmed or
the old episode to have ended.

⚠ **An episode opens only on a sweep bar.** After a fill the side is usually still armed; reopening
it there would reuse a key the alert layer has just forgotten and post a second root.
"""

from __future__ import annotations

import math
from typing import List, Optional

from backtest.setups import DEAD, FILLED, WATCHING, Confluence, SetupSnapshot

_FAMILY_BITS = (
    ("H4", 1, 2), ("session", 4, 8), ("daily", 16, 32), ("weekly", 64, 128),
)


def _finite(x) -> Optional[float]:
    return float(x) if x is not None and math.isfinite(x) else None


class _Episode:
    __slots__ = ("key", "sweep_ms", "families", "blocked", "last_block", "announced", "shifted")

    def __init__(self, key: str, sweep_ms: int) -> None:
        self.key = key
        self.sweep_ms = sweep_ms
        self.families: set = set()
        self.blocked: tuple = ()
        self.last_block: str = ""
        self.announced = False
        self.shifted = False


class LegSetupWatch:
    """One armed episode per side, turned into `SetupSnapshot`s."""

    #: How `key` is spelled — read by the live alert layer across a promote. Change it whenever
    #: the key format changes (`algos/live/setup_alerts.py::_key_scheme`).
    key_scheme = "xleg-time-v1"

    def __init__(self, config, strategy_name: str = "ExtremeLegStrategy") -> None:
        self._cfg = config
        self._name = strategy_name
        self._ep = {1: None, -1: None}
        self._last = {1: None, -1: None}
        self._done: List[SetupSnapshot] = []

    # ── fed once per bar by the strategy, after the order is decided ─────────────────────────
    def observe(self, st, was_busy: bool) -> None:
        for d in (1, -1):
            self._observe_side(st, d, was_busy)

    def _observe_side(self, st, d: int, was_busy: bool) -> None:
        long_ = d > 0
        armed = st.low_armed if long_ else st.high_armed
        age = st.low_age if long_ else st.high_age
        swept_bits = st.swept_now
        ep: Optional[_Episode] = self._ep[d]

        if ep is None:
            if not armed:
                return
            # An episode opens ONLY on a sweep bar. That is what keeps a still-armed side from
            # reopening after a fill, and what keeps a replay that starts mid-window (no sweep
            # time known, so no stable key) silent rather than keyed on a bar a restart moves.
            if age != 0:
                return
            sweep_ms = st.ts_ms
            side = "L" if long_ else "S"
            ep = _Episode(f"{self._name}:{side}:t{sweep_ms}", sweep_ms)
            self._ep[d] = ep

        if age == 0:
            for name, lo_bit, hi_bit in _FAMILY_BITS:
                if swept_bits & (lo_bit if long_ else hi_bit):
                    ep.families.add(name)

        raw = st.raw_long if long_ else st.raw_short
        go = st.go_long if long_ else st.go_short
        code = st.blk_long if long_ else st.blk_short
        entered = st.entered == d

        # 🔴 **Announced on the SHIFT, not on the sweep — MEASURED 2026-09-16, 189,331 PU Prime
        # M5 bars (2024-01 → 2026-09), `backtest/tools/alert_rate.py`.** Every armed episode:
        # 91 roots a month, 2% became trades. Episodes where the refusal ladder would already
        # pass: 46 a month, 3%. On the shift: 7.1 a month, 23% — the same order as the SOS Fade
        # bot's channel. A market-entry bot has no lead time to give once the shift prints, so a
        # root sent earlier is a guess, and a channel wrong 97% of the time goes unread.
        # A fill always has its shift, so no trade reaches the broker unannounced.
        if raw or entered:
            ep.shifted = True
            ep.announced = True

        if entered:
            self._end(st, d, FILLED, "entered at market on the 5m shift of structure")
            return

        blocked: tuple = ()
        if raw and code:
            from .execution import BLOCK_TEXT
            blocked = (BLOCK_TEXT.get(code, f"refusal code {code}"),)
        elif go and not entered:
            blocked = (("a trade is already open" if was_busy
                        else "the account's risk budget had no room"),)
        if blocked:
            ep.blocked = blocked
            ep.last_block = blocked[0]
        else:
            # A refusal is a fact about the bar it happened on; the message layer sends it once.
            ep.blocked = ()

        if not armed:
            why = f"the sweep's {self._cfg.swept_minutes}-minute window closed"
            why += (f" — last refusal: {ep.last_block}" if ep.last_block
                    else " with no 5m shift of structure")
            self._end(st, d, DEAD, why)
            return
        self._last[d] = self._snap(st, d, WATCHING) if ep.announced else None

    # ── snapshots ────────────────────────────────────────────────────────────────────────────
    def _snap(self, st, d: int, state: str, reason: str = "") -> SetupSnapshot:
        cfg = self._cfg
        ep = self._ep[d]
        long_ = d > 0
        fams = sorted(ep.families)
        conf = [Confluence(
            "Sweep", True,
            ("Swept " + " + ".join(fams) + (" low" if long_ else " high")) if fams
            else "level swept",
        )]
        if cfg.req_counter_trend:
            want = -1 if long_ else 1
            ok = st.dir15 == want
            conf.append(Confluence(
                "15m trend", ok,
                ("15m trend " + ("down" if long_ else "up") + ", against the trade") if ok
                else "15m trend not against the trade yet",
            ))
        conf.append(Confluence(
            "Shift of structure", ep.shifted,
            "5m shift confirmed" if ep.shifted else "waiting for the 5m shift",
        ))
        stop = _finite(st.stop_long if long_ else st.stop_short)
        tp = _finite(st.tp_long if long_ else st.tp_short)
        return SetupSnapshot(
            key=ep.key, strategy=self._name, symbol=cfg.symbol or "", side=d, state=state,
            confluences=tuple(conf), zone=None, entry=None, stop=stop,
            targets=(tp,) if tp is not None else (),
            blocked_by=ep.blocked if state == WATCHING else (),
            reason=reason,
            # A side switched off can never trade; everything else can still change.
            tradeable=bool(cfg.exec_longs if long_ else cfg.exec_shorts),
        )

    def _end(self, st, d: int, state: str, reason: str) -> None:
        # An episode never announced ends in silence: there is no thread to close.
        if self._ep[d].announced:
            self._done.append(self._snap(st, d, state, reason))
        self._ep[d] = None
        self._last[d] = None

    # ── the contract ─────────────────────────────────────────────────────────────────────────
    def live_setups(self) -> List[SetupSnapshot]:
        return list(self._done) + [s for s in (self._last[1], self._last[-1]) if s is not None]

    def drain_setups(self) -> List[SetupSnapshot]:
        out = self.live_setups()
        self._done.clear()
        return out
