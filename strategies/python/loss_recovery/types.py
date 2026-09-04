"""loss_recovery/types.py — the contract, and nothing else.

No behaviour here. `engine.py` owns the state machine.

The point of this file is that the recovery rule is defined against a PROTOCOL rather than
against `sos_fade.Trade`. A recovery trade is triggered by "a strategy lost", which is a fact
every strategy in this repo can state, so wiring it to one strategy's concrete class would make
the second consumer a rewrite. See CLAUDE.md → "Why this is a package and not a flag on
sos_fade".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LossEvent(Protocol):
    """What the recovery engine needs to know about a primary trade that lost.

    `sos_fade.execution.Trade` satisfies this already, and so does any dataclass with the
    same three names — that is the whole reason it is a Protocol. `r` is signed and expressed in
    the PRIMARY trade's own risk units; the engine only reads its sign and magnitude to decide
    whether the trade was a real loss or a scratch.
    """

    dir: int
    exit_index: int
    r: float


@runtime_checkable
class LossEventWithEntry(LossEvent, Protocol):
    """A `LossEvent` that also knows where the primary trade got IN.

    Required only by `stop_mode="loss_entry"`, which puts the recovery's stop on the losing
    trade's own entry. ⚠ A loss event without it is REFUSED rather than quietly falling back to
    the structural stop — the fallback would report a rule nobody ran, and the two stops are ~4x
    apart. `sos_fade.execution.Trade` satisfies this unchanged.
    """

    entry_price: float


@dataclass(frozen=True)
class RecoveryTrade:
    """One recovery trade, fully resolved.

    Two R figures, kept separate on purpose and NOT interchangeable:

      `r`        this trade's outcome in ITS OWN risk units (entry → stop distance).
      `scaled_r` the same outcome as the ACCOUNT sees it, i.e. `r * risk_fraction`.

    A recovery trade is sized at a fraction of a normal trade, so booking `r` into a journal
    alongside primary trades would silently count it at full size — the exact class of unit
    error rule 15 is about. `scaled_r` is the one a portfolio adds up.
    """

    trigger_index: int  # bar the primary loss closed on — the thing that armed this
    signal_index: int  # bar the opposing external CHoCH printed on
    entry_index: int  # bar the fill happened on (signal_index + 1)
    entry_price: float
    stop_price: float  # far end of the CHoCH break leg — the structural stop
    direction: int  # +1 counter-long (a short lost), -1 counter-short
    risk: float  # abs(entry_price - stop_price); this trade's 1R in price
    exit_index: int
    exit_price: float
    r: float
    scaled_r: float
    exit_reason: str  # stop | soft | be | locked | trail | choch | time | horizon
    locked: bool  # did it ever reach the lock threshold?
    # Excursion, both NON-NEGATIVE magnitudes in THIS trade's own R: the furthest it ever ran in
    # favour, and the deepest it ever sat against. Reporting-only — nothing decides on either, so
    # they cannot move a fill. `max_adverse_r` is capped at the exit price on the closing bar, so
    # it can never describe a move made after the position was already gone. Multiply either by
    # `risk` and step it off `entry_price` to get the PRICE a chart draws.
    max_favourable_r: float
    max_adverse_r: float
    bars_held: int

    @property
    def is_win(self) -> bool:
        return self.r > 0.0


@dataclass(frozen=True)
class ArmedSignal:
    """A loss waiting for its CHoCH. Exposed so a live runner can show what it is waiting on.

    `expires_index` is None when the config sets no arming window — deliberately None rather
    than a large sentinel, because "no deadline" and "a deadline 100000 bars away" are different
    facts and a consumer that cannot tell them apart will eventually report the wrong one.
    """

    trigger_index: int
    want_direction: int
    expires_index: Optional[int]
