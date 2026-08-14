"""
Trade decision log — the single, end-to-end audit record for one signal.

One record per signal the strategy raises, taken or not. It captures the whole story:
the idea (direction + setup score + why), every gate's verdict in order (which one shut
it down — and vice versa, that all passed), the sizing decision (how big and what limited
it, or why it was skipped), and, if taken, the full life of the trade (entry, exit, exit
reason, P&L). Written the SAME way in a backtest and live, so any trade can be investigated
from one file — "why did we lose this / why didn't it trade for three days" reads off one
line.

Extensible by design — the whole point. A new gate just calls `decision.gate(name, passed,
reason)`. The log never has to know the gate exists; gates are an ordered list, not a fixed
schema. Add a news gate, a spread gate, a score gate later — no change here.

Pure stdlib: no DB, no framework, no clock. Every part of the system (the sizing engine,
a live bot) can write the same format. Append-only JSONL — one JSON object per line,
human-readable and queryable in bulk.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# ── Outcomes (how a signal resolved) ──────────────────────────────────────────

OUTCOME_TAKEN = "taken"  # a gate let it through and it was sized > 0
OUTCOME_BLOCKED = "blocked"  # a gate vetoed it (see blocked_by)
OUTCOME_SKIPPED = "skipped"  # allowed, but sized to 0 (no legal size)
OUTCOME_OPEN = "open"  # built, not yet resolved (shouldn't persist)


# ── Exit reasons (the life-end of a taken trade) ──────────────────────────────

EXIT_TARGET = "target"
EXIT_STOP = "stop"
EXIT_BREAKEVEN = "breakeven"
EXIT_TIME_FLAT = "time_flat"  # closed by the force-flat / time-of-day rule
EXIT_MANUAL = "manual"
EXIT_OTHER = "other"


def classify_exit(label: Optional[str]) -> str:
    """Map a runner's raw exit-name (NT8 'Exit name', etc.) to a canonical reason.

    Heuristic and tolerant — unknown labels fall to EXIT_OTHER. Centralised here so
    backtest and live classify exits identically.
    """
    s = (label or "").strip().lower()
    if not s:
        return EXIT_OTHER
    if "forceflat" in s or "flat" in s or "time" in s or "session" in s:
        return EXIT_TIME_FLAT
    if "breakeven" in s or s in ("be", "b/e"):
        return EXIT_BREAKEVEN
    if "profit" in s or "target" in s or "tp" in s:
        return EXIT_TARGET
    if "stop" in s or "sl" in s or "loss" in s:
        return EXIT_STOP
    return EXIT_OTHER


# ── Pieces of a record ────────────────────────────────────────────────────────


@dataclass
class GateVerdict:
    """One gate's ruling on a signal. `passed=False` means this gate vetoed the trade."""

    gate: str
    passed: bool
    reason: str
    detail: dict = field(default_factory=dict)


@dataclass
class SizingDecision:
    """What the sizing engine decided and what bound it."""

    contracts: int
    bound_by: str  # which limit set the size
    room_to_floor: Optional[float] = None  # $ distance to the drawdown floor at decision
    ladder_cap: Optional[float] = None  # firm contract cap in force
    consistency_room: Optional[float] = None  # $ left under today's consistency share
    skipped: bool = False
    note: str = ""


# ── The record ────────────────────────────────────────────────────────────────


@dataclass
class TradeDecision:
    """The full end-to-end story of one signal. Build it as the decision unfolds, then
    `finalize()` and hand it to a DecisionLog.

    Identity is set at construction; everything else is filled in by the gates, the
    sizing engine, and (if taken) the entry/exit as they happen.
    """

    timestamp: str  # ISO — when the signal was raised
    instrument: str
    direction: int  # +1 long, -1 short
    strategy: str = ""
    account_id: str = ""  # run_id (backtest) or live account id
    signal_id: str = ""

    # The idea — why this is a signal at all.
    setup_score: Optional[str] = None  # 'A+' | 'A' | … (the confluence grade; future)
    setup_reason: Optional[str] = None  # human note: "range break + 1 confirm"
    stop_distance: Optional[float] = None  # risk per contract, price points
    proposed_stop: Optional[float] = None
    proposed_target: Optional[float] = None

    # The story.
    gates: list[GateVerdict] = field(default_factory=list)
    sizing: Optional[SizingDecision] = None
    account_snapshot: dict = field(default_factory=dict)  # balance, day_pnl, floor_distance…
    entry: Optional[dict] = None  # {time, price, stop, target}
    exit: Optional[dict] = None  # {time, price, reason, gross, net, r_multiple}
    outcome: str = OUTCOME_OPEN

    # ── Builders (chainable) ──
    def gate(self, name: str, passed: bool, reason: str, **detail: Any) -> "TradeDecision":
        """Record a gate's verdict. The first failing gate is what blocked the trade."""
        self.gates.append(GateVerdict(gate=name, passed=passed, reason=reason, detail=detail))
        return self

    def set_sizing(self, sizing: SizingDecision) -> "TradeDecision":
        self.sizing = sizing
        return self

    def snapshot(self, **fields: Any) -> "TradeDecision":
        self.account_snapshot.update(fields)
        return self

    def set_entry(
        self, time: str, price: float, stop: Optional[float] = None, target: Optional[float] = None
    ) -> "TradeDecision":
        self.entry = {"time": time, "price": price, "stop": stop, "target": target}
        return self

    def set_exit(
        self,
        time: str,
        price: float,
        reason: str,
        gross: Optional[float] = None,
        net: Optional[float] = None,
        r_multiple: Optional[float] = None,
    ) -> "TradeDecision":
        self.exit = {
            "time": time,
            "price": price,
            "reason": reason,
            "gross": gross,
            "net": net,
            "r_multiple": r_multiple,
        }
        return self

    # ── Resolution ──
    @property
    def blocked_by(self) -> Optional[str]:
        for g in self.gates:
            if not g.passed:
                return g.gate
        return None

    def finalize(self) -> "TradeDecision":
        """Set the outcome from what was recorded. Idempotent."""
        if self.blocked_by is not None:
            self.outcome = OUTCOME_BLOCKED
        elif self.sizing is not None and self.sizing.contracts <= 0:
            self.outcome = OUTCOME_SKIPPED
        elif self.entry is not None or (self.sizing and self.sizing.contracts > 0):
            self.outcome = OUTCOME_TAKEN
        else:
            self.outcome = OUTCOME_OPEN
        return self

    def to_dict(self) -> dict:
        return asdict(self)


# ── The log file (append-only JSONL) ──────────────────────────────────────────


class DecisionLog:
    """Append-only writer/reader for a `.jsonl` decision log. One line per signal.

    Used identically by the backtest engine (one file per run) and live bots (one file
    per account), so investigation reads one format everywhere.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, decision: TradeDecision) -> None:
        decision.finalize()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(decision.to_dict(), default=str) + "\n")

    def write_many(self, decisions: list[TradeDecision]) -> None:
        for d in decisions:
            self.write(d)

    @staticmethod
    def read(path: str | Path) -> list[dict]:
        p = Path(path)
        if not p.exists():
            return []
        out: list[dict] = []
        with p.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
