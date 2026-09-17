"""repo_paths.py — where the REPO is, whichever copy of the code is asking.

🔴 **Why this exists (2026-09-17).** `algos/live/` and `algos/shared/` are frozen into each bot's
`instances/<bot>/deployed/` snapshot, so the file asking may sit five folders below the repo it
belongs to. Code is looked up next to the file; DATA never is. The kill switch, the credentials,
the bot folders and the MT5 lock all live in the one repo checkout, and a snapshot copy that
looked for them beside itself would find nothing — a fleet kill switch that silently reads "not
set" is the worst way this could fail. Every data path in these two folders goes through here.

Pure path arithmetic, no imports beyond the standard library, so it is safe to load first.
"""

from __future__ import annotations

from pathlib import Path

#: Where a bot's snapshot sits, relative to the repo root.
INSTANCES_REL = Path("algos") / "markets" / "fx" / "instances"


def repo_root_for(file: str | Path) -> Path:
    """The repo checkout that owns `file`, whether `file` is in the repo or in a bot snapshot.

    A snapshot is `<repo>/algos/markets/fx/instances/<bot>/deployed/<mirror of the repo>`, so the
    first `deployed` folder whose grandparent is `instances` marks it. Anything else is the repo.
    """
    p = Path(file).resolve()
    for parent in p.parents:
        if parent.name == "deployed" and parent.parent.parent.name == "instances":
            return parent.parent.parent.parents[len(INSTANCES_REL.parts) - 1]
    # In the repo: algos/<live|shared>/<file>.py
    return p.parents[2]


REPO_ROOT = repo_root_for(__file__)
ALGOS_ROOT = REPO_ROOT / "algos"
INSTANCES = REPO_ROOT / INSTANCES_REL
