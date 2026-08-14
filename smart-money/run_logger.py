"""
Pipeline run logger. Wraps stdlib logging with structured stage-level counters.
Every pipeline run appends to smart-money.log and prints to stdout.
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

_LOG_FILE = Path(__file__).parent / "data" / "smart_money.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(_fmt)

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_fmt)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(_file_handler)
        logger.addHandler(_stream_handler)
        logger.propagate = False
    return logger


class StageLogger:
    """
    Wraps a standard logger with per-stage counters that are flushed
    as a single summary line at the end of each run.
    """

    def __init__(self, stage: str):
        self.stage = stage
        self._logger = get_logger(f"stage.{stage}")
        self._counts: dict[str, int] = {}
        self._start = datetime.utcnow()

    # ------------------------------------------------------------------
    # Passthrough logging
    # ------------------------------------------------------------------
    def info(self, msg: str):
        self._logger.info(msg)

    def warning(self, msg: str):
        self._logger.warning(msg)

    def error(self, msg: str):
        self._logger.error(msg)

    def debug(self, msg: str):
        self._logger.debug(msg)

    # ------------------------------------------------------------------
    # Counter helpers
    # ------------------------------------------------------------------
    def increment(self, key: str, n: int = 1):
        self._counts[key] = self._counts.get(key, 0) + n

    def set(self, key: str, value: int):
        self._counts[key] = value

    def get(self, key: str) -> int:
        return self._counts.get(key, 0)

    def log_api_error(self, endpoint: str, error: Exception):
        self._logger.error(f"API error [{endpoint}]: {error}")
        self.increment("api_errors")

    def log_disqualified(self, address: str, reason: str):
        self._logger.info(f"DISQUALIFIED {address[:10]}... — {reason}")
        self.increment("disqualified")

    def log_qualified(self, address: str, score: float = None):
        score_str = f" (score={score:.1f})" if score is not None else ""
        self._logger.info(f"QUALIFIED    {address[:10]}...{score_str}")
        self.increment("qualified")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def summary(self) -> dict:
        elapsed = (datetime.utcnow() - self._start).total_seconds()
        return {
            "stage": self.stage,
            "elapsed_seconds": round(elapsed, 1),
            **self._counts,
        }

    def print_summary(self):
        s = self.summary()
        lines = [f"\n{'=' * 60}", f"  Stage {self.stage} — Run Summary", f"{'=' * 60}"]
        for k, v in s.items():
            if k not in ("stage",):
                lines.append(f"  {k:<40} {v}")
        lines.append(f"{'=' * 60}\n")
        self._logger.info("\n".join(lines))
