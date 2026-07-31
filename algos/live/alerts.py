"""alerts.py — what a trade looks like in Telegram.

Pure formatting. No MT5, no network, no state — so the exact text can be tested, and so changing
the wording never risks changing what the bot trades.

**The shape, per Aaron (2026-07-31).** An ENTRY is a standalone message. An EXIT is a Telegram
REPLY to that entry, so the two halves of a trade sit together in the thread and the outcome is
never separated from the setup it came from. That is why `format_entry` is paired with a stored
`message_id` in the bridge — the reply link is part of the format, not an extra.

Deliberately plain text, no Markdown. Every one of these messages carries a strategy name, a
symbol or a broker string, and those are full of underscores (`mpc_sos_fade`, `MT5_FFT`). A lone
underscore opens a Markdown italic that never closes and Telegram rejects the WHOLE message —
measured on the first real send. `notify.send_telegram` retries unformatted when that happens, but
the better answer is not to depend on the rescue: an alert should never need one.

One emoji per message, and each one means something: direction on the way in, outcome on the way
out. They are there so the eye can find a message in a scroll, not for decoration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# Aaron's words, kept verbatim so the message says what he asked to see.
WIN, LOSE, BREAKEVEN = "WIN", "LOSE", "BREAKEVEN"

_VERDICT_MARK = {WIN: "✅", LOSE: "❌", BREAKEVEN: "➖"}


def pip_size(digits: int, point: float) -> float:
    """The value of one pip, DERIVED from the symbol rather than hardcoded per instrument.

    MT5's convention: a pip is ten points on the 3- and 5-digit quotes (JPY pairs and the 5-digit
    majors), and one point everywhere else. On 2-digit gold that makes a pip 0.01, so a $17.25
    stop reads as 1,725 pips.

    Worth knowing because gold has no settled convention — plenty of desks call 0.10 a pip there
    and would read the same stop as 172.5. This rule is at least consistent across every symbol
    the suite might trade, and it changes with the broker's own `digits`, so a 3-digit gold feed
    would re-derive rather than inherit a wrong constant.
    """
    return point * 10 if digits in (3, 5) else point


def _price(value: float, digits: int) -> str:
    return f"{value:,.{digits}f}"


def _stamp(when: Optional[datetime]) -> str:
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%a %d %b %Y, %H:%M UTC")


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
                 when: Optional[datetime] = None) -> str:
    """The message that opens a trade's thread.

    Ordered the way a trade is read: what it is and which way, then the two prices that define
    it, then how far away the risk sits, then how big it is. Direction is on the top line because
    it is the one thing worth seeing without opening the message.
    """
    is_long = direction.upper().startswith("L")
    mark = "📈" if is_long else "📉"
    side = "LONG" if is_long else "SHORT"
    pips = abs(entry - stop) / pip_size(digits, point)

    return (
        f"{mark} ENTRY · {side}\n"
        f"{strategy} — {symbol}\n"
        f"\n"
        f"Entry: {_price(entry, digits)}\n"
        f"Stop: {_price(stop, digits)}\n"
        f"Stop distance: {pips:,.0f} pips\n"
        f"Lot size: {lots:g}\n"
        f"\n"
        f"{_stamp(when)}"
    )


def format_exit(*, strategy: str, symbol: str, exit_price: float, pnl_usd: float,
                r_multiple: Optional[float] = None, digits: int = 2,
                currency: str = "USD", scratch_r: float = 0.15,
                threaded: bool = True, when: Optional[datetime] = None) -> str:
    """The reply that closes a trade's thread.

    Outcome first, money second, price third — the order the questions actually get asked in.

    `threaded` says whether this will post as a reply to its own entry alert. When it does, the
    strategy and symbol are left OUT: the entry is one tap away and repeating it is noise. When
    it does not — the entry alert never sent, so there is no message to reply to — the header
    carries them, because a bare "WIN" floating in the group names no trade at all.
    """
    v = verdict(pnl_usd, r_multiple, scratch_r)
    money = f"{pnl_usd:+,.2f} {currency}"
    r = f"  ({r_multiple:+.2f}R)" if r_multiple is not None else ""
    head = f"{_VERDICT_MARK[v]} {v}" if threaded else f"{_VERDICT_MARK[v]} {v} — {strategy} · {symbol}"

    return (
        f"{head}\n"
        f"\n"
        f"P&L: {money}{r}\n"
        f"Exit: {_price(exit_price, digits)}\n"
        f"\n"
        f"{_stamp(when)}"
    )
