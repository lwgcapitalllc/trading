"""
backup.py — VPS Data Backup to GitHub (backups branch)

Runs twice daily (midnight + noon CT) via SYS_BACKUP task.
Pushes VPS-only data to the `backups` orphan branch on GitHub.

The `backups` branch is SEPARATE from `main` — backup commits never
land on main, so local Mac development never conflicts with VPS backups.

Restore (new VPS): git clone -b backups <repo> C:\lwg-capital-backup
then manually copy files to their C:\lwg-capital\algos paths.

ONE-TIME VPS SETUP (run once after first deploy):
  python C:/lwg-capital/algos/scripts/backup.py --setup

Files backed up:
  bot_state.json        — balances, P&L, status (single source of truth)
  *_trades.json         — full trade history (AI training data)
  *_model.pkl           — trained AI model (Random Forest classifier)
  *_model_scaler.pkl    — feature scaler paired with each model
  *_equity.json         — equity curve history (Calmar ratio source data)
  *_daily.json          — daily P&L log (AI drawdown-awareness training)
  *_weekly.json         — weekly loss cap state
  *_stdout.log          — bot activity logs
  users.json            — Telegram user list

Run: python C:/lwg-capital/algos/scripts/backup.py
"""

import json
import subprocess
import shutil
import sys
from datetime import datetime
from pathlib import Path

ALGOS_ROOT     = Path("C:/lwg-capital/algos")
BACKUP_WORKTREE = Path("C:/lwg-capital-backup")   # git worktree for backups branch
BACKUP_BRANCH  = "backups"

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
    # Trained AI models — if lost, bots run unfiltered until 15+ trades re-accumulate
    "markets/fx/instances/gold_main/smc_trend_model.pkl",
    "markets/fx/instances/gold_main/smc_trend_model_scaler.pkl",
    "markets/fx/instances/gold_main/mean_reversion_model.pkl",
    "markets/fx/instances/gold_main/mean_reversion_model_scaler.pkl",
    "markets/fx/instances/gold_scalper/scalper_model.pkl",
    "markets/fx/instances/gold_scalper/scalper_model_scaler.pkl",
    "markets/fx/instances/gold_fft/fft_model.pkl",
    "markets/fx/instances/gold_fft/fft_model_scaler.pkl",
    # Equity curves (Calmar ratio source data)
    "markets/fx/instances/gold_main/gold_main_equity.json",
    "markets/fx/instances/gold_scalper/scalper_equity.json",
    "markets/fx/instances/gold_fft/fft_equity.json",
    # Daily P&L logs (AI drawdown-awareness training data)
    "markets/fx/instances/gold_main/smc_trend_daily.json",
    "markets/fx/instances/gold_main/mean_reversion_daily.json",
    "markets/fx/instances/gold_fft/fft_daily.json",
    # Weekly loss cap state
    "markets/fx/instances/gold_main/smc_trend_weekly.json",
    "markets/fx/instances/gold_main/mean_reversion_weekly.json",
    "markets/fx/instances/gold_fft/fft_weekly.json",
    # Bot activity logs
    "markets/fx/instances/gold_main/smc_trend_stdout.log",
    "markets/fx/instances/gold_main/mean_reversion_stdout.log",
    "markets/fx/instances/gold_scalper/scalper_stdout.log",
    "markets/fx/instances/gold_fft/fft_stdout.log",
    # Telegram users
    "users.json",
]


def run(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def setup():
    """
    One-time setup: create the backups orphan branch on GitHub and a local
    git worktree pointing to it at C:\\lwg-capital-backup.

    Run: python C:/lwg-capital/algos/scripts/backup.py --setup
    """
    print("Setting up backups branch and worktree...")

    # Check if backups branch already exists on remote
    result = run(["git", "ls-remote", "--heads", "origin", BACKUP_BRANCH],
                 cwd=ALGOS_ROOT, check=False)
    branch_exists = BACKUP_BRANCH in result.stdout

    if not branch_exists:
        print("  Creating orphan backups branch on GitHub...")
        # Create orphan branch, empty commit, push, return to main
        run(["git", "checkout", "--orphan", BACKUP_BRANCH], cwd=ALGOS_ROOT)
        run(["git", "reset", "--hard"], cwd=ALGOS_ROOT)
        run(["git", "commit", "--allow-empty", "-m", "init: backups branch"],
            cwd=ALGOS_ROOT)
        run(["git", "push", "origin", BACKUP_BRANCH], cwd=ALGOS_ROOT)
        run(["git", "checkout", "main"], cwd=ALGOS_ROOT)
        print("  backups branch created and pushed.")
    else:
        print("  backups branch already exists on remote.")

    # Create worktree
    if BACKUP_WORKTREE.exists():
        print(f"  Worktree already exists at {BACKUP_WORKTREE}.")
    else:
        run(["git", "worktree", "add", str(BACKUP_WORKTREE), BACKUP_BRANCH],
            cwd=ALGOS_ROOT)
        print(f"  Worktree created at {BACKUP_WORKTREE}.")

    print("Setup complete. Run 'python C:/lwg-capital/algos/scripts/backup.py' to take the first backup.")


def backup():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"Starting backup -- {now}")

    if not BACKUP_WORKTREE.exists():
        print("ERROR: Backup worktree not set up.")
        print("Run: python C:/lwg-capital/algos/scripts/backup.py --setup")
        return

    copied = []
    skipped = []
    for rel_path in BACKUP_FILES:
        src  = ALGOS_ROOT / rel_path
        dest = BACKUP_WORKTREE / rel_path
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
    with open(BACKUP_WORKTREE / "manifest.json", "w") as f:
        json.dump({
            "backed_up_at": now,
            "files_backed_up": len(copied),
            "files": copied,
        }, f, indent=2)

    # Commit and push to backups branch
    try:
        run(["git", "add", "."], cwd=BACKUP_WORKTREE)
        result = run(["git", "diff", "--cached", "--quiet"],
                     cwd=BACKUP_WORKTREE, check=False)
        if result.returncode != 0:
            run(["git", "commit", "-m", f"backup: {now}"], cwd=BACKUP_WORKTREE)
            run(["git", "push", "origin", BACKUP_BRANCH], cwd=BACKUP_WORKTREE)
            print(f"OK Pushed {len(copied)} files to GitHub ({BACKUP_BRANCH}) -- {now}")
        else:
            print("No changes since last backup.")
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e.stderr.strip()}")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup()
    else:
        backup()
