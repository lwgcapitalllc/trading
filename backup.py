"""
backup.py — VPS Data Backup to GitHub

Runs twice daily (midnight + noon CT) via SYS_BACKUP task.
Pushes VPS-only data to GitHub under backup/ directory.

IMPORTANT: This is ONE-WAY — VPS to GitHub only.
GitHub data NEVER overwrites VPS data automatically.
To restore (e.g. new VPS), manually copy from backup/ to their paths.

Files backed up:
  bot_state.json        — balances, P&L, status (single source of truth)
  *_trades.json         — full trade history (AI training data)
  *_stdout.log          — bot activity logs
  users.json            — Telegram user list

Run: python C:/algos/backup.py
"""

import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

ALGOS_ROOT  = Path("C:/algos")
BACKUP_DIR  = ALGOS_ROOT / "backup"

BACKUP_FILES = [
    # Single source of truth
    "markets/fx/instances/gold_main/bot_state.json",
    "markets/fx/instances/gold_scalper/bot_state.json",
    "markets/fx/instances/gold_fft/bot_state.json",
    # Trade histories (AI training data — never lose these)
    "markets/fx/instances/gold_main/smc_trend_trades.json",
    "markets/fx/instances/gold_main/mean_reversion_trades.json",
    "markets/fx/instances/gold_scalper/scalper_trades.json",
    "markets/fx/instances/gold_fft/fft_trades.json",
    # Bot activity logs
    "markets/fx/instances/gold_main/smc_trend_stdout.log",
    "markets/fx/instances/gold_main/mean_reversion_stdout.log",
    "markets/fx/instances/gold_scalper/scalper_stdout.log",
    "markets/fx/instances/gold_fft/fft_stdout.log",
    # Telegram users
    "users.json",
]


def backup():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"Starting backup -- {now}")

    BACKUP_DIR.mkdir(exist_ok=True)

    copied = []
    skipped = []
    for rel_path in BACKUP_FILES:
        src  = ALGOS_ROOT / rel_path
        dest = BACKUP_DIR / rel_path
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(rel_path)
            print(f"  OK {rel_path}")
        else:
            skipped.append(rel_path)

    if skipped:
        print(f"  Skipped {len(skipped)} missing files")

    if not copied:
        print("Nothing to back up.")
        return

    # Write manifest
    with open(BACKUP_DIR / "manifest.json", "w") as f:
        json.dump({
            "backed_up_at": now,
            "files_backed_up": len(copied),
            "files": copied,
        }, f, indent=2)

    # Commit and push to GitHub
    try:
        subprocess.run(["git", "add", "backup/"], cwd=ALGOS_ROOT, check=True,
                       capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=ALGOS_ROOT, capture_output=True
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", f"backup: {now}"],
                cwd=ALGOS_ROOT, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=ALGOS_ROOT, check=True, capture_output=True
            )
            print(f"OK Pushed {len(copied)} files to GitHub -- {now}")
        else:
            print("No changes since last backup.")
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")


if __name__ == "__main__":
    backup()
