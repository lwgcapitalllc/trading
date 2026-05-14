"""
bot_utils.py — Shared utility imported by every bot.

Handles:
  1. --config argument so each bot loads the right instance config
  2. sys.path injection so bots can always find shared\ modules
  3. Logging setup that writes to the instance directory

Usage in every bot (first two lines after docstring):
    from bot_utils import load_config, setup_logging, get_instance_dir
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

    Run a bot like:
        python bots\bot1_smc_trend.py --config instances\xauusd_main\config.json

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
            f"  Usage: python bots\\bot1_smc_trend.py "
            f"--config instances\\xauusd_main\\config.json\n"
        )

    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    cfg["_instance_dir"]  = str(cfg_path.parent.resolve())
    cfg["_config_path"]   = str(cfg_path.resolve())
    return cfg


def get_instance_dir(cfg: dict) -> Path:
    """Where logs, trade files, and model files are written for this instance."""
    return Path(cfg["_instance_dir"])


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
