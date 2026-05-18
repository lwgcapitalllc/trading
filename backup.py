"""
backup.py — VPS Data Backup to GitHub

Runs daily at midnight via SYS_BACKUP task.
Backs up all VPS-only data files to the GitHub repo under a
backup/ directory so data survives a VPS crash or rebuild.

Files backed up:
  - markets/fx/instances/*/bot_state.json     (balances, P&L, status)
  - markets/fx/instances/*/smc_trend_trades.json
  - markets/fx/instances/*/mean_reversion_trades.json
  - markets/fx/instances/*/scalper_trades.json
  - markets/fx/instances/*/fft_trades.json
  - users.json                                (Telegram users)

These are the only files that exist solely on the VPS and cannot
be recreated from the repo. Everything else is in git already.

Run: python C:/algos/backup.py
"""

import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

ALGOS_ROOT  = Path("C:/algos")
BACKUP_DIR  = ALGOS_ROOT / "backup"

# Files to back up — source path relative to ALGOS_ROOT
BACKUP_FILES = [
    # Bot state (balances, P&L, uptime)
    "markets/fx/instances/gold_main/bot_state.json",
    "markets/fx/instances/gold_scalper/bot_state.json",
    "markets/fx/instances/gold_fft/bot_state.json",
    # Trade histories
    "markets/fx/instances/gold_main/smc_trend_trades.json",
    "markets/fx/instances/gold_main/mean_reversion_trades.json",
    "markets/fx/instances/gold_scalper/scalper_trades.json",
    "markets/fx/instances/gold_fft/fft_trades.json",
    # Telegram users
    "users.json",
]


def backup():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"Starting backup — {now}")

    BACKUP_DIR.mkdir(exist_ok=True)

    copied = []
    for rel_path in BACKUP_FILES:
        src  = ALGOS_ROOT / rel_path
        dest = BACKUP_DIR / rel_path
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(rel_path)
            print(f"  OK {rel_path}")
        else:
            print(f"  -- {rel_path} (not found, skipping)")

    if not copied:
        print("Nothing to back up.")
        return

    # Write backup manifest
    manifest = {
        "backed_up_at": now,
        "files":        copied,
    }
    with open(BACKUP_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Commit and push to GitHub
    try:
        subprocess.run(["git", "add", "backup/"], cwd=ALGOS_ROOT, check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=ALGOS_ROOT, capture_output=True
        )
        if result.returncode != 0:  # there are changes to commit
            subprocess.run(
                ["git", "commit", "-m", f"backup: {now}"],
                cwd=ALGOS_ROOT, check=True
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=ALGOS_ROOT, check=True
            )
            print(f"OK Pushed {len(copied)} files to GitHub")
        else:
            print("No changes since last backup.")
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")


if __name__ == "__main__":
    backup()
