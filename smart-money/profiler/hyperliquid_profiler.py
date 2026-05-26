"""
Stage 1, Step 1.3: Parse Hyperliquid fills into matched trades.

Hyperliquid fills are individual executions — not pre-matched open/close pairs.
We reconstruct matched trades using FIFO position tracking:
  - Opening fills (dir contains "Open") are pushed to a per-(coin,side) queue.
  - Closing fills (dir contains "Close") are popped from that queue.
  - Matched pairs yield: entry_price, exit_price, open_ts, close_ts, hold_time, pnl, is_win.

Partial closes are handled by splitting the open fill proportionally.
Fills with no matching open (queue empty) are treated as orphaned and skipped.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from run_logger import StageLogger


# ---------------------------------------------------------------------------
# Trade matcher
# ---------------------------------------------------------------------------

class _OpenPosition:
    """Represents one open fill or partial open fill awaiting a close."""

    def __init__(self, coin: str, side: str, px: float, sz: float, ts_ms: int):
        self.coin = coin
        self.side = side
        self.px = px
        self.sz = sz          # remaining unmatched size
        self.ts_ms = ts_ms


def _parse_side(fill: dict) -> str:
    """Returns 'long' or 'short' from fill direction field."""
    direction = (fill.get("dir") or "").lower()
    if "long" in direction:
        return "long"
    if "short" in direction:
        return "short"
    # fallback: B = buy = long open / short close; A = sell = short open / long close
    side_char = (fill.get("side") or "").upper()
    return "long" if side_char == "B" else "short"


def _is_opening(fill: dict) -> bool:
    direction = (fill.get("dir") or "").lower()
    return "open" in direction


def _is_closing(fill: dict) -> bool:
    direction = (fill.get("dir") or "").lower()
    closed_pnl = float(fill.get("closedPnl", 0) or 0)
    return "close" in direction or closed_pnl != 0.0


def match_fills_to_trades(fills: list[dict]) -> list[dict]:
    """
    Converts raw Hyperliquid fills into matched trade records.
    Returns a list of trade dicts compatible with database.insert_trades().
    """
    # Sort ascending so we process openings before their closings
    sorted_fills = sorted(fills, key=lambda f: f.get("time", 0))

    # queues[coin][side] = deque of _OpenPosition
    queues: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
    matched_trades: list[dict] = []

    for fill in sorted_fills:
        coin = fill.get("coin", "UNKNOWN")
        try:
            px = float(fill.get("px", 0))
            sz = float(fill.get("sz", 0))
            ts_ms = int(fill.get("time", 0))
            closed_pnl = float(fill.get("closedPnl", 0) or 0)
        except (TypeError, ValueError):
            continue

        if sz <= 0:
            continue

        side = _parse_side(fill)

        if _is_opening(fill):
            queues[coin][side].append(_OpenPosition(coin, side, px, sz, ts_ms))

        elif _is_closing(fill):
            # Determine the opposite queue we're closing from
            # (closing a long means we previously opened a long)
            queue = queues[coin][side]
            remaining_close_sz = sz
            accumulated_open_sz = 0.0
            weighted_entry_px = 0.0
            earliest_open_ts = ts_ms  # fallback if queue empty

            while remaining_close_sz > 0 and queue:
                open_pos = queue[0]
                match_sz = min(open_pos.sz, remaining_close_sz)

                weighted_entry_px += open_pos.px * match_sz
                accumulated_open_sz += match_sz
                earliest_open_ts = min(earliest_open_ts, open_pos.ts_ms)

                open_pos.sz -= match_sz
                remaining_close_sz -= match_sz

                if open_pos.sz <= 1e-9:
                    queue.popleft()

            if accumulated_open_sz <= 0:
                # Orphaned close — no matching open in our window, skip
                continue

            entry_price = weighted_entry_px / accumulated_open_sz
            hold_seconds = max(0, int((ts_ms - earliest_open_ts) / 1000))

            trade = {
                "instrument": coin,
                "entry_price": round(entry_price, 8),
                "exit_price": round(px, 8),
                "size": round(sz, 8),
                "side": side,
                "open_ts": earliest_open_ts,
                "close_ts": ts_ms,
                "hold_time_seconds": hold_seconds,
                "pnl": round(closed_pnl, 6),
                "is_win": 1 if closed_pnl > 0 else 0,
            }
            matched_trades.append(trade)

    return matched_trades


# ---------------------------------------------------------------------------
# Profiler
# ---------------------------------------------------------------------------

class HyperliquidProfiler:
    """
    Step 1.3: Converts scanner output (wallets with fills) into matched trade
    records stored in the database, plus balance reconstruction.
    """

    def __init__(self, config: dict, logger: StageLogger):
        self._cfg = config
        self._log = logger

    def profile_wallet(self, wallet: dict) -> list[dict]:
        """
        Parse fills into trades. Returns the list of matched trade dicts.
        wallet must contain a 'fills' key from the scanner step.
        """
        address = wallet["address"]
        fills = wallet.get("fills", [])

        if not fills:
            self._log.warning(f"No fills for {address[:10]}… — skipping")
            return []

        trades = match_fills_to_trades(fills)
        self._log.debug(
            f"{address[:10]}… — {len(fills)} fills → {len(trades)} matched trades"
        )
        return trades

    def reconstruct_balance_series(
        self, trades: list[dict], initial_balance: float = 10_000.0
    ) -> list[dict]:
        """
        Reconstructs cumulative balance at each trade close.
        Uses a synthetic starting balance since Hyperliquid doesn't expose
        historical balance snapshots via the public API.

        Returns a list of {ts_ms, balance, cum_pnl} dicts sorted by timestamp.
        """
        sorted_trades = sorted(trades, key=lambda t: t["close_ts"])
        balance = initial_balance
        series = []
        cum_pnl = 0.0

        for t in sorted_trades:
            cum_pnl += t["pnl"]
            balance = initial_balance + cum_pnl
            series.append({
                "ts_ms": t["close_ts"],
                "balance": round(balance, 4),
                "cum_pnl": round(cum_pnl, 4),
            })

        return series

    def compute_balance_stats(
        self, balance_series: list[dict]
    ) -> dict[str, float]:
        """
        From the balance series, compute:
          - starting_balance, ending_balance, net_growth_pct
          - peak_balance, lowest_balance
          - peak_drawdown (max peak-to-trough as % of peak)
        """
        if not balance_series:
            return {}

        balances = [s["balance"] for s in balance_series]
        peak = balances[0]
        max_drawdown = 0.0

        for b in balances:
            if b > peak:
                peak = b
            dd = (peak - b) / peak if peak > 0 else 0.0
            if dd > max_drawdown:
                max_drawdown = dd

        start_bal = balance_series[0]["balance"]
        end_bal = balance_series[-1]["balance"]
        net_growth = (end_bal - start_bal) / start_bal if start_bal > 0 else 0.0

        return {
            "starting_balance": round(start_bal, 2),
            "ending_balance": round(end_bal, 2),
            "net_growth_pct": round(net_growth * 100, 2),
            "peak_balance": round(max(balances), 2),
            "lowest_balance": round(min(balances), 2),
            "peak_drawdown_pct": round(max_drawdown * 100, 2),
        }
