"""Every SSH call to the trading box goes through `run` — and the ONE failure it tries again.

🔴 **THE BOX TURNS A NEW CONNECTION AWAY BEFORE SAYING A WORD WHEN TOO MANY ARE STILL LOGGING IN
(2026-09-11).** MEASURED: 3 of 8 single, one-at-a-time connections refused within a second, each
with `kex_exchange_identification: read: Connection reset by peer`. The box's SSH server runs on its
defaults — `MaxStartups 10:30:100`: past 10 connections that have not logged in yet it drops 30% of
new ones, rising to all of them at 100 — and one internet address (106.13.170.216) was holding 19
open. 30% + (19 − 10) × 70/90 ≈ 37%, which is the rate measured. The Bots page reads one version per
bot on every load, so each load lost a bot or two to a 500 and a toast.

⚠ **ONLY that refusal is retried, because it is the one ssh failure that PROVES nothing ran.** The
identification exchange is the very first thing the protocol does — the two ends swap version
strings — so no login and no remote command can have happened. That is what makes a retry safe for
a WRITE (a stop request, a git pull, a credentials write), not only a read. Anything else is handed
back untouched: `Connection closed by <host> port 22` on its own, also seen that day, can come from
later in the handshake and is NOT retried.

⚠ **A timeout is never retried** — it raises out of the first attempt, because a command that timed
out may be running.

⚠ **This is a patch over a crowded box, not a fix for it.** The fix is on the box (keys only, a
short login grace, a firewall) — see backend CLAUDE.md → *The box refuses SSH*.
"""

from __future__ import annotations

import subprocess
import time
from typing import Sequence

# What ssh prints when the server hangs up before the protocol has started.
REFUSED_BEFORE_LOGIN = "kex_exchange_identification"

# The wait after each refusal. A refusal is instant, so these are the whole cost: 6.5s at worst,
# and four refusals in a row at the measured 37% is a 1.9% chance.
RETRY_DELAYS = (0.5, 1.0, 2.0, 3.0)

# Looked up at call time, so a test can take the waits out without touching `time.sleep` itself.
_sleep = time.sleep


def refused_before_login(result: subprocess.CompletedProcess) -> bool:
    """Did ssh fail before the server said anything, so the command provably never ran?

    255 is ssh's own failure code — a remote command reports its own — and the message must be
    the identification one. Read with `getattr` because a caller's stand-in may not carry both.
    """
    if getattr(result, "returncode", None) != 255:
        return False
    err = getattr(result, "stderr", None) or ""
    if isinstance(err, bytes):
        err = err.decode("utf-8", errors="replace")
    return REFUSED_BEFORE_LOGIN in err


def run(argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run(argv, **kwargs)`, asked again while the box refuses before login.

    Same arguments, same return, same exceptions as `subprocess.run`. The caller must capture
    stderr (every caller does), or there is nothing to recognise the refusal by and it is returned
    like any other failure.
    """
    for delay in RETRY_DELAYS:
        result = subprocess.run(argv, **kwargs)
        if not refused_before_login(result):
            return result
        _sleep(delay)
    return subprocess.run(argv, **kwargs)
