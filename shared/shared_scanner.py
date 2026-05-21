"""
shared_scanner.py — Multi-instrument watchlist scanner.

Wraps setup detection across a list of symbols. No strategy logic lives here.
Each bot supplies its own detect_fn(symbol) -> setup_dict | None.

The scanner's job:
  1. Resolve each symbol via mt5.symbol_info() — fail loudly, never silently.
  2. Call the bot's detect_fn for each resolvable symbol.
  3. Collect valid setups and rank best-first by confluence_score.
  4. Log + write bot_state flag for any unresolved symbol (section 1.5).

Unresolved symbol handling (hard requirement from spec):
  (a) WARNING log with unmissable message.
  (b) Append to symbol_errors.log in the instance directory.
  (c) Write unresolved_symbols list to bot_state so monitor.py can send
      one Telegram alert per bad symbol per day (alert-once enforced there).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import MetaTrader5 as mt5

from bot_state import read_bot, write_bot


@dataclass
class SetupCandidate:
    """A valid setup returned by detect_fn for one instrument."""
    symbol:           str
    setup:            dict
    confluence_score: float
    ai_probability:   float = 0.0


class InstrumentScanner:
    """
    Evaluates a watchlist every cycle by calling the bot's detect_fn per symbol.
    Returns candidates ranked best-first by confluence_score.

    One instance per bot. Create after loading config:
        scanner = InstrumentScanner(watchlist, "BOT_SMC_TREND", "smc_trend", _INST, log)
        candidates = scanner.scan(detect_setup)
    """

    def __init__(self, watchlist: list[str], bot_name: str,
                 bot_key: str, instance_dir: Path, log):
        self.watchlist    = watchlist
        self.bot_name     = bot_name
        self.bot_key      = bot_key
        self.instance_dir = Path(instance_dir)
        self.log          = log
        self._errors_log  = self.instance_dir / "symbol_errors.log"

    # ── Symbol validation ─────────────────────────────────────────────────────

    def _is_valid_symbol(self, symbol: str) -> bool:
        """
        True if the broker knows the symbol and has tick data.
        Attempts to select the symbol in Market Watch if not yet visible.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        return tick is not None

    def _report_unresolved(self, symbol: str) -> None:
        """
        Log + persist an unresolved symbol. Called once per scan cycle where
        the symbol fails; the Telegram alert-once logic lives in monitor.py.
        """
        msg = (
            f"UNRESOLVED SYMBOL '{symbol}' — not found on broker. "
            f"Skipping. Check watchlist in config.json."
        )
        self.log.warning(msg)

        # (a) Append to symbol_errors.log
        try:
            self._errors_log.parent.mkdir(parents=True, exist_ok=True)
            line = (
                f"{datetime.utcnow().isoformat()} | bot={self.bot_name} | "
                f"symbol='{symbol}' | config=config.json\n"
            )
            with open(self._errors_log, "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception as exc:
            self.log.error(f"Failed to write symbol_errors.log: {exc}")

        # (b) Write flag to bot_state for monitor.py
        try:
            state     = read_bot(self.bot_key)
            unresolved = state.get("unresolved_symbols", [])
            existing   = {s["symbol"] for s in unresolved}
            if symbol not in existing:
                unresolved.append({
                    "symbol":     symbol,
                    "first_seen": datetime.utcnow().isoformat(),
                })
            write_bot(self.bot_key, {"unresolved_symbols": unresolved})
        except Exception as exc:
            self.log.error(f"Failed to write unresolved_symbols to bot_state: {exc}")

    def _clear_resolved(self, still_unresolved: set[str]) -> None:
        """
        Remove symbols from the bot_state unresolved list that are now resolving.
        Keeps only those that failed in this scan cycle.
        """
        try:
            state     = read_bot(self.bot_key)
            current   = state.get("unresolved_symbols", [])
            updated   = [s for s in current if s["symbol"] in still_unresolved]
            if len(updated) != len(current):
                write_bot(self.bot_key, {"unresolved_symbols": updated})
        except Exception:
            pass

    # ── Main scan ─────────────────────────────────────────────────────────────

    def scan(self, detect_fn: Callable[[str], Optional[dict]]) -> list[SetupCandidate]:
        """
        Iterate the watchlist, call detect_fn(symbol) for each valid symbol,
        collect non-None results, and return them sorted best-first.

        detect_fn must return a dict with at minimum a "score" key, or None.
        """
        candidates:    list[SetupCandidate] = []
        unresolved_now: set[str]            = set()

        for symbol in self.watchlist:
            if not self._is_valid_symbol(symbol):
                self._report_unresolved(symbol)
                unresolved_now.add(symbol)
                continue
            try:
                setup = detect_fn(symbol)
                if setup is not None:
                    candidates.append(SetupCandidate(
                        symbol           = symbol,
                        setup            = setup,
                        confluence_score = float(setup.get("score", 0)),
                    ))
            except Exception as exc:
                self.log.error(f"Scanner: error in detect_fn for {symbol}: {exc}")

        self._clear_resolved(unresolved_now)

        candidates.sort(key=lambda c: c.confluence_score, reverse=True)

        if candidates:
            best = candidates[0]
            self.log.info(
                f"Scanner: {len(candidates)} setup(s) | "
                f"best={best.symbol} score={best.confluence_score:.1f} | "
                f"ranked: {[c.symbol for c in candidates]}"
            )
        else:
            self.log.info(
                f"Scanner: no setups on watchlist "
                f"{self.watchlist} this cycle."
            )

        return candidates
