"""fleet_halt.py — one switch that stops EVERY bot on the box from placing an order.

`algos/live/bridge.py` already halts a bot when its own emulator and the broker disagree, and
`runner.STOP_FILE` already shuts one process down cleanly. Neither is a fleet switch: both are
scoped to a single bot, and there was no way to say *"stop the whole account, now"* — which is the
one thing you want at 3am when you do not yet know which bot is wrong.

Live bots are separate OS PROCESSES, so the only things they can share are the filesystem and the
broker. `backtest/portfolio/` shares an in-memory account and cannot be reused here for exactly that
reason (see `docs/LIVE_TRADING_PIPELINE.md` → G10). A flag file is the mechanism, and every bot
re-reads it on every poll.

⚠ **WHAT IT DOES AND DOES NOT DO.** It stops NEW ORDERS. It does not close a position, does not
cancel a broker-side stop, and does not kill the process — the loop keeps running, keeps reading
bars and keeps writing its ledger, so the bot stays observable while it is muzzled. That is the same
shape as the bridge's own halt, and for the same reason: **anything open keeps its protection.** A
switch that flattened the book would be a trading decision taken by a safety device.

⚠ **IT LATCHES, AND CLEARING THE FILE DOES NOT RESUME TRADING.** Once a bot has seen the halt it
stays halted for the life of that process; the resume path is *clear the flag, then restart the
bots*. Two reasons. A flapping or intermittently-unreadable filesystem would otherwise toggle a live
book on and off with nobody watching, and — the one that decides it — every other halt in this
system is terminal-until-a-human-looks, so a fleet switch that quietly un-fired itself would be the
one safety device here you could not reason about from its own log.

## The unreadable case, and why it is the whole design

**`Path.exists()` cannot be used here and using it is the trap.** `exists()` answers `False` both
when the flag is absent — the healthy state — and when the DIRECTORY it lives in is gone, which
means this bot has no way to be told anything. Those are opposite situations reported with one
value, which is this repo's standing rule (*never let "no" and "cannot ask" be the same value*)
arriving on the one code path where the reassuring answer is also the dangerous one.

`stat` does not rescue you on its own either: a missing parent and a missing flag both raise
`FileNotFoundError` with the same errno. So this module stats the **directory FIRST** and the file
second, and only a clean directory stat makes `FileNotFoundError` on the flag mean "clear". Without
the directory probe, `rm -rf` on the folder is a silent way to disable the switch and nothing
anywhere reports it.

⚠ **A permissions failure is handled by letting the other `OSError`s through to the halt branch**,
rather than by relying on what `exists()` does with `EACCES` — which is version-dependent (3.9
propagates it, later versions swallow it; this repo runs 3.9 on the Macs and 3.11 on the VPS). The
module does not care which, and no test pins it.

**Cannot-read HALTS** (Aaron's call, 2026-08-09). ⚠ **This is the OPPOSITE default from
`runner._stop_file_present`, deliberately, and the asymmetry is the point** — each default is safe
against the failure ITS path causes, the same reasoning that makes `startup_coordinator` and
`runner.already_running` default in opposite directions:

| | what a false positive costs | so it defaults to |
|---|---|---|
| `stop.request` | the PROCESS ends; a filesystem blip takes a healthy bot off the box | keep running |
| this switch | no NEW orders; the bot stays alive, positions keep their stops | halt |

A missed trade is recoverable. A kill switch that goes quiet on the day the disk is sick is not a
kill switch, it is a configuration.

Pure and offline — `os` and `pathlib` only, no MT5 and no app imports, so it is testable against a
real temp directory rather than a mock.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["FleetHaltReading", "flag_path", "read_fleet_halt", "DEFAULT_FLAG_NAME"]

# Lives at the root of `algos/`, beside the code every bot already imports, because the switch has
# to be findable by a human over SSH under pressure — not nested under a per-bot instance directory,
# which is the one place a FLEET switch must not be.
DEFAULT_FLAG_NAME = "FLEET_HALT"

_ALGOS_ROOT = Path(__file__).resolve().parent.parent


def flag_path(root: Path | str | None = None) -> Path:
    """Where the flag lives. `root` is injectable so tests never touch the real one."""
    return (Path(root) if root is not None else _ALGOS_ROOT) / DEFAULT_FLAG_NAME


@dataclass(frozen=True)
class FleetHaltReading:
    """The answer to "may this bot place orders", and how confident it is.

    `halted` is the only field a caller must act on. `readable` exists so the ALERT can tell a
    human which of the two very different situations they are in — somebody pulled the switch, or
    the switch could not be read and this bot halted itself out of caution.
    """

    halted: bool
    reason: str
    readable: bool

    @property
    def kind(self) -> str:
        return "requested" if self.readable and self.halted else \
               "unreadable" if self.halted else "clear"


def read_fleet_halt(root: Path | str | None = None) -> FleetHaltReading:
    """Read the flag. Absent = clear. Present = halt. Anything else = halt.

    Never raises: a safety check that can throw is a safety check that takes the loop down with it,
    and the caller is a `while True` whose exception handler counts toward a shutdown.
    """
    path = flag_path(root)
    directory = path.parent

    # 1. THE DIRECTORY FIRST. A missing parent makes the file stat below raise FileNotFoundError,
    #    which is exactly what an absent flag raises — so without this probe, `rm -rf` on the
    #    folder is a silent way to disable the switch.
    try:
        os.stat(directory)
    except OSError as e:
        return FleetHaltReading(
            True,
            f"cannot read the halt directory {directory} ({type(e).__name__}: {e}), so this bot "
            f"cannot be told whether the fleet is halted and has stopped placing orders",
            readable=False)

    # 2. THE FLAG. FileNotFoundError here is the NORMAL state and the only clear answer; every
    #    other OSError is "cannot ask", which halts.
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return FleetHaltReading(False, "", readable=True)
    except OSError as e:
        return FleetHaltReading(
            True,
            f"cannot read the halt flag {path} ({type(e).__name__}: {e}), so this bot cannot be "
            f"told whether the fleet is halted and has stopped placing orders",
            readable=False)

    # 3. The flag is THERE, so the answer is halt whatever its contents say. Reading the reason is
    #    a courtesy to the human on the other end and must never change the verdict — an empty or
    #    unreadable flag file still halts.
    reason = ""
    if st.st_size:
        try:
            reason = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            reason = ""
    return FleetHaltReading(True, reason or f"fleet halt requested ({path})", readable=True)
