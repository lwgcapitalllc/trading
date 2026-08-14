"""
Stage 4, Steps 4.1–4.2: Myfxbook API client and account scanner.

Myfxbook requires authentication:
  POST https://www.myfxbook.com/api/login.json
    email=..., password=...
  Returns session token used for all subsequent calls.

Prerequisites (set as environment variables):
  MYFXBOOK_EMAIL    — registered Myfxbook account email
  MYFXBOOK_PASSWORD — account password

Status: SCAFFOLD — API integration pending.
  Create a free developer account at myfxbook.com,
  then implement _fetch_* methods below.

API reference: https://www.myfxbook.com/api
"""

from __future__ import annotations

import os

import requests
from run_logger import StageLogger

MYFXBOOK_BASE = "https://www.myfxbook.com/api"


class MyfxbookClient:
    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._email = os.environ.get(config["stage4"]["myfxbook_email_env"])
        self._password = os.environ.get(config["stage4"]["myfxbook_password_env"])
        self._session: str | None = None
        self._session_obj = requests.Session()

    def is_configured(self) -> bool:
        return bool(self._email and self._password)

    def login(self) -> bool:
        """Authenticates and stores session token. Returns True on success."""
        if not self.is_configured():
            self._log.warning("Myfxbook credentials not set in environment")
            return False
        try:
            resp = self._session_obj.get(
                f"{MYFXBOOK_BASE}/login.json",
                params={"email": self._email, "password": self._password},
                timeout=30,
            )
            data = resp.json()
            if not data.get("error", True):
                self._session = data.get("session")
                self._log.info("Myfxbook login successful")
                return True
            self._log.error(f"Myfxbook login failed: {data.get('message')}")
            return False
        except Exception as e:
            self._log.log_api_error("myfxbook/login", e)
            return False

    def get_public_accounts(self) -> list[dict]:
        """
        Step 4.1: Fetch list of public verified accounts.
        Returns list of account dicts with at minimum: id, name, gain, drawdown, trades.
        """
        if not self._session:
            raise RuntimeError("Not logged in — call login() first")
        raise NotImplementedError("Myfxbook get_public_accounts not yet implemented")

    def get_account_trades(self, account_id: int) -> list[dict]:
        """
        Step 4.2: Pull trade history for a specific account.
        Returns standardised trade list.
        """
        if not self._session:
            raise RuntimeError("Not logged in — call login() first")
        raise NotImplementedError("Myfxbook get_account_trades not yet implemented")

    def get_account_daily(self, account_id: int) -> list[dict]:
        """Daily PnL data for balance reconstruction."""
        raise NotImplementedError("Myfxbook get_account_daily not yet implemented")


class MyfxbookScanner:
    """
    Orchestrates Step 4.1–4.2: pulls public accounts, applies initial filters,
    returns wallets ready for qualification.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger
        self._client = MyfxbookClient(config, logger)
        self._min_trades = config["qualification"]["min_trades"]
        self._min_age_days = config["qualification"]["min_wallet_age_days"]

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def scan(self) -> list[dict]:
        """
        Returns list of account dicts with 'trades' key populated,
        ready for QualificationGate.
        """
        if not self.is_configured():
            self._log.warning(
                "Myfxbook not configured. "
                "Set MYFXBOOK_EMAIL and MYFXBOOK_PASSWORD to enable Stage 4 Myfxbook."
            )
            return []

        if not self._client.login():
            return []

        self._log.info("Myfxbook scanner not yet implemented — returning empty")
        return []
