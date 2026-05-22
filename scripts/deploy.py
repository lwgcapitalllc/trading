#!/usr/bin/env python3
"""
deploy.py — LWG Capital Algo Suite Deployment Script

TWO WAYS TO USE:

────────────────────────────────────────────────────────────
METHOD 1 — FLAT (for simple updates, most common)
────────────────────────────────────────────────────────────
Drop files flat into algos/files/ using the names in MANIFEST below.
Files with the same name in different folders get a prefix:

  config.json from gold_main/    → name it: gold_main_config.json
  config.json from gold_scalper/ → name it: gold_scalper_config.json
  config.json from gold_fft/     → name it: gold_fft_config.json
Everything else (bots, guides, xmls) has a unique name already.

────────────────────────────────────────────────────────────
METHOD 2 — STRUCTURED (mirrors the repo, best for bulk updates)
────────────────────────────────────────────────────────────
Create subfolders inside files/ that match the repo structure:

  files/
  ├── bots/
  │   ├── bot_smc_trend.py
  │   └── launcher.py
  ├── markets/
  │   └── fx/
  │       └── instances/
  │           └── gold_main/
  │               └── config.json
  └── notifications/
      └── reporter.py

Deploy will copy each file to the exact same relative path in the repo.

────────────────────────────────────────────────────────────
USAGE:
    cd /Users/alwg/algos
    python3 deploy.py
────────────────────────────────────────────────────────────
"""

import shutil
from pathlib import Path

ROOT  = Path(__file__).parent.parent
FILES = ROOT / "files"

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET} {msg}")
def err(msg):  print(f"  {RED}✗{RESET} {msg}")
def info(msg): print(f"  {GRAY}{msg}{RESET}")


# =============================================================================
# FLAT MANIFEST — filename in files/ → destination path in repo
# For files that share names across folders, use the prefixed names below.
# =============================================================================

MANIFEST = {
    # ── Bots ──────────────────────────────────────────────────────────────────
    "bot_smc_trend.py":              "bots/bot_smc_trend.py",
    "bot_mean_reversion.py":         "bots/bot_mean_reversion.py",
    "bot_scalper.py":                "bots/bot_scalper.py",
    "bot_fft.py":                    "bots/bot_fft.py",
    "bot_utils.py":                  "bots/bot_utils.py",
    "launcher.py":                   "bots/launcher.py",

    # ── Bot guides ────────────────────────────────────────────────────────────
    "BOT_SMC_TREND_GUIDE.md":        "bots/BOT_SMC_TREND_GUIDE.md",
    "BOT_MEAN_REVERSION_GUIDE.md":   "bots/BOT_MEAN_REVERSION_GUIDE.md",
    "BOT_SCALPER_GUIDE.md":          "bots/BOT_SCALPER_GUIDE.md",
    "BOT_FFT_GUIDE.md":              "bots/BOT_FFT_GUIDE.md",

    # ── Shared ────────────────────────────────────────────────────────────────
    "shared_ai_brain.py":            "shared/shared_ai_brain.py",
    "shared_calmar.py":              "shared/shared_calmar.py",
    "shared_regime.py":              "shared/shared_regime.py",

    # ── Notifications ─────────────────────────────────────────────────────────
    "reporter.py":                   "notifications/reporter.py",
    "monitor.py":                    "notifications/monitor.py",
    "telegram_bot.py":               "notifications/telegram_bot.py",
    "NOTIFICATIONS_GUIDE.md":        "notifications/NOTIFICATIONS_GUIDE.md",

    # ── Scheduler XMLs ────────────────────────────────────────────────────────
    "smc_trend_task.xml":            "scheduler/smc_trend_task.xml",
    "mean_reversion_task.xml":       "scheduler/mean_reversion_task.xml",
    "scalper_task.xml":              "scheduler/scalper_task.xml",
    "fft_task.xml":                  "scheduler/fft_task.xml",
    "telegram_task.xml":             "scheduler/telegram_task.xml",
    "reporter_task.xml":             "scheduler/reporter_task.xml",
    "monitor_task.xml":              "scheduler/monitor_task.xml",
    "SCHEDULER_GUIDE.md":            "scheduler/SCHEDULER_GUIDE.md",

    # ── Instance configs — use prefixed names to avoid name collisions ─────────
    "gold_main_config.json":         "markets/fx/instances/gold_main/config.json",
    "gold_main_credentials.template.json":
                                     "markets/fx/instances/gold_main/credentials.template.json",
    "gold_scalper_config.json":      "markets/fx/instances/gold_scalper/config.json",
    "gold_scalper_credentials.template.json":
                                     "markets/fx/instances/gold_scalper/credentials.template.json",
    "gold_fft_config.json":          "markets/fx/instances/gold_fft/config.json",
    "gold_fft_credentials.template.json":
                                     "markets/fx/instances/gold_fft/credentials.template.json",
    # ── Root files ────────────────────────────────────────────────────────────
    "algo.py":                                   "algo.py",
    "README.md":                                 "README.md",

    # ── Docs ─────────────────────────────────────────────────────────────────
    "docs/SETUP.md":                             "docs/SETUP.md",
    "docs/ALGO_CONTROL_PANEL_GUIDE.md":          "docs/ALGO_CONTROL_PANEL_GUIDE.md",

    # ── Scripts ───────────────────────────────────────────────────────────────
    "scripts/stress_test_suite.py":              "scripts/stress_test_suite.py",
    "scripts/deploy.py":                         "scripts/deploy.py",
}


# =============================================================================
# OLD FILES TO REMOVE
# =============================================================================

OLD_FILES = [
    "bots/bot1_smc_trend.py",
    "bots/bot2_mean_reversion.py",
    "bots/bot3_scalper.py",
    "bots/bot4_lucidflex.py",
    "bots/bot5_fft.py",
    "bots/BOT1_SMC_TREND_GUIDE.md",
    "bots/BOT2_MEAN_REVERSION_GUIDE.md",
    "bots/BOT3_SCALPER_GUIDE.md",
    "bots/BOT4_LUCIDFLEX_GUIDE.md",
    "bots/BOT5_FFT_GUIDE.md",
    "scheduler/bot1_task.xml",
    "scheduler/bot2_task.xml",
    "scheduler/bot3_task.xml",
    "scheduler/bot5_task.xml",
    "scheduler/telegram_bot_task.xml",
    "reporter.py",
    "monitor.py",
    "telegram_bot.py",
    "telegram_offset.json",
    "reporter_task.xml",
    "monitor_task.xml",
    "telegram_bot_task.xml",
    "SSH_SETUP_AND_COMMANDS.txt",
    "test_tradovate_auth.py",
    "executors/tradovate.py",
    "bots/bot_futures.py",
    "bots/BOT_FUTURES_GUIDE.md",
    "scheduler/futures_acct1_task.xml",
    "markets/futures/instances/futures_account1/config.json",
    "markets/futures/instances/futures_account1/credentials.template.json",
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
    print(f"Root:  {ROOT}")
    print(f"Files: {FILES}\n")

    if not FILES.exists():
        err(f"files/ folder not found.")
        print(f"\n  Create it and add your downloaded files:")
        print(f"  mkdir {FILES}")
        print(f"\n  Then either:")
        print(f"  A) Drop flat files using the names in MANIFEST")
        print(f"  B) Mirror the repo structure inside files/")
        return

    moved   = 0
    skipped = 0
    removed = 0
    errors  = 0

    # ── Step 1a: Structured files (mirror repo structure inside files/) ───────
    print(f"{BOLD}Step 1 — Copying files to correct locations{RESET}")

    # Walk all files inside files/ recursively
    structured_files = [f for f in FILES.rglob("*") if f.is_file()]
    for src in structured_files:
        rel = src.relative_to(FILES)
        # If it's a direct file (no subfolder), handle via manifest (Step 1b)
        if len(rel.parts) == 1:
            continue
        # Structured — copy to same relative path in ROOT
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
            ok(f"{rel} → {rel}")
            moved += 1
        except Exception as e:
            err(f"{rel}: {e}")
            errors += 1

    # ── Step 1b: Flat files — match via MANIFEST ──────────────────────────────
    for src_name, dest_rel in MANIFEST.items():
        src  = FILES / src_name
        dest = ROOT  / dest_rel
        if not src.exists():
            info(f"Skip (not in files/): {src_name}")
            skipped += 1
            continue
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

    # ── Step 3: Remove old directories ────────────────────────────────────────
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
        print(f"  Could not remove files/: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}── Summary ──────────────────────────────{RESET}")
    print(f"  {GREEN}Moved:   {moved}{RESET}")
    print(f"  {GREEN}Removed: {removed}{RESET}")
    print(f"  {GRAY}Skipped: {skipped}{RESET}")
    print(f"  {RED if errors else GREEN}Errors:  {errors}{RESET}")

    if errors == 0:
        print(f"\n{GREEN}{BOLD}✓ Deployment complete.{RESET}")
        print(f"\nNext steps:")
        print(f"  git add .")
        print(f"  git commit -m 'your message'")
        print(f"  git push")
        print(f"  ssh forexvps \"cd C:\\algos && git pull origin main\"")
    else:
        print(f"\n{YELLOW}Completed with {errors} error(s). Review above.{RESET}")


if __name__ == "__main__":
    deploy()
