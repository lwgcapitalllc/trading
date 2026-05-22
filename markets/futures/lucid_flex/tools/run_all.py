"""
Master orchestrator for the LucidFlex backtest pipeline.

Modes:
  Full pipeline (deploy + wait for manual runs + fetch + analyze):
    python run_all.py

  Deploy and compile only:
    python run_all.py --deploy-only

  Fetch results from VPS and analyze (skip deploy):
    python run_all.py --analyze-only

  Analyze a local results file you already have:
    python run_all.py --analyze-only --local-results

Automated backtest runs (requires NT8 open on VPS with Strategy Analyzer visible):
    python run_all.py --auto-run
    This SSHes to VPS and runs vps_backtest_runner.py via pywinauto.
"""

import subprocess
import sys
import os
import json
import argparse
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH   = os.path.join(SCRIPT_DIR, "backtest_config.json")


def load_config():
    with open(CFG_PATH) as f:
        return json.load(f)


def sh(cmd, check=True, echo=True):
    if echo:
        print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=False, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR: command exited {result.returncode}")
        sys.exit(1)
    return result.returncode


def scp_from_vps(cfg):
    user     = cfg["vps_user"]
    host     = cfg["vps_host"]
    remote   = cfg["results_remote_path"]
    local    = os.path.join(SCRIPT_DIR, cfg["results_local_path"])

    # Convert Windows path to scp-compatible path
    # e.g. Documents/NinjaTrader 8/... → /c/Users/Administrator/Documents/NinjaTrader 8/...
    remote_full = f'/c/Users/{user}/{remote}'

    print(f"\nFetching results from VPS...")
    rc = sh(f'scp "{host}:{remote_full}" "{local}"', check=False)
    if rc != 0:
        print(f"  Could not fetch {remote_full}")
        print(f"  Check that at least one backtest has been run and results file exists.")
        return False
    print(f"  Saved to {local}")
    return True


def run_deploy():
    print("=" * 60)
    print("STEP 1: Deploy + compile strategies on VPS")
    print("=" * 60)
    deploy_script = os.path.join(SCRIPT_DIR, "deploy.py")
    sh(f'python "{deploy_script}"')


def run_auto_backtest(cfg):
    print("=" * 60)
    print("STEP 2: Running backtests via pywinauto (VPS)")
    print("=" * 60)
    host   = cfg["vps_host"]
    user   = cfg["vps_user"]
    runner = f"C:/Users/{user}/Documents/NinjaTrader 8/tools/vps_backtest_runner.py"
    cfg_r  = f"C:/Users/{user}/Documents/NinjaTrader 8/tools/backtest_config.json"

    # Upload the runner and config to VPS
    local_runner = os.path.join(SCRIPT_DIR, "vps_backtest_runner.py")
    local_cfg    = CFG_PATH
    dst          = f"/c/Users/{user}/Documents/NinjaTrader 8/tools"

    sh(f'ssh {host} "mkdir -p \'{dst}\'"')
    sh(f'scp "{local_runner}" "{host}:{dst}/"')
    sh(f'scp "{local_cfg}"    "{host}:{dst}/"')

    print("\nLaunching vps_backtest_runner.py on VPS...")
    print("  (NT8 must be running with Strategy Analyzer open)")
    sh(f'ssh -t {host} "python \\"{runner}\\" --config \\"{cfg_r}\\""')


def wait_for_manual_run():
    print("=" * 60)
    print("STEP 2: Manual backtest runs")
    print("=" * 60)
    print()
    print("  On the VPS, run all 6 combos in the Strategy Analyzer.")
    print("  Settings per combo are in backtest_config.json.")
    print("  Each run will auto-export to: Documents\\NinjaTrader 8\\lucid_flex_results.csv")
    print()
    print("  Combos to run:")
    cfg = load_config()
    for c in cfg["combos"]:
        gp = cfg["global_params"]
        print(f"    [{c['id']}]  {c['strategy']}  on  {c['instrument']}")
        print(f"         5-min bars, RTH, {gp['start_date']} – {gp['end_date']}, "
              f"slippage={gp['slippage']}t")
        extra = ", ".join(f"{k}={v}" for k, v in c["params"].items())
        print(f"         {extra}")
        print()
    input("  Press ENTER when all 6 runs are complete...")


def run_analyze(local_only=False):
    print("=" * 60)
    print("STEP 3: Fetch + analyze results")
    print("=" * 60)
    cfg = load_config()

    local_results = os.path.join(SCRIPT_DIR, cfg["results_local_path"])

    if not local_only:
        ok = scp_from_vps(cfg)
        if not ok:
            print("\nSkipping analysis — no results file.")
            return

    if not os.path.exists(local_results):
        print(f"  No results file at {local_results}")
        return

    analyze_script = os.path.join(SCRIPT_DIR, "analyze.py")
    sh(f'python "{analyze_script}" --results "{local_results}"', echo=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deploy-only",   action="store_true")
    parser.add_argument("--analyze-only",  action="store_true")
    parser.add_argument("--auto-run",      action="store_true",
                        help="Automate Strategy Analyzer via pywinauto (requires NT8 open on VPS)")
    parser.add_argument("--local-results", action="store_true",
                        help="Use already-downloaded results file; skip VPS fetch")
    args = parser.parse_args()

    cfg = load_config()

    if args.deploy_only:
        run_deploy()
        return

    if args.analyze_only:
        run_analyze(local_only=args.local_results)
        return

    # Full pipeline
    run_deploy()

    if args.auto_run:
        run_auto_backtest(cfg)
        time.sleep(5)
        run_analyze()
    else:
        wait_for_manual_run()
        run_analyze()


if __name__ == "__main__":
    main()
