#!/usr/bin/env python3
"""rev_setup_feed.py — publish the REV SETUP bot's own decisions to a student channel.

**The ask (the user, 2026-09-23).** His students run the MPC JARVIS indicator on their own charts,
and when they are not at the chart he wants the channel to tell them what the BOT is doing: a rev
setup forming, where the entry would be, the limit going on, the stop being moved, and how it
ended. Named REV SETUP for them, which is what they are taught to call it.

🔴 **IT PUBLISHES PRICES AND RULES, AND NEVER A NUMBER DERIVED FROM AN ACCOUNT.** The bot's own
Telegram messages carry the lot size and the dollar risk, so forwarding them would publish one
owner's position sizing — and his balance by arithmetic — to a class. So this does not forward
messages at all: it reads the bot's RECORDS and renders its own lines from a WHITELIST of fields
per event (`_RENDER`). A field nobody listed cannot reach the channel, which is the safe direction:
a new field added to a record tomorrow is silently left out rather than silently published.

⚠ **It reads records, not the alert layer, and that is why it needs no promote.** The bot writes
`decisions-YYYY-MM-DD.jsonl` as it runs; `algos/shared` is frozen into each bot's deployed
snapshot, so anything added to the bot's own messaging would not reach a running bot until it was
promoted again. This is a separate process reading files that are already there.

⚠ **The forming half comes from the per-bar records, which is the part that looks surprising.**
A bar record carries each side's stage (`l_stage` / `s_stage`, 0-4 — `sos_fade/sequence.py`), so a
stage RISING is the "a setup is forming" event, with no cooperation needed from anything else.
Stage 1 is a liquidity sweep and is deliberately NOT published: it happens constantly and a
channel that pings all day is one students mute before the day it matters.

⚠ **Every run records that it ran** (`last_run_utc` in the state file) and a run that CRASHES says
so in the health room, once per cause. Most runs have nothing to publish, so silence is the normal
state — and a silent broken watcher must never look like a quiet market (this repo's oldest rule).

Usage, on the box, from `C:\\trading`:

    python algos/tools/rev_setup_feed.py --dry-run     # print what it WOULD post, publish nothing
    python algos/tools/rev_setup_feed.py               # publish what is new since the last run
    python algos/tools/rev_setup_feed.py --status      # when it last ran, and where it is up to

Config: `algos/markets/fx/rev_feed.json` (`enabled` is false until somebody turns it on).
Exit 0 = ran. Exit 1 = could not run, and the reason is on stdout and in the health room.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (_ALGOS / "shared", _ALGOS / "live"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ⚠ The messages carry icons and arrows, and this PRINTS each one it posts. The box's console is
# cp1252, where one unencodable character raises mid-print — so a successful run would read as a
# crash. Same trap `tools/verify_channel.py` documents; the message itself is UTF-8 to Telegram
# either way, and only the console needs the belt.
try:  # pragma: no cover - depends on the stream, not on the logic
    sys.stdout.reconfigure(errors="replace")
    sys.stderr.reconfigure(errors="replace")
except Exception:  # noqa: BLE001
    pass

CONFIG = _ALGOS / "markets" / "fx" / "rev_feed.json"
STATE_NAME = "rev_feed_state.json"

#: How many days of record files to look at. Two, so a run just after midnight UTC still finishes
#: yesterday's file — the ledger rotates by UTC day and a bot does not stop at the boundary.
DAYS = 2

#: The stages this publishes, and what each one is IN WORDS. Keys are `sos_fade/sequence.py`'s
#: stage values; 1 (a liquidity sweep) is absent on purpose — see the module docstring.
STAGES = {
    2: "Shift of structure confirmed — waiting for the retrace",
    3: "Retraced to the 50%",
    4: "Retraced to the 61.8% — in the entry zone",
}

#: 🔴 THE WHITELIST. Per record kind, the ONLY fields that may be read into a published line.
#: Everything else in that record is unreadable to this tool by construction — `lots`, `risk_pct`,
#: `risk_usd`, `pnl_usd`, `gross_usd`, `swap_usd`, `commission_usd`, the balance, the ticket.
#: A price, a level, an R multiple and a rule's own words say nothing about whose account it is.
#: ⚠ The keys are what `_kind_of` answers, NOT the raw `kind` field — a trade's open and close
#: share `kind: "trade"` and are told apart by their own `event`, and everything under
#: `kind: "event"` is named by its event. Checked against the writers in `live/ledger.py`
#: (`trade_opened` records `dir` and `trade_closed` records `r`, not `direction`/`r_multiple` —
#: guessing those names is what the first run of this tool got wrong).
_RENDER = {
    # ⚠ The arm source and the projected stop are on this list because the message SHOWS them —
    # the whitelist is the only route a value has, and leaving them off is exactly why the first
    # render of the bot's own shape said "SOS confirmed" with no "Sweep" beside it.
    "bar": ("l_stage", "s_stage", "long_edge", "short_edge", "l_arm_src", "s_arm_src", "stop"),
    "order_placed": ("dir", "intent", "price", "stop", "at_market", "fill_price"),
    "stop_moved": ("was", "now"),
    "trade_opened": ("dir", "symbol", "price", "stop", "tp1", "tp2", "intent"),
    "trade_closed": ("dir", "price", "r", "reason", "intent"),
    "blocked": ("dir", "edge", "reasons", "labels"),
    "missed": ("dir", "edge", "met", "of", "reasons"),
}


class FeedError(RuntimeError):
    """Something this tool needs is missing or unreadable. Reported, never swallowed."""


# ── config and state ─────────────────────────────────────────────────────────


def load_config(path: Path = CONFIG) -> Dict[str, Any]:
    """The feed's settings. RAISES when the file is missing or unreadable.

    ⚠ Not a default-shaped fallback: a config this cannot read and a feed switched off are
    different states, and answering "off" for an unreadable file is how a feed silently stops.
    """
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FeedError(f"{path} does not exist, so there is nothing to publish to")
    except (OSError, ValueError) as e:
        raise FeedError(f"{path} could not be read ({e})")
    for field in ("bot", "chat"):
        if not str(cfg.get(field) or "").strip():
            raise FeedError(f"{path} names no {field}")
    return cfg


def _bot_dir(bot_key: str) -> Path:
    """The bot's instance folder — through `bot_state`, so this asks the same registry the bots do."""
    import bot_state

    path = bot_state.BOT_INSTANCES.get(bot_key)
    if path is None:
        raise FeedError(
            f"no bot folder named {bot_key!r} — it is the folder name, never the display name"
        )
    return Path(path)


def _ledger_dir(bot_key: str) -> Path:
    d = _bot_dir(bot_key) / "ledger"
    if not d.is_dir():
        raise FeedError(f"{bot_key} has no ledger folder yet ({d}) — has it ever run?")
    return d


def read_state(ledger_dir: Path) -> Dict[str, Any]:
    """Where the last run got to. An absent or unreadable state file starts from NOW, never from
    the beginning of the file — a first run must not republish a day of history into the channel.
    """
    try:
        return json.loads((ledger_dir / STATE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(ledger_dir: Path, state: Dict[str, Any]) -> None:
    path = ledger_dir / STATE_NAME
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


# ── reading the records ──────────────────────────────────────────────────────


def _files(ledger_dir: Path, days: int = DAYS) -> List[Path]:
    today = datetime.now(timezone.utc).date()
    names = [f"decisions-{today - timedelta(days=n)}.jsonl" for n in range(days)]
    return [ledger_dir / n for n in reversed(names) if (ledger_dir / n).is_file()]


def new_rows(
    ledger_dir: Path, state: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Every record written since the last run, oldest first, with the new line counts.

    ⚠ Keyed by FILE AND LINE COUNT rather than by timestamp. Two records can share a timestamp
    (the same bar), and a timestamp cursor would either drop one or send it twice.
    """
    done = dict(state.get("lines") or {})
    rows: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for path in _files(ledger_dir):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            raise FeedError(f"{path} could not be read ({e})")
        seen = int(done.get(path.name, 0))
        counts[path.name] = len(lines)
        # A first sight of a file starts at its END: the cursor is set and nothing is published,
        # so turning the feed on does not replay the day into the channel.
        if path.name not in done:
            continue
        for line in lines[seen:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # one corrupt line must not stop the rest — the bot is still writing
    return rows, counts


def _kind_of(row: Dict[str, Any]) -> str:
    """What this record IS, as `_RENDER` spells it.

    Three shapes in one file: `bar`/`blocked`/`missed` are named by `kind`; everything under
    `kind: "event"` is named by its `event`; and a trade's two halves share `kind: "trade"` and
    are told apart by `event: "opened" | "closed"`.
    """
    kind = str(row.get("kind") or "")
    event = str(row.get("event") or "")
    if kind == "event":
        return event
    if kind == "trade" and event:
        return f"trade_{event}"
    return kind


def _pick(row: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """The row cut down to its whitelisted fields. The only way a value reaches a rendered line."""
    return {k: row.get(k) for k in _RENDER.get(kind, ())}


# ── rendering ────────────────────────────────────────────────────────────────


def _side(value) -> str:
    """LONG / SHORT from whatever the record holds, and "" when it holds nothing readable.

    ⚠ Both shapes are real: the order and refusal records carry a signed number, the trade
    records carry a word — and the word is "LONG"/"SHORT" from the bridge but "bullish"/"bearish"
    in several of its siblings, so both are read rather than assumed.
    """
    if value is None:
        return ""
    try:
        return "LONG" if float(value) > 0 else "SHORT"
    except (TypeError, ValueError):
        word = str(value).strip().lower()
    if word.startswith(("bull", "long", "buy")):
        return "LONG"
    if word.startswith(("bear", "short", "sell")):
        return "SHORT"
    return ""


def _px(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return ""


def _add_multiple(state: Dict[str, Any], side: str, price) -> str:
    """ "0.32 x your first lot" for an add at `price`, or "" when it cannot be worked out.

    🔴 **COMPUTED FROM THE PRICE THIS MESSAGE SHOWS, never from the bot's own lots**, and the
    difference is a safety one. The bot's rule is

        add = (profit the stop already locks in) / (what one more lot risks to that same stop)

    and it sizes that on the arming bar's CLOSE, then fills at market on the next bar. On
    2026-09-22 that gap was $11.42 the wrong way: it sized 0.47x against an estimate of 4332.00
    and sold at 4320.58, where the same arithmetic allows only 0.32x. A student copying the bot's
    multiple at the worse price would carry risk the locked profit does not cover — so this
    publishes the multiple for the price in front of them.

    ⚠ Capped at 0.5x, which is the bot's own per-add ceiling.

    ⚠ `""` whenever the entry or the stop is unknown (the feed can start mid-trade) or the numbers
    do not permit an add — a blank line beats a made-up multiple.
    """
    entry, stop = state.get("entry"), state.get("stop")
    if entry is None or stop is None or not side:
        return ""
    try:
        entry, stop, price = float(entry), float(stop), float(price)
    except (TypeError, ValueError):
        return ""
    if side == "SHORT":
        locked, risk = entry - stop, stop - price
    else:
        locked, risk = stop - entry, price - stop
    if locked <= 0 or risk <= 0:
        return ""  # the stop is not past the entry yet, so the bot's rule permits nothing
    return f"{min(locked / risk, 0.5):.2f}× your first lot"


def _money(value) -> str:
    """`4,369.93` — two places and thousands separated, the way every other message in the suite
    prints a price. `""` when there is no number to print."""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return ""


def _confluences(arm_src: str, stage: int) -> Tuple[str, int]:
    """The confluence line, from what the RECORDS hold.

    🔴 **It is deliberately SHORTER than the bot's own message and the gap is worth naming.** The
    bot says `Sweep · Day Low · SOS confirmed · not tagged yet` because it is reading a setup
    snapshot that carries the swept level's NAME, whether a fair-value gap is live in the zone, and
    the whole 0.5-0.886 band. None of that reaches the decision records — a bar record carries the
    arm SOURCE, the stage, the entry edge and the stop, and nothing else. So this says what it can
    prove and never invents the rest; the level name and the band need one line in the bot itself
    (`notes/telegram-and-notifications.md` → the REV SETUP feed).
    """
    arm = {"SWP": "Sweep", "DIV": "RSI divergence"}.get(str(arm_src or "").upper(), "")
    tagged = {2: "not tagged yet", 3: "tagged the 50%", 4: "tagged the 61.8%"}.get(stage, "")
    parts = [arm, "SOS confirmed" if stage >= 2 else "", tagged]
    # ⚠ "n of 3" counts the SAME three things the bot's own message counts — the arm, the shift
    # of structure, and the retrace zone being tagged — so a student reading both sees one scale
    # rather than two. The bot's four internal STAGES are not exposed as "of 4".
    met = (1 if arm else 0) + (1 if stage >= 2 else 0) + (1 if stage >= 3 else 0)
    return " · ".join(p for p in parts if p), met


def _lines_for(
    row: Dict[str, Any],
    state: Dict[str, Any],
    label: str,
    symbol: str,
    min_stop_move: float = 1.0,
) -> List[str]:
    """The message(s) this record produces, or `[]`. Reads ONLY `_pick`'s output.

    **The shape is the one the bot's own signals room uses** (`live/alerts.py`), which the user
    asked for by pasting a real message on 2026-09-23:

        <icon> <STATE> · <SIDE>
        <label> · <symbol> · <n> of 4
        <the confluences, joined>
        <the prices>

    with his own label in place of the strategy name and no live/demo tag — *"Just keep mines as
    REV and remove LIVE."*

    ⚠ `state` is updated in place: each side's last stage (a stage is published when it RISES),
    the last stop line, and the entry, stop and side the add multiple is worked out from.

    `min_stop_move` is in the instrument's own price units; see the stop-move branch.
    """
    kind = _kind_of(row)
    f = _pick(row, kind)
    out: List[str] = []
    arrow = {"LONG": "📈", "SHORT": "📉"}

    def head(side: str, met: Optional[int] = None) -> str:
        n = f" · {met} of 3" if met else ""
        return f"{label} · {symbol}{n}"

    if kind == "bar":
        for side, stage_key, edge_key, src_key in (
            ("LONG", "l_stage", "long_edge", "l_arm_src"),
            ("SHORT", "s_stage", "short_edge", "s_arm_src"),
        ):
            try:
                stage = int(f.get(stage_key) or 0)
            except (TypeError, ValueError):
                continue
            cursor_key = f"stage_{side.lower()}"
            was = int(state.get(cursor_key) or 0)
            state[cursor_key] = stage
            if stage <= was or stage not in STAGES:
                continue
            edge, stop = f.get(edge_key), f.get("stop")
            if edge is not None:
                # The setup's edge IS its entry price, so this doubles as the entry the add
                # multiple is measured from when the feed never saw the fill itself — which is
                # the ordinary case for a trade that opened before the feed's window.
                state["entry"], state["side"] = edge, side
            title = "ENTRY ZONE" if stage == 4 else "SETUP FORMING"
            icon = "🎯" if stage == 4 else "👀"
            conf, met = _confluences(f.get(src_key), stage)
            lines = [f"{icon} {title} · {side}", head(side, met)]
            if conf:
                lines.append(conf)
            prices = []
            if edge is not None:
                prices.append(f"Entry {_money(edge)}")
            if stop is not None:
                prices.append(f"stop {_money(stop)}")
            if prices:
                lines.append(" · ".join(prices))
            out.append("\n".join(lines))
        return out

    if kind == "order_placed":
        side, stop = _side(f.get("dir")), f.get("stop")
        # ⚠ For a MARKET order `price` is the ESTIMATE the size was computed from, not where it
        # filled — the bridge says so where it writes the record. Publishing the estimate as the
        # entry would be off by $11 on the real add of 2026-09-22 (4332.00 against 4320.58).
        at_market = bool(f.get("at_market"))
        price = f.get("fill_price") if at_market else None
        price = f.get("price") if price is None else price
        if not side or price is None:
            return []
        intent = str(f.get("intent") or "primary")
        if intent == "add":
            size = _add_multiple(state, side, price)
            lines = [f"➕ ADDED TO THE SAME POSITION · {side}", head(side)]
            facts = [f"Added at {_money(price)}"]
            if stop is not None:
                facts.append(f"one stop for it all {_money(stop)}")
            lines.append(" · ".join(facts))
            if size:
                lines.append(f"Your add: {size}")
            return ["\n".join(lines)]
        if stop is not None:
            state["stop"] = stop
        state["entry"], state["side"] = price, side
        word = "BUY" if side == "LONG" else "SELL"
        title = f"{word} MARKET ORDER" if at_market else f"{word} LIMIT RESTING"
        lines = [f"🎯 {title} · {side}", head(side)]
        facts = [f"Entry {_money(price)}"]
        if stop is not None:
            facts.append(f"stop {_money(stop)}")
        lines.append(" · ".join(facts))
        return ["\n".join(lines)]

    if kind == "stop_moved":
        was, now = f.get("was"), f.get("now")
        if now is None:
            return []
        # 🔴 Small trail nudges are NOT published. MEASURED on one real day (sos_fade_1,
        # 2026-09-22): seven stop moves, of 21.95, 11.77, 1.17, 0.09, 0.01, 0.07 and 0.13 — so a
        # $1 floor publishes the three that changed the trade and drops four that would have
        # pinged a class of students to tell them the stop moved by a cent.
        state["stop"] = now
        try:
            if was is not None and abs(float(now) - float(was)) < float(min_stop_move):
                return []
        except (TypeError, ValueError):
            pass
        side = str(state.get("side") or "")
        lines = [
            f"🔒 STOP MOVED{f' · {side}' if side else ''}",
            head(side),
            f"{_money(was)} → {_money(now)}",
        ]
        # "Risk off" is stated only when it is TRUE — the stop is at or past the entry. And it
        # says what it is rather than "cannot lose": price that GAPS through a stop fills past it,
        # which is the one thing the bot's own scaling rule warns it does not protect against.
        entry = state.get("entry")
        try:
            if entry is not None and side:
                past = float(now) <= float(entry) if side == "SHORT" else float(now) >= float(entry)
                # Said ONCE, the first time it becomes true. Repeating it on every trail step
                # turns the one line a student should act on into wallpaper.
                if past and not state.get("risk_off_said"):
                    state["risk_off_said"] = True
                    lines.append("Risk off — the stop is now past the entry")
        except (TypeError, ValueError):
            pass
        text = "\n".join(lines)
        # 🔴 One trail move writes ONE RECORD PER LEG. Seen on the real day of 2026-09-22: two
        # records at 07:45:02, the primary's and the scale-in's, both 4357.86 -> 4356.69 — and
        # the same sentence twice reads as the stop having moved twice. The legs are the bot's
        # bookkeeping, not something a student is being taught, so the line is published once.
        if state.get("last_stop_line") == text:
            return []
        state["last_stop_line"] = text
        return [text]

    if kind == "trade_opened":
        side, price, stop = _side(f.get("dir")), f.get("price"), f.get("stop")
        state["entry"], state["side"] = price, side
        if stop is not None:
            state["stop"] = stop
        lines = [f"{arrow.get(side, '🎯')} ENTERED · {side}", head(side)]
        facts = [f"In at {_money(price)}"]
        if stop is not None:
            facts.append(f"stop {_money(stop)}")
        lines.append(" · ".join(facts))
        targets = [_money(f.get("tp1")), _money(f.get("tp2"))]
        targets = [t for t in targets if t and t != "0.00"]
        if targets:
            lines.append("Targets " + " · ".join(targets))
        return ["\n".join(lines)]

    if kind == "trade_closed":
        price, reason = f.get("price"), str(f.get("reason") or "").strip()
        side = _side(f.get("dir")) or str(state.get("side") or "")
        r = f.get("r")
        try:
            r_val = float(r) if r is not None else None
        except (TypeError, ValueError):
            r_val = None
        icon = "➖" if r_val is None or abs(r_val) < 0.05 else ("✅" if r_val > 0 else "❌")
        lines = [f"{icon} CLOSED{f' · {side}' if side else ''}", head(side)]
        facts = [f"Out at {_money(price)}"]
        if r_val is not None:
            facts.append(f"{r_val:+.2f}R")
        lines.append(" · ".join(facts))
        # "closed" is the generic reason the bridge writes when nothing more specific applies —
        # real rows carry it (2026-09-22), and repeating it reads as a stutter.
        if reason and reason.lower() != "closed":
            lines.append(reason[:1].upper() + reason[1:])
        for key in ("entry", "stop", "side", "last_stop_line", "risk_off_said"):
            state.pop(key, None)  # the trade is over; nothing after it may be measured from it
        return ["\n".join(lines)]

    if kind == "blocked":
        reasons = f.get("reasons") or f.get("labels") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        why = " ".join(str(r) for r in reasons) or "one of the bot's own rules"
        side, edge = _side(f.get("dir")), f.get("edge")
        lines = [f"🚫 BLOCKED · {side}", head(side), why]
        if edge is not None:
            lines.append(f"It would have entered at {_money(edge)}")
        return ["\n".join(lines)]

    if kind == "missed":
        met, of = f.get("met"), f.get("of")
        reasons = f.get("reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        side, edge = _side(f.get("dir")), f.get("edge")
        lines = [f"👋 NO TRADE · {side}", head(side)]
        died = "Setup died"
        if met is not None and of is not None:
            died += f" at {met} of {of}"
        if edge is not None:
            died += f" · entry was {_money(edge)}"
        lines.append(died)
        if reasons:
            lines.append(" ".join(str(r) for r in reasons))
        return ["\n".join(lines)]

    return []


def render(
    rows: Iterable[Dict[str, Any]],
    state: Dict[str, Any],
    label: str,
    symbol: str,
    min_stop_move: float = 1.0,
) -> List[str]:
    out: List[str] = []
    for row in rows:
        out.extend(_lines_for(row, state, label, symbol, min_stop_move))
    return out


def _symbol(bot_key: str) -> str:
    """The instrument, without the broker's suffix — `XAUUSD.p` is `XAUUSD` to a student."""
    try:
        doc = json.loads((_bot_dir(bot_key) / "config.json").read_text(encoding="utf-8"))
        return str(doc.get("symbol") or "").split(".")[0] or "?"
    except (FeedError, OSError, ValueError):
        return "?"


# ── running ──────────────────────────────────────────────────────────────────


def run(dry_run: bool = False, config_path: Path = CONFIG) -> int:
    cfg = load_config(config_path)
    bot_key = str(cfg["bot"]).strip()
    ledger_dir = _ledger_dir(bot_key)
    state = read_state(ledger_dir)
    rows, counts = new_rows(ledger_dir, state)
    label = str(cfg.get("label") or "REV SETUP").strip()
    try:
        min_move = float(cfg.get("min_stop_move", 1.0))
    except (TypeError, ValueError):
        raise FeedError(f"min_stop_move is {cfg.get('min_stop_move')!r}, which is not a number")
    # 🔴 THE WHOLE STATE, snapshotted before the render, because the render ADVANCES it: the line
    # cursor, each side's last stage and the last stop line all decide what gets published. Rolling
    # back only the line cursor after a failed send leaves the others ahead, and the retried run
    # then suppresses the very message that did not go out as a duplicate — which is what the retry
    # test caught the first time this rolled back one field.
    before = dict(state)
    texts = render(rows, state, label, _symbol(bot_key), min_move)
    state["lines"] = counts
    state["last_run_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not cfg.get("enabled"):
        # The cursor still advances: a feed switched on later publishes what happens NEXT, not a
        # backlog of everything since somebody wrote the config file.
        print(f"rev_setup_feed: not enabled — {len(texts)} message(s) held back")
        for t in texts:
            print(f"  would post: {t}")
        write_state(ledger_dir, state)
        return 0

    sent = 0
    for text in texts:
        if dry_run:
            print(f"  would post: {text}")
            continue
        from notify import SIGNAL, send_telegram_id

        if send_telegram_id(text, SIGNAL, chat_id=str(cfg["chat"]), markdown=False) is None:
            # Stop at the first failure and DO NOT advance the cursor past it, so the next run
            # retries rather than losing the message. The state below keeps what was sent.
            print(f"rev_setup_feed: send failed, holding the rest for the next run: {text}")
            break
        sent += 1
        print(f"  posted: {text}")
    if not dry_run:
        if sent < len(texts):
            # Something was held back, so EVERY cursor goes back to where it was and the next run
            # reads these records again. ⚠ That can REPEAT a line that did go out — deliberate: a
            # student seeing one message twice is a nuisance, a channel silently missing the stop
            # move is the failure this feed exists to prevent.
            keep_run = state["last_run_utc"]
            state = dict(before)
            state["last_run_utc"] = keep_run
        write_state(ledger_dir, state)
    print(
        f"rev_setup_feed: {len(rows)} new record(s), {sent} posted{' (dry run)' if dry_run else ''}"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print what it would post, send nothing")
    ap.add_argument("--status", action="store_true", help="when it last ran and where it is up to")
    ap.add_argument("--config", default=str(CONFIG))
    args = ap.parse_args(argv)
    try:
        if args.status:
            cfg = load_config(Path(args.config))
            state = read_state(_ledger_dir(str(cfg["bot"])))
            print(
                json.dumps(
                    {
                        "enabled": bool(cfg.get("enabled")),
                        "bot": cfg["bot"],
                        "chat": cfg["chat"],
                        **state,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        return run(dry_run=args.dry_run, config_path=Path(args.config))
    except FeedError as e:
        # 🔴 A watcher that cannot run must SAY SO, or a broken feed reads exactly like a quiet
        # market. The health room, never the student channel — this is machinery, not a signal.
        print(f"rev_setup_feed: CANNOT RUN — {e}")
        try:
            from notify import HEALTH, send_telegram

            send_telegram(f"REV SETUP feed cannot run - {e}", HEALTH, markdown=False)
        except Exception as inner:  # noqa: BLE001 — the message above is already printed
            print(f"rev_setup_feed: and the health alert failed too ({inner})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
