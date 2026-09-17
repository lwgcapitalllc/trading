"""bot_registry.py — WHICH BOTS EXIST, answered once, off the folders on disk.

**A bot IS its instance folder: `algos/markets/fx/instances/<key>/config.json`.** Every roster that
starts, watches, names or reviews a bot derives from `discover()` — the boot sequence, the process
watchdog, the dead-man's switch, the hourly log review, the Telegram bot's `/status` — and the
Command Center derives its own list from the same folders by the same rule.

🔴 **Until 2026-09-13 a bot lived in FIVE hand-kept lists**, and every omission was silent and
failed differently: missing from the state map it died on startup with a bare KeyError AFTER
connecting and warming; missing from the boot sequence it was simply absent after a reboot;
missing from a watcher it was a bot nothing watched. A test held the five together, which caught
a mismatch and could not stop one being written. **Adding a bot is now creating its folder**,
which is the one thing every copy of a bot already had to do.

⚠ **"Cannot list the folders" is NOT "there are no bots"** (rule 1). `discover()` RAISES
`RegistryUnreadable` when the folder cannot be read, and returns `{}` only when it was read and
holds no bot. An empty registry answers every question confidently and wrongly (rule 8) — a
watchdog handed one watches nothing and says nothing.

⚠ **A folder without a `config.json` is not a bot.** A watcher that writes its liveness record
into a folder named after a bot key has CREATED such a folder before (2026-09-04, a renamed bot),
and counting it would register a bot that cannot start.

⚠ **An unreadable `config.json` still IS a bot.** Its folder says it exists; what it cannot say is
its account — and every watcher already treats *cannot read the config* as *keep watching, loudly*
(`bot_state.is_assigned`). Dropping it here would quietly stop watching a live bot whose file has
a typo in it.

Pure standard library and never imports anything from this repo, so the Command Center's tests,
the watchers and the live runner can all load it without dragging MT5 or the engines in.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

from repo_paths import ALGOS_ROOT  # noqa: E402 — the REPO's, even from a bot snapshot

INSTANCES = ALGOS_ROOT / "markets" / "fx" / "instances"
CONFIG_NAME = "config.json"

# What a bot key may look like. It names a folder, a process argument, a Telegram label and a
# section in the Command Center's batched SSH read, so it is kept to the one alphabet all four
# accept without quoting. A folder whose name does not match is not a bot.
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class RegistryUnreadable(RuntimeError):
    """The bot folders could not be listed. A DIFFERENT answer from "there are no bots"."""


def discover(root: Optional[Path] = None) -> Dict[str, Path]:
    """`{bot key: its instance folder}` for every folder holding a `config.json`, sorted by key.

    Raises `RegistryUnreadable` when the folder itself cannot be listed — see the module docstring
    for why that may never collapse into an empty answer.
    """
    base = Path(root) if root is not None else INSTANCES
    try:
        with os.scandir(base) as it:
            names = sorted(e.name for e in it if e.is_dir())
    except OSError as e:
        raise RegistryUnreadable(
            f"cannot list the bot folders at {base} ({type(e).__name__}: {e})"
        ) from e
    return {
        name: base / name
        for name in names
        if KEY_PATTERN.match(name) and (base / name / CONFIG_NAME).is_file()
    }


def read_config(folder: Path) -> Optional[dict]:
    """A bot folder's `config.json`, or **`None` when it could not be read** — never `{}`.

    `None` and `{}` are different answers: *this bot states nothing* and *we could not find out*.
    Never raises — every caller is building a roster or a label, and neither may be able to stop
    a watchdog pass.
    """
    try:
        raw = json.loads((Path(folder) / CONFIG_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def display_name(folder: Path, key: str) -> str:
    """What a person calls this bot: its config's `display_name`, else its key. Never raises."""
    name = (read_config(folder) or {}).get("display_name")
    return name.strip() if isinstance(name, str) and name.strip() else key


# ── which process IS a bot ──────────────────────────────────────────────────────
#
# 🔴 **Every live bot is the SAME program (`runner.py`), so only its key tells two apart — and a
# key matched as a SUBSTRING tells them apart wrongly.** `sos_fade_2` is a substring of
# `--bot sos_fade_20`; every tool that acts on a bot takes the same flag (`promote.py --bot X`,
# the hourly `watch_reentry.py --bot X`, the coordinator starting it), so a key anywhere in the
# process list read a STOPPED bot as running whenever one of those happened to be alive. The
# watchdog then declined to restart it. That is one bot disturbing another through a string.
#
# ⚠ **The Command Center carries the same rule in its own language** (`routers/bots.py`
# `_is_bot_runner`) because the two subsystems may not import each other. Both are driven over
# ONE list of cases, `algos/tests/fixtures/runner_lines.json`, so a shape one side learns and the
# other does not fails on the side that did not learn it.
_RUNNER_PY = re.compile(r'(?:^|[\\/\s"=])runner\.py(?=[\s"]|$)', re.IGNORECASE)


def is_runner_line(line: str, key: str) -> bool:
    """Is this ONE process-list line bot `key`'s runner — `runner.py` with `--bot <key>` exactly?

    The key must END at a space, a quote or the line end, so `sos_fade_2` never matches
    `sos_fade_20`; `--bot=key` is argparse's other spelling and counts too. A line that holds the
    key but not the runner (the coordinator launching it, a promote, a watcher) is not the bot.
    """
    if not key or not _RUNNER_PY.search(line):
        return False
    return (
        re.search(r'(?:^|[\s"])--bot(?:\s+|=)' + re.escape(key) + r'(?=[\s"]|$)', line) is not None
    )


def runner_keys(process_list: str, keys: Iterable[str]) -> Set[str]:
    """Which of `keys` have a runner process in a `wmic ... get commandline` answer — table or
    `/format:list`, one process per line either way."""
    lines = process_list.splitlines()
    return {k for k in keys if any(is_runner_line(line, k) for line in lines)}
