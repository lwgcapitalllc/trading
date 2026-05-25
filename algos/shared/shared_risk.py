"""
shared_risk.py — Dynamic risk / capacity engine (Phase 3).

Tracks portfolio-level risk across all open trades for one bot instance.
Replaces the static "X% per trade, Y% daily cap" with a continuously
recalculated available_risk budget.

Core formula:
    available_risk = daily_budget − used_risk − realized_daily_loss

used_risk = sum of current SL-to-price risk across all open trades.
  - A trade at breakeven (SL == entry) contributes ~0.
  - A trade with SL trailing in profit contributes a negative value
    (locked-in gain), which opens capacity above the baseline budget.

The daily hard cap still exists as a separate floor:
  when realized_daily_loss >= daily_budget, new entries are blocked
  regardless of used_risk.

Default daily_budget = each bot's existing daily loss cap, so day-one
behaviour is identical to the static cap.

Usage:
    engine = RiskEngine("BOT_SMC_TREND", daily_budget_pct=10.0, log=log)
    engine.reset_day(acct.balance)          # at startup + each midnight

    allowed, effective_risk = engine.evaluate(open_trades, balance, proposed_risk_pct)
    if not allowed:
        continue
    lots = lot_size(balance, sl_dist, ..., risk_pct=effective_risk)
"""

from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5


# ── Shared MT5 risk helper ────────────────────────────────────────────────────

def _calc_trade_live_risk_pct(trade: dict, balance: float) -> float:
    """
    Dollar risk if the current MT5 SL is hit, as % of balance.
    Returns negative when SL is in profit territory (locked-in gain).
    Returns 0.0 on any MT5 data error or missing trade fields.
    """
    ticket    = trade.get("ticket")
    symbol    = trade.get("symbol")
    direction = trade.get("dir")
    if not all([ticket, symbol, direction]) or balance <= 0:
        return 0.0

    positions = mt5.positions_get(ticket=int(ticket))
    if not positions:
        return 0.0
    pos = positions[0]

    si = mt5.symbol_info(symbol)
    if si is None or si.trade_tick_size <= 0:
        return 0.0

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return 0.0

    current_price = tick.bid if direction == "bullish" else tick.ask
    sl_dist  = (current_price - pos.sl) if direction == "bullish" else (pos.sl - current_price)
    ticks    = sl_dist / si.trade_tick_size
    risk_usd = ticks * si.trade_tick_value * pos.volume
    return (risk_usd / balance) * 100


class RiskEngine:
    """
    One instance per bot. open_trades is a list[dict] where each dict has
    at minimum: ticket, sl, dir, symbol (all set at order placement).
    """

    def __init__(self, bot_name: str, daily_budget_pct: float, log):
        self.bot_name         = bot_name
        self.daily_budget_pct = daily_budget_pct
        self.log              = log
        self._daily_start:    float = 0.0

    # ── Daily state ───────────────────────────────────────────────────────────

    def reset_day(self, balance: float) -> None:
        """Call once at bot startup and at each midnight rollover."""
        self._daily_start = balance
        self.log.info(
            f"RiskEngine ({self.bot_name}): day reset — "
            f"start_balance={balance:.2f} budget={self.daily_budget_pct:.1f}%"
        )

    # ── Per-trade live risk ───────────────────────────────────────────────────

    def _trade_live_risk_pct(self, trade: dict, balance: float) -> float:
        return _calc_trade_live_risk_pct(trade, balance)

    # ── Portfolio aggregates ──────────────────────────────────────────────────

    def _used_risk_pct(self, open_trades: list, balance: float) -> float:
        """Sum of live SL risk across all open trades as % of balance."""
        if not open_trades or balance <= 0:
            return 0.0
        return sum(self._trade_live_risk_pct(t, balance) for t in open_trades)

    def _realized_daily_loss_pct(self, balance: float) -> float:
        """Realized loss today as % of day-open balance. Floored at 0."""
        if self._daily_start <= 0:
            return 0.0
        return max(0.0, (self._daily_start - balance) / self._daily_start * 100)

    # ── Public interface ──────────────────────────────────────────────────────

    def evaluate(self, open_trades: list, balance: float,
                 proposed_risk_pct: float) -> tuple[bool, float]:
        """
        Single entry point for risk decisions. Computes the full risk state
        once and returns (allowed, effective_risk_pct).

        allowed          — False if daily cap is hit or budget is insufficient.
        effective_risk_pct — proposed_risk_pct capped at available budget.
                             Use this value directly in lot_size().

        Logs the full risk breakdown on every call for log-based verification.
        """
        realized = self._realized_daily_loss_pct(balance)
        used     = self._used_risk_pct(open_trades, balance)
        avail    = max(0.0, self.daily_budget_pct - used - realized)

        self.log.info(
            f"RiskEngine: budget={self.daily_budget_pct:.1f}% | "
            f"used={used:.2f}% ({len(open_trades)} trade(s)) | "
            f"realized_loss={realized:.2f}% | "
            f"available={avail:.2f}% | "
            f"proposed={proposed_risk_pct:.2f}%"
        )

        if realized >= self.daily_budget_pct:
            self.log.warning(
                f"RiskEngine: daily cap hit "
                f"({realized:.1f}% >= {self.daily_budget_pct:.1f}%) — "
                "blocking new entry."
            )
            return False, 0.0

        if avail < proposed_risk_pct:
            self.log.info(
                f"RiskEngine: insufficient capacity "
                f"({avail:.2f}% < {proposed_risk_pct:.2f}%) — skipping."
            )
            return False, 0.0

        return True, min(proposed_risk_pct, avail)

    # ── Monitoring helpers ────────────────────────────────────────────────────

    def available_risk_pct(self, open_trades: list, balance: float) -> float:
        """Read-only snapshot for status logging or monitor.py."""
        realized = self._realized_daily_loss_pct(balance)
        used     = self._used_risk_pct(open_trades, balance)
        return max(0.0, self.daily_budget_pct - used - realized)

    def daily_cap_hit(self, balance: float) -> bool:
        """True when realized losses alone exhaust the daily budget."""
        return self._realized_daily_loss_pct(balance) >= self.daily_budget_pct


# ── Correlation guard (Phase 4) ───────────────────────────────────────────────

class CorrelationGuard:
    """
    Pre-entry correlation filter. Prevents the scanner from opening multiple
    highly-correlated instruments simultaneously (which multiplies real exposure).

    correlation_map: list of {"symbols": [...], "tier": "high"|"medium"|"low"}
      All pairs within a group share the same tier.

    action: "block" or "shared_budget"
      "block"        — deny entry if any open position is high-correlation.
      "shared_budget" — allow entry but cap proposed_risk to the live risk of
                        the most-constraining correlated open trade. A trade at
                        breakeven contributes ~0, so the new entry is sized to
                        near-zero — the same net effect as a block, without a
                        hard rule.

    Only "high"-tier pairs trigger action. "medium" and "low" are informational.
    """

    def __init__(self, correlation_map: list, log):
        self._pairs: dict[frozenset, str] = {}
        self.log = log
        for entry in correlation_map:
            syms = entry.get("symbols", [])
            tier = entry.get("tier", "low")
            for i, s1 in enumerate(syms):
                for s2 in syms[i + 1:]:
                    self._pairs[frozenset({s1, s2})] = tier

    def tier(self, s1: str, s2: str) -> str:
        """Correlation tier between two symbols. 'low' if not in map."""
        return self._pairs.get(frozenset({s1, s2}), "low")

    def check(
        self,
        candidate_symbol: str,
        open_trades: list,
        proposed_risk_pct: float,
        action: str,
        balance: float,
    ) -> tuple[bool, float]:
        """
        Returns (allowed, effective_risk_pct).

        Iterates open trades; acts only on "high"-tier pairs.
        For "shared_budget", the cap is the minimum live risk across all
        high-correlated open trades — the most conservative bound.
        """
        min_live_risk: float | None = None

        for trade in open_trades:
            open_sym = trade.get("symbol", "")
            if not open_sym or open_sym == candidate_symbol:
                continue
            if self.tier(candidate_symbol, open_sym) != "high":
                continue

            if action == "block":
                self.log.warning(
                    f"CorrelationGuard: {candidate_symbol} BLOCKED — "
                    f"high correlation with open {open_sym}"
                )
                return False, 0.0

            # shared_budget: collect the most constraining live risk
            live = _calc_trade_live_risk_pct(trade, balance)
            if min_live_risk is None or live < min_live_risk:
                min_live_risk = live

        if min_live_risk is not None:
            capped = max(0.0, min(proposed_risk_pct, min_live_risk))
            self.log.info(
                f"CorrelationGuard: {candidate_symbol} — shared_budget: "
                f"proposed {proposed_risk_pct:.2f}% → capped {capped:.2f}% "
                f"(min correlated live_risk={min_live_risk:.2f}%)"
            )
            return True, capped

        return True, proposed_risk_pct
