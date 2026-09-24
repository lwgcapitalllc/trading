"""Realign's side of the pre-trade setup contract (`backtest/setups.py`) — the signals room.

REPORTING ONLY. `RealignStrategy._step_core` hands this the tracker's armed setups and what the
order layer did, AFTER the bar is decided. Every price is copied from the tracker's own `Armed`
record. Nothing here is read back by a decision; proven by replay in `notes/setup_alerts.md`.

**What one setup is on this bot.** One armed false break: the 15m prints a shift against its own
trend, the tracker latches the swing it left standing as the target, and the setup waits up to
`realign_window_hrs` for the 5m to break against it and then realign. The trade is a MARKET order
on the realignment bar's close, so there is no resting-limit message: the thread goes

    15m false break arms the setup   -> the ROOT (the conditions so far, projected stop, target)
    the realignment fires, taken     -> ENTERED
    fires, refused by a rule         -> NO TRADE, naming the rule
    window closes / a newer false break replaces it / the 15m breaks on   -> NO TRADE

⚠ **The key is the ARM TIME, never a bar number** — a live re-warm renumbers bars (the 2026-09-15
duplicate-thread defect in `sos_fade`). Arming is a 15m close, so a re-warm reproduces the time.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

from backtest.setups import DEAD, FILLED, WATCHING, Confluence, SetupSnapshot


def _finite(x) -> Optional[float]:
    return float(x) if x is not None and math.isfinite(x) else None


class RealignSetupWatch:
    """One snapshot stream per armed setup, keyed on the tracker's own `Armed` record."""

    #: How `key` is spelled — read by the live alert layer across a promote. Change it whenever
    #: the key format changes (`algos/live/setup_alerts.py::_key_scheme`).
    key_scheme = "realign-arm-time-v1"

    def __init__(self, config, strategy_name: str = "RealignStrategy") -> None:
        self._cfg = config
        self._name = strategy_name
        self._open: Dict[int, object] = {}  # id(Armed) -> the Armed record the tracker holds
        self._last: List[SetupSnapshot] = []
        self._done: List[SetupSnapshot] = []
        self._announced: set = set()  # keys already handed out as tradeable — see `_tradeable`

    def _key(self, a) -> str:
        return f"{self._name}:{'L' if a.dir > 0 else 'S'}:t{a.armed_ms}"

    # ── fed once per bar by the strategy, after the order is decided ─────────────────────────
    def observe(self, strat, rs, time_ms: int, was_in_position: bool) -> None:
        ex = strat.execution
        now = {id(a): a for a in strat.tracker._armed}
        new_dirs = {a.dir for k, a in now.items() if k not in self._open}
        for k, a in list(self._open.items()):
            if k in now:
                continue
            if rs.trigger_dir == a.dir:
                if not was_in_position and ex._pos_dir == a.dir:
                    self._end(strat, a, FILLED, "entered at market on the 5m realignment")
                elif was_in_position:
                    self._end(strat, a, DEAD, "the realignment fired while a trade was open")
                else:
                    why = getattr(ex, "refusal", None) or "the order was not placed"
                    self._end(strat, a, DEAD, f"the realignment fired, and {why}")
            elif a.dir in new_dirs:
                self._end(strat, a, DEAD, "a newer 15m false break replaced it")
            elif time_ms - a.armed_ms > self._cfg.realign_window_hrs * 3_600_000:
                self._end(
                    strat,
                    a,
                    DEAD,
                    f"the {self._cfg.realign_window_hrs:g}-hour window closed with no realignment",
                )
            else:
                self._end(strat, a, DEAD, "the 15m broke on the same way — the false break became a trend")
            del self._open[k]
        self._open.update(now)
        self._last = [self._snap(strat, a, WATCHING) for a in now.values()]

    # ── snapshots ────────────────────────────────────────────────────────────────────────────
    def _confluences(self, strat, a, fired: bool):
        cfg = self._cfg
        long_ = a.dir > 0
        was, against = ("up", "bearish") if long_ else ("down", "bullish")
        out = [
            Confluence("15m trend", True, f"the 15m trend was {was}"),
            Confluence(
                "False break",
                True,
                f"a 15m {against} shift — the first against the trend",
            ),
        ]
        if cfg.realign_mom_days is not None:
            m = getattr(strat.execution, "mom_dir", None)
            ok = m is not None and m != a.dir
            out.append(
                Confluence(
                    f"{cfg.realign_mom_days}-day momentum",
                    ok,
                    ("against the trade — this setup fades it" if ok
                     else "not read yet" if m is None
                     else "with the trade — the order would be refused"),
                )
            )
        out.append(
            Confluence(
                "5m counter move",
                a.counter_bar is not None or fired,
                "the 5m broke against the trade" if a.counter_bar is not None or fired
                else "waiting for the 5m to break against the trade",
            )
        )
        out.append(
            Confluence(
                "5m realignment",
                fired,
                "the 5m shifted back with the trend" if fired
                else "waiting for the 5m to shift back with the trend",
            )
        )
        return tuple(out)

    def _snap(self, strat, a, state: str, reason: str = "") -> SetupSnapshot:
        cfg = self._cfg
        stop = _finite(a.counter_ext)
        if stop is not None:
            stop -= a.dir * cfg.realign_sl_buf_tk * cfg.mintick
        return SetupSnapshot(
            key=self._key(a),
            strategy=self._name,
            symbol=cfg.symbol or "",
            side=a.dir,
            state=state,
            confluences=self._confluences(strat, a, fired=state == FILLED),
            zone=None,  # a market entry — no range and no resting price
            entry=None,
            stop=stop,
            targets=(a.target,) if _finite(a.target) is not None else (),
            reason=reason,
            tradeable=self._tradeable(strat, a, state),
        )

    def _tradeable(self, strat, a, state: str) -> bool:
        """Announce a setup only while the momentum rule would let it trade.

        🔴 **MEASURED 2026-09-24, `realign_1`, PU Prime M5 2020-01 → 2026-09**: announcing every
        armed false break sent 9.2 roots a month and 15% became trades; announcing only while the
        20-day momentum is against the trade (the rule the order layer refuses on) sent 4.6 a month
        at 31% — and all 115 trades were still announced first. The rest were setups the bot would
        refuse at the trigger.

        ⚠ **This is NOT the "already decided" use `backtest/setups.py` describes**: momentum is
        re-read every bar and can turn in the setup's favour inside its window. The alert layer
        checks `tradeable` before any bookkeeping for exactly this case, so the root arrives the
        bar it turns. Two rules keep it safe: a setup once announced stays tradeable, so its
        outcome still closes the thread; and a FILL is always tradeable, so no trade reaches the
        broker unannounced (`algos/tools/setup_alert_rate.py` checks that end to end)."""
        key = self._key(a)
        if state == FILLED or key in self._announced:
            ok = True
        elif state != WATCHING:
            ok = False
        else:
            m = getattr(strat.execution, "mom_dir", None)
            ok = self._cfg.realign_mom_days is None or (m is not None and m != a.dir)
        if ok and state == WATCHING:
            self._announced.add(key)
        elif state != WATCHING:
            self._announced.discard(key)
        return ok

    def _end(self, strat, a, state: str, reason: str) -> None:
        self._done.append(self._snap(strat, a, state, reason))

    # ── the contract ─────────────────────────────────────────────────────────────────────────
    def live_setups(self) -> List[SetupSnapshot]:
        return list(self._done) + list(self._last)

    def drain_setups(self) -> List[SetupSnapshot]:
        out = self.live_setups()
        self._done.clear()
        return out
