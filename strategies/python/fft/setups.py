"""FFT's side of the pre-trade setup contract (`backtest/setups.py`) — the signals room.

REPORTING ONLY. `FftStrategy.step` hands this what it has ALREADY decided — the touches recorded
this minute, the fill, and the order for the next minute — and every price below is copied from
that order. Nothing here is read back by a decision. Proven by replay: `notes/setup_alerts.md`.

**What one setup is on this bot.** One touch of one leg: the 5m fib's leg, identified by its
direction and the 5m candle its 1.0 is anchored on, and whether this is its FIRST touch or its
second. The bot rests a buy (sell) limit at the 61.8 whenever every rule passes, and the leg is
spent the first time price reaches the 61.8, traded or not.

    rules pass, a limit rests      -> the ROOT, and the LIMIT RESTING reply
    rules stop passing             -> the limit is WITHDRAWN, with the rule that pulled it
    the limit fills                -> ENTERED
    price reaches the 61.8 while a rule refuses it   -> NO TRADE, naming the rule
    the fib moves to another leg first               -> NO TRADE

⚠ **Nothing is announced until a limit has actually rested.** A leg that never passed every rule
is a leg the bot was never going to trade, and the study counts roughly sixteen such first touches
for every trade (2,644 touches, 157 trades, 2020-01 → 2025-09). Announcing them would bury the
channel, the failure `extreme_leg/notes/setup_alerts.md` measured. A fill always has a limit
resting the minute before, so no trade reaches the broker unannounced.

⚠ **The key is TIME, never a bar number.** The leg's 1.0 anchor is a 5m index this strategy
counts itself, and every live re-warm renumbers it (the 2026-09-15 duplicate-thread defect in
`sos_fade`). The key is the START TIME of that 5m candle. A leg whose anchor is older than the
5m candles kept has no stable key and is never announced.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from backtest.setups import DEAD, FILLED, RESTING, WATCHING, Confluence, SetupSnapshot


def _finite(x) -> Optional[float]:
    return float(x) if x is not None and math.isfinite(x) else None


class _Episode:
    __slots__ = ("key", "leg", "kind", "side", "entry", "stop", "target", "touched", "why")

    def __init__(self, key: str, leg: Tuple[int, int], kind: str) -> None:
        self.key = key
        self.leg = leg  # (direction, 5m anchor index) — the strategy's own leg identity
        self.kind = kind
        self.side = leg[0]
        self.entry: Optional[float] = None
        self.stop: Optional[float] = None
        self.target: Optional[float] = None
        self.touched = False  # the 61.8 printed; the limit rests on only because the ask lagged
        self.why: Tuple[str, ...] = ()  # the rule keeping the limit off the book right now


class FftSetupWatch:
    """At most one open setup per leg-and-touch, turned into `SetupSnapshot`s."""

    #: How `key` is spelled — read by the live alert layer across a promote. Change it whenever
    #: the key format changes (`algos/live/setup_alerts.py::_key_scheme`).
    key_scheme = "fft-time-v1"

    def __init__(self, config, why_text: Dict[str, str], strategy_name: str = "FftStrategy"):
        self._cfg = config
        self._why = why_text
        self._name = strategy_name
        self._open: Dict[Tuple[int, int, str], _Episode] = {}
        self._done: List[SetupSnapshot] = []

    # ── fed once per minute by the strategy, after the next minute's order is decided ────────
    def observe(self, strat, touches, fill, decision) -> None:
        # 1. Touches this minute spend their leg. A traded one is a fill; a refused one is over.
        for t in touches:
            ep = self._open.get((t.key[0], t.key[1], t.kind))
            if ep is None:
                continue
            if t.traded:
                self._end(ep, FILLED, f"the limit at the 61.8 filled at {t.fill_price:g}")
            elif strat._carry_setup is t:
                ep.touched = True  # the bid reached it, the ask has not: the limit still rests
            else:
                self._end(ep, DEAD, "price reached the 61.8 while " + self._rule(t.why))

        # 2. A limit that outlived its touch fills later, or stops resting when TP1 prints.
        for ep in [e for e in self._open.values() if e.touched]:
            if fill is not None and tuple(fill.key) == ep.leg:
                self._end(ep, FILLED, f"the limit at the 61.8 filled at {fill.price:g}")
            elif strat._carry is None:
                self._end(ep, DEAD, "TP1 printed before the broker's ask reached the limit")

        # 3. The order for the next minute: open, update or pause the setup it belongs to.
        live = None
        if decision:
            k = decision["key"]
            live = (k[0], k[1], decision["kind"])
            order = decision.get("order")
            ep = self._open.get(live)
            if order is not None:
                if ep is None:
                    key = self._key(strat, k, decision["kind"])
                    if key is None:
                        live = None
                    else:
                        ep = self._open[live] = _Episode(key, tuple(k), decision["kind"])
                if ep is not None:
                    pend = order["pend"]
                    ep.entry, ep.stop, ep.target = pend.edge, pend.sl, pend.tp1
                    ep.why = ()
            elif ep is not None:
                ep.why = (self._rule(decision.get("why")),)

        # 4. Every other open setup: its leg is still the chart's, or it has gone.
        r = strat.row5
        for slot, ep in list(self._open.items()):
            if slot == live or ep.touched:
                continue
            if r is not None and (r.dir, r.origin) == ep.leg:
                # A run past TP3 is the fib EXTENDING: the limit comes back at the new 61.8 on the
                # next 5m close, and the thread says so once as a moved order. Naming it as a pull
                # posted a WITHDRAWN and a MOVED for every extension (2026-06 → 09 replay).
                ep.why = () if strat._dropped else (self._paused(strat),)
            elif r is None:
                ep.why = ("the 5m fib is not drawn right now",)
            else:
                self._end(ep, DEAD, "the 5m fib moved to a new leg before price came back")

    # ── wording — the strategy's own sentences, never re-derived ────────────────────────────
    def _rule(self, code: Optional[str]) -> str:
        if not code:
            return "no order was resting"
        if code.startswith("unfilled"):
            return "the limit was not filled"
        return self._why.get(code, f"refusal code {code}")

    def _paused(self, strat) -> str:
        r = strat.row5
        if r.sdir != r.dir:
            return "the 5m trend is not the fib's direction"
        return "the 5m close is not beyond the 61.8"

    def _key(self, strat, leg, kind: str) -> Optional[str]:
        c = strat._candles5.get(leg[1])
        if c is None:
            return None
        side = "L" if leg[0] > 0 else "S"
        return f"{self._name}:{side}:t{c.start_ms}:{kind}"

    # ── snapshots ────────────────────────────────────────────────────────────────────────────
    def _confluences(self, ep: _Episode) -> Tuple[Confluence, ...]:
        cfg = self._cfg
        long_ = ep.side > 0
        up, down = ("up", "down") if long_ else ("down", "up")
        out = [
            Confluence("5m trend", True, f"5m trend {up}, with the fib"),
            Confluence(
                "First leg",
                True,
                "the 5m first leg since the shift"
                if cfg.max_bos == 0
                else f"at most {cfg.max_bos} 5m BOS since the shift",
            ),
        ]
        if cfg.req_15m:
            out.append(Confluence("15m trend", True, f"15m trend {up}, with the trade"))
        if cfg.req_1m_against:
            out.append(
                Confluence("1m pullback", True, f"1m trend {down}, no 1m break {up} since the extreme")
            )
        if ep.kind == "second":
            out.append(Confluence("Second touch", True, "TP1 printed after the first touch"))
        return tuple(out)

    def _snap(self, ep: _Episode, state: str, reason: str = "") -> SetupSnapshot:
        resting = state == RESTING
        return SetupSnapshot(
            key=ep.key,
            strategy=self._name,
            symbol=self._cfg.symbol or "",
            side=ep.side,
            state=state,
            confluences=self._confluences(ep),
            zone=None,  # one price, the 61.8 — no range to report
            entry=_finite(ep.entry) if resting else None,
            stop=_finite(ep.stop),
            targets=(ep.target,) if _finite(ep.target) is not None else (),
            reason=reason,
            paused_by=ep.why if state == WATCHING else (),
        )

    def _end(self, ep: _Episode, state: str, reason: str) -> None:
        self._done.append(self._snap(ep, state, reason))
        self._open.pop((ep.leg[0], ep.leg[1], ep.kind), None)

    # ── the contract ─────────────────────────────────────────────────────────────────────────
    def live_setups(self) -> List[SetupSnapshot]:
        out = list(self._done)
        for ep in self._open.values():
            out.append(self._snap(ep, WATCHING if ep.why else RESTING))
        return out

    def drain_setups(self) -> List[SetupSnapshot]:
        out = self.live_setups()
        self._done.clear()
        return out
