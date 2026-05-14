"""
launcher.py — Universal launcher for all bots.
Used by Windows Task Scheduler. Accepts bot name and config path.

Usage:
    python bots\launcher.py --bot bot1 --config instances\xauusd_main\config.json
    python bots\launcher.py --bot bot2 --config instances\xauusd_main\config.json
    python bots\launcher.py --bot bot3 --config instances\xauusd_scalper\config.json

This replaces launch_bot1.py / launch_bot2.py / launch_bot3.py.
One launcher handles all bots and all instances.
"""

import subprocess
import sys
import argparse
from pathlib import Path

BOT_SCRIPTS = {
    "bot1": "bot1_smc_trend.py",
    "bot2": "bot2_mean_reversion.py",
    "bot3": "bot3_scalper.py",
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot",    required=True, choices=BOT_SCRIPTS.keys())
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    bots_dir   = Path(__file__).parent
    script     = bots_dir / BOT_SCRIPTS[args.bot]
    config     = Path(args.config).resolve()

    # Log file sits next to the config (instance dir)
    log_out    = config.parent / f"{args.bot}_stdout.log"

    if not script.exists():
        print(f"ERROR: Bot script not found: {script}")
        sys.exit(1)

    if not config.exists():
        print(f"ERROR: Config not found: {config}")
        sys.exit(1)

    print(f"Starting {args.bot} with config: {config}")

    with open(log_out, "a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            [sys.executable, str(script), "--config", str(config)],
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=out,
            cwd=str(bots_dir),
        )
        proc.stdin.write(b"CONFIRM\n")
        proc.stdin.flush()
        proc.stdin.close()
        proc.wait()

if __name__ == "__main__":
    main()
