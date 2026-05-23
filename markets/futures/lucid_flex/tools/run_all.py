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
    host   = cfg["vps_host"]
    remote = cfg["results_remote_path"].replace("/", "\\")
    local  = os.path.join(SCRIPT_DIR, cfg["results_local_path"])

    print(f"\nFetching results from VPS...")
    result = subprocess.run(
        f'ssh {host} "type \\"{remote}\\""',
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Could not fetch {remote}")
        print(f"  Check that at least one backtest has been run and results file exists.")
        return False
    with open(local, "w", encoding="utf-8") as f:
        f.write(result.stdout)
    print(f"  Saved to {local}")
    return True


def run_deploy():
    print("=" * 60)
    print("STEP 1: Deploy + compile strategies on VPS")
    print("=" * 60)
    deploy_script = os.path.join(SCRIPT_DIR, "deploy.py")
    sh(f'"{sys.executable}" "{deploy_script}"')


def run_auto_backtest(cfg):
    """
    Upload backtest runner to VPS, then launch it in the Administrator's
    interactive RDP session via Task Scheduler (/it flag).
    SSH sessions are isolated from the RDP session, so direct SSH → pywinauto
    doesn't work — Task Scheduler bridges the gap.
    """
    print("=" * 60)
    print("STEP 2: Running backtests via pywinauto (VPS)")
    print("=" * 60)
    host      = cfg["vps_host"]
    # Use C:\algos path — no spaces, already exists on VPS from git pull
    tools_win = r"C:\algos\markets\futures\lucid_flex\tools"
    runner_win = rf"{tools_win}\vps_backtest_runner.py"
    cfg_win    = rf"{tools_win}\backtest_config.json"
    log_win    = rf"{tools_win}\backtest_runner.log"
    task_name  = "NT8BacktestRunner"

    local_runner = os.path.join(SCRIPT_DIR, "vps_backtest_runner.py")
    local_cfg    = CFG_PATH

    # Upload runner + config (SCP to home → move to tools dir)
    for local, fname in [(local_runner, "vps_backtest_runner.py"),
                         (local_cfg,    "backtest_config.json")]:
        r = subprocess.run(["scp", local, f"{host}:{fname}"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  SCP ERROR: {r.stderr.strip()}")
            sys.exit(1)
        sh(f'ssh {host} "move /Y {fname} {tools_win}\\"')

    # Build task command — no spaces in any path now
    task_cmd = (
        f"cmd /c python {runner_win} "
        f"--config {cfg_win} "
        f"> {log_win} 2>&1"
    )

    # Create + immediately run the scheduled task in the interactive session (/it)
    print("\nScheduling backtest runner in interactive RDP session...")
    sh(f'ssh {host} "schtasks /create /F /tn {task_name} '
       f'/tr \\"{task_cmd}\\" /sc ONCE /st 00:00 '
       f'/ru ADMINISTRATOR /it /rl HIGHEST"')
    sh(f'ssh {host} "schtasks /run /tn {task_name}"')

    # Poll until the log file appears and runner exits (up to 90 minutes)
    print("  Waiting for backtests to complete (up to 90 min)...")
    deadline = time.time() + 90 * 60
    done = False
    while time.time() < deadline:
        time.sleep(30)
        # Task is done when schtasks status is no longer "Running"
        status_out = subprocess.run(
            f'ssh {host} "schtasks /query /tn {task_name} /fo LIST"',
            shell=True, capture_output=True, text=True
        ).stdout
        if "Running" not in status_out:
            done = True
            break
        elapsed = int(time.time() - (deadline - 90 * 60))
        print(f"  Still running... ({elapsed // 60}m {elapsed % 60}s elapsed)")

    # Pull and print the log
    log_result = subprocess.run(
        f'ssh {host} "type \\"{log_win}\\""',
        shell=True, capture_output=True, text=True
    )
    if log_result.stdout.strip():
        print("\n--- VPS backtest runner output ---")
        print(log_result.stdout)
        print("--- end ---\n")

    if not done:
        print("  WARNING: timed out waiting for backtest runner. Check VPS.")
        sys.exit(1)


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
    sh(f'"{sys.executable}" "{analyze_script}" --results "{local_results}"', echo=False)


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
