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


def fetch_results_via_agent(local_path, agent_url="http://localhost:8765"):
    """Fetch results from vps_agent /results endpoint and write CSV locally."""
    import csv as csv_mod
    import urllib.request, urllib.error
    print(f"\nFetching results from agent ({agent_url}/results)...")
    try:
        with urllib.request.urlopen(f"{agent_url}/results", timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  Agent returned {e.code}: {body}")
        return False
    except Exception as e:
        print(f"  Could not reach agent: {e}")
        print("  Ensure SSH tunnel is up: ssh -N -f -L 8765:127.0.0.1:8765 forexvps")
        return False
    rows = data.get("rows", [])
    if not rows:
        print("  No results rows yet. Run backtests first.")
        return False
    fieldnames = list(rows[0].keys())
    with open(local_path, "w", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {len(rows)} row(s) saved to {local_path}")
    return True


def trigger_and_wait(agent_url="http://localhost:8765"):
    """Trigger /run-backtests and poll /status until done."""
    import urllib.request, urllib.error
    print("\nTriggering backtests via agent...")
    try:
        req = urllib.request.Request(f"{agent_url}/run-backtests",
                                     data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  {json.loads(resp.read())}")
    except urllib.error.HTTPError as e:
        print(f"  {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"  Could not reach agent: {e}")
        return False

    print("  Waiting for completion (polling every 15s)...")
    deadline = time.time() + 90 * 60
    while time.time() < deadline:
        time.sleep(15)
        try:
            with urllib.request.urlopen(f"{agent_url}/status", timeout=10) as resp:
                st = json.loads(resp.read())
            logs = st.get("log", [])
            if logs:
                print(f"  {logs[-1]}")
            if not st.get("running"):
                print("  Run complete.")
                return True
        except Exception:
            pass
    print("  WARNING: timed out waiting for agent.")
    return False


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
        sh(f'ssh {host} "move /Y {fname} {tools_win}"')

    # Launch via wmic in session 0 — pywinauto UIA backend can reach NT8 cross-session as admin
    wmic_cmd = f"python {runner_win} --config {cfg_win}"
    print("\nLaunching backtest runner on VPS (wmic)...")
    print("  NT8 must be running with Strategy Analyzer open.")
    sh(f'ssh {host} "wmic process call create \\"{wmic_cmd}\\" "', check=False)
    time.sleep(5)

    # Poll the log file until runner exits (up to 90 minutes)
    print("  Waiting for backtests to complete (up to 90 min)...")
    deadline = time.time() + 90 * 60
    last_size = -1
    done = False
    while time.time() < deadline:
        time.sleep(30)
        log_out = subprocess.run(
            f'ssh {host} "type {log_win}"',
            shell=True, capture_output=True, text=True
        )
        size = len(log_out.stdout)
        if size != last_size:
            last_size = size
            if log_out.stdout.strip():
                last_line = log_out.stdout.strip().splitlines()[-1]
                print(f"  [{last_line}]")
        # Done when log contains a final status line
        if "Complete" in log_out.stdout or "ERROR" in log_out.stdout:
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


def run_analyze(local_only=False, use_http=False):
    print("=" * 60)
    print("STEP 3: Fetch + analyze results")
    print("=" * 60)
    cfg = load_config()
    local_results = os.path.join(SCRIPT_DIR, cfg["results_local_path"])

    if not local_only:
        ok = fetch_results_via_agent(local_results) if use_http else False
        if not ok and not use_http:
            print("\nSkipping analysis — no results file.")
            return
        if not ok:
            print("\nSkipping analysis — could not fetch results.")
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
    parser.add_argument("--http",          action="store_true",
                        help="Use vps_agent HTTP API (requires SSH tunnel on port 8765)")
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
        run_analyze(local_only=args.local_results, use_http=args.http)
        return

    # Full HTTP pipeline: trigger run, wait, fetch, analyze
    if args.http:
        trigger_and_wait()
        time.sleep(3)
        run_analyze(use_http=True)
        return

    # Full pipeline (legacy)
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
