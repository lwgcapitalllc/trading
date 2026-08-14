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
      "broker":   { "dir": 1, "lots": 0.25, "entry": 3290.00, "stop": 3280.00 },
      "strategy": { ... whatever the emulator needs to carry on ... }
    }

`broker` is what the BRIDGE verifies against MT5 — the four facts both sides independently know.
`strategy` is opaque here: it comes from `Execution.snapshot_position()` and goes straight back
to `Execution.restore_position()`. That keeps the emulator free to add state without a change in
this file, and stops this module from growing opinions about what a stage is.

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
    """The four things the bridge and MT5 both know about one position, independently."""

    dir: int  # +1 long, -1 short
    lots: float  # BROKER lots — never instrument units. See the module docstring.
    entry: float
    stop: float


@dataclass(frozen=True)
class PositionRecord:
    bot: str
    symbol: str
    magic: int
    ticket: int
    written: str
    broker: BrokerFacts
    strategy: Dict[str, Any]


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


def read(instance_dir) -> Optional[PositionRecord]:
    """The recorded position, or None if there is not one we can fully trust.

    None covers every distinguishable failure on purpose — absent, unreadable, torn, wrong
    version, missing field, wrong type. The caller's response to all of them is identical (halt
    and tell a human), and giving them separate return values would invite a caller to treat one
    of them as recoverable.
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
