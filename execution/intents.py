"""What a strategy ASKS FOR — the one vocabulary the backtest and the live bot both speak.

🔴 **THIS EXISTS SO A FEATURE IS BUILT ONCE.** Before it, a strategy decided AND booked its own
fill in the same step, and `algos/live/bridge.py` separately re-derived what the position should
look like so it could make the broker match. That mirror is why every new order shape was two
builds and why the bridge carries SIX refusals, each one "the strategy can do this and the live
path was never taught it". Scale-in is one of them.

**The split, and it is the whole design:**

  * the STRATEGY decides — what to open, where the stop goes, how much to bank;
  * an EXECUTOR carries it out — a simulator against bars, or a broker over the wire;
  * an ACCOUNT sizes it — and may refuse.

Nothing here knows what a bar is, what MetaTrader is, or what a lot is. That is the point: an
intent is a REQUEST, and the two executors are the only things that differ.

⚠ **An intent is not a fill.** It is what was asked for; `FillReport` is what happened. Keeping
them separate is what lets the live side answer *rejected* or *partially filled* — the two answers
a backtest never has to give, and the two the old design had nowhere to put. **A strategy that
assumes its own fill cannot be run against a broker without a second implementation to paper over
the difference, and that second implementation was the duplication.**

⚠ **Every field is what the STRATEGY knows.** Quantity is in the strategy's own units, never lots
— converting to a venue's lot count needs the broker's balance, its volume band and the account's
remaining risk, none of which a strategy can see. That conversion stays at the one sizing seam it
already lives at, on the executor's side of this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IntentKind(str, Enum):
    """Every order-shaped thing a strategy in this repo asks for. There are four.

    ⚠ **The list is short because it was MEASURED, not designed** — the shipped strategy produces
    exactly three fills (an entry, a partial exit, and the banking of its added lots) plus a stop
    it re-states each bar. A vocabulary invented from imagination would have a dozen entries and
    would be wrong in both directions: unused kinds nobody implements, and the one real case
    missing.

    ⚠ **`ADD` is deliberately NOT `OPEN`.** An add is more size on a position that is still open,
    sharing one stop that ratchets; an open starts a trade. Collapsing them is exactly the
    confusion that made the live path treat a re-entry's slot as if it could serve a scale-in.
    """

    OPEN = "open"
    ADD = "add"
    CLOSE_PORTION = "close_portion"
    MOVE_STOP = "move_stop"


@dataclass(frozen=True)
class OrderIntent:
    """One instruction, in the strategy's own terms. Immutable on purpose.

    ⚠ **Frozen because an intent is a REQUEST that has been made.** The old code mutated its
    pending order in place while deciding, which is how a shift could carry into a later replay;
    a request that can be edited after it is submitted is a request nobody can reconcile against.

    ⚠ **`price = None` means AT MARKET**, and it is three-state against a price of 0.0, which
    would be a real (absurd) limit. Never read this falsily.
    """

    kind: IntentKind
    #: +1 long, -1 short. The direction of the POSITION, not of this instruction — closing a long
    #: is still `direction = +1`, because it names the trade being acted on.
    direction: int
    #: Strategy units, never lots. `None` on MOVE_STOP, which names no quantity.
    qty: Optional[float] = None
    #: The limit to rest at, or `None` for market. See the note above on the three-state.
    price: Optional[float] = None
    #: Where the protective stop belongs after this instruction. Carried on OPEN and MOVE_STOP.
    stop: Optional[float] = None
    #: Why, in the strategy's own words — the exit tag for a close, the entry method for an open.
    #: It reaches the ledger and the chart, so it is the reader's label, not an internal code.
    reason: str = ""
    #: Anything the executor needs that is not universal. Kept explicit rather than **kwargs so a
    #: typo is a missing key at the seam rather than a silently ignored instruction.
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {self.direction!r}")
        if self.kind is IntentKind.MOVE_STOP:
            if self.stop is None:
                raise ValueError("MOVE_STOP must carry the stop it is moving to")
            if self.qty is not None:
                raise ValueError("MOVE_STOP names no quantity — it moves the whole position's stop")
        else:
            if self.qty is None or self.qty <= 0:
                raise ValueError(f"{self.kind.value} needs a positive quantity, got {self.qty!r}")


@dataclass(frozen=True)
class FillReport:
    """What actually happened. The answer to exactly one `OrderIntent`.

    🔴 **THIS IS THE HALF THE OLD DESIGN HAD NOWHERE TO PUT.** A backtest fills what it asks for,
    so the strategy booked its own trade and moved on. A broker can refuse, or fill part of it,
    and the live layer existed largely to reconcile that difference after the fact. With the
    answer travelling back through the same seam the request went out on, both sides say it the
    same way and the strategy handles it once.

    ⚠ **`filled_qty = 0.0` with `rejected_reason` set is a REFUSAL; `filled_qty = 0.0` with no
    reason is a bug**, not a quiet no. This repo's rule 1 in the one place it matters most: never
    let *no* and *could not ask* be the same value.

    ⚠ **A partial fill is `filled_qty < intent.qty` and is NOT an error.** It is the honest answer
    to a request the venue could only partly meet, and a strategy must be able to hold a position
    smaller than it asked for rather than assume it got what it wanted.
    """

    intent: OrderIntent
    filled_qty: float
    #: The price it actually transacted at. `None` only when nothing filled.
    fill_price: Optional[float] = None
    #: Set when the venue (or the account) refused. Reader-facing.
    rejected_reason: Optional[str] = None
    #: Venue's own identifier, when there is one. Absent in a backtest, and that is not a failure.
    order_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.filled_qty < 0:
            raise ValueError(f"filled_qty cannot be negative, got {self.filled_qty!r}")
        if self.filled_qty > 0 and self.fill_price is None:
            raise ValueError("a fill must carry the price it transacted at")
        if self.filled_qty == 0 and not self.rejected_reason:
            raise ValueError(
                "nothing filled and no reason given — a silent zero is indistinguishable from "
                "a refusal nobody recorded (rule 1). Say why, or report a fill."
            )

    @property
    def rejected(self) -> bool:
        return self.filled_qty == 0.0

    @property
    def partial(self) -> bool:
        """Filled, but less than asked. MOVE_STOP names no quantity, so it is never partial."""
        want = self.intent.qty
        return want is not None and 0.0 < self.filled_qty < want
