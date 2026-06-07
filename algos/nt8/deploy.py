"""
Deploy NinjaScript strategies to VPS and trigger NT8 compilation.

Usage:
    python deploy.py
"""

import subprocess
import sys
import json
import os
import time

CFG_PATH = os.path.join(os.path.dirname(__file__), "backtest_config.json")
STRATEGY_FILES = ["ORB_LucidFlex.cs", "VWAP_MR_LucidFlex.cs", "Momentum_LucidFlex.cs"]


def load_config():
    with open(CFG_PATH) as f:
        return json.load(f)


def run_local(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip() or result.stdout.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def ssh(cfg, remote_cmd, check=True):
    cmd = f'ssh {cfg["vps_host"]} "{remote_cmd}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  SSH ERROR: {result.stderr.strip() or result.stdout.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def copy_strategies(cfg):
    """
    SCP each .cs file to the VPS home dir (no spaces), then SSH-move to the
    NinjaTrader 8 strategies folder (which has a space in the path).
    """
    src_dir  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    host     = cfg["vps_host"]
    dst_win  = cfg["strategies_dst_dir"].replace("/", "\\")

    print("Copying strategy files to VPS...")
    for fname in STRATEGY_FILES:
        src = os.path.join(src_dir, fname)
        if not os.path.exists(src):
            print(f"  WARNING: {fname} not found at {src}, skipping")
            continue

        # Step 1 — SCP to home dir (no spaces, always works)
        result = subprocess.run(
            ["scp", src, f"{host}:{fname}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  SCP ERROR: {result.stderr.strip()}")
            sys.exit(1)

        # Step 2 — move from home dir to strategies folder
        move_cmd = f'move /Y "{fname}" "{dst_win}\\"'
        result = subprocess.run(
            ["ssh", host, move_cmd],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  MOVE ERROR ({fname}): {result.stderr.strip() or result.stdout.strip()}")
            sys.exit(1)

        print(f"  {fname}")
    print("  Done.")


def trigger_compile(cfg):
    """
    Run NinjaTrader.exe /compile on the VPS.
    NT8 compiles all Custom scripts and exits.  Output goes to NT8's own log.
    """
    nt8    = cfg["nt8_exe"].replace("\\", "\\\\")
    user   = cfg["vps_user"]
    logdir = f"C:\\\\Users\\\\{user}\\\\Documents\\\\NinjaTrader 8\\\\log"

    print("Triggering NT8 compilation on VPS...")
    # Run in background — /compile exits after it finishes
    out = ssh(cfg,
              f'"{nt8}" /compile',
              check=False)

    # Give NT8 a moment to write the log
    time.sleep(8)

    # Pull the latest log file and check for compile errors
    log_check = ssh(cfg,
        f'powershell -Command "Get-ChildItem \\"{logdir}\\" | '
        f'Sort-Object LastWriteTime -Descending | '
        f'Select-Object -First 1 | '
        f'Get-Content | Select-String -Pattern \\"Error\\",\\"error\\",\\"failed\\"" ',
        check=False)

    if log_check:
        print("  Potential compile issues detected:")
        print(f"  {log_check}")
        print("  Check NT8 NinjaScript Editor (F5 on each tab) to confirm.")
    else:
        print("  Compilation appears clean.")


def clear_results(cfg):
    user    = cfg["vps_user"]
    path    = f"/c/Users/{user}/{cfg['results_remote_path']}"
    print("Clearing previous results file on VPS (if any)...")
    ssh(cfg, f'del /f /q "C:\\Users\\{user}\\Documents\\NinjaTrader 8\\lucid_flex_results.csv"',
        check=False)
    print("  Done.")


def main():
    cfg = load_config()
    copy_strategies(cfg)
    trigger_compile(cfg)
    clear_results(cfg)
    print("\nDeploy complete. Now run Strategy Analyzer backtests on the VPS,")
    print("then run: python run_all.py --analyze-only")


if __name__ == "__main__":
    main()
