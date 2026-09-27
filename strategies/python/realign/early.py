"""EarlyTrigger1m — the 1-minute realignment that may fire BEFORE the 5-minute one.

`realign_early_1m` (config). One object per strategy, fed every CLOSED 1m bar by the dual clock
(`dual.py`), and only while the switch is on.

The rule, written long (the short is the mirror):

  * A setup is eligible once the 5m has gone counter inside the dip — the tracker holds a
    counter extreme for it, as of the LAST CLOSED 5m bar. Before that there is no dip and no stop.
  * On the 1m, a bullish SHIFT (CHoCH, the engine's `bull_sos`) marks the chain; a following
    plain bullish BREAK (`bull_bos` on a bar that is not itself a shift) completes it and FIRES.
  * Any bearish 1m break (BOS or shift) resets the chain.
  * The stop extreme is the lower of the tracker's counter extreme and every closed 1m low since
    the last closed 5m bar. The order layer adds `realign_sl_buf_tk`, as for the 5m trigger.

🔴 **NO LOOKAHEAD, AND THIS IS WHERE IT WOULD HIDE.** A 1m bar reaches `update` only once it has
closed, and only after every 5m bar that closed at or before its open has been stepped (the
merge rule in `dual.py`). So the tracker state read here is the last CLOSED 5m bar's, never the
forming one's, and the running 1m extreme covers exactly the closed 1m bars inside the forming
5m bar. ⚠ One information lag is accepted on purpose: the 15m bar that closes on a 5m boundary is
only published when that next 5m bar closes (`htf.py`), so a 1m bar inside that 5m bar still
sees the setup the 15m close may be about to kill. That is the 5m path's own publication delay,
and it uses LESS information than was available, never more.

🔴 **THE STRUCTURE IS THE CANONICAL ENGINE** (`engines/market_structure`), at this bot's own swing
length (`htf.MAJOR_LENGTH`), fed every 1m bar whether or not anything is armed — it is a streaming
state machine and skipping bars would compute over a history that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .htf import MAJOR_LENGTH  # also puts `engines/` on the path

from market_structure import Bar, StructureEngine  # noqa: E402  — the canonical engine


@dataclass
class EarlyFire:
    """One 1m trigger, before the order layer has had its say."""
    armed: object          # the tracker's `Armed` record
    dir: int
    stop_ext: float        # the dip extreme — the order layer adds the tick buffer
    target: float


class EarlyTrigger1m:
    def __init__(self, cfg, major_length: int = MAJOR_LENGTH) -> None:
        self._cfg = cfg
        self._engine = StructureEngine(major_length=major_length)
        self._n = 0
        # Extremes of the CLOSED 1m bars since the last closed 5m bar. `None` = none yet.
        self._run_low: Optional[float] = None
        self._run_high: Optional[float] = None

    def on_primary_closed(self) -> None:
        """A 5m bar has been stepped: its range is now inside the tracker's counter extreme."""
        self._run_low = self._run_high = None

    def update(self, time_ms: int, o: float, h: float, l: float, c: float,
               armed: List[object], bucket_ms: int) -> List[EarlyFire]:
        """Fold one CLOSED 1m bar in. Returns every setup whose chain completed on it.

        `armed` is the tracker's live list as of the last closed 5m bar. `bucket_ms` is the open
        time of the 5m bar this 1m bar sits inside — the setup's expiry is judged on it exactly as
        the tracker would judge that 5m bar.
        """
        ev = self._engine.update(Bar(index=self._n, open=o, high=h, low=l, close=c)).external
        self._n += 1
        self._run_low = l if self._run_low is None else min(self._run_low, l)
        self._run_high = h if self._run_high is None else max(self._run_high, h)

        window_ms = int(self._cfg.realign_window_hrs * 3_600_000)
        out: List[EarlyFire] = []
        for a in armed:
            if a.counter_ext is None:
                continue                 # the 5m has not gone counter yet — no dip, no stop
            if bucket_ms - a.armed_ms > window_ms:
                continue                 # the tracker kills it on this 5m bar
            d = a.dir
            if d > 0:
                counter = ev.bear_bos or ev.bear_sos
                with_sos = ev.bull_sos
                with_bos = ev.bull_bos and not ev.bull_sos
            else:
                counter = ev.bull_bos or ev.bull_sos
                with_sos = ev.bear_sos
                with_bos = ev.bear_bos and not ev.bear_sos
            if counter:
                a.m1_sos_seen = False
            if with_sos:
                a.m1_sos_seen = True
            if with_bos and a.m1_sos_seen:
                ext = (min(a.counter_ext, self._run_low) if d > 0
                       else max(a.counter_ext, self._run_high))
                out.append(EarlyFire(armed=a, dir=d, stop_ext=ext, target=a.target))
        return out
