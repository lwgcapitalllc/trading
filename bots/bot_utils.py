"""
bot_utils.py — Shared utility imported by every bot.

Handles:
  1. --config argument so each bot loads the right instance config
  2. sys.path injection so bots can always find shared/ modules
  3. Logging setup that writes to the instance directory

Usage in every bot (first two lines after docstring):
    from bot_utils import load_config, setup_logging, get_instance_dir, load_weekly_start
    CFG = load_config()
"""

import sys, json, logging, argparse
from pathlib import Path


def _inject_shared_path():
    bots_dir   = Path(__file__).parent        # C:\algos\bots\
    shared_dir = bots_dir.parent / "shared"   # C:\algos\shared\
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))

_inject_shared_path()


def load_config() -> dict:
    """
    Load config from --config path argument.
    Credentials are loaded separately from credentials.json in the same
    instance directory and merged in. credentials.json is never committed
    to GitHub.

    Run a bot like:
        python bots/bot1_smc_trend.py --config instances/xauusd_main/config.json

    Falls back to config.json next to the bot file if --config not given.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str, default=None)
    args, _ = parser.parse_known_args()

    if args.config:
        cfg_path = Path(args.config)
    else:
        cfg_path = Path(sys.argv[0]).resolve().parent / "config.json"

    if not cfg_path.exists():
        raise FileNotFoundError(
            f"\n\n  Config not found: {cfg_path}\n"
            f"  Usage: python bots/bot1_smc_trend.py "
            f"--config instances/xauusd_main/config.json\n"
        )

    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    # Load credentials.json from same instance directory
    creds_path = cfg_path.parent / "credentials.json"
    if not creds_path.exists():
        platform = cfg.get("platform", "mt5")
        if platform == "tradovate":
            example = (
                f"  {{\n"
                f"      \"username\":    \"your_tradovate_username\",\n"
                f"      \"password\":    \"your_tradovate_password\",\n"
                f"      \"account_id\":  12345678,\n"
                f"      \"environment\": \"demo\"\n"
                f"  }}\n"
            )
        else:
            example = (
                f"  {{\n"
                f"      \"login\":    YOUR_ACCOUNT_NUMBER,\n"
                f"      \"password\": \"YOUR_PASSWORD\",\n"
                f"      \"server\":   \"YOUR_BROKER_SERVER\"\n"
                f"  }}\n"
            )
        raise FileNotFoundError(
            f"\n\n  credentials.json not found at: {creds_path}\n"
            f"  Create it in the same folder as config.json with:\n"
            f"{example}"
            f"  This file is never committed to GitHub.\n"
        )

    with open(creds_path, encoding="utf-8") as f:
        creds = json.load(f)

    # Merge credentials into config under "account" key
    cfg["account"] = creds

    cfg["_instance_dir"]  = str(cfg_path.parent.resolve())
    cfg["_config_path"]   = str(cfg_path.resolve())
    return cfg


def get_instance_dir(cfg: dict) -> Path:
    """Where logs, trade files, and model files are written for this instance."""
    return Path(cfg["_instance_dir"])


def load_weekly_start(bot_key: str, current_week: int, balance: float) -> float:
    """
    Load or initialise the weekly starting balance from bot_state.json.

    If bot_state has a weekly_start for the current ISO week, returns it.
    Otherwise writes the current balance as the new weekly_start and returns it.
    bot_state.json is the single source of truth — no separate *_weekly.json files needed.
    """
    from bot_state import read_bot, write_bot
    state = read_bot(bot_key)
    if state.get("last_week") == current_week and state.get("weekly_start"):
        return float(state["weekly_start"])
    write_bot(bot_key, {"last_week": current_week, "weekly_start": balance})
    return balance


def setup_logging(bot_name: str, cfg: dict) -> logging.Logger:
    """Set up logging — writes to instance directory."""
    d = get_instance_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    log_file = d / f"{bot_name.lower()}.log"

    # Remove any existing handlers (prevents duplicate logs on restart)
    root = logging.getLogger()
    root.handlers.clear()

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s | {bot_name} | %(levelname)-8s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ]
    )
    logger = logging.getLogger(bot_name)
    logger.info(f"Config: {cfg['_config_path']}")
    logger.info(f"Logs  : {log_file}")
    return logger
