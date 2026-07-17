"""
Dynamic sizing & risk engine (Phase 1).

The governing principle (docs/dynamic_sizing_engine.md, LWG_Strategy_Framework.md): NO
STRATEGY KNOWS HOW TO MANAGE RISK. A strategy proposes setups at unit size; layered gates
decide WHETHER a trade is allowed; this engine decides HOW BIG and walks the account
forward, reserving risk for open trades and detecting breaches. Written once, runner-agnostic.

This module is PURE: no DB, no network, no clock. It takes a raw trade stream plus a ruleset
view and returns sized trades + a day-by-day timeline + correct-size daily P&L (which feeds
the existing services.evaluator.evaluate_run unchanged) + a full decision log (one record per
signal, taken or not — see services.decision_log).

Sizing is goal-driven (the per-run bullet/consistent switch):
  - bullet     → take the most the rules allow (pass an eval fast), guarded so one stop-out
                 can never breach the floor.
  - consistent → risk a fixed fraction of the room left to the drawdown floor: room ÷ 7 per
                 trade, recomputed every trade (funded / live; survive to payout).

Order of operations per signal:
  1. Gates — daily halt, then open-trade room (a running trade reserves its risk; if nothing
     is left, the next signal is BLOCKED). Future gates (news, regime, session, score) slot
     in the same way.
  2. Sizing waterfall — base (by goal) → drawdown/open-risk ceiling → contract ladder →
     consistency throttle. Smallest wins, floored, ≥ 0. 0 ⇒ skipped.
  3. Walk — apply the trade at its real size when it closes, update balance / peak / floor,
     apply the daily-loss and profit-target halts, detect breaches.

Intraday-only (framework rule: flat by session end) ⇒ every trade exits the day it enters,
so days are self-contained; concurrency (and open-risk reservation) is within a day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from services.decision_log import TradeDecision, SizingDecision, classify_exit

# Per-trade risk when a ruleset carries no explicit risk % AND no drawdown floor at all
# (rare — some demos). Used only as the uncapped-account fallback for consistent mode.
_DEFAULT_RISK_PCT = 1.0

# Funded / live: risk the room to the floor ÷ this, per trade (locked 2026-06-21).
_CONSISTENT_DIVISOR = 7

MODE_BULLET = "bullet"
MODE_CONSISTENT = "consistent"
# Manual: YOU set the risk % per trade and it does not move — no room÷7, no goal-driven base.
# The account's HARD caps still clamp it (a stop can't punch through the drawdown floor, and the
# contract ladder is still a rule), so on a ruleset WITH limits manual is a request, not a
# guarantee. On a no-limits ruleset there are no clamps and X% means exactly X%.
MODE_MANUAL = "manual"

MODES = (MODE_BULLET, MODE_CONSISTENT, MODE_MANUAL)


# ── The runner→engine contract: one raw trade ─────────────────────────────────

@dataclass
class RawTrade:
    """One strategy-proposed trade at UNIT size, before the engine sizes it.

    This is the contract every runner must emit. The strategy is the only place that knows
    ``stop_distance`` at entry, so the strategy must record it — it is not recoverable from
    a standard NT8/MT5 trade export.
    """

    index: int
    entry_time: datetime
    exit_time: datetime
    direction: int                    # +1 long, -1 short
    entry_price: float
    exit_price: float
    stop_distance: float              # price points entry→stop (> 0); risk/contract = ×point_value
    point_value: float                # $ per 1.0 price point per contract
    commission_per_side: float = 0.0
    exit_reason: Optional[str] = None
    breakeven_time: Optional[datetime] = None   # when the stop reached BE (future; unused — see note)

    def gross_per_contract(self) -> float:
        return (self.exit_price - self.entry_price) * self.direction * self.point_value

    def net_per_contract(self) -> float:
        return self.gross_per_contract() - self.commission_per_side * 2.0

    def risk_per_contract(self) -> float:
        return max(0.0, self.stop_distance * self.point_value)

    def stop_price(self) -> float:
        return self.entry_price - self.direction * self.stop_distance

    @property
    def day(self) -> str:
        return self.entry_time.strftime("%Y-%m-%d")

    @classmethod
    def from_record(cls, rec: dict) -> "RawTrade":
        """Build from the enriched per-trade record the runners will emit. Times accept
        ISO strings or datetime; direction accepts +1/-1 or 'Long'/'Short'."""
        def _dt(v) -> datetime:
            return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

        d = rec["direction"]
        if isinstance(d, str):
            d = 1 if d.strip().lower().startswith("l") else -1

        be = rec.get("breakeven_time")
        return cls(
            index=int(rec["index"]),
            entry_time=_dt(rec["entry_time"]),
            exit_time=_dt(rec["exit_time"]),
            direction=int(d),
            entry_price=float(rec["entry_price"]),
            exit_price=float(rec["exit_price"]),
            stop_distance=float(rec["stop_distance"]),
            point_value=float(rec["point_value"]),
            commission_per_side=float(rec.get("commission_per_side", 0.0) or 0.0),
            exit_reason=rec.get("exit_reason"),
            breakeven_time=(_dt(be) if be else None),
        )


# ── The contract ladder (eval fixed cap; funded scaling) ──────────────────────

class ContractLadder:
    """Resolves the max contracts allowed at a given simulated profit, for the instrument's
    contract class (micro vs mini). eval rows carry a fixed cap; funded rows carry a
    ``scaling`` block (bidirectional_band or cumulative_ratchet). null ⇒ uncapped."""

    def __init__(self, max_contracts: Optional[dict], is_micro: bool):
        self._mc = max_contracts or {}
        self._is_micro = is_micro
        self._key = "micro" if is_micro else "mini"
        self._max_key = "micro_max" if is_micro else "mini_max"

    @property
    def active(self) -> bool:
        return bool(self._mc)

    def cap_at(self, simulated_profit: float) -> Optional[float]:
        if not self._mc:
            return None
        scaling = self._mc.get("scaling")
        if not scaling:
            cap = self._mc.get(self._max_key)
            return float(cap) if cap is not None else None
        return self._scaling_cap(scaling, simulated_profit)

    def _scaling_cap(self, scaling: dict, profit: float) -> Optional[float]:
        mode = scaling.get("mode")
        if mode == "bidirectional_band":
            for band in scaling.get("bands", []):
                lo = band.get("profit_min", 0) or 0
                hi = band.get("profit_max")
                if profit >= lo and (hi is None or profit <= hi):
                    return float(band[self._key])
            ceil = scaling.get("ceiling")
            return float(ceil[self._key]) if ceil else None
        if mode == "cumulative_ratchet":
            start = scaling.get("start", {})
            cap = float(start.get(self._key)) if start.get(self._key) is not None else None
            for tier in scaling.get("tiers", []):
                if profit >= tier.get("profit_trigger", math.inf):
                    cap = float(tier[self._key])
            ceil = scaling.get("ceiling")
            if ceil and ceil.get(self._key) is not None:
                cap = min(cap, float(ceil[self._key])) if cap is not None else float(ceil[self._key])
            return cap
        flat = self._mc.get(self._max_key)
        return float(flat) if flat is not None else None


# ── The ruleset view the engine needs ─────────────────────────────────────────

@dataclass
class EngineRuleset:
    """The slice of a ruleset the engine reads. Built via from_ruleset()."""

    ruleset_type: str
    account_size: float
    profit_target: float
    trailing_mll_amount: Optional[float]      # max_loss_eod; None/0 = no trailing rule
    mll_lock_balance: Optional[float]
    consistency_pct: Optional[float]
    daily_loss_limit: Optional[float]         # daily_loss_cap; drives the daily-loss halt
    risk_per_trade_pct: Optional[float]
    daily_halt_fraction: Optional[float]
    daily_profit_target: Optional[float]
    max_dd_from_peak_pct: Optional[float]     # personal/demo drawdown-from-peak floor
    ladder: ContractLadder

    @property
    def has_trailing_floor(self) -> bool:
        return bool(self.trailing_mll_amount) and self.ruleset_type not in ("personal", "demo")

    @property
    def has_peak_floor(self) -> bool:
        return bool(self.max_dd_from_peak_pct) and not self.has_trailing_floor

    def risk_pct(self) -> float:
        return float(self.risk_per_trade_pct or _DEFAULT_RISK_PCT)

    @classmethod
    def from_ruleset(cls, r: dict, is_micro: bool) -> "EngineRuleset":
        return cls(
            ruleset_type=r.get("ruleset_type", "prop_eval"),
            account_size=float(r.get("account_size") or 0.0),
            profit_target=float(r.get("profit_target") or 0.0),
            trailing_mll_amount=(float(r["max_loss_eod"]) if r.get("max_loss_eod") else None),
            mll_lock_balance=(float(r["mll_lock_balance"]) if r.get("mll_lock_balance") is not None else None),
            consistency_pct=(float(r["consistency_pct"]) if r.get("consistency_pct") is not None else None),
            daily_loss_limit=(float(r["daily_loss_cap"]) if r.get("daily_loss_cap") else None),
            risk_per_trade_pct=(float(r["risk_per_trade_pct"]) if r.get("risk_per_trade_pct") else None),
            daily_halt_fraction=(float(r["daily_halt_fraction"]) if r.get("daily_halt_fraction") else None),
            daily_profit_target=(float(r["daily_profit_target"]) if r.get("daily_profit_target") else None),
            max_dd_from_peak_pct=(float(r["max_drawdown_from_peak_pct"]) if r.get("max_drawdown_from_peak_pct") else None),
            ladder=ContractLadder(r.get("max_contracts"), is_micro),
        )


# ── Result shapes ─────────────────────────────────────────────────────────────

@dataclass
class SizedTrade:
    index: int
    day: str
    direction: int
    contracts: int
    net_pnl: float
    bound_by: str
    risk_per_contract: float
    skipped: bool = False
    blocked: bool = False


@dataclass
class DayTimeline:
    date: str
    trades_taken: int
    contracts_total: int
    day_pnl: float
    eod_balance: float
    risk_floor: Optional[float]
    floor_distance: Optional[float]
    consistency_share_pct: Optional[float]
    halt_reason: Optional[str] = None


@dataclass
class EngineResult:
    ruleset_id: Optional[str]
    mode: str = MODE_CONSISTENT
    sized_trades: list[SizedTrade] = field(default_factory=list)
    timeline: list[DayTimeline] = field(default_factory=list)
    daily_pnl: list[dict] = field(default_factory=list)     # [{date, pnl}] — feeds evaluator
    decisions: list[dict] = field(default_factory=list)     # one per signal — the audit log
    final_balance: float = 0.0
    net_pnl: float = 0.0
    skipped_trades: int = 0
    blocked_trades: int = 0
    breach_day: Optional[str] = None
    breach_reason: Optional[str] = None
    risk_budget_note: str = ""


# ── The sizing waterfall (each step can only shrink) ──────────────────────────

def _base_contracts(mode: str, trade: RawTrade, rs: EngineRuleset,
                    balance: float, available_room: Optional[float],
                    manual_risk_pct: Optional[float] = None) -> tuple[float, str]:
    """Step 1 — the base size, set by the account's GOAL.

    bullet     → ∞ here; the ladder / drawdown / open-risk clamps cap it to the max legal size.
    consistent → risk a fixed fraction of the room left: room ÷ 7, recomputed every trade.
                 With no drawdown limit at all, fall back to a small % of balance.
    manual     → risk exactly `manual_risk_pct` of the CURRENT balance, every trade. Compounds
                 with the balance (that is what "5% per trade" means); ignores the room entirely
                 here — the hard clamps below still apply.
    """
    rpc = trade.risk_per_contract()
    if rpc <= 0:
        return 0.0, "no_stop"
    if mode == MODE_MANUAL:
        pct = manual_risk_pct if manual_risk_pct is not None else rs.risk_pct()
        return (balance * (pct / 100.0)) / rpc, "manual_pct"
    if mode == MODE_BULLET:
        return math.inf, "bullet_max"
    if available_room is None:
        budget = balance * (rs.risk_pct() / 100.0)
    else:
        if available_room <= 0:
            return 0.0, "no_room"
        budget = available_room / _CONSISTENT_DIVISOR
    return budget / rpc, "room_div7"


def size_trade(mode: str, trade: RawTrade, rs: EngineRuleset, balance: float,
               available_room: Optional[float], simulated_profit: float,
               day_profit: float, manual_risk_pct: Optional[float] = None) -> tuple[int, str]:
    """Run the full waterfall for one trade. Returns (contracts, bound_by)."""
    rpc = trade.risk_per_contract()
    base, base_label = _base_contracts(mode, trade, rs, balance, available_room, manual_risk_pct)
    clamps: dict[str, float] = {base_label: base}

    # Drawdown / open-risk ceiling — one stop can't punch through the room left.
    if available_room is not None and rpc > 0:
        clamps["drawdown_clamp"] = max(0.0, available_room) / rpc

    # Contract ladder.
    cap = rs.ladder.cap_at(simulated_profit)
    if cap is not None:
        clamps["contract_ladder"] = cap

    # Consistency throttle (winning trades only).
    if rs.consistency_pct and rs.profit_target > 0:
        per = trade.net_per_contract()
        if per > 0:
            allowed = (rs.consistency_pct / 100.0) * rs.profit_target
            clamps["consistency_throttle"] = max(0.0, allowed - day_profit) / per

    bound, val = min(clamps.items(), key=lambda kv: kv[1])
    if val == math.inf:
        # bullet with no finite cap at all (misconfigured uncapped account) — refuse rather
        # than size infinitely.
        return 0, "unbounded_config"

    contracts = max(0, int(math.floor(val)))
    if contracts == 0 and val > 0:
        # The ideal size rounded down below the smallest tradeable unit (1 contract/micro).
        # Round UP to 1 ONLY if the minimum breaks no HARD cap — the room (one loss can't
        # breach) and the firm's contract ladder. If a SOFT target (room÷7 budget or the
        # consistency throttle) is what shrank it below 1, the minimum is allowed; if a hard
        # cap did, the trade genuinely can't be taken and is skipped.
        hard_room_ok = available_room is None or (rpc > 0 and rpc <= available_room)
        hard_ladder_ok = cap is None or cap >= 1
        if hard_room_ok and hard_ladder_ok:
            return 1, "min_size"
    return contracts, bound


# ── The equity walk ───────────────────────────────────────────────────────────

def _iso(t: datetime) -> str:
    return t.isoformat()


def run_engine(trades: list[RawTrade], ruleset: dict, *, is_micro: bool,
               mode: str = MODE_CONSISTENT, ruleset_id: Optional[str] = None,
               instrument: str = "", account_id: str = "", strategy: str = "",
               manual_risk_pct: Optional[float] = None) -> EngineResult:
    """Size every trade and walk the account forward, reserving risk for open trades and
    detecting breaches. Returns an EngineResult whose ``daily_pnl`` feeds
    services.evaluator.evaluate_run and whose ``decisions`` are the audit log."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if mode == MODE_MANUAL and (manual_risk_pct is None or manual_risk_pct <= 0):
        raise ValueError("manual mode needs a positive manual_risk_pct")

    rs = EngineRuleset.from_ruleset(ruleset, is_micro)
    result = EngineResult(ruleset_id=ruleset_id, mode=mode)
    result.risk_budget_note = (
        f"mode={mode}; "
        + (f"manual = {manual_risk_pct}% of balance per trade" if mode == MODE_MANUAL
           else "bullet = max size the rules allow" if mode == MODE_BULLET
           else f"consistent = room ÷ {_CONSISTENT_DIVISOR} per trade")
    )

    by_day: dict[str, list[RawTrade]] = {}
    for t in trades:
        by_day.setdefault(t.day, []).append(t)
    days = sorted(by_day.keys())

    balance = rs.account_size
    peak = balance
    highest_eod = balance
    trailing_floor: Optional[float] = (
        rs.account_size - rs.trailing_mll_amount if rs.has_trailing_floor else None)
    cumulative_pnl = 0.0
    cumulative_profit = 0.0
    breached = False

    def current_floor() -> Optional[float]:
        if rs.has_trailing_floor:
            return trailing_floor
        if rs.has_peak_floor:
            return peak * (1.0 - rs.max_dd_from_peak_pct / 100.0)
        return None

    for day in days:
        sim_profit_into_day = cumulative_pnl
        day_trades = sorted(by_day[day], key=lambda x: (x.entry_time, x.index))
        # Interleave entry/exit events so concurrency (and open-risk) is handled within the day.
        events = []
        for t in day_trades:
            events.append((t.entry_time, 0, t))   # 0 = entry sorts before 1 = exit at same ts
            events.append((t.exit_time, 1, t))
        events.sort(key=lambda e: (e[0], e[1], e[2].index))

        day_pnl = 0.0
        day_contracts = 0
        day_taken = 0
        halt_reason: Optional[str] = None
        open_trades: dict[int, dict] = {}          # index -> {contracts, reserved, decision}
        day_decisions: dict[int, TradeDecision] = {}

        for _ts, kind, t in events:
            if kind == 0:  # ── ENTRY ──
                dec = TradeDecision(
                    timestamp=_iso(t.entry_time), instrument=instrument, direction=t.direction,
                    strategy=strategy, account_id=account_id, signal_id=str(t.index),
                    stop_distance=t.stop_distance, proposed_stop=t.stop_price(),
                )
                day_decisions[t.index] = dec

                floor_now = current_floor()
                room = (balance - floor_now) if floor_now is not None else None
                reserved = sum(o["reserved"] for o in open_trades.values())
                available = (room - reserved) if room is not None else None
                dec.snapshot(
                    balance=round(balance, 2), day_pnl=round(day_pnl, 2),
                    risk_floor=(round(floor_now, 2) if floor_now is not None else None),
                    room=(round(room, 2) if room is not None else None),
                    reserved_open_risk=round(reserved, 2),
                    available_room=(round(available, 2) if available is not None else None),
                )

                # Gate: account already dead (a prior day breached).
                if breached:
                    dec.gate("account_breached", False, "account already failed its drawdown rule")
                    result.blocked_trades += 1
                    continue
                # Gate: the day is halted.
                if halt_reason is not None:
                    dec.gate("daily_halt", False, f"day halted: {halt_reason}")
                    result.blocked_trades += 1
                    continue
                dec.gate("daily_halt", True, "trading open for the day")

                # Gate: open trades reserve the room.
                if available is not None and available <= 0:
                    dec.gate("insufficient_room", False,
                             "open trade(s) reserve all remaining room",
                             room=room, reserved=reserved)
                    dec.set_sizing(SizingDecision(
                        contracts=0, bound_by="insufficient_room", room_to_floor=room,
                        skipped=True, note="no room left after open-trade reservation"))
                    result.blocked_trades += 1
                    continue
                if available is not None:
                    dec.gate("insufficient_room", True, "room available after open reservations")

                contracts, bound = size_trade(
                    mode, t, rs, balance, available, sim_profit_into_day, day_pnl,
                    manual_risk_pct=manual_risk_pct)

                consistency_room = None
                if rs.consistency_pct and rs.profit_target > 0:
                    consistency_room = round(
                        (rs.consistency_pct / 100.0) * rs.profit_target - day_pnl, 2)
                dec.set_sizing(SizingDecision(
                    contracts=contracts, bound_by=bound,
                    room_to_floor=(round(room, 2) if room is not None else None),
                    ladder_cap=rs.ladder.cap_at(sim_profit_into_day),
                    consistency_room=consistency_room,
                    skipped=(contracts <= 0)))

                if contracts <= 0:
                    result.skipped_trades += 1
                    result.sized_trades.append(SizedTrade(
                        index=t.index, day=day, direction=t.direction, contracts=0,
                        net_pnl=0.0, bound_by=bound, risk_per_contract=t.risk_per_contract(),
                        skipped=True))
                    continue

                # Take it: reserve its full risk until it closes (conservative — until a
                # breakeven-move event exists, an open trade always reserves full risk).
                reserved_risk = contracts * t.risk_per_contract()
                dec.set_entry(time=_iso(t.entry_time), price=t.entry_price, stop=t.stop_price())
                open_trades[t.index] = {"contracts": contracts, "reserved": reserved_risk,
                                        "decision": dec}
                day_contracts += contracts
                day_taken += 1

            else:  # ── EXIT ──
                o = open_trades.pop(t.index, None)
                if o is None:
                    continue  # trade was blocked/skipped — no position to close
                contracts = o["contracts"]
                dec = o["decision"]
                net = t.net_per_contract() * contracts
                balance += net
                day_pnl += net
                cumulative_pnl += net
                if balance > peak:
                    peak = balance
                rpc = t.risk_per_contract()
                dec.set_exit(
                    time=_iso(t.exit_time), price=t.exit_price, reason=classify_exit(t.exit_reason),
                    gross=round(t.gross_per_contract() * contracts, 2), net=round(net, 2),
                    r_multiple=(round(t.net_per_contract() / rpc, 2) if rpc > 0 else None))
                result.sized_trades.append(SizedTrade(
                    index=t.index, day=day, direction=t.direction, contracts=contracts,
                    net_pnl=round(net, 2), bound_by=dec.sizing.bound_by,
                    risk_per_contract=rpc))

                # Intraday halts — checked after the trade closes.
                if rs.daily_loss_limit and rs.daily_halt_fraction:
                    if -day_pnl >= rs.daily_loss_limit * rs.daily_halt_fraction:
                        halt_reason = "daily_loss"
                if halt_reason is None and rs.daily_profit_target:
                    if day_pnl >= rs.daily_profit_target:
                        halt_reason = "profit_target"

        # ── EOD bookkeeping ──
        if day_pnl > 0:
            cumulative_profit += day_pnl
        eod_balance = balance

        floor_eod = current_floor()
        if floor_eod is not None and not breached and eod_balance <= floor_eod:
            breached = True
            result.breach_day = day
            result.breach_reason = "trailing_max_loss" if rs.has_trailing_floor else "drawdown_from_peak"

        share = (day_pnl / cumulative_profit * 100.0) if (day_pnl > 0 and cumulative_profit > 0) else None

        # Trail the prop floor for the next day.
        if rs.has_trailing_floor:
            highest_eod = max(highest_eod, eod_balance)
            candidate = highest_eod - rs.trailing_mll_amount
            if rs.mll_lock_balance is not None:
                candidate = min(candidate, rs.mll_lock_balance)
            trailing_floor = max(trailing_floor, candidate) if trailing_floor is not None else candidate

        result.timeline.append(DayTimeline(
            date=day, trades_taken=day_taken, contracts_total=day_contracts,
            day_pnl=round(day_pnl, 2), eod_balance=round(eod_balance, 2),
            risk_floor=(round(floor_eod, 2) if floor_eod is not None else None),
            floor_distance=(round(eod_balance - floor_eod, 2) if floor_eod is not None else None),
            consistency_share_pct=(round(share, 1) if share is not None else None),
            halt_reason=halt_reason))
        result.daily_pnl.append({"date": day, "pnl": round(day_pnl, 2)})

        # Emit the day's decisions in entry order (taken ones now carry their exit).
        for t in day_trades:
            dec = day_decisions.get(t.index)
            if dec is not None:
                result.decisions.append(dec.finalize().to_dict())

    result.final_balance = round(balance, 2)
    result.net_pnl = round(cumulative_pnl, 2)
    return result
