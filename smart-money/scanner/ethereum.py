"""
Stage 3, Steps 3.1–3.4: Ethereum on-chain scanners.

Sources:
  - Dune Analytics  (Step 3.1) — public SQL queries for GMX, dYdX
  - Flipside Crypto  (Step 3.2) — historical trade data for GMX, dYdX
  - DeBank / Zerion  (Step 3.4) — wallet PnL snapshots and trade history

Prerequisites (set as environment variables):
  DUNE_API_KEY      — Dune Analytics API key
  FLIPSIDE_API_KEY  — Flipside API key
  DEBANK_API_KEY    — DeBank API key (or use Zerion)

Status: SCAFFOLD — API integration pending.
"""

from __future__ import annotations

import os

from run_logger import StageLogger


class GmxScanner:
    """
    GMX (Ethereum/Arbitrum) perpetuals trader scanner via Dune + Flipside.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._dune_key = os.environ.get(config["stage3"]["dune_api_key_env"])
        self._flipside_key = os.environ.get(config["stage3"]["flipside_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._dune_key or self._flipside_key)

    def fetch_top_traders(self) -> list[dict]:
        if not self.is_configured():
            self._log.warning("No Dune/Flipside keys — skipping GMX scan")
            return []
        raise NotImplementedError("GMX Dune/Flipside integration not yet implemented")


class DydxScanner:
    """
    dYdX (Ethereum/StarkEx) trader scanner via Dune + Flipside.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._dune_key = os.environ.get(config["stage3"]["dune_api_key_env"])
        self._flipside_key = os.environ.get(config["stage3"]["flipside_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._dune_key or self._flipside_key)

    def fetch_top_traders(self) -> list[dict]:
        if not self.is_configured():
            self._log.warning("No Dune/Flipside keys — skipping dYdX scan")
            return []
        raise NotImplementedError("dYdX integration not yet implemented")


class DeBankScanner:
    """
    DeBank API for Ethereum wallet PnL snapshots (Step 3.4).
    Cross-references wallets found via Dune/Flipside.
    """

    DEBANK_API_BASE = "https://pro-openapi.debank.com"

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._api_key = os.environ.get(config["stage3"]["debank_api_key_env"])

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def fetch_trades_for_wallet(self, address: str) -> list[dict]:
        if not self.is_configured():
            self._log.warning("DEBANK_API_KEY not set — skipping DeBank")
            return []
        raise NotImplementedError("DeBank integration not yet implemented")


class EthereumScanner:
    """
    Orchestrates GMX + dYdX + DeBank for Stage 3 Ethereum coverage.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._gmx = GmxScanner(config, logger)
        self._dydx = DydxScanner(config, logger)
        self._debank = DeBankScanner(config, logger)

    def scan(self) -> list[dict]:
        """
        Returns candidate wallets ready for profiling.
        Returns empty list if no sources are configured.
        """
        if not any(s.is_configured() for s in [self._gmx, self._dydx, self._debank]):
            self._log.warning(
                "No Ethereum API keys configured. "
                "Set DUNE_API_KEY, FLIPSIDE_API_KEY, and/or DEBANK_API_KEY to enable Stage 3."
            )
            return []

        self._log.info("Ethereum scanner not yet implemented — returning empty")
        return []
