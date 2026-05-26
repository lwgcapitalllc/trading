"""
Stage 4, Step 4.3: FX Blue account scanner.

FX Blue does not have a formal public REST API.
Data is accessed via:
  1. Web scraping of public statistics pages (Terms of Service permitting), or
  2. Direct session cookie from a logged-in browser session.

Prerequisites (set as environment variables):
  FX_BLUE_SESSION — session cookie value from authenticated browser session

Status: SCAFFOLD — web access integration pending.
  Review FX Blue's Terms of Service before implementing web scraping.
  If TOS prohibits automated access, this stage must be completed manually.

FX Blue base URL: https://www.fxblue.com
"""

from __future__ import annotations

import os
from run_logger import StageLogger


class FxBlueScanner:
    FX_BLUE_BASE = "https://www.fxblue.com"

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._session_token = os.environ.get(config["stage4"]["fx_blue_session_env"])

    def is_configured(self) -> bool:
        return bool(self._session_token)

    def fetch_public_accounts(self) -> list[dict]:
        """
        Step 4.3: Fetch list of verified public accounts from FX Blue.
        Returns list of account dicts with id, stats URL, and summary metrics.
        """
        if not self.is_configured():
            self._log.warning(
                "FX_BLUE_SESSION not set — skipping FX Blue scan. "
                "This stage requires manual account setup or session cookie."
            )
            return []
        raise NotImplementedError("FX Blue integration not yet implemented")

    def fetch_account_trades(self, account_id: str) -> list[dict]:
        """Step 4.3: Pull standardised trade list for an FX Blue account."""
        raise NotImplementedError("FX Blue fetch_account_trades not yet implemented")

    def scan(self) -> list[dict]:
        """Returns accounts ready for qualification. Empty list if not configured."""
        if not self.is_configured():
            return []
        self._log.info("FX Blue scanner not yet implemented — returning empty")
        return []
