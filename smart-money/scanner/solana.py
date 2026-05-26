"""
Stage 3, Steps 3.1–3.3: Solana on-chain scanners.

Sources:
  - Dune Analytics  (Step 3.1) — public SQL queries for Drift Protocol, Mango Markets
  - Flipside Crypto  (Step 3.2) — historical DEX trade data for Drift Protocol
  - Birdeye API      (Step 3.3) — Solana wallet trade history, cross-reference

Prerequisites (set as environment variables):
  DUNE_API_KEY      — Dune Analytics API key (free tier)
  FLIPSIDE_API_KEY  — Flipside API key (free tier)
  BIRDEYE_API_KEY   — Birdeye API key (free tier)

Status: SCAFFOLD — API integration pending.
  Set up accounts, retrieve keys, place them in environment variables,
  then implement _fetch_* methods below.
"""

from __future__ import annotations

import os
import time
from run_logger import StageLogger


class DuneScanner:
    """
    Queries Dune Analytics for on-chain Solana perpetuals traders.
    Target protocols: Drift Protocol, Mango Markets.
    """

    DUNE_API_BASE = "https://api.dune.com/api/v1"

    # Public query IDs for perpetuals PnL (community queries — verify before use)
    DRIFT_PNL_QUERY_ID = None   # TODO: find or create Drift Protocol PnL query
    MANGO_PNL_QUERY_ID = None   # TODO: find or create Mango Markets PnL query

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._api_key = os.environ.get(config["stage3"]["dune_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def fetch_drift_traders(self) -> list[dict]:
        """
        Returns list of Drift Protocol trader dicts:
          {address, trade_count, total_pnl, first_trade_ts, last_trade_ts}
        """
        if not self.is_configured():
            self._log.warning("DUNE_API_KEY not set — skipping Dune/Drift scan")
            return []
        # TODO: implement Dune query execution and polling
        # Pattern:
        #   POST /query/{DRIFT_PNL_QUERY_ID}/execute
        #   GET  /execution/{execution_id}/results
        raise NotImplementedError("Dune Drift integration not yet implemented")

    def fetch_mango_traders(self) -> list[dict]:
        if not self.is_configured():
            self._log.warning("DUNE_API_KEY not set — skipping Dune/Mango scan")
            return []
        raise NotImplementedError("Dune Mango integration not yet implemented")


class FlipsideScanner:
    """
    Queries Flipside Crypto for Solana DEX trade histories.
    Target: Drift Protocol.
    """

    FLIPSIDE_API_BASE = "https://api-v2.flipsidecrypto.xyz"

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._api_key = os.environ.get(config["stage3"]["flipside_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def fetch_trades_for_wallet(self, address: str) -> list[dict]:
        """
        Returns standardised trade list for a Solana wallet:
          {instrument, entry_price, exit_price, size, side,
           open_ts, close_ts, hold_time_seconds, pnl, is_win}
        """
        if not self.is_configured():
            self._log.warning("FLIPSIDE_API_KEY not set — skipping Flipside")
            return []
        raise NotImplementedError("Flipside integration not yet implemented")


class BirdeyeScanner:
    """
    Pulls Solana wallet trade histories via Birdeye API (Step 3.3).
    Used to cross-reference and fill gaps from Dune/Flipside.
    """

    BIRDEYE_API_BASE = "https://public-api.birdeye.so"

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._api_key = os.environ.get(config["stage3"]["birdeye_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def fetch_trades_for_wallet(self, address: str) -> list[dict]:
        if not self.is_configured():
            self._log.warning("BIRDEYE_API_KEY not set — skipping Birdeye")
            return []
        raise NotImplementedError("Birdeye integration not yet implemented")


class SolanaScanner:
    """
    Orchestrates all Solana sources for Stage 3.
    Merges Dune + Flipside + Birdeye into a deduplicated wallet list.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._dune = DuneScanner(config, logger)
        self._flipside = FlipsideScanner(config, logger)
        self._birdeye = BirdeyeScanner(config, logger)

    def scan(self) -> list[dict]:
        """
        Returns candidate wallets with fills ready for profiling.
        Returns empty list if no sources are configured.
        """
        configured = [
            s for s in [self._dune, self._flipside, self._birdeye]
            if s.is_configured()
        ]
        if not configured:
            self._log.warning(
                "No Solana API keys configured. "
                "Set DUNE_API_KEY, FLIPSIDE_API_KEY, and/or BIRDEYE_API_KEY to enable Stage 3."
            )
            return []

        self._log.info("Solana scanner not yet implemented — returning empty")
        return []
