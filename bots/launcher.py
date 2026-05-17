"""
launcher.py — Universal launcher for all bots.
Used by Windows Task Scheduler. Accepts bot name and config path.

Usage:
    python bots/launcher.py --bot bot1 --config instances/gold_main/config.json
    python bots/launcher.py --bot bot2 --config instances/gold_main/config.json
    python bots/launcher.py --bot bot3 --config instances/gold_scalper/config.json
    python bots/launcher.py --bot bot4 --config instances/futures_account1/config.json

Bot map:
    bot1 = bot_smc_trend.py       (FX, MT5)
    bot2 = bot_mean_reversion.py  (FX, MT5)
    bot3 = bot_scalper.py         (FX, MT5)
    bot4 = bot_futures.py       (Futures, Tradovate)

One launcher handles all bots and all instances.
To add a new bot: add its script name to BOT_SCRIPTS below.
"""

import subprocess
import sys
import argparse
from pathlib import Path

BOT_SCRIPTS = {
    "bot_smc_trend":      "bot_smc_trend.py",
    "bot_mean_reversion": "bot_mean_reversion.py",
    "bot_scalper":        "bot_scalper.py",
    "bot_futures":        "bot_futures.py",
    "bot_fft":            "bot_fft.py",
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
    bot_name = args.bot.replace("bot_", "")
    log_out  = config.parent / f"{bot_name}_stdout.log"

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
        # Do NOT call proc.wait() — the bot runs forever
        # Task Scheduler will track this process directly
        print(f"{args.bot} started with PID {proc.pid}")

if __name__ == "__main__":
    main()
