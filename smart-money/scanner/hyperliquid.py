"""
Stage 1, Steps 1.1–1.2: Hyperliquid API client and leaderboard scanner.

API notes (public, no key required):
  POST https://api.hyperliquid.xyz/info
  {"type": "leaderboard", "window": "allTime"}
  {"type": "userFills",   "user":   "0x..."}
  {"type": "clearinghouseState", "user": "0x..."}

Rate limiting: Hyperliquid's public endpoint rate-limits by IP.  We use a
single shared token-bucket (_SharedRateLimiter) across all concurrent
scanner workers.  Per-worker delays don't work — N workers × 1/delay RPS
still fires N×(1/delay) total RPS at the same IP, instantly triggering 429s.
The shared limiter serialises token acquisition so combined throughput stays
at or below `requests_per_second` regardless of worker count.
"""

from __future__ import annotations

import time
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import requests

from run_logger import StageLogger, get_logger

_log = get_logger("hyperliquid.client")

INFO_URL = "https://api.hyperliquid.xyz/info"
LEADERBOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"


# ---------------------------------------------------------------------------
# Shared rate limiter (token bucket)
# ---------------------------------------------------------------------------

class _SharedRateLimiter:
    """
    Thread-safe token-bucket rate limiter for use across all scanner workers.

    All workers share one instance — the combined request throughput is
    bounded to `requests_per_second` regardless of how many concurrent
    workers are running.

    Usage: call acquire() before each outbound API request.  The call blocks
    until the inter-request interval has elapsed, then returns.  Holding the
    lock during the sleep is intentional — threads queue up and each one is
    released exactly `min_interval` seconds after the previous one fired.

    Example: 500 wallets at 3 req/s = ~167 s (~2.8 min).
    """

    def __init__(self, requests_per_second: float):
        self._min_interval = 1.0 / max(requests_per_second, 0.01)
        self._last: float = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


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
        # Per-client spacing — a safety valve for direct (non-scanner) calls.
        # Scanner workers set _delay=0 and use _SharedRateLimiter instead.
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)

        wait = max(self._delay, 0.2)  # minimum backoff seed
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
                    # 429 needs a proper cooldown — much longer than inter-request
                    # spacing.  Use 5s × (attempt+1) so successive 429s back off
                    # progressively (5s, 10s, 15s…).
                    rl_wait = 5.0 * (attempt + 1)
                    _log.warning(
                        f"Rate limited (attempt {attempt+1}/{self._max_retries}). "
                        f"Sleeping {rl_wait:.0f}s"
                    )
                    time.sleep(rl_wait)
                    wait *= self._backoff
                elif status and 400 <= status < 500:
                    raise  # non-retryable client errors
                else:
                    _log.warning(f"HTTP {status} on attempt {attempt+1}. Retrying in {wait:.1f}s")
                    time.sleep(wait)
                    wait *= self._backoff
            except requests.RequestException as e:
                _log.warning(f"Request error on attempt {attempt+1}: {e}. Retrying in {wait:.1f}s")
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
        self._max_candidates: int    = hl.get("max_leaderboard_candidates", 3000)
        self._min_alltime_pnl: float  = hl.get("min_alltime_pnl", 10_000)
        self._min_alltime_roi: float  = hl.get("min_alltime_roi", 0.5)    # 0.5 = 50%
        self._min_month_roi: float    = hl.get("min_month_roi", 0.0)      # 0.0 = disabled
        self._min_week_roi: float     = hl.get("min_week_roi", 0.0)       # 0.0 = disabled
        self._min_account_value: float = hl.get("min_account_value", 1_000)
        # Prescore weights: controls which time-window ROI dominates the pre-scan ranking.
        # Human profile: weight all-time heavily (0.50/0.30/0.20).
        # Bot profile: weight recent heavily (0.20/0.50/0.30) — is it growing right now?
        self._prescore_weights: dict  = hl.get("prescore_weights", {
            "alltime_roi": 0.50,
            "month_roi":   0.30,
            "week_roi":    0.20,
        })

    def _parse_leaderboard_entry(self, entry: dict) -> dict | None:
        """
        Normalises a raw leaderboard entry into a standard dict.

        windowPerformances is a list of [window_name, {pnl, roi, vlm}] pairs.
        Windows seen in the wild: "allTime", "month", "week", "day".
        We extract pnl AND roi for allTime, plus recent-window roi for recency scoring.
        """
        address = entry.get("ethAddress") or entry.get("address") or entry.get("user")
        if not address:
            return None

        perf: dict[str, dict] = {}
        for item in entry.get("windowPerformances", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                window_name, stats = item
                perf[window_name] = stats

        all_time = perf.get("allTime", {})
        month    = perf.get("month", {})
        week     = perf.get("week", {})

        def _f(d: dict, key: str) -> float | None:
            v = d.get(key)
            return float(v) if v is not None else None

        return {
            "address":       address,
            "account_value": float(entry.get("accountValue", 0) or 0),
            "all_time_pnl":  _f(all_time, "pnl"),
            "all_time_roi":  _f(all_time, "roi"),   # fractional, e.g. 3.9 = 390%
            "month_roi":     _f(month,    "roi"),
            "week_roi":      _f(week,     "roi"),
        }

    def _get_account_age_days(self, address: str, fills: list[dict]) -> int:
        """Derives wallet age in days from the oldest fill timestamp."""
        if not fills:
            return 0
        oldest_ts_ms = min(f["time"] for f in fills if "time" in f)
        age_seconds = time.time() - oldest_ts_ms / 1000.0
        return max(0, int(age_seconds / 86400))

    def _prescore(self, p: dict) -> float:
        """
        Composite pre-sort score using leaderboard-only data (no API calls needed).

        Weighted sum of time-window ROIs × log10(PnL scale factor).

        - Weights come from config `hyperliquid.prescore_weights`.
        - Human profile (default): weights all-time ROI heavily — rewards long track records.
        - Bot profile: weights month_roi and week_roi heavily — rewards what's growing *now*.
        - log10(pnl) keeps micro-accounts from dominating over traders managing real capital.

        Example bot formula: 0.20×alltime_roi + 0.50×month_roi + 0.30×week_roi × log10(pnl)
        A bot with 50%/month ranks far above one that peaked 2 years ago and is flat now.
        """
        import math
        w = self._prescore_weights
        pnl = p.get("all_time_pnl") or 0.0

        weighted_roi = (
            (p.get("all_time_roi") or 0.0) * w.get("alltime_roi", 0.50) +
            (p.get("month_roi")    or 0.0) * w.get("month_roi",   0.30) +
            (p.get("week_roi")     or 0.0) * w.get("week_roi",    0.20)
        )

        score = weighted_roi * math.log10(max(pnl, 1))
        # Small bonus for recent positive month performance (not in a long slump)
        if (p.get("month_roi") or 0.0) > 0:
            score *= 1.10
        return score

    def fetch_leaderboard(self) -> list[dict]:
        """
        Step 1.2a: Pull raw leaderboard, apply hard floors, rank by composite
        skill score (ROI × log PnL), and cap to top N for API scanning.
        """
        self._log.info("Fetching Hyperliquid leaderboard…")
        raw = self._client.get_leaderboard()
        self._log.info(f"Raw leaderboard entries: {len(raw)}")
        self._log.set("leaderboard_raw", len(raw))

        passed, dropped_pnl, dropped_roi, dropped_val, dropped_month, dropped_week = [], 0, 0, 0, 0, 0
        for entry in raw:
            p = self._parse_leaderboard_entry(entry)
            if not p:
                continue
            pnl = p.get("all_time_pnl") or 0.0
            roi = p.get("all_time_roi") or 0.0
            if pnl < self._min_alltime_pnl:
                dropped_pnl += 1
                continue
            if roi < self._min_alltime_roi:
                dropped_roi += 1
                continue
            if self._min_account_value > 0 and p["account_value"] < self._min_account_value:
                dropped_val += 1
                continue
            # Recent activity floors — key for finding currently active bots.
            # min_month_roi = 0.0 disables this check (default for human profile).
            if self._min_month_roi > 0:
                if (p.get("month_roi") or 0.0) < self._min_month_roi:
                    dropped_month += 1
                    continue
            if self._min_week_roi > 0:
                if (p.get("week_roi") or 0.0) < self._min_week_roi:
                    dropped_week += 1
                    continue
            passed.append(p)

        drop_parts = [
            f"{dropped_pnl} low-PnL",
            f"{dropped_roi} low-ROI",
        ]
        if self._min_account_value > 0:
            drop_parts.append(f"{dropped_val} low-balance")
        if self._min_month_roi > 0:
            drop_parts.append(f"{dropped_month} low-month-ROI (<{self._min_month_roi:.0%})")
        if self._min_week_roi > 0:
            drop_parts.append(f"{dropped_week} low-week-ROI (<{self._min_week_roi:.0%})")

        self._log.info(
            f"Hard floors: {len(raw)} raw → {len(passed)} pass "
            f"(dropped {', '.join(drop_parts)})"
        )

        # Sort by composite skill score: ROI × log(PnL) + recency bonus
        passed.sort(key=self._prescore, reverse=True)
        candidates = passed[: self._max_candidates]

        self._log.info(
            f"Pre-sort (ROI × log PnL): top {len(candidates)} of {len(passed)} selected for API scan"
        )
        if candidates:
            best = candidates[0]
            worst = candidates[-1]
            self._log.info(
                f"Score range: best={self._prescore(best):.1f} "
                f"(ROI={best.get('all_time_roi', 0):.1%}, PnL=${best.get('all_time_pnl', 0):,.0f}) "
                f"| cutoff={self._prescore(worst):.1f} "
                f"(ROI={worst.get('all_time_roi', 0):.1%}, PnL=${worst.get('all_time_pnl', 0):,.0f})"
            )
        return candidates

    def _scan_one_wallet(
        self,
        wallet: dict,
        client: "HyperliquidClient",
        rate_limiter: "_SharedRateLimiter",
        prefetched_fills: list | None = None,
    ) -> tuple[str, dict]:
        """
        Fetch fills for a single wallet and apply initial filters.
        Returns ("passed", wallet_dict) or ("failed", wallet_with_reason).
        Designed to run inside a thread pool — client is per-worker.

        prefetched_fills: pass cached fills here to skip the API call entirely.
        rate_limiter.acquire() is also skipped — thread only runs filter logic.

        rate_limiter is a shared token bucket — calling acquire() before the
        API request ensures total throughput across all workers stays bounded.
        """
        address = wallet["address"]

        if prefetched_fills is not None:
            fills = prefetched_fills
        else:
            rate_limiter.acquire()  # global rate gate — serialises across all workers
            try:
                fills = client.get_user_fills(address)
            except Exception as e:
                self._log.log_api_error(f"userFills/{address[:10]}", e)
                return "failed", {**wallet, "reason": f"API error: {e}"}

        # Count only closing fills (non-zero closedPnl)
        closing_fills = [
            f for f in fills
            if float(f.get("closedPnl", 0) or 0) != 0.0
        ]
        trade_count = len(closing_fills)
        age_days = self._get_account_age_days(address, fills)

        wallet = {
            **wallet,
            "fills": fills,
            "trade_count": trade_count,
            "account_age_days": age_days,
            "first_seen_ts": (
                min(f["time"] for f in fills if "time" in f) if fills else None
            ),
        }

        if trade_count < self._min_trades:
            reason = f"Trade count {trade_count} < {self._min_trades}"
            self._log.log_disqualified(address, reason)
            return "failed", {**wallet, "reason": reason}

        if age_days < self._min_age_days:
            reason = f"Account age {age_days} days < {self._min_age_days} days"
            self._log.log_disqualified(address, reason)
            return "failed", {**wallet, "reason": reason}

        return "passed", wallet

    def apply_initial_filters(
        self,
        candidates: list[dict],
        on_progress: Callable[[int, int, str, str], None] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        """
        Step 1.2b: For each candidate, fetch fills and apply trade-count + age filters.

        Cache path (default, TTL 24h via hyperliquid.fills_cache_hours):
            Fills already in the DB are loaded upfront — those wallets skip the
            API call entirely.  On re-runs within the TTL window all wallets are
            served from cache and the scan completes in ~30s.

        Direct path (cache miss or TTL expired):
            Workers run concurrently but share a single _SharedRateLimiter so
            combined throughput stays at or below `requests_per_second`.

        on_progress: optional callable(wallets_scanned, wallets_total, address, result)
            called (thread-safely) after each wallet completes.
            result is "passed" or "failed".
        """
        passed: list[dict] = []
        failed: list[dict] = []
        total = len(candidates)

        hl_cfg  = self._cfg.get("hyperliquid", {})
        workers = hl_cfg.get("concurrent_workers", 5)

        # ── Cache: load fills already fetched this session ───────────────────
        # TTL default 24h.  Set fills_cache_hours = 0 to disable.
        cache_hours   = hl_cfg.get("fills_cache_hours", 24)
        cache_max_age = int(cache_hours * 3600)
        use_cache     = cache_max_age > 0

        prefetched: dict[str, list] = {}  # address → cached fills

        if use_cache:
            import database as db
            cache_hits = 0
            for c in candidates:
                cached = db.get_cached_fills(c["address"], cache_max_age)
                if cached is not None:
                    prefetched[c["address"]] = cached
                    cache_hits += 1
            if cache_hits:
                self._log.info(
                    f"Fills cache: {cache_hits}/{len(candidates)} wallets loaded from DB "
                    f"(TTL {cache_hours:.0f}h) — skipping their API calls"
                )

        # ── Build shared rate limiter for uncached wallets ───────────────────
        rps = hl_cfg.get(
            "requests_per_second",
            1.0 / max(hl_cfg.get("rate_limit_delay_seconds", 0.3), 0.01),
        )
        shared_limiter = _SharedRateLimiter(rps)

        uncached = len(candidates) - len(prefetched)
        if uncached > 0:
            eta_s = int(uncached / rps)
            self._log.info(
                f"Scanning {uncached} uncached wallets — {workers} workers, "
                f"{rps:.1f} req/s (est. {eta_s // 60}m {eta_s % 60}s)…"
            )
        else:
            self._log.info(f"All {total} wallets served from cache — no API calls needed")

        # Each worker gets its own session/client for connection management.
        # rate_limit_delay=0 because timing is handled by the shared limiter.
        def _make_client() -> HyperliquidClient:
            return HyperliquidClient(
                rate_limit_delay=0,
                max_retries=hl_cfg.get("max_retries", 5),
                backoff_factor=hl_cfg.get("retry_backoff_factor", 2.0),
                timeout=hl_cfg.get("timeout_seconds", 30),
            )

        # Thread-safe progress counter
        lock = threading.Lock()
        completed = [0]

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_wallet = {
                executor.submit(
                    self._scan_one_wallet,
                    w,
                    _make_client(),
                    shared_limiter,
                    prefetched.get(w["address"]) if prefetched else None,
                ): w
                for w in candidates
            }
            for future in as_completed(future_to_wallet):
                result_type, wallet = future.result()
                with lock:
                    completed[0] += 1
                    i = completed[0]
                    if result_type == "passed":
                        passed.append(wallet)
                        self._log.increment("passed_initial_filter")
                    else:
                        failed.append(wallet)
                    if i % 10 == 0 or i == 1 or i == total:
                        self._log.info(f"Scanned {i}/{total} wallets ({i/total:.0%})…")
                    if on_progress:
                        on_progress(i, total, wallet.get("address", ""), result_type)

                    # Store freshly fetched fills in the cache so re-runs skip the API
                    if use_cache and wallet.get("address") not in prefetched:
                        fills = wallet.get("fills")
                        if fills is not None:
                            try:
                                import database as db
                                db.cache_fills(wallet["address"], fills)
                            except Exception:
                                pass  # cache write failure is non-fatal

        self._log.set("total_scanned", total)
        self._log.info(
            f"Initial filter: {len(passed)} passed, {len(failed)} failed "
            f"(from {total} candidates)"
        )
        return passed, failed

    def run(self, on_progress: Callable[[int, int, str, str], None] | None = None) -> tuple[list[dict], list[dict]]:
        """
        Full Step 1.1–1.2 execution.
        Returns (passed_wallets, failed_wallets).
        Each passed wallet includes: address, fills, trade_count, account_age_days.

        on_progress: optional callable(wallets_scanned, wallets_total, address, result)
            forwarded to apply_initial_filters for per-wallet progress reporting.
        """
        endpoints = self._client.verify_endpoints()
        for ep, ok in endpoints.items():
            status = "OK" if ok else "FAILED"
            self._log.info(f"Endpoint check [{ep}]: {status}")
        if not endpoints.get("leaderboard") or not endpoints.get("user_fills"):
            raise RuntimeError("Critical Hyperliquid endpoints unreachable. Check connectivity.")

        candidates = self.fetch_leaderboard()
        return self.apply_initial_filters(candidates, on_progress=on_progress)
