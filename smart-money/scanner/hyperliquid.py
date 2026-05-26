"""
Stage 1, Steps 1.1–1.2: Hyperliquid API client and leaderboard scanner.

API notes (public, no key required):
  POST https://api.hyperliquid.xyz/info
  {"type": "leaderboard", "window": "allTime"}
  {"type": "userFills",   "user":   "0x..."}
  {"type": "clearinghouseState", "user": "0x..."}

Rate limiting: the public endpoint is tolerant but we enforce a configurable
delay between requests and exponential backoff on failures.
"""

from __future__ import annotations

import time
import json
import logging
from typing import Any

import requests

from run_logger import StageLogger, get_logger

_log = get_logger("hyperliquid.client")

INFO_URL = "https://api.hyperliquid.xyz/info"
LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class HyperliquidClient:
    def __init__(
        self,
        rate_limit_delay: float = 0.5,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        timeout: int = 30,
    ):
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._delay = rate_limit_delay
        self._max_retries = max_retries
        self._backoff = backoff_factor
        self._timeout = timeout
        self._last_call: float = 0.0

    def _get(self, url: str) -> Any:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        wait = self._delay
        for attempt in range(self._max_retries):
            try:
                resp = self._session.get(url, timeout=self._timeout)
                self._last_call = time.monotonic()
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 429:
                    _log.warning(f"Rate limited (attempt {attempt+1}). Sleeping {wait}s")
                    time.sleep(wait)
                    wait *= self._backoff
                elif status and 400 <= status < 500:
                    raise
                else:
                    _log.warning(f"HTTP {status} on attempt {attempt+1}. Retrying in {wait}s")
                    time.sleep(wait)
                    wait *= self._backoff
            except requests.RequestException as e:
                _log.warning(f"Request error on attempt {attempt+1}: {e}. Retrying in {wait}s")
                time.sleep(wait)
                wait *= self._backoff

        raise RuntimeError(f"All {self._max_retries} attempts failed for GET {url}")

    def _post(self, payload: dict) -> Any:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        wait = self._delay
        for attempt in range(self._max_retries):
            try:
                resp = self._session.post(
                    INFO_URL,
                    data=json.dumps(payload),
                    timeout=self._timeout,
                )
                self._last_call = time.monotonic()
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 429:
                    _log.warning(f"Rate limited (attempt {attempt+1}). Sleeping {wait}s")
                    time.sleep(wait)
                    wait *= self._backoff
                elif status and 400 <= status < 500:
                    raise  # non-retryable client errors
                else:
                    _log.warning(f"HTTP {status} on attempt {attempt+1}. Retrying in {wait}s")
                    time.sleep(wait)
                    wait *= self._backoff
            except requests.RequestException as e:
                _log.warning(f"Request error on attempt {attempt+1}: {e}. Retrying in {wait}s")
                time.sleep(wait)
                wait *= self._backoff

        raise RuntimeError(f"All {self._max_retries} attempts failed for payload type={payload.get('type')}")

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_leaderboard(self, window: str = "allTime") -> list[dict]:
        """
        Returns raw leaderboard entries from Hyperliquid.
        Each entry: ethAddress, accountValue, windowPerformances (list of [window, {pnl,roi,vlm}]).
        """
        data = self._get(LEADERBOARD_URL)
        if isinstance(data, dict) and "leaderboardRows" in data:
            return data["leaderboardRows"]
        _log.warning(f"Unexpected leaderboard response shape: {type(data)}")
        return []

    def get_user_fills(self, address: str) -> list[dict]:
        """
        Returns all fills for the given wallet address.
        Each fill: coin, px, sz, side, time (ms), closedPnl, dir, fee, oid, tid.
        """
        return self._post({"type": "userFills", "user": address})

    def get_user_state(self, address: str) -> dict:
        """
        Returns clearinghouse state: marginSummary (accountValue, totalPnl, etc.),
        assetPositions, crossMaintenanceMarginUsed, ...
        """
        return self._post({"type": "clearinghouseState", "user": address})

    def verify_endpoints(self) -> dict[str, bool]:
        """Smoke-tests all three endpoints and reports what's reachable."""
        results = {}
        dummy = "0x0000000000000000000000000000000000000000"
        try:
            lb = self.get_leaderboard()
            results["leaderboard"] = isinstance(lb, list) and len(lb) > 0
        except Exception as e:
            _log.error(f"Leaderboard endpoint failed: {e}")
            results["leaderboard"] = False

        try:
            fills = self.get_user_fills(dummy)
            results["user_fills"] = isinstance(fills, list)
        except Exception as e:
            _log.error(f"userFills endpoint failed: {e}")
            results["user_fills"] = False

        try:
            state = self.get_user_state(dummy)
            results["user_state"] = isinstance(state, dict)
        except Exception as e:
            _log.error(f"clearinghouseState endpoint failed: {e}")
            results["user_state"] = False

        return results


# ---------------------------------------------------------------------------
# Scanner (Steps 1.1–1.2)
# ---------------------------------------------------------------------------

class HyperliquidScanner:
    """
    Pulls the leaderboard, applies initial count + age filters, and
    returns the wallet list ready for deep profiling.
    """

    def __init__(self, client: HyperliquidClient, config: dict, logger: StageLogger):
        self._client = client
        self._cfg = config
        self._log = logger
        self._min_trades: int = config["qualification"]["min_trades"]
        self._min_age_days: int = config["qualification"]["min_wallet_age_days"]
        hl = config.get("hyperliquid", {})
        self._max_candidates: int = hl.get("max_leaderboard_candidates", 500)
        self._min_alltime_pnl: float = hl.get("min_alltime_pnl", 10000)
        self._min_account_value: float = hl.get("min_account_value", 1000)

    def _parse_leaderboard_entry(self, entry: dict) -> dict | None:
        """Normalises a raw leaderboard entry into a standard dict."""
        address = entry.get("ethAddress") or entry.get("address") or entry.get("user")
        if not address:
            return None

        # windowPerformances is a list of [window_name, {pnl, roi, vlm}] pairs
        all_time_pnl = None
        for item in entry.get("windowPerformances", []):
            if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] == "allTime":
                all_time_pnl = item[1].get("pnl")
                break

        return {
            "address": address,
            "all_time_pnl": float(all_time_pnl) if all_time_pnl is not None else None,
            "account_value": float(entry.get("accountValue", 0) or 0),
        }

    def _get_account_age_days(self, address: str, fills: list[dict]) -> int:
        """Derives wallet age in days from the oldest fill timestamp."""
        if not fills:
            return 0
        oldest_ts_ms = min(f["time"] for f in fills if "time" in f)
        age_seconds = time.time() - oldest_ts_ms / 1000.0
        return max(0, int(age_seconds / 86400))

    def fetch_leaderboard(self) -> list[dict]:
        """Step 1.2a: Pull raw leaderboard, pre-filter by PnL/value, cap to top N."""
        self._log.info("Fetching Hyperliquid leaderboard…")
        raw = self._client.get_leaderboard()
        self._log.info(f"Raw leaderboard entries: {len(raw)}")
        self._log.set("leaderboard_raw", len(raw))

        parsed = []
        for entry in raw:
            p = self._parse_leaderboard_entry(entry)
            if not p:
                continue
            pnl = p.get("all_time_pnl") or 0
            if pnl < self._min_alltime_pnl:
                continue
            if p["account_value"] < self._min_account_value:
                continue
            parsed.append(p)

        # Sort by all-time PnL descending; take top N before making API calls
        parsed.sort(key=lambda x: x.get("all_time_pnl") or 0, reverse=True)
        candidates = parsed[: self._max_candidates]

        self._log.info(
            f"Pre-filter: {len(parsed)} entries pass PnL/value thresholds → "
            f"top {len(candidates)} selected for API scan"
        )
        return candidates

    def apply_initial_filters(
        self, candidates: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """
        Step 1.2b: For each candidate, pull fills to check trade count and age.
        Returns (passed, disqualified_with_reasons).

        This is the expensive step — one fills API call per candidate.
        Candidates are disqualified immediately if they fail, so we log them.
        """
        passed: list[dict] = []
        failed: list[dict] = []

        total = len(candidates)
        for i, wallet in enumerate(candidates, 1):
            address = wallet["address"]
            if i % 10 == 0 or i == 1:
                self._log.info(f"Scanning wallet {i}/{total} ({i/total:.0%})…")
            try:
                fills = self._client.get_user_fills(address)
            except Exception as e:
                self._log.log_api_error(f"userFills/{address[:10]}", e)
                failed.append({**wallet, "reason": f"API error: {e}"})
                continue

            # count only closing fills (they have non-zero closedPnl)
            closing_fills = [
                f for f in fills
                if float(f.get("closedPnl", 0) or 0) != 0.0
            ]
            trade_count = len(closing_fills)
            age_days = self._get_account_age_days(address, fills)

            wallet["fills"] = fills
            wallet["trade_count"] = trade_count
            wallet["account_age_days"] = age_days
            wallet["first_seen_ts"] = (
                min(f["time"] for f in fills if "time" in f) if fills else None
            )

            if trade_count < self._min_trades:
                reason = f"Trade count {trade_count} < {self._min_trades}"
                self._log.log_disqualified(address, reason)
                failed.append({**wallet, "reason": reason})
                continue

            if age_days < self._min_age_days:
                reason = f"Account age {age_days} days < {self._min_age_days} days"
                self._log.log_disqualified(address, reason)
                failed.append({**wallet, "reason": reason})
                continue

            passed.append(wallet)
            self._log.increment("passed_initial_filter")

        self._log.set("total_scanned", len(candidates))
        self._log.info(
            f"Initial filter: {len(passed)} passed, {len(failed)} failed "
            f"(from {len(candidates)} candidates)"
        )
        return passed, failed

    def run(self) -> tuple[list[dict], list[dict]]:
        """
        Full Step 1.1–1.2 execution.
        Returns (passed_wallets, failed_wallets).
        Each passed wallet includes: address, fills, trade_count, account_age_days.
        """
        endpoints = self._client.verify_endpoints()
        for ep, ok in endpoints.items():
            status = "OK" if ok else "FAILED"
            self._log.info(f"Endpoint check [{ep}]: {status}")
        if not endpoints.get("leaderboard") or not endpoints.get("user_fills"):
            raise RuntimeError("Critical Hyperliquid endpoints unreachable. Check connectivity.")

        candidates = self.fetch_leaderboard()
        return self.apply_initial_filters(candidates)
