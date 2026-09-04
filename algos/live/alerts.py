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
underscore in `sos_fade` or `XAUUSD.s` makes Telegram reject the whole message; and no
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

from alert_format import alert, joined  # noqa: E402

# 🔴 **NOTHING FROM `backtest` OR `strategies` MAY BE IMPORTED AT THIS MODULE'S TOP LEVEL, and
# this is enforced by the version pin rather than by discipline.** `bridge.py` imports this file,
# `runner.py` imports `bridge`, and all of that happens BEFORE `runner._bind_code()` puts the
# frozen `deployed/` snapshot on `sys.path`. An import here therefore resolves against the REPO,
# and the bot would then run a mix of deployed and repo code while reporting the deployed
# version — the exact thing the pin exists to prevent.
#
# It is not theoretical: a module-level `from backtest.setups import FILLED` here took the live
# bot down on 2026-08-13 and it crash-looped until the import moved. `version.py` refused every
# start with `Cannot freeze this deployment: backtest.setups was already imported from the repo
# before the snapshot was bound`, which is the guard working exactly as designed — it named the
# module, named the cause and told us to move the import later.
#
# The same rule binds any future need for a strategy-side constant in this file: import it INSIDE
# the function that uses it.

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


def verdict(pnl_usd: float, r_multiple: Optional[float] = None, scratch_r: float = 0.15) -> str:
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


# ── the signals channel — a setup, before the outcome is known ──────────────────────────────
#
# These are SIGNAL-kind messages and go to their own room (`algos/CLAUDE.md` → *Two rooms*, now
# three). They are read when you have time, not the moment they arrive, and there are roughly five
# times as many of them as there are fills — which is exactly why they must not share the chat
# that carries fills.
#
# ⚠ **Every number here is COPIED from the strategy's own `SetupSnapshot`.** Nothing in this file
# computes a price, a level or a confluence. An alert naming a level the bot never traded is worse
# than no alert, because you would act on it — `docs/LIVE_SETUP_ALERTS.md` §9.


def _zone_text(zone, digits: int) -> str:
    """The tradeable RANGE, shallow-to-deep, always printed low-to-high.

    A long's zone runs 0.5 down to 0.886 and a short's runs up, so the raw pair arrives in either
    order. Printing it as stored would render `3,418.60 – 3,405.10` on one side and the reverse on
    the other, and a reader comparing two messages would read the inconsistency as a bug in the
    setup rather than in the formatter.
    """
    lo, hi = (zone[0], zone[1]) if zone[0] <= zone[1] else (zone[1], zone[0])
    return f"{_price(lo, digits)} – {_price(hi, digits)}"


def _confluence_line(snap) -> str:
    """Every confluence on ONE line, each as the strategy's own `detail`.

    ⚠ **The DETAIL, not `name — detail`.** A strategy writes its details to be read
    ("swept Day Low", "not tagged yet", "0.5-0.886 tagged, FVG live"), so the name in front of it
    is the part that repeats on every message. Falls back to the NAME when a strategy gives no
    detail, so a terser contributor renders something true rather than a stray separator.
    """
    parts = [(c.detail or c.name) for c in snap.confluences]
    line = " · ".join(p for p in parts if p)
    return line[:1].upper() + line[1:] if line else ""


def _outstanding(snap) -> str:
    """What is still missing, named — and "" when everything is met.

    🔴 **The empty case is the load-bearing half.** An unconditional `Still missing:` with nothing
    after it sends a reader hunting for a confluence that is already met.
    """
    missing = [c.name for c in snap.confluences if not c.met]
    return f"Still missing: {', '.join(missing)}" if missing else ""


def format_watching(snap, digits: int = 2, display: str = "") -> str:
    """A setup forming — Aaron's "2 of 3", the root of the thread.

    ⚠ **"SETUP FORMING", never "POTENTIAL TRADE".** Measured over 6.5 years, 609 setups reach this
    point and 159 fill: three of every four of these messages do not become a trade. A headline
    that promises a trade is wrong 74% of the time, and a channel that is wrong that often is one
    you stop reading on the day it matters.

    ⚠ **Four lines, and it was eight** (Aaron, 2026-08-13, on the first real renders). What went is
    everything the reader already knew by the time they reached it: the confluences one per line,
    `Waiting on a retrace into that zone` sitting directly under `Retrace zone — not tagged yet`,
    and `(the zone's deep edge)` explaining a number rather than giving one. **Every FACT is still
    here** — what changed is how many lines they take. The prices are last on purpose: they are
    what a reader opens the message again for.

    ⚠ **The stop is still a PROJECTION.** No order exists yet; it is derived from the deep edge of
    the zone. It shares a line with the zone rather than getting its own sentence, which is why the
    wording no longer says so — if that ever reads as a resting order, put the word back rather
    than trusting the layout to carry it.

    `display` is the BOT's name (`SOS Fade`); `snap.strategy` is only ever the class name.
    """
    head = joined([display or snap.strategy, snap.symbol, f"{snap.met} of {snap.of}"])
    lines = [head, _confluence_line(snap)]
    if snap.zone:
        zone = f"Zone {_zone_text(snap.zone, digits)}"
        # ⚠ The stop and the zone's deep edge are the SAME price on this strategy. `exec_sl_level`
        # is 0.886, which is also the deep end of the 0.5-0.886 entry band — a documented property
        # (`sos_fade/CLAUDE.md` → the `exec_sl_level` warning), not a rounding artefact. A fill
        # at the very bottom of the zone has almost no stop distance, which is exactly what the
        # minimum-stop guard exists to refuse.
        if snap.stop is not None:
            zone = f"{zone} · stop {_price(snap.stop, digits)}"
        lines.append(zone)
    return alert("👀", "SETUP FORMING", snap.direction, *lines)


def format_entry_zone(snap, digits: int = 2, lots: Optional[float] = None) -> str:
    """A limit order is RESTING at a price, unfilled. Replies to `format_watching`.

    Sent ONCE per setup. The resting price is recomputed every bar and can shift when a new gap
    forms, and re-announcing each shift was measured at double the volume for no new decision —
    Aaron's call, 2026-08-13. The fill message carries the price that was actually got.

    🔴 **An order can rest at 2 of 3, and the message must NOT imply otherwise.** The entry edge
    comes from a gap overlapping the 0.5-0.886 band, and a gap can be there before PRICE is — so
    the limit is placed in advance and the retrace confluence is still outstanding. Listing only
    the met confluences (the first version of this) hid exactly the fact a reader needs: the
    order is real, and price has not come to it yet.

    🔴 **The header says RESTING because "ENTRY ZONE LIVE" was read as a FILL** (Aaron, 2026-08-14,
    on a real send: *"I thought the trade entered when you just did a limit order"*). It had not —
    price was 41 points above the limit and stayed there. **This is the one message in the thread
    whose whole job is to say that an order EXISTS and has NOT filled**, and the old header said
    neither word. `BUY LIMIT` / `SELL LIMIT` is the MT5 order type he sees in the terminal, so the
    message and the platform now call the same thing by the same name; it also carries the
    direction, which is why there is no `· LONG` subject to repeat it.

    ⚠ **`Limit`, never `Entry`.** An entry is a price you got; a limit is a price you are offering.
    Same misreading one line down from the header that just caused it.

    ⚠ **The targets are NUMBERED.** `TP 3,296.10 · 3,311.75` leaves the reader to infer that the
    first is TP1 — true here, and an inference the message should not be asking for.

    🔴 **`lots` is the size ACTUALLY SENT TO THE BROKER, handed in by the live layer — it is never
    derived here and this module must never learn how (2026-09-03, Aaron: *"I need to see how much
    lots are going to be traded"*).** The strategy sizes in INSTRUMENT UNITS (ounces for gold) and
    MT5 takes LOTS; a message that converted for itself would be a second answer competing with
    `order_sizing`'s one seam, which is the 54.82-lots-on-$2,000 defect exactly. `bridge.
    resting_lots` reads the placed order and this renders whatever it is given.

    ⚠ **`None` prints NO SIZE rather than a zero or a guess**, because it means the caller had no
    broker to ask — a backtest, or `alert_rate.py`. The unit is NAMED in the title for the same
    reason the conversion is not done here: a bare number on this message is the one place a
    reader could take ounces for lots.
    """
    order = []
    if snap.entry is not None:
        order.append(f"Limit {_price(snap.entry, digits)}")
    if snap.stop is not None:
        order.append(f"stop {_price(snap.stop, digits)}")
    lines = [f"{snap.met} of {snap.of}", " · ".join(order)]
    if snap.targets:
        lines.append(
            " · ".join(f"TP{i} {_price(t, digits)}" for i, t in enumerate(snap.targets, 1) if t)
        )
    # ⚠ This line IS the safety property above. The full confluence dump it replaces said the same
    # thing in three lines and buried it among two that were fine.
    lines.append(_outstanding(snap))
    side = "BUY" if snap.side > 0 else "SELL"
    size = f"{lots:.2f} lots · " if lots is not None else ""
    return alert("🎯", f"{size}{side} LIMIT RESTING", "", *lines)


def format_blocked(snap, digits: int = 2) -> str:
    """One of your own rules refused a setup that was otherwise ready. Replies to the root.

    Carries EVERY refusing rule rather than only the first. The Pine reports one because a chart
    tag has room for one line; a reader asking "is this rule earning its keep" needs the whole set,
    and "blocked by the veto" has to stay true on a setup the final-hour rule was also blocking.
    """
    # One line, however many rules. `The setup was ready and this rule stopped it` is gone: it is
    # what BLOCKED already means, and it was on every send this message ever made.
    return alert("🚫", "BLOCKED", snap.direction, " · ".join(snap.blocked_by))


def format_resolved(snap, digits: int = 2) -> str:
    """What became of a setup — filled, or died. Replies to the root.

    `reason` is the STRATEGY's own sentence, never one composed here. Two explanations for one
    death can disagree, and a reader has no way to tell which one is the bot's.
    """
    # Imported HERE, not at module level — see the block at the top of this file. By the time any
    # message is formatted the deployed snapshot is bound, so this resolves against the code the
    # bot was promoted with rather than against the working tree.
    from backtest.setups import FILLED

    if snap.state == FILLED:
        # The trade alert lands seconds later with the price, the size and the risk, so this one
        # only has to close the thread.
        return alert("✅", "ENTERED", snap.direction, "Size and risk are in the trade alert.")
    return alert("👋", "NO TRADE", snap.direction, snap.reason)


def format_entry(
    *,
    strategy: str,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    lots: float,
    digits: int = 2,
    point: float = 0.01,
    risk_usd: Optional[float] = None,
    risk_pct: Optional[float] = None,
    when: Optional[datetime] = None,
) -> str:
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

    return alert(
        "📈" if is_long else "📉",
        "ENTRY",
        f"{side} {symbol}",
        f"Entry {_price(entry, digits)} · Stop {_price(stop, digits)}",
        size,
        strategy,
    )


def format_exit(
    *,
    strategy: str,
    symbol: str,
    exit_price: float,
    pnl_usd: float,
    r_multiple: Optional[float] = None,
    digits: int = 2,
    currency: str = "USD",
    scratch_r: float = 0.15,
    threaded: bool = True,
    exit_reason: str = "",
    when: Optional[datetime] = None,
) -> str:
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

    return alert(_VERDICT_MARK[v], _VERDICT_LABEL[v], "" if threaded else symbol, amount + r, price)
