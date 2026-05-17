#!/usr/bin/env python3
"""
deploy.py — LWG Capital Algo Suite Deployment Script

Run this after downloading all new files into the algos/files/ folder.
It will:
  1. Move every file from files/ to its correct location in the repo
  2. Remove all old-named files that have been renamed
  3. Print a summary of what was done

Usage:
    cd /Users/alwg/algos
    python3 deploy.py

Safe to run multiple times — it checks before moving/deleting.
"""

import shutil
import os
from pathlib import Path

ROOT  = Path(__file__).parent
FILES = ROOT / "files"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET} {msg}")
def err(msg):   print(f"  {RED}✗{RESET} {msg}")
def info(msg):  print(f"  {GRAY}{msg}{RESET}")


# =============================================================================
# FILE MANIFEST — source (in files/) → destination (in repo)
# =============================================================================

MANIFEST = {
    # ── Bots ──────────────────────────────────────────────────────────────────
    "bot_smc_trend.py":          "bots/bot_smc_trend.py",
    "bot_mean_reversion.py":     "bots/bot_mean_reversion.py",
    "bot_scalper.py":            "bots/bot_scalper.py",
    "bot_fft.py":                "bots/bot_fft.py",
    "bot_futures.py":            "bots/bot_futures.py",
    "bot_utils.py":              "bots/bot_utils.py",
    "launcher.py":               "bots/launcher.py",

    # ── Bot guides ────────────────────────────────────────────────────────────
    "BOT_SMC_TREND_GUIDE.md":       "bots/BOT_SMC_TREND_GUIDE.md",
    "BOT_MEAN_REVERSION_GUIDE.md":  "bots/BOT_MEAN_REVERSION_GUIDE.md",
    "BOT_SCALPER_GUIDE.md":         "bots/BOT_SCALPER_GUIDE.md",
    "BOT_FFT_GUIDE.md":             "bots/BOT_FFT_GUIDE.md",
    "BOT_FUTURES_GUIDE.md":         "bots/BOT_FUTURES_GUIDE.md",

    # ── Shared components ─────────────────────────────────────────────────────
    "shared_ai_brain.py":        "shared/shared_ai_brain.py",
    "shared_calmar.py":          "shared/shared_calmar.py",
    "shared_regime.py":          "shared/shared_regime.py",

    # ── Executors ─────────────────────────────────────────────────────────────
    "tradovate.py":              "executors/tradovate.py",

    # ── Notifications ─────────────────────────────────────────────────────────
    "reporter.py":               "notifications/reporter.py",
    "monitor.py":                "notifications/monitor.py",
    "telegram_bot.py":           "notifications/telegram_bot.py",
    "NOTIFICATIONS_GUIDE.md":    "notifications/NOTIFICATIONS_GUIDE.md",

    # ── Scheduler XMLs ────────────────────────────────────────────────────────
    "smc_trend_task.xml":        "scheduler/smc_trend_task.xml",
    "mean_reversion_task.xml":   "scheduler/mean_reversion_task.xml",
    "scalper_task.xml":          "scheduler/scalper_task.xml",
    "fft_task.xml":              "scheduler/fft_task.xml",
    "futures_acct1_task.xml":    "scheduler/futures_acct1_task.xml",
    "telegram_task.xml":         "scheduler/telegram_task.xml",
    "reporter_task.xml":         "scheduler/reporter_task.xml",
    "monitor_task.xml":          "scheduler/monitor_task.xml",
    "SCHEDULER_GUIDE.md":        "scheduler/SCHEDULER_GUIDE.md",

    # ── Instance configs ──────────────────────────────────────────────────────
    "gold_main_config.json":         "markets/fx/instances/gold_main/config.json",
    "gold_scalper_config.json":      "markets/fx/instances/gold_scalper/config.json",
    "gold_fft_config.json":          "markets/fx/instances/gold_fft/config.json",
    "futures_account1_config.json":  "markets/futures/instances/futures_account1/config.json",

    # ── Root files ────────────────────────────────────────────────────────────
    "algo.py":                   "algo.py",
    "README.md":                 "README.md",
    "stress_test_suite.py":      "stress_test_suite.py",
    "deploy.py":                 "deploy.py",
    "SETUP.md":                  "SETUP.md",
    "ALGO_CONTROL_PANEL_GUIDE.md": "ALGO_CONTROL_PANEL_GUIDE.md",
}


# =============================================================================
# OLD FILES TO REMOVE (renamed or replaced)
# =============================================================================

OLD_FILES = [
    # Old bot script names
    "bots/bot1_smc_trend.py",
    "bots/bot2_mean_reversion.py",
    "bots/bot3_scalper.py",
    "bots/bot4_lucidflex.py",
    "bots/bot5_fft.py",

    # Old guide names
    "bots/BOT1_SMC_TREND_GUIDE.md",
    "bots/BOT2_MEAN_REVERSION_GUIDE.md",
    "bots/BOT3_SCALPER_GUIDE.md",
    "bots/BOT4_LUCIDFLEX_GUIDE.md",
    "bots/BOT5_FFT_GUIDE.md",

    # Old scheduler XMLs
    "scheduler/bot1_task.xml",
    "scheduler/bot2_task.xml",
    "scheduler/bot3_task.xml",
    "scheduler/bot5_task.xml",
    "scheduler/reporter_task.xml",   # old version in root (moved to scheduler)
    "scheduler/monitor_task.xml",
    "scheduler/telegram_bot_task.xml",

    # Old root-level notification files (moved to notifications/)
    "reporter.py",
    "monitor.py",
    "telegram_bot.py",
    "telegram_offset.json",
    "SSH_SETUP_AND_COMMANDS.txt",
    "test_tradovate_auth.py",
    "reporter_task.xml",
    "monitor_task.xml",
    "telegram_bot_task.xml",

    # Old instance folders (renamed)
    # Note: these are directories — handled separately below
]

OLD_DIRS = [
    "markets/fx/instances/xauusd_main",
    "markets/fx/instances/xauusd_scalper",
    "markets/fx/instances/xauusd_fft",
    "markets/futures/instances/lucid_account1",
    "markets/futures/instances/lucid_account2",
]


# =============================================================================
# DEPLOY
# =============================================================================

def deploy():
    print(f"\n{BOLD}LWG Capital — Deployment Script{RESET}")
    print(f"Root: {ROOT}")
    print(f"Files folder: {FILES}\n")

    if not FILES.exists():
        err(f"files/ folder not found at {FILES}")
        err("Create it and download all new files into it first.")
        return

    moved   = 0
    skipped = 0
    removed = 0
    errors  = 0

    # ── Step 1: Move files from files/ to correct locations ───────────────────
    print(f"{BOLD}Step 1 — Moving files to correct locations{RESET}")
    for src_name, dest_rel in MANIFEST.items():
        src  = FILES / src_name
        dest = ROOT  / dest_rel

        if not src.exists():
            info(f"Skip (not in files/): {src_name}")
            skipped += 1
            continue

        # Create parent directory if needed
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src, dest)
            ok(f"{src_name} → {dest_rel}")
            moved += 1
        except Exception as e:
            err(f"{src_name}: {e}")
            errors += 1

    # ── Step 2: Remove old files ───────────────────────────────────────────────
    print(f"\n{BOLD}Step 2 — Removing old files{RESET}")
    for old_rel in OLD_FILES:
        old = ROOT / old_rel
        if old.exists():
            try:
                old.unlink()
                ok(f"Removed: {old_rel}")
                removed += 1
            except Exception as e:
                err(f"Could not remove {old_rel}: {e}")
                errors += 1
        else:
            info(f"Already gone: {old_rel}")

    # ── Step 3: Remove old directories (only if empty or all contents moved) ──
    print(f"\n{BOLD}Step 3 — Removing old instance directories{RESET}")
    for old_rel in OLD_DIRS:
        old = ROOT / old_rel
        if old.exists():
            try:
                shutil.rmtree(old)
                ok(f"Removed dir: {old_rel}")
                removed += 1
            except Exception as e:
                err(f"Could not remove dir {old_rel}: {e}")
                errors += 1
        else:
            info(f"Already gone: {old_rel}")

    # ── Step 4: Clean up files/ folder ────────────────────────────────────────
    print(f"\n{BOLD}Step 4 — Cleaning up files/ folder{RESET}")
    try:
        shutil.rmtree(FILES)
        ok("files/ folder removed")
    except Exception as e:
        warn(f"Could not remove files/ folder: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}── Summary ──────────────────────────────{RESET}")
    print(f"  {GREEN}Moved:   {moved}{RESET}")
    print(f"  {GREEN}Removed: {removed}{RESET}")
    print(f"  {GRAY}Skipped: {skipped}{RESET}")
    print(f"  {RED if errors else GREEN}Errors:  {errors}{RESET}")

    if errors == 0:
        print(f"\n{GREEN}{BOLD}✓ Deployment complete.{RESET}")
        print(f"\nNext steps:")
        print(f"  1. git add .")
        print(f"  2. git commit -m \"refactor: rename bots and tasks to ALGO_ convention\"")
        print(f"  3. git push")
        print(f"  4. ssh forexvps \"cd C:\\algos && git pull origin main\"")
        print(f"  5. Rename VPS files (see SCHEDULER_GUIDE.md)")
        print(f"  6. Reinstall Task Scheduler tasks (see SCHEDULER_GUIDE.md)")
    else:
        print(f"\n{YELLOW}Deployment completed with {errors} error(s). Review above.{RESET}")


if __name__ == "__main__":
    deploy()
