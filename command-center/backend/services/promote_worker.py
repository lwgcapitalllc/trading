"""One deploy, in its own process: `python -m services.promote_worker <job id>`, run from `backend/`.

🔴 **Why a process and not a thread (2026-09-24).** The backend restarts on any `.py` edit under
`backend/`, and a deploy running on its thread died with it — twice that day, once on the LIVE SOS
Fade bot. A deploy stops and starts a live bot, so it must not end halfway because somebody saved a
file. `routers/bots.py::_launch_worker` starts this in its own SESSION, so a restart of the backend
does not reach it, and it runs the SAME steps the thread did (`_run_promote_job`) — there is still
one implementation of what a deploy does. Its progress goes to its own job file
(`services/promote_jobs.py`), which the backend reads.

⚠ **Its name is load-bearing**: `promote_jobs.WORKER_MARK` looks for it in a pid's command line to
tell this process from an unrelated one that inherited the number after it ended.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m services.promote_worker <job id>", file=sys.stderr)
        return 2
    # Imported here, not at the top: the router is heavy, and a bad argument should not pay for it.
    from routers import bots

    bots._run_promote_job(argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
