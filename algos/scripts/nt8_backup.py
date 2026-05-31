"""
NT8 data backup — drop-in extension for algos/scripts/backup.py.

WHY
    backup.py currently covers only MT5 algos runtime state under
    algos/markets/fx/instances/. The NinjaTrader 8 user folder is NOT backed up.
    A VPS wipe therefore loses workspaces, chart templates, Strategy Analyzer
    result logs, and any custom NinjaScript that isn't one of the three strategy
    .cs files already tracked in git.

WHAT THIS BACKS UP (small, recovery-critical, git-friendly)
    bin\\Custom               all custom NinjaScript SOURCE (indicators / addons /
                              strategies). The 3 lucid_flex strategy .cs are in the
                              repo already, but anything else under Custom lives
                              only here. Generated build output (obj/, bin/) is
                              excluded — NT8 recompiles on launch.
    workspaces               saved Strategy Analyzer / chart window layouts
    templates                chart templates
    strategyanalyzerlogs     backtest result XMLs (audit trail)

WHAT IS DELIBERATELY *NOT* BACKED UP BY DEFAULT
    db\\   NT8's database mixes a little critical config (instruments, accounts)
           with a LOT of re-downloadable market history — often hundreds of MB to
           multiple GB. Pushing that to a git branch twice a day will bloat the
           repo and can hit GitHub's file/repo size limits. If you truly want it,
           add "db" to NT8_BACKUP_DIRS and raise MAX_DIR_MB knowingly — but the
           better answer for db\\ is a periodic zip to object storage / a file
           share, not git. The size guard below will skip it loudly by default.

ACCOUNT / PERMISSIONS
    You run everything as `trader`, which is your VPS login and a local admin.
    Because an admin can read any user profile, this works whether NT8's folder
    lives under trader's profile or Administrator's. NT8_USER_DIR is resolved
    automatically (trader's profile first, then Administrator) — see
    resolve_nt8_user_dir(). If NT8 ends up somewhere else entirely, pass an
    explicit user_dir to backup_nt8().

PLACEMENT
    Put this file next to backup.py at:  C:\\trading\\algos\\scripts\\nt8_backup.py
    Running `python scripts/backup.py` puts scripts/ on sys.path, so
    `from nt8_backup import backup_nt8` resolves with no path juggling.

INTEGRATION (algos/scripts/backup.py)
    Place this file next to backup.py, then:

        from nt8_backup import backup_nt8

    Inside the existing copy phase, just before the git add/commit/push, add:

        nt8_summary = backup_nt8(dest_root=<your backup worktree root>)
        log(f"NT8 backup: {nt8_summary}")

    Use whatever variable backup.py already uses for the worktree root that maps
    to the `backups` branch checkout (e.g. C:\\trading-backup). The NT8 tree lands
    under <root>/nt8/… and the commit/push you already do will pick it up.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# NT8's user folder may live under the trader profile (target state — everything
# runs as trader) or the Administrator profile (older boxes). trader is an admin,
# so it can read either. Resolve automatically: first existing wins.
CANDIDATE_USER_DIRS = [
    Path(r"C:\Users\trader\Documents\NinjaTrader 8"),
    Path(r"C:\Users\Administrator\Documents\NinjaTrader 8"),
]


def resolve_nt8_user_dir() -> Path:
    for p in CANDIDATE_USER_DIRS:
        if p.exists():
            return p
    return CANDIDATE_USER_DIRS[0]


NT8_USER_DIR = resolve_nt8_user_dir()

# Subfolders to back up, relative to NT8_USER_DIR. Small + git-friendly.
NT8_BACKUP_DIRS = [
    r"bin\Custom",
    "workspaces",
    "templates",
    "strategyanalyzerlogs",
    # "db",   # opt-in ONLY — see the size warning in the module docstring.
]

# Names skipped anywhere inside a copied tree (generated NinjaScript build output).
NT8_EXCLUDE_NAMES = {"obj", "bin"}

# Per-dir hard ceiling (MB). A configured dir larger than this is skipped with a
# warning instead of silently bloating the git branch.
MAX_DIR_MB = 100

# Where, under the backup worktree, the NT8 tree is written.
NT8_DEST_PREFIX = "nt8"


def _dir_size_mb(path: Path) -> float:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def _ignore(_dir, names):
    # shutil.copytree ignore callback: drop generated build dirs.
    return [n for n in names if n in NT8_EXCLUDE_NAMES]


def backup_nt8(dest_root, user_dir: Path = NT8_USER_DIR, log=print) -> dict:
    """
    Copy the configured NT8 subfolders into <dest_root>/nt8/<subfolder>.

    Defensive by design: a missing path, an oversized path, or a path the backup
    account cannot read is SKIPPED with a warning — never raised — so this can
    never take down the existing MT5 backup. Call before the git commit/push.

    Returns: {"copied": [...], "skipped": [...], "too_big": [(rel, mb), ...]}.
    """
    dest_root = Path(dest_root)
    summary = {"copied": [], "skipped": [], "too_big": []}

    if not user_dir.exists():
        log(f"[nt8-backup] NT8 user dir not found: {user_dir} — skipping all NT8 backup.")
        summary["skipped"].append(str(user_dir))
        return summary

    for rel in NT8_BACKUP_DIRS:
        src = user_dir / rel
        dst = dest_root / NT8_DEST_PREFIX / rel
        try:
            if not src.exists():
                log(f"[nt8-backup] not present, skipped: {rel}")
                summary["skipped"].append(rel)
                continue

            size = _dir_size_mb(src)
            if size > MAX_DIR_MB:
                log(f"[nt8-backup] {rel} is {size:.0f} MB (> {MAX_DIR_MB} MB) — "
                    f"skipped to protect the git branch. See db\\ note in module docstring.")
                summary["too_big"].append((rel, round(size)))
                continue

            # Remove the prior copy first so deletions in the source propagate.
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst, ignore=_ignore, dirs_exist_ok=True)
            log(f"[nt8-backup] copied {rel} ({size:.1f} MB)")
            summary["copied"].append(rel)

        except PermissionError:
            log(f"[nt8-backup] PERMISSION DENIED reading {rel} under {user_dir}. "
                f"Unexpected since the backup runs as admin (trader) — check folder "
                f"ACLs / that the path is on a readable drive. Skipped.")
            summary["skipped"].append(rel)
        except OSError as e:
            log(f"[nt8-backup] error on {rel}: {e} — skipped.")
            summary["skipped"].append(rel)

    return summary


if __name__ == "__main__":
    # Standalone smoke test — prints sizes and what WOULD be backed up. No copying.
    print(f"NT8 user dir: {NT8_USER_DIR}  (exists={NT8_USER_DIR.exists()})")
    for _rel in NT8_BACKUP_DIRS:
        _p = NT8_USER_DIR / _rel
        if _p.exists():
            flag = "  <-- OVER LIMIT" if _dir_size_mb(_p) > MAX_DIR_MB else ""
            print(f"  {_rel:24} {_dir_size_mb(_p):8.1f} MB{flag}")
        else:
            print(f"  {_rel:24} (missing)")
