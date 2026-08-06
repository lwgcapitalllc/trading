"""alerts.py — what a trade looks like in Telegram.

Pure formatting. No MT5, no network, no state — so the exact text can be tested, and so changing
the wording never risks changing what the bot trades.

**The shape, per Aaron (2026-07-31).** An ENTRY is a standalone message. An EXIT is a Telegram
REPLY to that entry, so the two halves of a trade sit together in the thread and the outcome is
never separated from the setup it came from. That is why `format_entry` is paired with a stored
`message_id` in the bridge — the reply link is part of the format, not an extra.

**These are the only two TRADE-kind messages in the repo.** Everything else — starts, stops,
halts, link outages, review findings — is HEALTH and goes to a different chat. See
`algos/CLAUDE.md` → *Two rooms*.

**The house shape and the no-Markdown rule both live in `shared/alert_format.py`** — read its
docstring before changing any wording here. The short version: plain text always, because a lone
underscore in `mpc_sos_fade` or `XAUUSD.s` makes Telegram reject the whole message; and no
timestamp, because Telegram already prints the send time in the reader's own local clock.

One emoji per message, and each one means something: direction on the way in, outcome on the way
out. They are there so the eye can find a message in a scroll, not for decoration.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_SHARED = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from alert_format import alert  # noqa: E402

# Aaron's words, kept verbatim so the message says what he asked to see.
WIN, LOSE, BREAKEVEN = "WIN", "LOSE", "BREAKEVEN"

_VERDICT_MARK = {WIN: "✅", LOSE: "❌", BREAKEVEN: "➖"}

#: What the reader sees. The VALUE stays `LOSE` because `verdict()` is compared against it by the
#: bridge, the ledger and the tests; the LABEL is the noun, because the message describes an
#: outcome rather than issuing an instruction. Splitting the two is what lets the wording be
#: changed on Aaron's say-so without touching anything that reasons about a trade.
_VERDICT_LABEL = {WIN: "WIN", LOSE: "LOSS", BREAKEVEN: "BREAKEVEN"}




def _price(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"




def verdict(pnl_usd: float, r_multiple: Optional[float] = None,
            scratch_r: float = 0.15) -> str:
    """WIN / LOSE / BREAKEVEN for a closed trade.

    **BREAKEVEN is decided on R, not on dollars, and that is the point.** A trade whose stop was
    moved to entry and then hit is a scratch — but it still comes back a few dollars down after
    spread and commission. Calling that a LOSE would file a working risk rule alongside real
    losers and make the win rate read worse than the strategy behaves. So the VERDICT describes
    the trade and the DOLLAR FIGURE stays honest about the cost; Aaron asked for exactly that
    ("even if broke even but lost money due to commissions").

    Falls back to the sign of the P&L when R is unknown, which is the best that can be said then.
    """
    if r_multiple is not None and abs(r_multiple) <= scratch_r:
        return BREAKEVEN
    if pnl_usd > 0:
        return WIN
    if pnl_usd < 0:
        return LOSE
    return BREAKEVEN


def format_entry(*, strategy: str, symbol: str, direction: str, entry: float, stop: float,
                 lots: float, digits: int = 2, point: float = 0.01,
                 risk_usd: Optional[float] = None, risk_pct: Optional[float] = None,
                 when: Optional[datetime] = None) -> str:
    """The message that opens a trade's thread.

    Three groups, in the order the questions get asked: what it is and which way, the two prices
    that define it, then how big it is and what it costs to be wrong.

    ⚠ **The risk is stated HERE and nowhere else** (Aaron, 2026-08-05). The exit posts as a reply
    to this message, so restating "on $200.00 risked" there is repeating what is one tap above.

    ⚠ **"Risking", not "losing if stopped"** — a gap or a fast market can fill worse than the
    stop, so the smaller word is the accurate one. `_stamp` is gone: Telegram already prints the
    send time in the reader's own local clock, and a trade alert is always about now.
    """
    is_long = direction.upper().startswith("L")
    side = "LONG" if is_long else "SHORT"

    size = f"Size {lots:g} lots"
    if risk_usd is not None:
        pct = f" ({risk_pct:g}%)" if risk_pct is not None else ""
        size += f" · Risking ${risk_usd:,.2f}{pct}"

    return alert("📈" if is_long else "📉", "ENTRY", f"{side} {symbol}",
                 f"Entry {_price(entry, digits)} · Stop {_price(stop, digits)}",
                 size,
                 strategy)


def format_exit(*, strategy: str, symbol: str, exit_price: float, pnl_usd: float,
                r_multiple: Optional[float] = None, digits: int = 2,
                currency: str = "USD", scratch_r: float = 0.15,
                threaded: bool = True, exit_reason: str = "",
                when: Optional[datetime] = None) -> str:
    """The reply that closes a trade's thread.

    Outcome, money, price — and nothing about what was risked, because this message hangs under
    the entry that already said so.

    `threaded` says whether this really will post as a reply. When it does not — the entry alert
    never sent, so there is no message to reply to — the header carries the symbol, because a bare
    "WIN" floating in the group names no trade at all.

    `exit_reason` is a short parenthetical like `stop` or `stop moved to entry`. It is the
    difference between reading a number and understanding it: a −0.02R scratch and a −1.00R loser
    both exited at a stop, and only one of them is the risk rule working.
    """
    v = verdict(pnl_usd, r_multiple, scratch_r)
    verb = {WIN: "Made", LOSE: "Lost", BREAKEVEN: "Lost"}[v]
    if v == BREAKEVEN and pnl_usd > 0:
        verb = "Made"
    amount = f"{verb} ${abs(pnl_usd):,.2f}"
    r = f" · {r_multiple:+.2f}R" if r_multiple is not None else ""
    price = f"Exit {_price(exit_price, digits)}"
    if exit_reason:
        price += f" ({exit_reason})"

    return alert(_VERDICT_MARK[v], _VERDICT_LABEL[v], "" if threaded else symbol,
                 amount + r,
                 price)
