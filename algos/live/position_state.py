"""position_state.py — the open position, written down, so a restart can pick it up.

**The failure this exists for.** Until now `OrderBridge.adopt_broker_state` HALTED on any
position MT5 already held at startup, and the runner exited. So a bot that restarted overnight
with a trade open — a box reboot, the watchdog, a crash, a deploy — left that trade with
whatever stop it had at the moment the process died. It kept its broker-side stop, so it was
never naked; but nothing ratcheted the stop again, the time stop never fired, and no structure
exit could close it. Aaron's words: *"this is crucial because this can happen when I go to bed."*

**Why the halt was right, and why this is not a reversal of it.** The strategy is a broker
EMULATOR holding its own position, entry, stop and stage, and a restart rebuilds it EMPTY from a
warm-up replay. Adopting a broker position the emulator knows nothing about is how a restart
doubles a book: the strategy would size a fresh entry with no idea it is already exposed. The
halt is still the answer to that. What this module adds is the one case where the bot is NOT
guessing — it wrote the position down itself, and can prove the thing at the broker is the same
one.

**Strictly narrower than the halt it replaces.** A restore requires ALL of:
  * exactly one position under this bot's magic,
  * a record written by THIS bot for THIS symbol,
  * the record's ticket EQUAL to the broker's ticket,
  * direction, size, entry and stop all agreeing within the symbol's own point size.
Anything else — no record, a torn record, a ticket that does not match, a field that disagrees —
**halts exactly as before**. It never infers, never adopts the broker's numbers, and never
guesses a stop.

**Why not read this back out of the decision ledger.** The ledger is an append-only AUDIT log; it
records what happened, for a human asking why. Recovering live operational state from it would
mean re-deriving what it does not hold (the running favourable extreme the trail ratchets off,
the equity baseline R is measured against, the one-trade-per-leg latch) and would couple the
restart path to a schema written for a different job. `command-center` already learned this the
expensive way — a Stop button that recovered a job id out of `lab_progress.json` cancelled other
platforms' work for months. **Never recover an identity from a channel built to carry a status.**

## The file

`<instance>/position.json`, one per bot, rewritten whenever the position changes and DELETED the
moment the bot goes flat. Two blocks, and the split is deliberate:

    {
      "version": 1,
      "bot": "...", "symbol": "...", "magic": 123456,
      "ticket": 320620565,
      "written": "2026-08-09T21:14:03Z",
      "broker":   { "dir": 1, "lots": 0.25, "entry": 3290.00, "stop": 3280.00,
                    "risk_usd": 250.0, "stop_opened": 3280.00 },
      "alert_id": 4471,
      "strategy": { ... whatever the emulator needs to carry on ... }
    }

`broker` is what the BRIDGE verifies against MT5 — the four facts both sides independently know.
`strategy` is opaque here: it comes from `Execution.snapshot_position()` and goes straight back
to `Execution.restore_position()`. That keeps the emulator free to add state without a change in
this file, and stops this module from growing opinions about what a stage is.

⚠ **`risk_usd` is the dollars at risk when the trade OPENED, and it is OPTIONAL.** `stop` is
rewritten on every move, so once the stop has ratcheted the entry risk cannot be worked back out
of this record — and the restore used to try, so every R after a mid-trade restart was divided by
the distance the stop had LOCKED (or dropped, at breakeven). MT5 does not know it, so
`disagreements` does not check it. A record without it (anything written before 2026-09-12) still
restores; its R is unknown. `VERSION` was NOT bumped for it — a bump reads every open trade's
record as NO record, and that halts the bot.

⚠ **`stop_opened` and `alert_id` are the two fields MT5 has never heard of, and both are
OPTIONAL for the same reason `risk_usd` is.** `stop_opened` is the 1R yardstick every stop-move
message is measured against — `stop` above is rewritten on every ratchet, so without it a
restored trade can say its stop moved but not what that move locked in. `alert_id` is Telegram's
id for the trade's ENTRY message, so the bot goes on replying into the thread the trade already
has instead of dropping messages loose in the room from the restart onward. A record missing
either still restores; it loses the R, or loses the thread. **`VERSION` was NOT bumped for
them** — a bump reads every open trade's record as NO record, and that halts the bot.

⚠ **`lots` is BROKER lots and the emulator sizes in INSTRUMENT UNITS.** They are not the same
number — gold's contract is 100 oz — and conflating them is exactly the fault that rested a
54.82-lot order on a $2,000 account on 2026-08-07. The conversion belongs to the caller that owns
a `SymbolSpec`; nothing here multiplies or divides a quantity.

⚠ **A record that cannot be read is NOT a record.** Corrupt JSON, a missing field, an unknown
version and an unreadable directory all return `None`, which halts. That is the safe direction on
this path: refusing to manage a trade costs a ratchet, adopting the wrong one costs the trade.
It is deliberately the OPPOSITE default from `stop.request`, where cannot-read means do nothing.

⚠ **Written atomically** (temp file + `os.replace`), because the process can die at any moment and
a half-written record read back on the next boot is precisely the state this is meant to remove.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

FILENAME = "position.json"

# Bump when the shape of a record changes incompatibly. An unknown version reads as NO record
# rather than as a best-effort parse: a bot that has just been upgraded must halt on the old
# position and let a human look, not carry on against fields it is guessing the meaning of.
VERSION = 1


@dataclass(frozen=True)
class BrokerFacts:
    """The four things the bridge and MT5 both know about one position, independently — and the
    risk it opened with, which only the bridge knows (see the module docstring)."""

    dir: int  # +1 long, -1 short
    lots: float  # BROKER lots — never instrument units. See the module docstring.
    entry: float
    stop: float
    # Dollars at risk when the position OPENED (fill to the stop attached with it). `None` = not
    # recorded — never recomputed from `stop`, which is rewritten on every move.
    risk_usd: Optional[float] = None
    # The stop the position OPENED with, in price. `None` = not recorded. Added 2026-09-22 for
    # the same reason as `risk_usd` and it is the same trap one field along: `stop` above is
    # rewritten on every ratchet, so after a restart there is nothing left to measure a stop
    # move AGAINST. It is what lets a restored trade's breakeven and trail messages still quote
    # an R — and `None` must print no R rather than 0.00R, which is rule 1.
    stop_opened: Optional[float] = None


@dataclass(frozen=True)
class PositionRecord:
    bot: str
    symbol: str
    magic: int
    ticket: int
    written: str
    broker: BrokerFacts
    strategy: Dict[str, Any]
    #: Telegram's id for this trade's ENTRY message. `None` = not recorded, and every message
    #: about the trade then posts loose rather than under it.
    alert_id: Optional[int] = None


def path_for(instance_dir) -> Path:
    return Path(instance_dir) / FILENAME


def write(
    instance_dir,
    *,
    bot: str,
    symbol: str,
    magic: int,
    ticket: int,
    broker: BrokerFacts,
    strategy: Dict[str, Any],
    alert_id=None,
) -> bool:
    """Record the open position. Returns False on failure rather than raising.

    A failure here must never stop the trading loop: the position exists either way, and the
    cost of not writing it is that a restart halts — which is exactly the behaviour this whole
    module replaces, i.e. the old, safe one. Raising out of the per-bar sync path to protect a
    convenience would be trading a real position for a bookkeeping one.
    """
    record = {
        "version": VERSION,
        "bot": bot,
        "symbol": symbol,
        "magic": int(magic),
        "ticket": int(ticket),
        "written": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "broker": {
            "dir": int(broker.dir),
            "lots": float(broker.lots),
            "entry": float(broker.entry),
            "stop": float(broker.stop),
        },
        "strategy": strategy,
    }
    # Telegram's id for this trade's ENTRY message, so a restart keeps replying into the thread
    # the trade already has. 🔴 **Before this the thread was LOST on every restart** — the bot
    # would go on managing the trade and every message about it would land loose in the room,
    # detached from the fill it was about. Top level rather than inside `broker`: MT5 has never
    # heard of it, and `disagreements` compares `broker` field by field against the position.
    if _message_id(alert_id) is not None:
        record["alert_id"] = int(alert_id)
    if _entry_price(broker.stop_opened) is not None:
        record["broker"]["stop_opened"] = float(broker.stop_opened)
    # Written only when it is a real figure, so an unknown reads back as absent — one "not
    # recorded", never a stored zero that looks like a measurement.
    if _entry_risk(broker.risk_usd) is not None:
        record["broker"]["risk_usd"] = float(broker.risk_usd)
    target = path_for(instance_dir)
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        return True
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


#: The FLAT-state record's file. Its own file, not a block inside `position.json`, because the
#: two live in opposite states: `position.json` is deleted the moment the bot goes flat, and
#: everything here only matters once it is.
WATCH_FILENAME = "setup_watch.json"


def watch_path_for(instance_dir) -> Path:
    return Path(instance_dir) / WATCH_FILENAME


def write_watch(instance_dir, record: Optional[Dict[str, Any]]) -> bool:
    """Record what the strategy is still WATCHING while flat, or clear it when there is nothing.

    The record is opaque here, exactly as `strategy` is in `write`: it comes from
    `Execution.snapshot_setup_watch()` and goes straight back to `restore_setup_watch()`. This
    module stays free of opinions about what a watch is.

    ⚠ **`None` CLEARS rather than writing an empty record**, so "nothing is being watched" and
    "nothing was ever written" are the same state on disk — which is the truth, and leaves no
    stale artefact for the next reader.

    Returns False on failure rather than raising, for `write`'s reason: this is a convenience,
    and it must never be able to stop the trading loop.
    """
    target = watch_path_for(instance_dir)
    if record is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            return False
        return True
    payload = {
        "written": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "watch": record,
    }
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        return True
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass
        return False


def read_watch(instance_dir) -> Optional[Dict[str, Any]]:
    """The recorded watch, or None — absent, unreadable, torn or the wrong shape.

    ⚠ **Unlike `read`, a failure here is NOT a halt and must not be treated as one.** A lost
    watch costs one possible re-entry; it can never put the bot in a position it does not know
    about, which is the whole reason `read`'s failures are so strict. The strategy applies its
    own checks to whatever comes back.
    """
    try:
        raw = json.loads(watch_path_for(instance_dir).read_text(encoding="utf-8"))
    except Exception:
        return None
    watch = raw.get("watch") if isinstance(raw, dict) else None
    return watch if isinstance(watch, dict) else None


def _entry_risk(value) -> Optional[float]:
    """The recorded entry risk, or `None` for NOT RECORDED — absent, a boolean, not a number, zero,
    negative, NaN or infinite. Optional by design: a record that cannot state its entry risk is
    still a position the bot can prove is its own, and failing the whole read over a field the
    restore does not need would halt the bot for nothing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if 0 < v < float("inf") else None


def _entry_price(value) -> Optional[float]:
    """A recorded PRICE, or `None` for NOT RECORDED. Same optional-by-design reading as
    `_entry_risk` — a record that cannot state the stop it opened with is still a position the
    bot can prove is its own, and the only cost is that its stop moves quote no R."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if 0 < v < float("inf") else None


def _message_id(value) -> Optional[int]:
    """A recorded Telegram message id, or `None` for NOT RECORDED. Telegram ids are positive
    integers; anything else is a value nobody can reply to, and passing it on would cost the send
    rather than just the thread."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def read(instance_dir) -> Optional[PositionRecord]:
    """The recorded position, or None if there is not one we can fully trust.

    None covers every distinguishable failure on purpose — absent, unreadable, torn, wrong
    version, missing field, wrong type. The caller's response to all of them is identical (halt
    and tell a human), and giving them separate return values would invite a caller to treat one
    of them as recoverable. ⚠ `broker.risk_usd` is the one exception: optional, and read as `None`
    when it cannot be used (`_entry_risk`), never as a failed read — and since 2026-09-22
    `broker.stop_opened` and the top-level `alert_id` read the same way, for the same reason.

    ⚠ **VERSION IS DELIBERATELY NOT BUMPED FOR AN ADDED OPTIONAL FIELD.** A bump reads every
    open trade's record as NO record, and that HALTS the bot holding it — the note already on
    `risk_usd`, and it applies identically to the two fields added beside it.
    """
    target = path_for(instance_dir)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict) or raw.get("version") != VERSION:
        return None
    try:
        b = raw["broker"]
        broker = BrokerFacts(
            dir=int(b["dir"]),
            lots=float(b["lots"]),
            entry=float(b["entry"]),
            stop=float(b["stop"]),
            risk_usd=_entry_risk(b.get("risk_usd")),
            stop_opened=_entry_price(b.get("stop_opened")),
        )
        strategy = raw["strategy"]
        if not isinstance(strategy, dict):
            return None
        return PositionRecord(
            bot=str(raw["bot"]),
            symbol=str(raw["symbol"]),
            magic=int(raw["magic"]),
            ticket=int(raw["ticket"]),
            written=str(raw.get("written", "")),
            broker=broker,
            strategy=strategy,
            alert_id=_message_id(raw.get("alert_id")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def clear(instance_dir) -> None:
    """Delete the record. Called the moment the bot is flat.

    ⚠ **A stale record is the one way this module could be worse than the halt it replaces.**
    If a position closes and the file survives, the next start reads a ticket the broker no
    longer has — which does not restore anything (the ticket cannot match a position that is not
    there) but would leave a misleading artefact for a human reading the instance directory. It
    is cleared on close, and a failure to clear is swallowed for the same reason `write` swallows
    one: bookkeeping must not be able to stop the loop.
    """
    try:
        path_for(instance_dir).unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def disagreements(record: PositionRecord, position, *, point: float) -> list[str]:
    """Every way the recorded position and the broker's position differ, named.

    ⚠ **Compared against the symbol's POINT, never exactly.** MT5 rounds prices to the symbol's
    digits and a float round-trip through JSON is not bit-exact, so an equality test here would
    halt on every ordinary restart and the feature would be switched off within a week. A
    tolerance of one point is below the smallest price move the broker can quote, so it cannot
    hide a stop somebody actually moved.

    Returns an empty list when everything agrees. The caller HALTS on anything else — this
    function deliberately reports rather than decides, so the halt message can quote both
    numbers instead of saying "they disagreed".
    """
    tol = max(float(point), 0.0)
    out: list[str] = []

    got_dir = 1 if getattr(position, "type", 0) == 0 else -1
    if got_dir != record.broker.dir:
        out.append(f"direction: recorded {_side(record.broker.dir)}, broker {_side(got_dir)}")

    if abs(float(position.volume) - record.broker.lots) > 1e-9:
        out.append(f"size: recorded {record.broker.lots} lots, broker {position.volume}")

    if abs(float(position.price_open) - record.broker.entry) > tol:
        out.append(f"entry: recorded {record.broker.entry}, broker {position.price_open}")

    # The stop is the one a human is most likely to have moved by hand in the terminal, and it is
    # the one we least want to adopt silently — every later ratchet would be computed off a level
    # the strategy never chose, and the trade's recorded R would be wrong with nothing to say so.
    if abs(float(position.sl) - record.broker.stop) > tol:
        out.append(f"stop: recorded {record.broker.stop}, broker {position.sl}")

    return out


def _side(direction: int) -> str:
    return "long" if direction > 0 else "short"
