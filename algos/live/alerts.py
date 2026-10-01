"""alerts.py — what a trade looks like in Telegram.

Pure formatting. No MT5, no network, no state — so the exact text can be tested, and so changing
the wording never risks changing what the bot trades.

**The shape, per Aaron (2026-07-31).** An ENTRY is a standalone message. An EXIT is a Telegram
REPLY to that entry, so the two halves of a trade sit together in the thread and the outcome is
never separated from the setup it came from. That is why `format_entry` is paired with a stored
`message_id` in the bridge — the reply link is part of the format, not an extra.

**The trades room carries a trade's WHOLE life, and since 2026-09-22 that is more than two
messages.** The entry opens the thread, the exit closes it, and in between every change the bot
makes to the trade replies to the entry — the stop reaching breakeven, the stop trailing, size
banked at a rung, size added to a runner. See *how a trade is MANAGED* below for why those are
derived from prices rather than from any one strategy's stages, which is what makes them
automatic for a bot nobody has written yet. Everything else — starts, stops, halts, link
outages, review findings — is HEALTH and goes to a different chat. See `algos/CLAUDE.md` →
*Two rooms*.

**The house shape and the no-Markdown rule both live in `shared/alert_format.py`** — read its
docstring before changing any wording here. The short version: plain text always, because a lone
underscore in `sos_fade` or `XAUUSD.s` makes Telegram reject the whole message; and no
timestamp, because Telegram already prints the send time in the reader's own local clock.

One emoji per message, and each one means something: direction on the way in, outcome on the way
out. They are there so the eye can find a message in a scroll, not for decoration.
"""

from __future__ import annotations

# 🔴 **ONE SWITCH FOR SIZE, AND IT GOVERNS BOTH ROOMS EQUALLY** (Aaron, 2026-09-27: *"make lot
# sizes show equally ... show when we scale in ... make sure all messages are as equal as
# possible"*). True: every trade AND setup message states its lots, and the trade messages their
# dollars. It was False from 2026-09-24 (Kelly: no sizes in the rooms people follow) while the
# signals room kept printing lots, so the two rooms disagreed about the same order. False now
# hides size in BOTH rooms at once — the setup thread passes this too.
# ⚠ **An add to a position is announced either way**; False drops only its lot counts. A follower
# who is not told the bot added has a thread that no longer describes the trade.
# The formatters still take `show_size` explicitly, so the tests cover BOTH renderings.
SHOW_SIZE = True

import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional

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


def _sentence(text: str) -> str:
    """A reason as one sentence: capital first letter, a full stop at the end.

    🔴 **The house rule (Aaron, 2026-09-30): every bot's reasons read in ONE voice.** Each
    strategy writes its own refusal and death sentences, and they arrived in four styles —
    lower-case fragments, "label — Sentence", "rule 4 — …". This is the one place that evens out
    the punctuation, so a strategy only has to get the WORDS plain.
    """
    t = (text or "").strip()
    if not t:
        return ""
    t = t[:1].upper() + t[1:]
    return t if t[-1] in ".!?" else t + "."


def _bot_line(display: str, symbol: str, *extra: str) -> str:
    """Line 2 of EVERY setup and trade message: which bot, which symbol.

    🔴 **Always, including replies** (Aaron's house rules, 2026-09-30). A lock screen shows the
    reply without the message it quotes, so a reply with no bot name names no trade at all.
    """
    return joined([display, symbol, *extra])


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
    """Every check on ONE line, ticked or crossed: `✓ Took out today's low · ✗ Pullback …`.

    🔴 **Ticks, not prose (Aaron, 2026-09-30).** The old line printed each strategy's own STATE
    sentence ("SOS confirmed", "not tagged yet", "5m break pending"), so every bot read
    differently and a reader had to parse each phrase to learn whether it was done. A tick or a
    cross says that in one glance and reads the same for every bot; the strategy's `detail` now
    only has to NAME the condition. Falls back to the name when a strategy gives no detail.
    """
    parts = [
        f"{'✓' if c.met else '✗'} {c.detail or c.name}"
        for c in snap.confluences
        if (c.detail or c.name)
    ]
    return " · ".join(parts)


def _outstanding(snap) -> str:
    """What is still missing, named — and "" when everything is met.

    🔴 **The empty case is the load-bearing half.** An unconditional `Still missing:` with nothing
    after it sends a reader hunting for a check that is already met.
    """
    missing = [(c.detail or c.name) for c in snap.confluences if not c.met]
    if not missing:
        return ""
    names = ", ".join(m[:1].lower() + m[1:] for m in missing)
    return f"Still missing: {names}."


def _targets(targets, digits: int) -> str:
    """`Target 3,331.20`, or `Targets 3,296.10 · 3,311.75` — the word, never "TP1" (2026-09-30)."""
    ts = [_price(t, digits) for t in targets if t]
    if not ts:
        return ""
    return ("Target " if len(ts) == 1 else "Targets ") + " · ".join(ts)


def format_watching(snap, digits: int = 2, display: str = "") -> str:
    """A setup forming — the root of the thread.

    ⚠ **"SETUP FORMING", never "POTENTIAL TRADE".** Measured over 6.5 years, 609 setups reach this
    point and 159 fill: three of every four of these messages do not become a trade.

    The shape every bot shares (Aaron, 2026-09-30): the bot and its check count, the checks as
    ticks and crosses, then the prices — what a reader opens the message again for.

    ⚠ **The stop is still a PROJECTION.** No order exists yet.

    `display` is the BOT's name (`SOS Fade`); `snap.strategy` is only ever the class name.
    """
    head = _bot_line(display or snap.strategy, snap.symbol, f"{snap.met} of {snap.of} checks")
    lines = [head, _confluence_line(snap)]
    stop = f"Stop {_price(snap.stop, digits)}" if snap.stop is not None else ""
    if snap.zone:
        lines.append(joined([f"Entry zone {_zone_text(snap.zone, digits)}", stop]))
    else:
        # A MARKET-entry setup has no zone, so its price line is the projected stop and target.
        lines.append(joined([stop, _targets(snap.targets, digits)]))
    return alert("👀", "SETUP FORMING", snap.direction, *lines)


def _still_watching(snap) -> str:
    return "Still watching in case this changes."


def format_blocked_root(snap, digits: int = 2, display: str = "") -> str:
    """A setup REFUSED on the very bar it is first announced — ONE message, not two.

    🔴 **Why (2026-10-01, extreme_leg_demo 01:20 UTC):** the thread opened with SETUP FORMING
    quoting a target of 4,162.44 while price stood at 4,163.35, and BLOCKED arrived under it in
    the same second. The root described a trade that could not happen, at a target price had
    already passed. Folded into one BLOCKED message, and it prints NO prices: no order exists, so
    no number on it can be acted on.
    """
    return alert(
        "🚫",
        "BLOCKED",
        snap.direction,
        _bot_line(display or snap.strategy, snap.symbol),
        " ".join(_sentence(b) for b in snap.blocked_by),
        _still_watching(snap),
    )


def format_entry_zone(
    snap,
    digits: int = 2,
    lots: Optional[float] = None,
    show_size: bool = True,
    display: str = "",
) -> str:
    """A limit order is WAITING at a price, unfilled. Replies to `format_watching`.

    Sent ONCE per setup; later changes go out as `format_order_moved`.

    🔴 **An order can wait at 2 of 3, and the message must NOT imply otherwise.** The limit can be
    placed before price reaches the zone, so the line naming what is still missing is the safety
    property of this message.

    🔴 **"Not filled yet" is said in words because "ENTRY ZONE LIVE" was read as a FILL** (Aaron,
    2026-08-14). This message's whole job is to say an order EXISTS and has NOT filled.

    🔴 **`lots` is the size ACTUALLY SENT TO THE BROKER, handed in by the live layer — never
    derived here.** `None` prints no size rather than a zero or a guess.
    """
    # ⚠ LIMIT in the header: the MT5 order type Aaron sees in the terminal (2026-08-14), and a
    # limit is a price offered, never an entry got — so the body says "Buy at", never "Entry".
    side = "Buy" if snap.side > 0 else "Sell"
    size = f"{lots:.2f} lots" if (lots is not None and show_size) else ""
    order = []
    if snap.entry is not None:
        order.append(f"{side} at {_price(snap.entry, digits)}")
    if snap.stop is not None:
        order.append(f"Stop {_price(snap.stop, digits)}")
    return alert(
        "🎯",
        "LIMIT ORDER WAITING",
        snap.direction,
        _bot_line(display or snap.strategy, snap.symbol, size),
        " · ".join(order),
        _targets(snap.targets, digits),
        joined(["Not filled yet.", _outstanding(snap)], " "),
    )


class RestingOrder(NamedTuple):
    """The pending order the BROKER is holding for one side — price, stop and lots as sent.

    Built by `bridge.resting_order` from its own record of the placed order, never recomputed.
    Lives here because both the bridge and the setup thread import this file, and neither may
    import the other.
    """

    price: float
    stop: float
    lots: float


def _moved(old: Optional[float], new: Optional[float], fmt) -> str:
    if new is None:
        return ""
    if old is None or fmt(old) == fmt(new):
        return fmt(new)
    return f"{fmt(old)} → {fmt(new)}"


def format_order_moved(
    snap, digits: int = 2, now=None, before=None, show_size: bool = True, display: str = ""
) -> str:
    """The waiting order CHANGED — price, stop or size. Replies to the root.

    🔴 **Why this exists (Aaron, 2026-09-16):** the order is re-placed as the levels move, and a
    thread that only ever showed the FIRST price and size described an order the broker no longer
    held. `now` / `before` are what the broker holds and what the thread last said; either may be
    None when there is no broker to ask, and the strategy's own prices are shown instead.
    """
    side = "Buy" if snap.side > 0 else "Sell"
    p = lambda v: _price(v, digits)  # noqa: E731
    new_px = now.price if now else snap.entry
    new_sl = now.stop if now else snap.stop
    old_px = before.price if before else None
    old_sl = before.stop if before else None
    size = ""
    if now is not None and show_size:
        size = f"{_moved(before.lots if before else None, now.lots, lambda v: f'{v:.2f}')} lots"
    px, sl = _moved(old_px, new_px, p), _moved(old_sl, new_sl, p)
    order = joined([f"{side} at {px}" if px else "", f"Stop {sl}" if sl else ""])
    return alert(
        "🔁",
        "LIMIT ORDER MOVED",
        snap.direction,
        _bot_line(display or snap.strategy, snap.symbol, size),
        order,
        joined(["Not filled yet.", _outstanding(snap)], " "),
    )


def format_order_withdrawn(snap, display: str = "") -> str:
    """The strategy pulled the waiting order but still watches the setup. Replies to the root.

    🔴 **Why (2026-09-16, sos_fade_demo 20:15 UTC):** the final-hour rule cancelled the sell
    limit and the thread's last word was still that an order was waiting. Sent only when the
    strategy NAMES the rule (`paused_by`); a broker cancel-and-replace stays silent.
    """
    return alert(
        "⏸",
        "LIMIT ORDER PAUSED",
        snap.direction,
        _bot_line(display or snap.strategy, snap.symbol),
        " ".join(_sentence(r) for r in snap.paused_by),
        "The order comes back if this changes while the setup is still valid.",
    )


def format_blocked(snap, digits: int = 2, display: str = "") -> str:
    """One of your own rules refused a setup that was otherwise ready. Replies to the root.

    Carries EVERY refusing rule rather than only the first — "blocked by the veto" has to stay
    true on a setup the final-hour rule was also blocking.
    """
    return alert(
        "🚫",
        "BLOCKED",
        snap.direction,
        _bot_line(display or snap.strategy, snap.symbol),
        " ".join(_sentence(b) for b in snap.blocked_by),
        _still_watching(snap),
    )


def format_resolved(snap, digits: int = 2, display: str = "") -> str:
    """What became of a setup — filled, or died. Replies to the root.

    `reason` is the STRATEGY's own sentence, never one composed here. Two explanations for one
    death can disagree, and a reader has no way to tell which one is the bot's.
    """
    # Imported HERE, not at module level — see the block at the top of this file.
    from backtest.setups import DEAD, FILLED

    bot = _bot_line(display or snap.strategy, snap.symbol)
    if snap.state == FILLED:
        # The trade alert lands seconds later with the price, the size and the risk.
        return alert("✅", "ENTERED", snap.direction, bot, "Filled. Details in the trades room.")
    if snap.state != DEAD:
        # Not an outcome at all. Saying NO TRADE would tell the reader to stop watching a setup
        # that may still trade.
        raise ValueError(f"format_resolved called on a {snap.state!r} setup — not an outcome")
    # A NO TRADE is a claim that the bot refused this setup, and it must always say why.
    return alert(
        "👋",
        "NO TRADE",
        snap.direction,
        bot,
        _sentence(snap.reason) or "The bot did not record a reason.",
    )


def format_lost(side=None, symbol: str = "", display: str = "") -> str:
    """Close a thread whose OUTCOME was never recorded, and say exactly that.

    Sent once, on a start, for a setup announced before the bot stopped that it is no longer
    watching now.

    🔴 **It must NOT borrow the wording of a real death.** `NO TRADE` says the bot looked at this
    setup and refused it. Here the bot does not know whether it filled, died or aged out.

    ⚠ **The direction is printed when it is known and simply absent when it is not.**
    """
    direction = {1: "LONG", -1: "SHORT"}.get(side, "")
    return alert(
        "🧹",
        "NO LONGER TRACKED",
        direction,
        _bot_line(display, symbol),
        "The bot restarted while this setup was open, so how it ended is unknown.",
    )


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
    show_size: bool = True,
) -> str:
    """The message that opens a trade's thread.

    `show_size=False` is FOLLOWER mode (Kelly, 2026-09-24): a reader following how the bot trades
    needs the prices and the management, and nothing that states the account's size. The size and
    risk line is dropped whole rather than rounded or bucketed — a "small / medium / large" would
    still leak the account, and an approximate dollar figure is a number nobody measured (rule 4).
    ⚠ **Default True, so nothing already running changes wording until a caller asks.**

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

    risk = ""
    if show_size and risk_usd is not None:
        pct = f" ({risk_pct:g}% of the account)" if risk_pct is not None else ""
        risk = f"Risking ${risk_usd:,.2f}{pct}"

    # The same shape as the signals room (2026-09-30): state and direction, then bot · symbol.
    return alert(
        "📈" if is_long else "📉",
        "ENTERED",
        side,
        _bot_line(strategy, symbol, f"{lots:.2f} lots" if show_size else ""),
        f"Entry {_price(entry, digits)} · Stop {_price(stop, digits)}",
        risk,
    )


# ── how a trade is MANAGED, between the fill and the outcome ─────────────────────────────────
#
# 🔴 **EVERY BOT GETS THESE, AND THAT IS THE WHOLE POINT OF PUTTING THEM HERE (Aaron,
# 2026-09-22).** A trade's thread said ENTRY and then, hours later, WIN or LOSS — and everything
# the bot did in between happened in silence: the stop reaching entry, the stop trailing a
# winner up, size banked at a rung, size added to a runner. His words: *"right now we are only
# told when we enter a trade and whether we won or lost but nothing about break even and nothing
# about how the trade is being managed... I need that to be consistently applied as a rule of
# thumb to any bots I create."*
#
# 🔴 **THEY ARE DERIVED FROM PRICES, NEVER FROM A STRATEGY'S OWN STAGE NUMBER.** Each strategy
# names its stages differently — SOS Fade counts 0/1/2, others do not count at all — so a message
# keyed off a stage would be a message only ONE bot could send, and the next bot built would
# start silent again. The entry, the old stop and the new stop are facts the bridge holds for
# every bot that will ever run here, so the classification below already works for a strategy
# nobody has written yet. **That is what makes this a rule rather than a feature.**
#
# ⚠ **They REPLY TO THE ENTRY, not to each other.** A trade's thread has one root, and a reader
# tapping any message in it lands on the fill that started it. A chain would make finding the
# entry a walk back through however many trail moves there happened to be, and one failed send
# would orphan every message after it.

#: What a stop move DID to the trade's risk. These are the three things that can happen to a
#: stop, and every bot's stop move is exactly one of them.
TO_BREAKEVEN, TRAILING, TIGHTENED = "to_breakeven", "trailing", "tightened"

_STOP_MARK = {TO_BREAKEVEN: "🛡", TRAILING: "🪜", TIGHTENED: "🔒"}
_STOP_LABEL = {
    TO_BREAKEVEN: "STOP MOVED TO ENTRY",
    TRAILING: "PROFIT LOCKED IN",
    TIGHTENED: "RISK REDUCED",
}


def stop_move_kind(*, direction: int, entry: float, was: Optional[float], now: float) -> str:
    """Which of the three a stop move is, from prices alone.

    **BREAKEVEN is the CROSSING, not the price.** It is the move that takes the stop from behind
    the entry to at-or-beyond it — the moment the trade stops being able to lose — and it is
    reported even when the stop lands PAST the entry rather than exactly on it, because a strategy
    that jumps straight to a buffered breakeven has still just removed the risk and that is the
    message Aaron asked for by name. Every later move in profit is a TRAIL.

    ⚠ **`was` of `None` means the previous stop is not known, and it is read as BEHIND the entry**
    — so a first move into profit on a restored trade reports the breakeven crossing rather than a
    trail out of nowhere. That is the safe direction: the worst case is one extra message saying a
    true thing, where the other way round the one event he asked for goes missing.
    """
    at_or_past = (now >= entry) if direction > 0 else (now <= entry)
    if not at_or_past:
        return TIGHTENED
    was_past = was is not None and ((was >= entry) if direction > 0 else (was <= entry))
    return TRAILING if was_past else TO_BREAKEVEN


def stop_locked_r(
    *, direction: int, entry: float, stop: float, opening_stop: Optional[float]
) -> Optional[float]:
    """What this stop has locked in, in R. Positive = profit banked if it is hit.

    🔴 **`None` means NOT KNOWN and must print as no R at all.** The yardstick is the distance
    from entry to the stop the trade OPENED with, and a trade restored from a record written
    before that stop was kept has no yardstick — the stop on the record has already moved, so
    dividing by it would grade every later move against a distance the trade never risked. Rule
    1: "no R" and "0R" are different answers and may not share a value.
    """
    if not opening_stop:
        return None
    risk = abs(entry - opening_stop)
    if risk <= 0:
        return None
    return (stop - entry) * (1 if direction > 0 else -1) / risk


def format_stop_moved(
    *,
    direction: int,
    entry: float,
    was: Optional[float],
    now: float,
    opening_stop: Optional[float] = None,
    symbol: str = "",
    digits: int = 2,
    threaded: bool = True,
    strategy: str = "",
) -> str:
    """The stop moved. Replies to the entry.

    One message shape for all three kinds, because they are one event — the bot changed what this
    trade can still cost — and three shapes would be three things to learn.

    ⚠ **The R is stated as what it MEANS on each side of entry**: `locking +1.15R` above it,
    `risk now 0.62R` below it. The same signed number read two ways, because "locking −0.62R" is
    a sentence a reader has to translate.
    """
    kind = stop_move_kind(direction=direction, entry=entry, was=was, now=now)
    side = "LONG" if direction > 0 else "SHORT"
    r = stop_locked_r(direction=direction, entry=entry, stop=now, opening_stop=opening_stop)

    move = f"Stop {_moved(was, now, lambda v: _price(v, digits))}"
    # ⚠ A figure that ROUNDS to zero is not printed. `now risking 0.00R` under STOP MOVED TO ENTRY
    # says the same thing twice and invites the reader to wonder which of the two is the rounding.
    if r is not None and abs(r) >= 0.005:
        move += f" · locks in {r:+.2f}R" if r > 0 else f" · now risking {abs(r):.2f}R"

    note = ""
    if kind == TO_BREAKEVEN:
        # ⚠ "unless price jumps past the stop", never "nothing left to lose". A gap or a fast
        # market fills past a stop, and this thread's own entry message says "Risking" for the
        # same reason — the smaller word is the accurate one.
        note = "This trade can no longer lose, unless price jumps past the stop."

    return alert(
        _STOP_MARK[kind],
        _STOP_LABEL[kind],
        side if not threaded else "",
        _bot_line(strategy, symbol),
        move,
        note,
    )


def format_partial_banked(
    *,
    lots_banked: float,
    lots_before: float,
    lots_after: float,
    symbol: str = "",
    threaded: bool = True,
    show_size: bool = True,
    strategy: str = "",
) -> str:
    """Size taken off at a rung. Replies to the entry.

    `show_size=False` says THAT a rung banked without saying how much — a follower needs to know
    the bot took profit and left the rest running; the lot counts are the account's business.

    ⚠ **It names WHERE the fill happened and does not pretend to a price.** The bridge banks at
    MARKET on a closed bar, never at the rung the backtest fills at (`bridge._sync_partials`), so
    a reader comparing this trade with the lab has the divergence in front of them instead of
    hunting it. The price itself is deliberately absent: the bridge reconciles a SIZE and does
    not read the deal back, and a price quoted here would be one nobody measured.
    """
    return alert(
        "💰",
        "PROFIT TAKEN",
        "",
        _bot_line(strategy, symbol),
        (
            f"Closed {lots_banked:.2f} of {lots_before:.2f} lots · {lots_after:.2f} still open"
            if show_size
            else "Closed part of the position · the rest is still open"
        ),
        "Taken at market price, so it can differ slightly from the target.",
    )


def format_scaled_in(
    *,
    lots_added: float,
    lots_now: float,
    price: Optional[float] = None,
    stop: Optional[float] = None,
    symbol: str = "",
    digits: int = 2,
    threaded: bool = True,
    show_size: bool = True,
    strategy: str = "",
) -> str:
    """The strategy ADDED to a winner. Replies to the entry.

    `show_size=False` says THAT the bot added, where and on what stop, without the lot counts —
    sent either way (2026-09-27), because a thread that never says the bot added no longer
    describes the trade a follower is copying.

    🔴 **This one is not a nicety.** A scale-in changes what the trade can make and lose after the
    entry message has already stated its size and its risk, so without this the thread's only
    statement of size is out of date from the moment the add fills — and the exit's dollars would
    arrive with nothing in between explaining them.

    ⚠ **`price` is where the STRATEGY added, which is the arming bar's close, not the broker's
    fill.** The bridge sends an add at market and does not read the deal back, so this is an
    estimate and the word "about" is load-bearing. Rule 3. **`None` prints no price at all** —
    a ladder can arm two lots on one bar, and one of their two prices standing for both would be
    a number nobody measured.

    ⚠ **The LOTS are what the broker's own book gained, not what was asked for.** Rule 3 from the
    other side: an add can be refused for size or rejected outright, and a message counting the
    request would report size the account does not hold.
    """
    added = f"Added {lots_added:.2f} lots" if show_size else "Added to the trade"
    if price is not None:
        added += f" at about {_price(price, digits)}"
    held = f"{lots_now:.2f} lots open now" if show_size else ""
    if stop is not None:
        on_stop = f"all on one stop at {_price(stop, digits)}"
        held = f"{held} · {on_stop}" if held else on_stop[0].upper() + on_stop[1:]
    return alert("➕", "ADDED TO TRADE", "", _bot_line(strategy, symbol), added, held)


#: The strategy's exit reason, said the way a person says it. Anything not listed prints as is,
#: so a new reason from a new bot still reaches the reader rather than vanishing.
_EXIT_WORDS = {
    "target": "hit target",
    "stop": "hit stop",
    "your stop": "hit your stop",
    "stop moved to entry": "stopped at entry",
}


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
    show_size: bool = True,
) -> str:
    """The reply that closes a trade's thread.

    `show_size=False` drops the dollars and keeps the R. R is the honest thing to publish: it is
    the result in units of the trade's own risk, so it says how well the bot traded without saying
    what the account stands to make. ⚠ **With no R available there is nothing left to state**, so
    the outcome word and the exit price carry the message alone rather than inventing a figure.

    Outcome, money, price — and nothing about what was risked, because this message hangs under
    the entry that already said so.

    `threaded` is kept for the callers; the bot · symbol line is printed either way since
    2026-09-30, so a bare "WIN" never floats in the group naming no trade.

    `exit_reason` is a short parenthetical like `stop` or `stop moved to entry`. It is the
    difference between reading a number and understanding it: a −0.02R scratch and a −1.00R loser
    both exited at a stop, and only one of them is the risk rule working.
    """
    v = verdict(pnl_usd, r_multiple, scratch_r)
    verb = {WIN: "Made", LOSE: "Lost", BREAKEVEN: "Lost"}[v]
    if v == BREAKEVEN and pnl_usd > 0:
        verb = "Made"
    price = f"Closed at {_price(exit_price, digits)}"
    if exit_reason:
        price += f" ({_EXIT_WORDS.get(exit_reason, exit_reason)})"

    if show_size:
        amount = f"{verb} ${abs(pnl_usd):,.2f}"
        r = f" · {r_multiple:+.2f}R" if r_multiple is not None else ""
        body = [amount + r, price]
    else:
        body = [f"{r_multiple:+.2f}R", price] if r_multiple is not None else [price]

    return alert(_VERDICT_MARK[v], _VERDICT_LABEL[v], "", _bot_line(strategy, symbol), *body)


def format_manual_close(
    *,
    symbol: str,
    exit_price: float,
    pnl_usd: float,
    r_multiple: Optional[float] = None,
    digits: int = 2,
    threaded: bool = True,
    show_size: bool = True,
    strategy: str = "",
) -> str:
    """The reply when the OWNER closed the trade by hand (2026-09-17).

    Its own label rather than WIN/LOSS, so a hand close is never read as the strategy's exit —
    the same line the ledger draws with its `closed_by_you` reason. The R leads because it is
    the header a lock screen shows; `None` (risk unknown) prints no R rather than a zero.
    """
    head = f"{r_multiple:+.2f}R" if r_multiple is not None else ""  # as the WIN/LOSS states it
    verb = "Made" if pnl_usd >= 0 else "Lost"
    money = [f"{verb} ${abs(pnl_usd):,.2f}"] if show_size else []
    return alert(
        "✋",
        "CLOSED BY YOU",
        head,
        _bot_line(strategy, symbol),
        *money,
        f"Closed at {_price(exit_price, digits)}",
        "The bot keeps trading.",
    )


def format_stop_moved_by_you(
    *, stop: float, symbol: str = "", digits: int = 2, strategy: str = ""
) -> str:
    """The owner tightened the stop at the broker and the bot KEPT it (2026-09-17). Replies to the
    entry. It lived inline in the bridge until 2026-09-30 and had no bot line."""
    return alert(
        "✋",
        "STOP MOVED BY YOU",
        "",
        _bot_line(strategy, symbol),
        f"Stop now {_price(stop, digits)}. The bot keeps it.",
    )
