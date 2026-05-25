"""
Register the LucidFlex Agent as a Windows Task Scheduler logon task on the VPS.

Run once from Mac after deploying vps_agent.py:
    python3 markets/futures/lucid_flex/tools/setup_agent_task.py

What it does:
  1. SSHes to VPS and installs flask (if missing)
  2. Creates a Task Scheduler task that auto-starts vps_agent.py when
     Administrator logs in via RDP

After setup, the agent will start automatically on each RDP login.
You can also start it manually on the VPS with:
    schtasks /run /tn "LucidFlexAgent"

To use from Mac:
    ssh -N -L 8765:localhost:8765 forexvps &
    curl http://localhost:8765/health
"""

import subprocess
import sys
import json
import os

CFG_PATH = os.path.join(os.path.dirname(__file__), "backtest_config.json")
AGENT_WIN = r"C:\trading\algos\markets\futures\lucid_flex\tools\vps_agent.py"
TASK_NAME = "LucidFlexAgent"


def ssh(host, cmd, check=True):
    result = subprocess.run(
        f'ssh {host} "{cmd}"',
        shell=True, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f"  SSH ERROR: {result.stderr.strip() or result.stdout.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    with open(CFG_PATH) as f:
        cfg = json.load(f)
    host = cfg["vps_host"]

    # Step 1: ensure flask is installed on VPS
    print("Checking flask on VPS...")
    out = ssh(host, "python -c \"import flask; print(flask.__version__)\"", check=False)
    if out:
        print(f"  flask {out} already installed.")
    else:
        print("  Installing flask...")
        ssh(host, "pip install flask", check=True)
        print("  Done.")

    # Step 2: register Task Scheduler logon task
    # /sc onlogon  — fires when Administrator logs in
    # /rl HIGHEST  — run with highest privileges
    # /f           — overwrite if task already exists
    # Omit /ru so it defaults to current user (Administrator)
    print(f"\nRegistering Task Scheduler task '{TASK_NAME}'...")
    task_cmd = (
        f"schtasks /create /tn {TASK_NAME} "
        f"/tr \"python {AGENT_WIN}\" "
        f"/sc onlogon /rl HIGHEST /f"
    )
    out = ssh(host, task_cmd, check=False)
    if out:
        print(f"  {out}")

    # Verify it registered
    verify = ssh(host, f"schtasks /query /tn {TASK_NAME} /fo LIST", check=False)
    if TASK_NAME in verify:
        print(f"  Task registered successfully.")
    else:
        print("  WARNING: could not verify task. Check Task Scheduler on VPS manually.")
        print(f"  Command to register manually:")
        print(f"    {task_cmd}")

    print()
    print("Setup complete. The agent will auto-start on next RDP login.")
    print("To start it now (from VPS terminal):")
    print(f"    schtasks /run /tn {TASK_NAME}")
    print()
    print("To connect from Mac:")
    print("    ssh -N -L 8765:localhost:8765 forexvps &")
    print("    curl http://localhost:8765/health")


if __name__ == "__main__":
    main()
